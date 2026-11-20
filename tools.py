"""The three Python functions (tools) the AI model is allowed to call.

1. create_study_plan -> makes a day-by-day plan and saves it
2. check_workload    -> says if the student has enough time
3. get_day_plan      -> says what to study on one day

Every number comes from data.py. Nothing is invented.
"""

from data import COURSES, find_subject, total_hours

DEFAULT_HOURS_PER_DAY = 2


def subject_not_found(subject):
    """The answer every tool gives when the subject is not in data.py."""
    return {
        "found": False,
        "subject": subject,
        "message": "This subject is not in my course list.",
        "known_subjects": list(COURSES.keys()),
    }


def split_into_days(subject, days, hours_per_day):
    """Put the chapters into days. Each day gets at most hours_per_day hours.

    A long chapter can continue on the next day.
    Chapters that do not fit in the days given are returned as 'not_covered'.
    """
    # A list of [chapter title, hours still to study].
    to_study = []
    for chapter in COURSES[subject]["chapters"]:
        to_study.append([chapter["title"], chapter["hours"]])

    plan = []
    for day in range(1, days + 1):
        free_time = hours_per_day
        today = []
        while free_time > 0 and len(to_study) > 0:
            title = to_study[0][0]
            hours_left = to_study[0][1]
            study = min(free_time, hours_left)
            today.append({"chapter": title, "hours": study})
            free_time = round(free_time - study, 1)
            hours_left = round(hours_left - study, 1)
            if hours_left == 0:
                to_study.pop(0)          # chapter finished
            else:
                to_study[0][1] = hours_left  # continue it tomorrow
        if len(today) == 0:
            break                         # everything is already planned
        plan.append({"day": day, "study": today})

    not_covered = []
    for title, hours_left in to_study:
        not_covered.append({"chapter": title, "hours_left": hours_left})
    return plan, not_covered


def create_study_plan(subject, days_available, hours_per_day, saved_plans):
    name = find_subject(subject)
    if name is None:
        return subject_not_found(subject)

    plan, not_covered = split_into_days(name, days_available, hours_per_day)
    result = {
        "found": True,
        "subject": name,
        "exam_date": COURSES[name]["exam_date"],
        "hours_needed": total_hours(name),
        "hours_available": round(days_available * hours_per_day, 1),
        "hours_per_day": hours_per_day,
        "plan": plan,
        "not_covered": not_covered,
    }
    saved_plans[name] = result  # remember it, so get_day_plan can use it later
    return result


def check_workload(subject, days_available, hours_per_day, saved_plans):
    name = find_subject(subject)
    if name is None:
        return subject_not_found(subject)

    needed = total_hours(name)
    available = round(days_available * hours_per_day, 1)
    return {
        "found": True,
        "subject": name,
        "exam_date": COURSES[name]["exam_date"],
        "hours_needed": needed,
        "hours_available": available,
        "enough_time": available >= needed,
        "difference": round(available - needed, 1),
    }


def get_day_plan(subject, day_number, saved_plans):
    name = find_subject(subject)
    if name is None:
        return subject_not_found(subject)

    if name in saved_plans:
        plan = saved_plans[name]["plan"]
        source = "your saved plan"
    else:
        # No plan yet: use 2 hours per day and enough days for the whole course.
        plan, not_covered = split_into_days(name, 60, DEFAULT_HOURS_PER_DAY)
        source = "the default pace of 2 hours per day"

    for day in plan:
        if day["day"] == day_number:
            return {"found": True, "subject": name, "day": day_number,
                    "source": source, "study": day["study"]}

    return {"found": True, "subject": name, "day": day_number, "source": source,
            "study": [], "message": "The plan has only " + str(len(plan)) + " days."}


# The functions the model may call. This dictionary is also the ALLOW LIST.
FUNCTIONS = {
    "create_study_plan": create_study_plan,
    "check_workload": check_workload,
    "get_day_plan": get_day_plan,
}

# The same three tools, described for the AI model (JSON schema format).
TOOLS_FOR_MODEL = [
    {
        "type": "function",
        "function": {
            "name": "create_study_plan",
            "description": "Make a day-by-day study plan for one subject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject name, e.g. Data Structures"},
                    "days_available": {"type": "integer", "description": "Number of days (1 to 30)"},
                    "hours_per_day": {"type": "number", "description": "Hours per day (0.5 to 8)"},
                },
                "required": ["subject", "days_available", "hours_per_day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_workload",
            "description": "Check if the student has enough time to study one subject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject name, e.g. Machine Learning"},
                    "days_available": {"type": "integer", "description": "Number of days (1 to 30)"},
                    "hours_per_day": {"type": "number", "description": "Hours per day (0.5 to 8)"},
                },
                "required": ["subject", "days_available", "hours_per_day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_day_plan",
            "description": "Say what to study on one day of the plan for one subject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject name, e.g. Database Systems"},
                    "day_number": {"type": "integer", "description": "Day number (1 to 60)"},
                },
                "required": ["subject", "day_number"],
            },
        },
    },
]
