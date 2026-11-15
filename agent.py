"""Link the language model to the three study functions.

The loop is short:
1. If the message is unsafe, stop. Do not call the model.
2. Ask the model. It may ask to call one function.
3. Check the function name and the arguments.
4. Run the function only if the check passes.
5. Write the answer from the function result, not from a guess.
"""

import ast
import json
import os
import re
import threading

from data import COURSES
from tools import execute
from validation import (
    MAX_HOURS,
    MIN_HOURS,
    GuardrailError,
    ValidationError,
    apply_argument_guardrail,
    screen_user_message,
    tool_specs_for_model,
    validate_call,
)

DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def system_prompt():
    names = []
    for name, course in COURSES.items():
        names.append(name + " (" + course["code"] + ")")
    subject_list = ", ".join(names)
    return (
        "You are a study-planning agent. You help a student revise. "
        "Use tools for facts about courses. Never invent subjects, chapters, hours, or exam dates.\n\n"
        "Subjects in the local dataset: " + subject_list + ".\n\n"
        "Choose a tool only when the user wants one of these:\n"
        "- create_study_plan: they want a day-by-day schedule. "
        "Arguments: subject, days_available, hours_per_day.\n"
        "- check_workload: they ask whether their time is enough. "
        "Arguments: subject, days_available, hours_per_day.\n"
        "- get_day_plan: they ask what to study on one day. "
        "Arguments: subject, day_number.\n\n"
        "Copy the subject and the numbers from the user. If something is missing, ask. Do not call a tool.\n"
        "hours_per_day must be between " + str(MIN_HOURS) + " and " + str(MAX_HOURS) + ". "
        "days_available must be between 1 and 30.\n"
        "When you call a tool, call it and do not add any other text.\n"
        "Do not write assignments, give exam answers, or ask for private records."
    )


def read_json_objects(text):
    """Pull {...} objects out of model text. Nested braces are counted."""
    found = []
    start = 0
    while True:
        opening = text.find("{", start)
        if opening < 0:
            break
        depth = 0
        end = None
        index = opening
        while index < len(text):
            if text[index] == "{":
                depth = depth + 1
            elif text[index] == "}":
                depth = depth - 1
                if depth == 0:
                    end = index
                    break
            index = index + 1
        if end is None:
            break
        chunk = text[opening:end + 1]
        value = None
        try:
            value = json.loads(chunk)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(chunk)
            except (ValueError, SyntaxError):
                value = None
        if isinstance(value, dict):
            found.append(value)
        start = end + 1
    return found


def read_simple_value(text):
    text = text.strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def call_from_dict(obj):
    name = obj.get("name") or obj.get("function")
    arguments = obj.get("arguments", obj.get("parameters", {}))
    if isinstance(name, dict):
        arguments = name.get("arguments", arguments)
        name = name.get("name")
    if not isinstance(name, str) or name.strip() == "":
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"_unparsed": arguments}
    if not isinstance(arguments, dict):
        arguments = {"_invalid": arguments}
    return {"name": name.strip(), "arguments": arguments}


def parse_tool_calls(text):
    """Read a tool call from the model text. Do not run it yet.

    The model may write <tool_call>{...}</tool_call> or a JSON object:
    {"function": "create_study_plan", "arguments": {...}}
    """
    if not text:
        return []

    calls = []
    blocks = re.findall(r"<tool_call>(.*?)</tool_call>", text, flags=re.DOTALL | re.IGNORECASE)
    if len(blocks) > 0:
        regions = blocks
        inside_tag = True
    else:
        regions = [text]
        inside_tag = False

    for region in regions:
        for obj in read_json_objects(region):
            looks_like_call = (
                "arguments" in obj
                or "parameters" in obj
                or isinstance(obj.get("function"), dict)
            )
            if inside_tag or looks_like_call:
                call = call_from_dict(obj)
                if call is not None and (inside_tag or looks_like_call):
                    calls.append(call)

        # Older Qwen style: <function=name><parameter=key>value</parameter></function>
        pairs = re.findall(r"<function=([^>]+)>(.*?)</function>", region, flags=re.DOTALL)
        for name, body in pairs:
            arguments = {}
            params = re.findall(r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>", body, flags=re.DOTALL)
            for key, raw_value in params:
                arguments[key.strip()] = read_simple_value(raw_value)
            calls.append({"name": name.strip(), "arguments": arguments})

    unique = []
    seen = set()
    for call in calls:
        marker = call["name"] + "|" + json.dumps(call["arguments"], sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(call)
    return unique


def clean_reply(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<\|.*?\|>", "", text)
    return text.strip()


def format_hours(value):
    number = round(float(value), 1)
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}"


def item_phrase(item):
    hours = format_hours(item["hours"])
    total = format_hours(item["chapter_total_hours"])
    if item["hours"] < item["chapter_total_hours"]:
        return item["chapter"] + " (" + hours + " of " + total + " hours)"
    return item["chapter"] + " (" + hours + " hours)"


def reply_invents_facts(text):
    """True if the model stated a chapter or exam date without a tool result."""
    for course in COURSES.values():
        if course["exam_date"] in text:
            return True
        for chapter in course["chapters"]:
            title = chapter["title"]
            if len(title) < 5:
                if re.search(r"\b" + re.escape(title) + r"\b", text, flags=re.IGNORECASE):
                    return True
            elif title.lower() in text.lower():
                return True
    return False


def explain_not_found(result):
    if result.get("ambiguous"):
        choices = ", ".join(result.get("candidates", []))
        return (
            'I am not sure which subject you mean by "' + str(result.get("subject", "")) + '". '
            "It matches more than one course: " + choices + ". Tell me which one you want."
        )
    known = ", ".join(result.get("known_subjects", []))
    subject = result.get("subject") or "that subject"
    return (
        'I do not have "' + str(subject) + '" in my course list, so I cannot give you chapters or hours for it.\n\n'
        "I only have these subjects: " + known + "."
    )


def explain_plan(result):
    lines = [
        "**" + result["subject"] + "** (" + result["code"] + "), exam date " + result["exam_date"] + ".",
        (
            "The course needs **" + format_hours(result["total_hours"]) + " hours**. "
            "You have **" + format_hours(result["available_hours"]) + " hours** "
            "(" + str(result["days_available"]) + " days × " + format_hours(result["hours_per_day"]) + " hours)."
        ),
    ]
    if result["fits"]:
        if result["spare_hours"] > 0:
            lines.append(
                "This fits, with " + format_hours(result["spare_hours"]) + " hour(s) still free. "
                "Those free hours are not filled with extra topics."
            )
        else:
            lines.append("This fits the time you have.")
    else:
        lines.append(
            "This does not fit. You are short by **" + format_hours(result["shortfall_hours"]) + " hours**."
        )
    lines.append("")
    lines.append("Plan from the course list:")
    for day in result["days"]:
        pieces = []
        for item in day["items"]:
            pieces.append(item_phrase(item))
        lines.append("- Day " + str(day["day"]) + " (" + format_hours(day["hours"]) + "h): " + ", ".join(pieces))
    if result["uncovered"]:
        lines.append("")
        lines.append("Not covered, because the time runs out:")
        for item in result["uncovered"]:
            lines.append("- " + item["chapter"] + " (" + format_hours(item["hours_remaining"]) + " hours left)")
    return "\n".join(lines)


def explain_workload(result):
    lines = [
        "**" + result["subject"] + "** (" + result["code"] + "), exam date " + result["exam_date"] + ".",
        "The course needs **" + format_hours(result["total_hours"]) + " hours**:",
    ]
    for chapter in result["chapters"]:
        lines.append("- " + chapter["title"] + " (" + format_hours(chapter["hours"]) + " hours)")
    lines.append("")
    lines.append(
        "You have **" + format_hours(result["available_hours"]) + " hours** "
        "(" + str(result["days_available"]) + " days × " + format_hours(result["hours_per_day"]) + " hours)."
    )
    if result["fits"]:
        if result["spare_hours"] > 0:
            lines.append("Yes. The workload fits, and you would have " + format_hours(result["spare_hours"]) + " hour(s) spare.")
        else:
            lines.append("Yes. The workload fits exactly.")
    else:
        lines.append(
            "No. You are short by **" + format_hours(result["shortfall_hours"]) + " hours**. "
            "I am not going to pretend the course is shorter than the dataset says."
        )
    return "\n".join(lines)


def explain_day(result):
    if not result.get("day_found"):
        text = (
            "**" + result["subject"] + "** (" + result["code"] + ") has a plan of "
            + str(result["plan_days"]) + " day(s) at " + format_hours(result["hours_per_day"]) + " hours per day. "
            "Day " + str(result["day_number"]) + " is outside that plan, so there is nothing scheduled. "
            "I am not going to invent work for that day."
        )
        note = result.get("note", "")
        if note:
            text = text + "\n\n" + note
        return text

    lines = [
        (
            "**" + result["subject"] + "** (" + result["code"] + "), day " + str(result["day_number"])
            + " (" + format_hours(result["hours"]) + " hours at " + format_hours(result["hours_per_day"]) + " hours per day)."
        ),
        result.get("note", ""),
        "",
    ]
    for item in result["items"]:
        lines.append("- " + item_phrase(item))
    kept = []
    for line in lines:
        if line is not None and line != "":
            kept.append(line)
        elif line == "":
            kept.append("")
    return "\n".join(kept).strip()


def explain_result(call):
    result = call["result"]
    if result.get("found") is False:
        return explain_not_found(result)
    if call["name"] == "create_study_plan":
        return explain_plan(result)
    if call["name"] == "check_workload":
        return explain_workload(result)
    if call["name"] == "get_day_plan":
        return explain_day(result)
    return json.dumps(result, indent=2, ensure_ascii=False)


def explain_failure(call):
    reason = call["result"].get("error") or call["result"].get("message") or "The call was rejected."
    name = call["name"] or "that function"
    if call["status"] == "blocked":
        return "I did not run `" + str(name) + "`. " + reason
    return "I did not run `" + str(name) + "`, because the arguments were rejected. " + reason


def explain_trace(trace):
    done = []
    failed = []
    for call in trace:
        if call["status"] == "executed":
            done.append(call)
        elif call["status"] == "rejected" or call["status"] == "blocked":
            failed.append(call)
    if len(done) > 0:
        parts = []
        for call in done:
            parts.append(explain_result(call))
        return "\n\n".join(parts)
    if len(failed) > 0:
        parts = []
        for call in failed:
            parts.append(explain_failure(call))
        return "\n\n".join(parts)
    return None


def format_trace(user_message, trace):
    """Text for the Ask page: name, arguments, and result of every call."""
    lines = ["User: " + user_message, ""]
    if not trace:
        lines.append("Function calls: none")
        return "\n".join(lines)
    number = 1
    for call in trace:
        name = call["name"] or "(not called)"
        lines.append(str(number) + ". " + str(name))
        lines.append("   status: " + call["status"])
        if call.get("rule"):
            lines.append("   rule: " + call["rule"])
        if call.get("arguments") is not None:
            lines.append("   arguments: " + json.dumps(call["arguments"], ensure_ascii=False))
        rendered = json.dumps(call["result"], ensure_ascii=False, indent=2)
        lines.append("   result: " + rendered.replace("\n", "\n   "))
        lines.append("")
        number = number + 1
    return "\n".join(lines).rstrip()


def repair_prompt(outcomes):
    lines = ["The tool call was not run."]
    for item in outcomes:
        reason = item["result"].get("error") or item["result"].get("message")
        lines.append("- " + str(item["name"]) + " (" + item["status"] + "): " + str(reason))
    lines.append(
        "Call one allowed tool again with corrected arguments, "
        "or ask the user for the missing detail. "
        "Allowed tools: create_study_plan, check_workload, get_day_plan."
    )
    return "\n".join(lines)


class StudyPlannerAgent:
    """One shared model. Each browser session keeps its own saved plans."""

    def __init__(self, model_id=None):
        self.model_id = model_id or os.environ.get("STUDY_PLANNER_MODEL", DEFAULT_MODEL)
        self.model = None
        self.tokenizer = None
        self.supports_tools = True
        self.lock = threading.Lock()

    def load(self):
        if self.model is not None:
            return
        with self.lock:
            if self.model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token

            if torch.cuda.is_available():
                dtype = torch.float16
                device = "cuda"
            else:
                dtype = torch.float32
                device = "cpu"

            model = AutoModelForCausalLM.from_pretrained(self.model_id, torch_dtype=dtype)
            model.to(device)
            model.eval()
            self.tokenizer = tokenizer
            self.model = model

    def build_prompt(self, messages, use_tools):
        if use_tools and self.supports_tools:
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tools=tool_specs_for_model(),
                    add_generation_prompt=True,
                    tokenize=False,
                )
            except Exception:
                self.supports_tools = False

        prepared = messages
        if use_tools and not self.supports_tools:
            extra = (
                "If you need a tool, reply with only a JSON object like "
                '{"function": "create_study_plan", "arguments": {"subject": "Data Structures", '
                '"days_available": 8, "hours_per_day": 2}}. '
                "Use create_study_plan, check_workload, or get_day_plan. "
                "If you do not need a tool, reply with a short answer."
            )
            prepared = []
            for message in messages:
                if message["role"] == "system":
                    prepared.append({"role": "system", "content": message["content"] + "\n\n" + extra})
                else:
                    prepared.append(message)
        return self.tokenizer.apply_chat_template(
            prepared,
            add_generation_prompt=True,
            tokenize=False,
        )

    def generate(self, messages, use_tools):
        self.load()
        prompt = self.build_prompt(messages, use_tools)
        import torch

        inputs = self.tokenizer(prompt, return_tensors="pt")
        moved = {}
        for key, value in inputs.items():
            moved[key] = value.to(self.model.device)
        with self.lock:
            with torch.inference_mode():
                output_ids = self.model.generate(
                    **moved,
                    max_new_tokens=256,
                    do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
        new_tokens = output_ids[0, moved["input_ids"].shape[-1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True)

    def try_call(self, call, store):
        name = call["name"]
        raw_arguments = call["arguments"]
        try:
            cleaned = validate_call(name, raw_arguments)
            apply_argument_guardrail(name, cleaned)
            result = execute(name, cleaned, store)
            return {
                "name": name,
                "arguments": cleaned,
                "status": "executed",
                "result": result,
            }
        except GuardrailError as exc:
            return {
                "name": name,
                "arguments": raw_arguments,
                "status": "blocked",
                "rule": "unsafe_arguments",
                "result": {"error": str(exc)},
            }
        except ValidationError as exc:
            return {
                "name": name,
                "arguments": raw_arguments,
                "status": "rejected",
                "result": {"error": str(exc)},
            }
        except Exception as exc:
            return {
                "name": name,
                "arguments": raw_arguments,
                "status": "rejected",
                "result": {"error": "The function failed: " + str(exc)},
            }

    def run(self, user_message, history=None, store=None):
        """One question from the Ask page."""
        if store is None:
            store = {}
        if history is None:
            history = []

        screened = screen_user_message(user_message)
        if screened:
            trace = [{
                "name": None,
                "arguments": None,
                "status": "blocked",
                "rule": screened["rule"],
                "result": {"message": screened["message"]},
            }]
            return {
                "answer": screened["message"],
                "trace": trace,
                "store": store,
                "raw_model": "(The language model was not called. A Python guardrail blocked this message.)",
            }

        messages = [{"role": "system", "content": system_prompt()}]
        recent = history[-8:]
        for turn in recent:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        trace = []
        raw_parts = []
        model_text = ""
        try:
            round_index = 0
            while round_index < 2:
                model_text = self.generate(messages, True)
                raw_parts.append(model_text.strip())
                parsed = parse_tool_calls(model_text)
                if len(parsed) == 0:
                    break
                outcomes = []
                for call in parsed:
                    outcomes.append(self.try_call(call, store))
                trace.extend(outcomes)
                ran = False
                for item in outcomes:
                    if item["status"] == "executed":
                        ran = True
                if ran or round_index == 1:
                    break
                messages.append({"role": "user", "content": repair_prompt(outcomes)})
                round_index = round_index + 1
        except Exception as exc:
            return {
                "answer": (
                    "The language model could not be run (" + str(exc) + "). "
                    "Install the packages in requirements.txt and try again. "
                    "The first run also needs a network connection so the model can download."
                ),
                "trace": trace,
                "store": store,
                "raw_model": "\n\n".join(raw_parts),
            }

        grounded = explain_trace(trace)
        if grounded:
            answer = grounded
        else:
            answer = clean_reply(model_text)
            if answer == "":
                answer = "Tell me the subject, how many days you have, and how many hours you can study each day."
            elif reply_invents_facts(answer):
                answer = (
                    "I can only state chapters, hours, and exam dates after a tool returns them. "
                    "Ask again with the subject and, if you want a plan or a workload check, "
                    "the number of days and the hours per day."
                )
        return {
            "answer": answer,
            "trace": trace,
            "store": store,
            "raw_model": "\n\n--- next generation ---\n\n".join(raw_parts),
        }
