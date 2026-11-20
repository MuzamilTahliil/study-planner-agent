"""The course data.

The agent is only allowed to use what is written in this file.
If a subject is not here, the agent must say "I do not have it".
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

# Short names a student might type (always lower case).
NICKNAMES = {
    "ai": "Artificial Intelligence Techniques",
    "ai techniques": "Artificial Intelligence Techniques",
    "artificial intelligence": "Artificial Intelligence Techniques",
    "wqf 7002": "Artificial Intelligence Techniques",
    "data structure": "Data Structures",
    "database": "Database Systems",
    "databases": "Database Systems",
    "db": "Database Systems",
}


def simplify(text):
    """Lower case, no punctuation. 'WQF-7002' becomes 'wqf 7002'."""
    text = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
    return text.strip()


def find_subject(text):
    """Return the full subject name, or None if we do not have that subject."""
    typed = simplify(text)
    if typed == "":
        return None

    # 1. A nickname, like "ml" or "database".
    if typed in NICKNAMES:
        return NICKNAMES[typed]

    # 2. The exact name or the course code.
    for name, course in COURSES.items():
        if typed == simplify(name) or typed == simplify(course["code"]):
            return name

    # 3. The full name appears inside what was typed.
    for name in COURSES:
        if simplify(name) in typed:
            return name

    return None


def total_hours(subject):
    """Add up the hours of every chapter of one subject."""
    total = 0
    for chapter in COURSES[subject]["chapters"]:
        total = total + chapter["hours"]
    return total
