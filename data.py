"""The only course list the agent is allowed to use.

If a subject is not in COURSES, the tools must say it is missing.
They must not invent chapters or hours.
"""

import re

COURSES = {
    "Artificial Intelligence Techniques": {
        "code": "WQF7002",
        "exam_date": "2026-12-15",
        "chapters": [
            {"title": "Intelligent Agents and PEAS", "hours": 3},
            {"title": "Search Algorithms", "hours": 4},
            {"title": "Adversarial Search", "hours": 3},
            {"title": "Knowledge Representation", "hours": 4},
            {"title": "Machine Learning Basics", "hours": 4},
        ],
    },
    "Data Structures": {
        "code": "DSA",
        "exam_date": "2026-12-18",
        "chapters": [
            {"title": "Arrays and Linked Lists", "hours": 3},
            {"title": "Stacks and Queues", "hours": 2},
            {"title": "Trees and Heaps", "hours": 4},
            {"title": "Hash Tables", "hours": 3},
            {"title": "Graphs", "hours": 4},
        ],
    },
    "Database Systems": {
        "code": "DBS",
        "exam_date": "2026-12-12",
        "chapters": [
            {"title": "Relational Model", "hours": 3},
            {"title": "SQL", "hours": 4},
            {"title": "Normalisation", "hours": 3},
            {"title": "Transactions", "hours": 3},
            {"title": "Indexing", "hours": 2},
        ],
    },
    "Machine Learning": {
        "code": "ML",
        "exam_date": "2026-12-20",
        "chapters": [
            {"title": "Supervised Learning", "hours": 4},
            {"title": "Model Evaluation", "hours": 3},
            {"title": "Neural Networks", "hours": 4},
            {"title": "Unsupervised Learning", "hours": 3},
        ],
    },
}

# Short names a student might type.
EXTRA_NAMES = {
    "ai": "Artificial Intelligence Techniques",
    "ai techniques": "Artificial Intelligence Techniques",
    "artificial intelligence": "Artificial Intelligence Techniques",
    "wqf 7002": "Artificial Intelligence Techniques",
    "dsa": "Data Structures",
    "data structure": "Data Structures",
    "database": "Database Systems",
    "databases": "Database Systems",
    "db": "Database Systems",
    "ml": "Machine Learning",
}


def clean_name(text):
    """Make a name lower-case and remove punctuation, so 'WQF-7002' still matches."""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def subject_names():
    return list(COURSES.keys())


def course_record(name):
    course = COURSES[name]
    chapters = []
    total = 0
    for chapter in course["chapters"]:
        chapters.append({"title": chapter["title"], "hours": chapter["hours"]})
        total = total + chapter["hours"]
    return {
        "name": name,
        "code": course["code"],
        "exam_date": course["exam_date"],
        "chapters": chapters,
        "total_hours": total,
    }


def build_name_table():
    table = {}
    for name in COURSES:
        table[clean_name(name)] = name
        table[clean_name(COURSES[name]["code"])] = name
    for short_name, full_name in EXTRA_NAMES.items():
        table[clean_name(short_name)] = full_name
    return table


NAME_TABLE = build_name_table()


def resolve_subject(query):
    """Return found, missing, or ambiguous. Do not guess when two courses match."""
    raw = (query or "").strip()
    key = clean_name(raw)
    if key == "":
        return {"status": "missing", "query": raw}
    if key in NAME_TABLE:
        return {"status": "found", "name": NAME_TABLE[key], "query": raw}
    if len(key) < 3:
        return {"status": "missing", "query": raw}

    hits = []
    for name in COURSES:
        normal = clean_name(name)
        if key in normal or normal in key:
            hits.append(name)
    if len(hits) == 1:
        return {"status": "found", "name": hits[0], "query": raw}
    if len(hits) > 1:
        return {"status": "ambiguous", "candidates": hits, "query": raw}
    return {"status": "missing", "query": raw}
