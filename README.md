# Study Planner Agent

A small goal-based agent for WQF7002 Assignment 1. It plans revision for four subjects stored in `data.py`. A free Hugging Face instruction model decides which Python function to call. Python checks that call before it runs, and the answer is written from the function result.

The model is [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct). It is instruction-tuned and its chat template accepts tools. The agent passes the three functions with `apply_chat_template(..., tools=...)`. If a model has no native tool calling, the same loop accepts a JSON object:

```json
{"function": "create_study_plan", "arguments": {"subject": "Data Structures", "days_available": 8, "hours_per_day": 2}}
```

Either way, the function runs only after the allow list and the argument checks accept it.

## Layout

| File | Role |
| --- | --- |
| `app.py` | Gradio screens: Home, Dashboard, Study Planner, Ask AI, and About. Ask AI shows every function call. |
| `agent.py` | Loads the model, reads the tool call, and runs the tool loop. |
| `tools.py` | `create_study_plan`, `check_workload`, `get_day_plan`. |
| `validation.py` | Allow list, argument checks, and the guardrail. |
| `data.py` | Subjects, chapters, hours, and exam dates. |
| `tests/test_cases.md` | The eight Part 3 tests. Fill in the actual column after you run them. |
| `screenshots/` | One screenshot per test, for the report appendix. |

## What the three functions do

- `create_study_plan(subject, days_available, hours_per_day)` builds a day-by-day plan from the chapter hours and saves it for this chat session.
- `check_workload(subject, days_available, hours_per_day)` compares the hours the course needs with `days × hours per day`.
- `get_day_plan(subject, day_number)` returns one day. It uses the saved plan when there is one. Otherwise it uses a default pace of 2 hours per day and says that it did so.

A name that is not in `data.py` comes back as `found: false`. The chat then says the subject is missing and lists the subjects it does have. It does not invent chapters.

Hours are packed in tenths of an hour. A chapter that does not fit in the rest of a day is split, and the answer shows how many of its hours fall on that day. Time that runs out is listed as uncovered. Those chapters are not pushed onto an extra day.

## Checks before a function runs

1. **Allow list.** The name must be one of the three functions. `dump_database` and anything else is rejected.
2. **Arguments.** Required fields must be present. Types are checked. `days_available` is an integer from 1 to 30. `day_number` is an integer from 1 to 60. `hours_per_day` is a number from 0.5 to 8, with at most one decimal place. More than 8 hours in a day is rejected. Unknown extra fields are removed and are not passed in.
3. **Guardrail, in Python.**
   - A message that tries to override the instructions (for example "Ignore your instructions") is stopped before the model is called.
   - A request for exam answers, a written assignment, a hacked account, a password, or another student's records is stopped the same way.
   - If an allowed function is called with arguments that contain the same kind of request, that call is blocked as well.

Blocked turns record `status: blocked` and show that no function ran. The raw-output box says the model was not called.

If the model answers with chapter names or an exam date without calling a tool, that reply is replaced. Those facts are only allowed when a tool returned them.

## Design notes for the report

Rewrite this in your own words. A short copy of these notes is not a substitute for understanding the program.

**PEAS**

- **Performance:** a plan or a workload answer whose hours match `data.py`; a clear "I do not have that subject" when the name is missing; a refusal on an unsafe or injected request; no invented chapters.
- **Environment:** the local course list, the current chat, and the plan saved in this session.
- **Actuators:** the three Python functions, plus the text shown in the chat.
- **Sensors:** the user's message, the tool result, and the saved plan.

**Environment properties**

- **Partially observable.** The agent cannot see a real calendar, only this dataset and this chat.
- **Deterministic.** The same arguments return the same plan.
- **Sequential.** A plan saved earlier changes what `get_day_plan` returns later in the session.
- **Static.** The course list does not change while the model is generating.
- **Discrete.** Days, chapters, and tenths of an hour.
- **Single agent.**

**Agent type.** Goal-based, with a small internal model. The goal is a revision plan that fits the hours the student stated. The saved plan is the internal model `get_day_plan` reads. It is not a learning agent: nothing is trained.

**Limits.** It only knows the four subjects in `data.py`. It will not invent a missing course, write an assignment, give exam answers, or touch another person's account. It rejects a daily load above 8 hours, a function name that is not on the allow list, and a message that tells it to ignore its rules.

## Run it

Use Python 3.10 or newer.

```powershell
cd "d:\UM\Semister 1\AI TECHNIQUES\Assignments\Assignment1\study-planner-agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python app.py
```

Open the local URL Gradio prints (normally `http://127.0.0.1:7860`). The top bar opens **Home**, **Dashboard**, **Study Planner**, **Ask AI**, and **About**. The look is Bootstrap. The function-call box is on Ask AI.

The first real question downloads `Qwen/Qwen2.5-1.5B-Instruct` (about 3 GB) and loads it. On a CPU, leave several minutes for that first reply. A machine with an NVIDIA GPU uses float16 automatically. To try a stronger model:

```powershell
$env:STUDY_PLANNER_MODEL = "Qwen/Qwen2.5-3B-Instruct"
python app.py
```

`do_sample` is off, so the same prompt should produce the same tool call on the same model.

## The eight tests

The inputs are the example buttons in the app, and they are written out in `tests/test_cases.md`.

1. Press **Clear** so the previous plan is forgotten.
2. Click the example, then **Send**.
3. Screenshot the chat, the function-call panel, and the raw model output together.
4. Save it as `screenshots/test-01.png` through `screenshots/test-08.png`.
5. Copy the function name, arguments, and answer into `tests/test_cases.md`, and mark pass or fail.

Pass a normal test only when the function and the arguments match the user, and the hours match the dataset. Pass the unknown-subject test only when the agent says the subject is missing and does not invent chapters. Pass the injection and unsafe tests only when the panel says `blocked` and no function ran.

## Dataset

| Subject | Code | Hours | Exam date |
| --- | --- | --- | --- |
| Artificial Intelligence Techniques | WQF7002 | 18 | 2026-12-15 |
| Data Structures | DSA | 16 | 2026-12-18 |
| Database Systems | DBS | 15 | 2026-12-12 |
| Machine Learning | ML | 14 | 2026-12-20 |

`DSA`, `DBS`, and `ML` are labels for this file. They are not a live timetable. Only `WQF7002` is the real course code from the assignment brief.

## AI-use declaration

The submission needs the signed WQF7002 AI-use form. List every AI tool you used, what you used it for, and which files it affected. You need to be able to explain the code.
