"""Safety checks. They run in Python, BEFORE any function runs.

1. guardrail()  -> blocks prompt injection and unsafe requests
2. check_call() -> allow list + checks the arguments (required, type, range)
                   + checks that the student really said them (Part 4 improvement)
"""

import re

from data import COURSES, NICKNAMES, find_subject, simplify
from tools import FUNCTIONS

# ---------------------------------------------------------------
# 1. Guardrail
# ---------------------------------------------------------------

INJECTION_PHRASES = [
    "ignore your instructions",
    "ignore all instructions",
    "ignore previous instructions",
    "ignore the instructions",
    "forget your instructions",
    "disregard your instructions",
    "override your rules",
    "you are now",
    "jailbreak",
]

UNSAFE_PHRASES = [
    "exam answer",
    "answer key",
    "cheat",
    "write my assignment",
    "do my assignment",
    "do my homework",
    "hack",
    "password",
    "steal",
    "change my grade",
    "another student",
    "delete all",
]


def guardrail(text):
    """Return a refusal message if the text is not allowed. Return None if it is fine."""
    text = str(text).lower()
    for phrase in INJECTION_PHRASES:
        if phrase in text:
            return ("Blocked (prompt injection): I will not ignore my rules. "
                    "I only plan revision for the subjects in my list.")
    for phrase in UNSAFE_PHRASES:
        if phrase in text:
            return ("Blocked (unsafe request): I do not write assignments, give exam answers, "
                    "or access other people's accounts or records. I can help you plan your own revision.")
    return None


# ---------------------------------------------------------------
# 2. Allow list and argument checks
# ---------------------------------------------------------------

# Which arguments each function needs.
REQUIRED_ARGUMENTS = {
    "create_study_plan": ["subject", "days_available", "hours_per_day"],
    "check_workload": ["subject", "days_available", "hours_per_day"],
    "get_day_plan": ["subject", "day_number"],
}


def to_whole_number(value, name, smallest, largest):
    """Check that value is a whole number between smallest and largest."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be a number.")
    if number != int(number):
        raise ValueError(name + " must be a whole number.")
    number = int(number)
    if number < smallest or number > largest:
        raise ValueError(name + " must be from " + str(smallest) + " to " + str(largest) + ".")
    return number


def subject_in_question(subject, question):
    """True if the student wrote this subject (its name, code or nickname) in the question."""
    question = " " + simplify(question) + " "

    # The exact subject text, e.g. "Quantum Basket Weaving"
    if " " + simplify(subject) + " " in question:
        return True

    # Another name for the same course, e.g. "ML" for "Machine Learning"
    course = find_subject(subject)
    if course is None:
        return False
    other_names = [course, COURSES[course]["code"]]
    for nickname, full_name in NICKNAMES.items():
        if full_name == course:
            other_names.append(nickname)
    for other_name in other_names:
        if " " + simplify(other_name) + " " in question:
            return True
    return False


def numbers_in_question(question):
    """All numbers the student wrote, e.g. 'I have 5 days and 2.5 hours' -> [5.0, 2.5]."""
    numbers = []
    for text in re.findall(r"\d+(?:\.\d+)?", question):
        numbers.append(float(text))
    return numbers


def check_question_has_details(clean, question):
    """Part 4 improvement: the model may not invent arguments.

    The subject and every number must come from the student's question.
    If something is missing, the function does not run and the agent asks for it.
    """
    missing = []
    if not subject_in_question(clean["subject"], question):
        missing.append("which subject")

    numbers = numbers_in_question(question)
    if "days_available" in clean and clean["days_available"] not in numbers:
        missing.append("how many days you have")
    if "hours_per_day" in clean and clean["hours_per_day"] not in numbers:
        missing.append("how many hours you can study each day")
    if "day_number" in clean and clean["day_number"] not in numbers:
        missing.append("which day number")

    if len(missing) > 0:
        raise ValueError("You did not tell me " + " and ".join(missing) + ". "
                         "Please add it to your question, for example: "
                         "\"Create a 10-day plan for Machine Learning, 2 hours a day.\"")


def check_call(name, arguments, question):
    """Return clean arguments, or raise ValueError with the reason."""
    # Step 1: allow list
    if name not in FUNCTIONS:
        raise ValueError("'" + str(name) + "' is not on the allow list. "
                         "Allowed: " + ", ".join(FUNCTIONS.keys()) + ".")
    if not isinstance(arguments, dict):
        raise ValueError("The arguments must be a JSON object.")

    # Step 2: required arguments
    for needed in REQUIRED_ARGUMENTS[name]:
        if needed not in arguments:
            raise ValueError("Missing argument: " + needed + ".")

    # Step 3: type and range of each argument (extra arguments are dropped)
    clean = {}
    subject = arguments["subject"]
    if not isinstance(subject, str) or subject.strip() == "" or len(subject) > 80:
        raise ValueError("subject must be a short piece of text.")
    clean["subject"] = subject.strip()

    if "days_available" in REQUIRED_ARGUMENTS[name]:
        clean["days_available"] = to_whole_number(arguments["days_available"], "days_available", 1, 30)

    if "hours_per_day" in REQUIRED_ARGUMENTS[name]:
        try:
            hours = float(arguments["hours_per_day"])
        except (TypeError, ValueError):
            raise ValueError("hours_per_day must be a number.")
        if hours < 0.5 or hours > 8:
            raise ValueError("hours_per_day must be from 0.5 to 8. More than 8 hours a day is not allowed.")
        hours = round(hours, 1)
        if hours == int(hours):
            hours = int(hours)       # show 2 instead of 2.0
        clean["hours_per_day"] = hours

    if "day_number" in REQUIRED_ARGUMENTS[name]:
        clean["day_number"] = to_whole_number(arguments["day_number"], "day_number", 1, 60)

    # Step 4: the student must have said these details (no invented arguments)
    check_question_has_details(clean, question)

    return clean
