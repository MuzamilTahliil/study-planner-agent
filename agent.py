"""The agent: it connects the AI model to the three tools.

What happens for every question:
  Step 1. Guardrail: if the question is unsafe, stop. The model is not called.
  Step 2. Ask the model. It gets the 3 tools and decides if it needs one.
  Step 3. Read the tool call the model wrote (function name + arguments).
  Step 4. Check the call: allow list + argument checks + guardrail.
  Step 5. Run the function and write the answer from the REAL result.
"""

import json

from transformers import AutoModelForCausalLM, AutoTokenizer

from data import COURSES
from tools import TOOLS_FOR_MODEL, check_workload, create_study_plan, get_day_plan
from validation import check_call, guardrail

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"   # a free model from Hugging Face

SYSTEM_PROMPT = (
    "You are a study planner assistant. "
    "The subjects you know are: " + ", ".join(COURSES.keys()) + ". "
    "If the user wants a study plan, call create_study_plan. "
    "If the user asks whether they have enough time, call check_workload. "
    "If the user asks what to study on a certain day, call get_day_plan. "
    "Copy the subject name and the numbers exactly from the user. "
    "Never invent chapters, hours or exam dates."
)

# ------------------------------------------------------------
# Load the model once, when the program starts.
# The first time, this downloads about 3 GB from Hugging Face.
# ------------------------------------------------------------
print("Loading the model, please wait...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
print("Model ready.")


def ask_model(question):
    """Send the question and the 3 tools to the model. Return the text it writes."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    # tools=TOOLS_FOR_MODEL tells the model which functions it may call
    prompt = tokenizer.apply_chat_template(
        messages, tools=TOOLS_FOR_MODEL, add_generation_prompt=True, tokenize=False
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    output = model.generate(**inputs, max_new_tokens=200, do_sample=False)

    # Keep only the new words the model wrote (not the prompt)
    prompt_length = inputs["input_ids"].shape[1]
    new_tokens = output[0][prompt_length:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def read_tool_call(model_text):
    """Find the tool call in the model's text.

    The model writes something like:
        <tool_call>{"name": "check_workload", "arguments": {...}}</tool_call>

    Return (name, arguments), or (None, None) if there is no tool call.
    """
    start = model_text.find("{")
    end = model_text.rfind("}")
    if start == -1 or end == -1:
        return None, None

    try:
        data = json.loads(model_text[start:end + 1])
    except json.JSONDecodeError:
        return None, None

    if not isinstance(data, dict):
        return None, None

    # Qwen uses "name". Some models use "function".
    name = data.get("name") or data.get("function")
    arguments = data.get("arguments", {})
    return name, arguments


def run_function(name, arguments, saved_plans):
    """Run one of the 3 tools. The name was already checked."""
    if name == "create_study_plan":
        return create_study_plan(arguments["subject"], arguments["days_available"],
                                 arguments["hours_per_day"], saved_plans)
    if name == "check_workload":
        return check_workload(arguments["subject"], arguments["days_available"],
                              arguments["hours_per_day"], saved_plans)
    if name == "get_day_plan":
        return get_day_plan(arguments["subject"], arguments["day_number"], saved_plans)


# ------------------------------------------------------------
# Turn a function result into a friendly answer
# ------------------------------------------------------------

def answer_not_found(result):
    known = ", ".join(result["known_subjects"])
    return ("Sorry, I do not have \"" + result["subject"] + "\" in my course list, "
            "so I cannot help with it. I only know: " + known + ".")


def answer_study_plan(result):
    text = "**Study plan for " + result["subject"] + "** (exam on " + result["exam_date"] + ")\n\n"
    text += ("You need " + str(result["hours_needed"]) + " hours and you have "
             + str(result["hours_available"]) + " hours.\n\n")

    for day in result["plan"]:
        chapters = []
        for item in day["study"]:
            chapters.append(item["chapter"] + " (" + str(item["hours"]) + "h)")
        text += "- Day " + str(day["day"]) + ": " + ", ".join(chapters) + "\n"

    if len(result["not_covered"]) > 0:
        text += "\n**Not enough time for:**\n"
        for item in result["not_covered"]:
            text += "- " + item["chapter"] + " (" + str(item["hours_left"]) + "h left)\n"
    return text


def answer_workload(result):
    text = (result["subject"] + " needs " + str(result["hours_needed"]) + " hours. "
            "You have " + str(result["hours_available"]) + " hours. ")
    if result["enough_time"]:
        return "Yes, you have enough time. " + text + "You have " + str(result["difference"]) + " hours spare."
    else:
        return "No, that is not enough time. " + text + "You are short by " + str(-result["difference"]) + " hours."


def answer_day_plan(result):
    if len(result["study"]) == 0:
        return "Nothing is planned for day " + str(result["day"]) + ". " + result["message"]
    chapters = []
    for item in result["study"]:
        chapters.append(item["chapter"] + " (" + str(item["hours"]) + "h)")
    return ("**" + result["subject"] + ", day " + str(result["day"]) + ":** " + ", ".join(chapters)
            + "\n\n(Taken from " + result["source"] + ".)")


def write_answer(name, result):
    if result["found"] == False:
        return answer_not_found(result)
    if name == "create_study_plan":
        return answer_study_plan(result)
    if name == "check_workload":
        return answer_workload(result)
    if name == "get_day_plan":
        return answer_day_plan(result)


def mentions_course_facts(text):
    """True if the text names a chapter or an exam date from data.py."""
    for course in COURSES.values():
        if course["exam_date"] in text:
            return True
        for chapter in course["chapters"]:
            if chapter["title"].lower() in text.lower():
                return True
    return False


# ------------------------------------------------------------
# The main function: answer one question
# ------------------------------------------------------------

def run_agent(question, saved_plans):
    """Answer one question.

    Returns 3 things:
      answer     - the text shown to the student
      calls      - a list of the function calls (for the details box)
      model_text - exactly what the model wrote
    """
    calls = []

    # Step 1: guardrail on the question
    refusal = guardrail(question)
    if refusal is not None:
        calls.append({"function": None, "arguments": None,
                      "status": "BLOCKED by guardrail", "result": "No function was run."})
        return refusal, calls, "(The model was not called.)"

    # Step 2: ask the model
    model_text = ask_model(question)

    # Step 3: did the model ask for a tool?
    name, arguments = read_tool_call(model_text)
    if name is None:
        # No tool was called. The model may not state course facts by itself.
        if mentions_course_facts(model_text) or model_text.strip() == "":
            answer = "Please tell me the subject, the number of days and the hours per day."
        else:
            answer = model_text.strip()
        return answer, calls, model_text

    # Step 4: check the call (we also pass the question, so we can check
    # that the student really said the subject and the numbers)
    try:
        clean_arguments = check_call(name, arguments, question)
    except ValueError as error:
        calls.append({"function": name, "arguments": arguments,
                      "status": "REJECTED", "result": str(error)})
        return "I did not run " + str(name) + ". " + str(error), calls, model_text

    refusal = guardrail(json.dumps(clean_arguments))
    if refusal is not None:
        calls.append({"function": name, "arguments": clean_arguments,
                      "status": "BLOCKED by guardrail", "result": "No function was run."})
        return refusal, calls, model_text

    # Step 5: run the function and answer from its result
    result = run_function(name, clean_arguments, saved_plans)
    calls.append({"function": name, "arguments": clean_arguments, "status": "RUN", "result": result})
    return write_answer(name, result), calls, model_text
