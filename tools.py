"""The three functions the model may call.

1. create_study_plan  -> make a day-by-day plan and save it
2. check_workload     -> say if the hours are enough
3. get_day_plan       -> say what to study on one day

All numbers come from data.py. A missing subject stays missing.
"""

import math

from data import course_record, resolve_subject, subject_names

DEFAULT_HOURS_PER_DAY = 2.0


def to_tenths(hours):
    """Turn 1.5 hours into 15 tenths, so the split does not drift."""
    return int(math.floor(float(hours) * 10 + 0.5))


def from_tenths(tenths):
    return round(tenths / 10, 1)


def pack_chapters(chapters, days_available, hours_per_day):
    """Fill each day up to hours_per_day. Split a chapter if it does not fit.

    Hours that do not fit are returned as uncovered. They are not placed on an extra day.
    """
    per_day = to_tenths(hours_per_day)
    pending = []
    for chapter in chapters:
        pending.append({
            "title": chapter["title"],
            "left": to_tenths(chapter["hours"]),
            "total": to_tenths(chapter["hours"]),
        })

    days = []
    index = 0
    day_number = 1
    while day_number <= days_available and index < len(pending) and per_day > 0:
        space = per_day
        items = []
        while index < len(pending) and space > 0:
            chapter = pending[index]
            take = min(space, chapter["left"])
            if take <= 0:
                break
            items.append({
                "chapter": chapter["title"],
                "hours": from_tenths(take),
                "chapter_total_hours": from_tenths(chapter["total"]),
            })
            chapter["left"] = chapter["left"] - take
            space = space - take
            if chapter["left"] == 0:
                index = index + 1
        if len(items) > 0:
            days.append({
                "day": day_number,
                "hours": from_tenths(per_day - space),
                "items": items,
            })
        day_number = day_number + 1

    uncovered = []
    for chapter in pending:
        if chapter["left"] > 0:
            uncovered.append({
                "chapter": chapter["title"],
                "hours_remaining": from_tenths(chapter["left"]),
            })
    return days, uncovered


def missing_subject(resolved):
    if resolved["status"] == "ambiguous":
        return {
            "found": False,
            "ambiguous": True,
            "subject": resolved.get("query", ""),
            "candidates": list(resolved["candidates"]),
            "message": "More than one subject matches that name.",
        }
    return {
        "found": False,
        "ambiguous": False,
        "subject": resolved.get("query", ""),
        "known_subjects": subject_names(),
        "message": "That subject is not in the local course list.",
    }


def hours_budget(total_hours, days_available, hours_per_day):
    total = to_tenths(total_hours)
    available = days_available * to_tenths(hours_per_day)
    fits = total <= available
    shortfall = 0
    spare = 0
    if fits:
        spare = available - total
    else:
        shortfall = total - available
    return {
        "total_hours": from_tenths(total),
        "available_hours": from_tenths(available),
        "fits": fits,
        "shortfall_hours": from_tenths(shortfall),
        "spare_hours": from_tenths(spare),
    }


def create_study_plan(subject, days_available, hours_per_day, store):
    """Build the plan and save it under the subject name."""
    resolved = resolve_subject(subject)
    if resolved["status"] != "found":
        return missing_subject(resolved)

    record = course_record(resolved["name"])
    days, uncovered = pack_chapters(record["chapters"], days_available, hours_per_day)
    scheduled = 0
    for day in days:
        for item in day["items"]:
            scheduled = scheduled + to_tenths(item["hours"])

    plan = {
        "found": True,
        "subject": record["name"],
        "code": record["code"],
        "exam_date": record["exam_date"],
        "days_available": days_available,
        "hours_per_day": hours_per_day,
        "scheduled_hours": from_tenths(scheduled),
        "days": days,
        "uncovered": uncovered,
    }
    budget = hours_budget(record["total_hours"], days_available, hours_per_day)
    plan.update(budget)
    store[record["name"]] = plan
    return plan


def check_workload(subject, days_available, hours_per_day, store=None):
    """Compare needed hours with the hours the student has. Does not save a plan."""
    resolved = resolve_subject(subject)
    if resolved["status"] != "found":
        return missing_subject(resolved)

    record = course_record(resolved["name"])
    result = {
        "found": True,
        "subject": record["name"],
        "code": record["code"],
        "exam_date": record["exam_date"],
        "chapters": record["chapters"],
        "days_available": days_available,
        "hours_per_day": hours_per_day,
    }
    result.update(hours_budget(record["total_hours"], days_available, hours_per_day))
    return result


def get_day_plan(subject, day_number, store):
    """One day from the saved plan, or from a default of 2 hours per day."""
    resolved = resolve_subject(subject)
    if resolved["status"] != "found":
        return missing_subject(resolved)

    record = course_record(resolved["name"])
    saved = store.get(record["name"])
    if saved:
        days = saved["days"]
        source = "saved_plan"
        hours_per_day = saved["hours_per_day"]
        note = "This day is taken from the plan saved earlier in this session."
    else:
        per_day = to_tenths(DEFAULT_HOURS_PER_DAY)
        total = to_tenths(record["total_hours"])
        needed_days = 1
        if per_day > 0:
            needed_days = max(1, math.ceil(total / per_day))
        days, _uncovered = pack_chapters(record["chapters"], needed_days, DEFAULT_HOURS_PER_DAY)
        source = "default_2_hours_per_day"
        hours_per_day = DEFAULT_HOURS_PER_DAY
        note = (
            "No plan was saved for this subject in this session, "
            "so this day uses the default pace of 2 hours per day."
        )

    chosen = None
    for day in days:
        if day["day"] == day_number:
            chosen = day
            break

    result = {
        "found": True,
        "subject": record["name"],
        "code": record["code"],
        "exam_date": record["exam_date"],
        "day_number": day_number,
        "day_found": chosen is not None,
        "source": source,
        "hours_per_day": hours_per_day,
        "plan_days": len(days),
        "note": note,
    }
    if chosen is None:
        result["items"] = []
        result["hours"] = 0
        result["message"] = (
            "The plan has " + str(len(days)) + " day(s). Day " + str(day_number)
            + " has no study block, and none was invented."
        )
        return result

    result["hours"] = chosen["hours"]
    result["items"] = chosen["items"]
    return result


def execute(name, arguments, store):
    """Run one allowed function. validate_call must run before this."""
    if name == "create_study_plan":
        return create_study_plan(
            arguments["subject"],
            arguments["days_available"],
            arguments["hours_per_day"],
            store,
        )
    if name == "check_workload":
        return check_workload(
            arguments["subject"],
            arguments["days_available"],
            arguments["hours_per_day"],
            store,
        )
    if name == "get_day_plan":
        return get_day_plan(arguments["subject"], arguments["day_number"], store)
    raise KeyError(name)
