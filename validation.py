"""Check a function call before it runs.

Step 1. The name must be on the allow list.
Step 2. The arguments must have the right type and a safe range.
Step 3. The guardrail blocks unsafe text, even if the name is allowed.
"""

import re

MIN_HOURS = 0.5
MAX_HOURS = 8.0
MIN_DAYS = 1
MAX_DAYS = 30
MIN_DAY_NUMBER = 1
MAX_DAY_NUMBER = 60

# This dictionary is the allow list. A name that is not here is rejected.
TOOLS = {
    "create_study_plan": {
        "description": (
            "Build a day-by-day study plan for one subject. "
            "Use the days and hours the student wrote. Do not invent them."
        ),
        "parameters": {
            "subject": {"type": "string", "description": "Course name, for example Data Structures."},
            "days_available": {"type": "integer", "description": "Number of days, from 1 to 30."},
            "hours_per_day": {"type": "number", "description": "Hours each day, from 0.5 to 8."},
        },
        "required": ["subject", "days_available", "hours_per_day"],
    },
    "check_workload": {
        "description": (
            "Check if the student has enough hours for one subject. "
            "Use the days and hours the student wrote. Do not invent them."
        ),
        "parameters": {
            "subject": {"type": "string", "description": "Course name, for example Machine Learning."},
            "days_available": {"type": "integer", "description": "Number of days, from 1 to 30."},
            "hours_per_day": {"type": "number", "description": "Hours each day, from 0.5 to 8."},
        },
        "required": ["subject", "days_available", "hours_per_day"],
    },
    "get_day_plan": {
        "description": (
            "Say what to study on one day. "
            "Use a saved plan if there is one. Otherwise use 2 hours per day."
        ),
        "parameters": {
            "subject": {"type": "string", "description": "Course name, for example Database Systems."},
            "day_number": {"type": "integer", "description": "Day number, from 1 to 60."},
        },
        "required": ["subject", "day_number"],
    },
}


class ValidationError(Exception):
    """The name or the arguments are not acceptable."""


class GuardrailError(Exception):
    """The request is unsafe, so the function must not run."""


INJECTION_MESSAGE = (
    "I will not ignore my rules or follow that instruction. "
    "I can only help you plan revision for the subjects in my dataset. "
    "Tell me the subject, how many days you have, and how many hours you can study each day."
)

UNSAFE_MESSAGE = (
    "I will not do that. I do not write assignments, provide exam answers, "
    "or access private accounts and records. I can help you plan your own revision instead."
)

GUARDRAIL_MESSAGE = (
    "Blocked by the guardrail: the arguments ask for an unsafe or unsupported action, "
    "so the function was not run."
)

# Simple phrase checks. These are easier to read than one long pattern.
INJECTION_PHRASES = [
    "ignore your instructions",
    "ignore all instructions",
    "ignore the instructions",
    "ignore previous instructions",
    "disregard your instructions",
    "disregard the instructions",
    "forget your instructions",
    "you are now",
    "jailbreak",
    "override your rules",
    "do not follow your instructions",
]

UNSAFE_PHRASES = [
    "exam answer",
    "exam answers",
    "answer key",
    "cheat",
    "write my assignment",
    "write the assignment",
    "do my assignment",
    "do my homework",
    "complete my assignment",
    "another student",
    "hack",
    "steal",
    "password",
    "change my grade",
    "delete all",
]


def tool_specs_for_model():
    """The tool list given to the language model. The model chooses one."""
    specs = []
    for name, spec in TOOLS.items():
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": {
                    "type": "object",
                    "properties": spec["parameters"],
                    "required": spec["required"],
                },
            },
        })
    return specs


def find_blocked_phrase(text):
    """Return 'injection', 'unsafe', or None."""
    low = (text or "").lower()
    for phrase in INJECTION_PHRASES:
        if phrase in low:
            return "injection"
    for phrase in UNSAFE_PHRASES:
        if phrase in low:
            return "unsafe"
    return None


def screen_user_message(text):
    """Stop a bad message before the model is called. Return None if it is ok."""
    kind = find_blocked_phrase(text)
    if kind == "injection":
        return {"rule": "prompt_injection", "message": INJECTION_MESSAGE}
    if kind == "unsafe":
        return {"rule": "unsafe_request", "message": UNSAFE_MESSAGE}
    return None


def apply_argument_guardrail(name, arguments):
    """Block a call when the arguments themselves ask for something unsafe."""
    text = ""
    for value in arguments.values():
        text = text + " " + str(value)
    if find_blocked_phrase(text) is not None:
        raise GuardrailError(GUARDRAIL_MESSAGE)
    if name not in TOOLS:
        raise GuardrailError(GUARDRAIL_MESSAGE)


def validate_call(name, arguments):
    """Check the name and the arguments. Return a clean dict, or raise an error."""
    if not isinstance(name, str) or name not in TOOLS:
        allowed = ", ".join(TOOLS.keys())
        raise ValidationError(
            "Function '" + str(name) + "' is not on the allow list. Allowed functions: " + allowed + "."
        )
    if not isinstance(arguments, dict):
        raise ValidationError("Arguments must be an object with named fields.")

    spec = TOOLS[name]
    clean = {}
    for field in spec["required"]:
        if field not in arguments:
            raise ValidationError("Missing required argument: " + field + ".")

    for field in spec["parameters"]:
        if field not in arguments:
            continue
        clean[field] = check_one_field(field, arguments[field])
    return clean


def check_one_field(field, value):
    if field == "subject":
        return check_subject(value)
    if field == "days_available":
        number = check_int(value, field)
        if number < MIN_DAYS or number > MAX_DAYS:
            raise ValidationError("days_available must be an integer from 1 to 30.")
        return number
    if field == "day_number":
        number = check_int(value, field)
        if number < MIN_DAY_NUMBER or number > MAX_DAY_NUMBER:
            raise ValidationError("day_number must be an integer from 1 to 60.")
        return number
    if field == "hours_per_day":
        number = check_hours(value)
        if number < MIN_HOURS or number > MAX_HOURS:
            raise ValidationError(
                "hours_per_day must be a number from 0.5 to 8.0. More than 8 hours in a day is rejected."
            )
        return number
    raise ValidationError("Unsupported argument: " + field + ".")


def check_subject(value):
    if not isinstance(value, str):
        raise ValidationError("subject must be a short course name.")
    text = value.strip().strip("\"'")
    if text == "":
        raise ValidationError("subject is required.")
    if len(text) > 80:
        raise ValidationError("subject must be at most 80 characters.")
    if re.search(r"[\x00-\x1f]", text):
        raise ValidationError("subject contains unsupported characters.")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 +#&'./-]{0,79}", text) is None:
        raise ValidationError("subject must be a short course name.")
    return text


def check_int(value, field):
    if isinstance(value, bool):
        raise ValidationError(field + " must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    raise ValidationError(field + " must be an integer.")


def check_hours(value):
    if isinstance(value, bool):
        raise ValidationError("hours_per_day must be a number.")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()):
        number = float(value.strip())
    else:
        raise ValidationError("hours_per_day must be a number.")
    if number != number or number == float("inf") or number == float("-inf"):
        raise ValidationError("hours_per_day must be a finite number.")
    scaled = number * 10
    if abs(scaled - round(scaled)) > 0.000001:
        raise ValidationError("hours_per_day must use at most one decimal place.")
    return round(number, 1)
