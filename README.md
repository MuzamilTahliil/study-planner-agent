# Study Planner Agent (WQF7002 Assignment 1)

An AI agent that helps a student plan revision. It uses the free Hugging Face model
**Qwen/Qwen2.5-1.5B-Instruct**, which supports tool calling. The model decides which Python
function to call. Python checks the call before running it, and the answer is written from
the real function result.

## How to run (2 steps)

You need Python 3.10 or newer.

**Step 1. Install the packages (only the first time):**

```
pip install -r requirements.txt
```

**Step 2. Start the app:**

```
python app.py
```

The browser opens by itself at **http://127.0.0.1:7860**.
The first start downloads the model (about 3 GB). Wait until the terminal says
`Running on local URL`. On a laptop without a graphics card, each answer can take
1–4 minutes, so please be patient after pressing **Send**. The two guardrail tests (7 and 8)
answer immediately because the model is not called.

To stop the app, press `Ctrl + C` in the terminal.

## How to test it

Under the page there are **8 example buttons** (the 8 tests of Part 3).
Click one example, then press **Send**. The answer appears in **Response**.
On the right you see every function call (name, arguments, result), what the model wrote,
and your message. Reload the page to forget saved plans.

| # | Test | Expected |
|---|------|----------|
| 1–5 | Normal questions | The correct function is called with the right numbers |
| 6 | Quantum Basket Weaving | The agent says it does not have this subject |
| 7 | "Ignore your instructions…" | Blocked by the guardrail, no function runs |
| 8 | "Write my assignment… hack…" | Blocked by the guardrail, no function runs |

## Files

| File | What it does |
|------|--------------|
| `app.py` | The web page (Gradio) |
| `style.css` | Colours and layout of the page (orange and white) |
| `agent.py` | Talks to the model, reads its tool call, checks it, runs it |
| `tools.py` | The 3 functions: `create_study_plan`, `check_workload`, `get_day_plan` |
| `validation.py` | Guardrail + allow list + argument checks |
| `data.py` | The 4 subjects, their chapters, hours and exam dates |

## How tool calling works

The 3 functions are passed to the model with `apply_chat_template(..., tools=TOOLS_FOR_MODEL)`
(native tool calling). The model answers with a call such as:

```json
{"name": "create_study_plan", "arguments": {"subject": "Data Structures", "days_available": 8, "hours_per_day": 2}}
```

Before running it, Python checks:
1. **Allow list** – the name must be one of the 3 functions.
2. **Arguments** – required fields are present; `days_available` 1–30, `hours_per_day` 0.5–8, `day_number` 1–60.
3. **Guardrail** – messages with prompt injection ("ignore your instructions") or unsafe requests
   (exam answers, hacking, passwords, writing assignments) are blocked before the model is even called.

If a subject is not in `data.py`, the agent says so and does not invent chapters.

## Improvement (Part 4)

**Weakness found:** for *"i have 10 days to prepare 8 chapters for my course so give me plan"*
the model called `create_study_plan` with subject **Artificial Intelligence Techniques** and
**4 hours per day**. The student never said either of these. The arguments had the right type
and range, so the old checks let the call run, and the agent gave a confident but made-up plan.

**Why:** partial observability. The agent did not have the information it needed (which
subject, how many hours), but the model filled the gaps with guesses instead of asking.

**Change:** one new check in `validation.py` (`check_question_has_details`). Before a function
runs, the subject and every number in the arguments must appear in the student's question.
If not, the call is rejected and the agent asks for the missing details.

**After:** the same question is rejected with *"You did not tell me which subject and how many
hours you can study each day…"*, and no function runs. The 8 tests still pass.
