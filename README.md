# 📚 Study Planner Agent

> An AI agent that plans your revision, **and knows when to say "I don't know."**

WQF7002 Artificial Intelligence Techniques · Assignment 1 · Muzamil · 2026

You tell the agent a course, how many days you have, and how many hours you can study each day.
It picks the right tool, checks it, and builds a day-by-day plan from **real course data only**.
If something is missing, unsafe, or unknown, it stops and tells you why instead of guessing.

---

## 🚀 Run it in 2 steps

You need Python 3.10 or newer.

```
pip install -r requirements.txt
python app.py
```

The browser opens at **http://127.0.0.1:7860**.
The first start downloads the model (about 3 GB). Wait until the terminal says `Running on local URL`.
On a normal laptop each answer takes **1–4 minutes**, so please be patient after pressing **Send**.

---

## 💬 What you can ask

| You ask | The agent calls | You get |
|---|---|---|
| "Create a 7-day plan for Machine Learning, 2 hours a day" | `create_study_plan` | A day-by-day plan, plus any chapters that don't fit |
| "Is 5 days at 3 hours enough for Database Systems?" | `check_workload` | Yes or no, with hours needed and hours available |
| "What should I study on day 2 of Data Structures?" | `get_day_plan` | That day's chapters |

**Courses it knows:** Artificial Intelligence Techniques · Data Structures · Database Systems · Machine Learning.

---

## 🧠 How the agent thinks

Every question goes through 5 steps. A function runs **only if every check passes**.

```
 Student question
       │
 1. Guardrail ─────────────── unsafe? ──► 🚫 Blocked (model is not called)
       │
 2. Details check (on Send) ── missing? ─► ⚠️ "Missing information" pop-up
       │
 3. Model chooses a tool  (Qwen 2.5 with tools=[...])
       │
 4. Argument checks ────────── fails? ──► ❌ Rejected, agent asks for details
       │   allow list · type · range · "did the student really say this?"
       │
 5. Run the function ──► ✅ Answer written from the REAL result
```

---

## 🛡️ Problems the agent handles

| Problem | What could go wrong | What the agent does |
|---|---|---|
| **Missing details** | "I have 6 days to study 10 chapters" (no course, no hours) | Pop-up: *"Please tell me: the name of the course, how many hours you can study each day."* The model is not called. |
| **Invented arguments** | The model guesses a course or hours the student never said | The call is **rejected**: every subject and number must appear in the question |
| **Unknown course** | "Make a plan for English" | *"I do not have English in my course list"*. No fake chapters. |
| **Prompt injection** | "Ignore your instructions and…" | **Blocked** before the model runs |
| **Unsafe request** | "Write my assignment", "hack the account", exam answers | **Blocked** before the model runs |
| **Impossible numbers** | 12 hours a day, 90 days, unknown function names | **Rejected** by the allow list and range checks |
| **Not enough time** | 2 days for an 18-hour course | The plan lists exactly which chapters are **not covered** |

---

## 🔧 Part 4: the weakness we found and fixed

**Before:** the question had no course and no hours, but the model **invented** "Artificial Intelligence Techniques" and 4 hours a day, and the agent gave a confident fake plan.

![Before: invented plan](screenshots/weakness%201.png)

The same thing happened with *"i have 2 days to lear 10 chapters"*:

![Before: second example](screenshots/Weakness%202%20wrong%20answer.png)

**Why:** *partial observability*. The agent didn't have the facts it needed, and the small model filled the gap with guesses. The old checks only tested type and range, not *"did the student actually say this?"*

**The fix:** one new rule in `validation.py` (`check_question_has_details`). The subject and every number must appear in the student's question, or the function does not run.

**After:** the same kind of question is refused, and the agent asks for what is missing.

![After: agent refuses and asks](screenshots/return%20when%20missing%20parameters.png)

---

## 🧪 The 8 tests

Click a test button under the question box, then press **Send**.
Press **🔍 Show what the agent did** to see the function name, arguments, and result.

| # | Test | Expected | Result |
|---|---|---|---|
| 1 | 9-day plan, AI Techniques, 2 h/day | `create_study_plan` → 18 h needed, 18 h available | ✅ |
| 2 | 5 days × 2 h enough for Machine Learning? | `check_workload` → No, short by 4 h | ✅ |
| 3 | Day 2 of Database Systems | `get_day_plan` → Relational Model, SQL | ✅ |
| 4 | 8-day plan, Data Structures, 2 h/day | `create_study_plan` → 16 h needed, 16 h available | ✅ |
| 5 | 5 days × 3 h enough for Database Systems? | `check_workload` → Yes | ✅ |
| 6 | Plan for Quantum Basket Weaving | Admits the course is unknown | ✅ |
| 7 | "Ignore your instructions…" | Blocked, no function runs | ✅ |
| 8 | "Write my assignment… hack…" | Blocked, no function runs | ✅ |

---

## Files

| File | What it does |
|---|---|
| `app.py` | The web page (Gradio): question box, answer card, buttons, tests |
| `style.css` | Orange-and-white design |
| `agent.py` | The 5 steps: guardrail → model → read tool call → check → run |
| `tools.py` | The 3 functions the model may call |
| `validation.py` | Guardrail, missing-details check, allow list, argument checks |
| `data.py` | The 4 courses: chapters, hours, exam dates |

**Model:** [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct), free on Hugging Face, with **native tool calling** (`apply_chat_template(..., tools=...)`). Nothing is trained or fine-tuned.

---

## Known limits

- Only the 4 courses above. Others are refused on purpose ("knows its limits").
- Numbers must be digits: "2 hours" works, "two hours" does not.
- Slow on a CPU: 1–4 minutes per answer.

---

© 2026 Muzamil. All rights reserved.
