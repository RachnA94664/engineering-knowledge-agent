# Engineering Knowledge Agent

[![CI](https://github.com/RachnA94664/engineering-knowledge-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/RachnA94664/engineering-knowledge-agent/actions/workflows/ci.yml)

A small AI-assisted system that stores **Requirements**, **Test Cases** and **Risk Items** in a
database and lets you work with them in plain English.

> Ask *"Which requirements have no test cases?"* and get an answer taken **from the database**,
> with the records it is based on. Say *"Set REQ-006 priority to high"* and the AI **proposes**
> the change; a **person confirms** it, and the system then works out automatically what the
> change affects (which tests must be re-run, which risks need a second look).

**The three ideas this project is built around**

1. **The AI never invents data.** Every answer must come from tool results, and every ID in an
   answer is checked against them.
2. **The AI never changes data.** It can only *propose*. A human presses *Confirm*.
3. **Everything is recorded.** Every change goes into an append-only audit log.

---

## Contents

1. [What the application does](#1-what-the-application-does)
2. [Quick start](#2-quick-start)
3. [Architecture](#3-architecture)
4. [Database design](#4-database-design)
5. [Agent design](#5-agent-design)
6. [Rules and validations](#6-rules-and-validations)
7. [The automatic impact workflow](#7-the-automatic-impact-workflow)
8. [Example user queries](#8-example-user-queries)
9. [API overview](#9-api-overview)
10. [Tests and CI](#10-tests-and-ci)
11. [Project structure and how to change things](#11-project-structure-and-how-to-change-things)
12. [Technical decisions and why](#12-technical-decisions-and-why)
13. [Known limitations](#13-known-limitations)
14. [Troubleshooting](#14-troubleshooting)
15. [Git workflow](#15-git-workflow)

---

## 1. What the application does

| You want to... | Where | What happens |
|---|---|---|
| Ask a question about the data | **Ask** page | A router picks a specialist agent; it reads the database with tools; the answer shows a verdict badge and the records behind it |
| Ask for a change | **Ask** page | The agent creates a *proposal*; nothing changes yet |
| Review and decide on proposals | **Pending** page | You see current vs. proposed values and press *Confirm* or *Reject* |
| See what a change affected | after *Confirm*, or **Requirements** → a requirement | The impact report: tests reset, risks flagged, warnings, impact level |
| Browse and filter | **Requirements**, **Risks** | Tables with filters; risks flagged for review can be marked *reviewed* |
| Check who did what | **Audit log** | Every change: who, when, before, after, and whether a person, the agent or the system did it |

The sample data is an EV-charging-station product: 15 requirements, 30 test cases, 12 risk items
and 16 requirement-to-risk links.

---

## 2. Quick start

You need **Git**. Then pick one way to run it.

```bash
git clone https://github.com/RachnA94664/engineering-knowledge-agent.git
cd engineering-knowledge-agent
```

### The AI: choose one

The app needs a language model for the **Ask** page. Everything else (browsing, proposing from the
form, confirming, impact analysis, audit) works without one.

| Option | Cost | Setup |
|---|---|---|
| **Ollama** (default for Docker) | free, runs on your PC, private | Install [Ollama](https://ollama.com), then `ollama pull qwen2.5:3b` |
| **OpenAI** | paid API credits | Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` |

A small model on a CPU is slow: the first answer can take **30-90 seconds**, later ones are faster.
The UI shows a timer and a Cancel button.

### Option A: Docker (one command)

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) and (for the AI) Ollama running.

```bash
docker compose up --build
```

Open **http://localhost:8080** (the app) and **http://localhost:8000/docs** (interactive API docs).
Stop with `docker compose down` (your data is kept in a volume; `docker compose down -v` deletes it).

On start the backend container applies the database migrations and loads the sample data **only if
the database is empty**, so restarting is safe.

To use OpenAI instead of Ollama in Docker (PowerShell):

```powershell
$env:LLM_PROVIDER="openai"; $env:OPENAI_API_KEY="sk-..."; docker compose up --build
```

### Option B: run it locally (for development)

You need **Python 3.12** and **Node 22**. Commands are for Windows PowerShell; the macOS/Linux
differences are noted.

**1. Backend** (terminal 1)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy ..\.env.example .env             # macOS/Linux: cp ../.env.example .env
```

Open `backend/.env` and set `LLM_PROVIDER=ollama` (or put in your OpenAI key). **`.env` is
git-ignored: never commit it and never paste a key into chat or an issue.**

```powershell
alembic upgrade head                   # create the tables
python -m app.db.seed                  # validate and load the sample data
uvicorn app.main:app --reload --port 8000
```

Check it: http://localhost:8000/health should say `{"status":"ok","database":"ok"}`.

**2. Frontend** (terminal 2)

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Type your name in the box at the bottom of the sidebar: it is
written into the audit log when you confirm something.

**3. Try the agents without the UI** (optional)

```powershell
cd backend
python -m app.agents.cli "Which requirements have no test cases?"
```

### Configuration

All settings are environment variables (see [`.env.example`](.env.example)); nothing is hard-coded.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `openai` (Docker: `ollama`) | `openai` or `ollama` |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | - , `gpt-4o-mini` | OpenAI settings |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `http://localhost:11434`, `qwen2.5:3b` | Ollama settings |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | A CPU model can be slow |
| `DATABASE_URL` | `sqlite:///./knowledge.db` | Where the data lives |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Which web addresses may call the API (CORS) |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` | off | Optional tracing. Traces contain your text: use dummy data, or set `LANGSMITH_HIDE_DATA=true` |
| `VITE_API_URL` (frontend) | `http://localhost:8000` | Address of the API, fixed when the frontend is built |

---

## 3. Architecture

The code is split into **layers**. Each layer only talks to the one below it, so you can change
one part without breaking the others.

```mermaid
flowchart TB
  UI["React UI (Vite + TypeScript)"] -->|"HTTP + JSON"| API["FastAPI routes<br/>one error format for every failure"]
  API --> AG["Agents (LangGraph)<br/>router + 3 specialists"]
  API --> SV["Services<br/>use cases, transactions, audit log"]
  AG -->|"tools call services only"| SV
  SV --> DM["Domain rules<br/>pure Python, no database"]
  SV --> RP["Repositories<br/>the only place with SQL"]
  RP --> DB[("SQLite")]
```

**Why the layers matter**

- **Domain** (`backend/app/domain/`): the rules (allowed status moves, risk score, impact). Plain
  Python functions: easy to read and to test.
- **Repositories** (`app/repositories/`): the only code that writes SQL.
- **Services** (`app/services/`): one function per use case ("propose a change", "confirm a
  change"). They open the transaction and write the audit log.
- **Agents** (`app/agents/`): the AI. Its tools call **services**, never the database directly, so
  the AI is subject to exactly the same rules as the UI.
- **API** (`app/api/`): HTTP only; it turns errors into one JSON shape
  `{"error": {"code", "message", "details"}}`.

### How a chat message flows

```mermaid
flowchart LR
  M["Message"] --> R{"Router<br/>rules first, AI only if unsure"}
  R -->|"delete / confirm words"| X["Refuse<br/>no AI call at all"]
  R -->|"unclear, AI says unrelated"| O["Polite decline"]
  R -->|"read / search"| Q["Query agent<br/>read-only tools"]
  R -->|"change something"| U["Update agent<br/>propose-only tool"]
  R -->|"what did it affect?"| A["Analysis agent<br/>reads stored impact report"]
  Q --> G["Grounding check"]
  U --> G
  A --> G
  G --> ANS["Answer + records + tool trace"]
```

---

## 4. Database design

SQLite, managed by **Alembic migrations** (`backend/migrations/`). The tables:

```mermaid
erDiagram
  REQUIREMENTS ||--o{ TEST_CASES : "has"
  REQUIREMENTS ||--o{ REQUIREMENT_RISKS : "linked by"
  RISK_ITEMS ||--o{ REQUIREMENT_RISKS : "linked by"
  REQUIREMENTS ||--o{ IMPACT_REPORTS : "gets"
  PENDING_CHANGES ||--o| IMPACT_REPORTS : "produces one"

  REQUIREMENTS {
    string id PK "REQ-001"
    string title
    text description
    string priority "low medium high critical"
    string status "draft approved implemented verified obsolete"
    int version "optimistic locking"
  }
  TEST_CASES {
    string id PK "TC-001"
    string requirement_id FK
    string title
    text steps
    text expected_result
    string status "not_run pass fail blocked"
  }
  RISK_ITEMS {
    string id PK "RISK-001"
    string title
    int severity "1-5"
    int likelihood "1-5"
    string status "open mitigated accepted closed"
    bool needs_review
  }
  REQUIREMENT_RISKS {
    string requirement_id PK
    string risk_id PK
  }
  PENDING_CHANGES {
    int id PK
    string entity_id
    text proposed_patch "JSON"
    int base_version
    string proposed_by
    string status "pending applied rejected expired"
  }
  IMPACT_REPORTS {
    int id PK
    string requirement_id FK
    int change_id FK "UNIQUE"
    string level "low medium high"
    text report "JSON"
  }
  AUDIT_LOG {
    int id PK
    datetime ts "UTC"
    string actor
    string source "ui agent system"
    string entity_id
    string action
    text old_value
    text new_value
  }
```

**Relationships**

- A requirement has **many test cases**; a test case belongs to **exactly one** requirement (foreign key).
- Requirements and risks are **many-to-many**, through the link table `requirement_risks`.
- Each confirmed change has **at most one** impact report (`change_id` is unique).
- `audit_log` stands alone on purpose: it must outlive and never depend on the rows it describes.

**Design decisions**

- **Readable IDs** (`REQ-001`, `TC-001`, `RISK-001`) are the primary keys. The format is enforced by
  a database `CHECK` constraint, not only by code.
- **Allowed values** (statuses, priorities) are `CHECK` constraints generated from the same Python
  tuples the code uses (`domain/enums.py`), so code and database cannot disagree.
- **The risk score is not stored.** `score = severity x likelihood` is calculated in code
  (`domain/risk.py`): `>= 15` high, `>= 8` medium, otherwise low. A stored value could go stale.
- **Foreign keys use `ON DELETE RESTRICT`:** you cannot delete a requirement that still has tests.
- **All timestamps are UTC** (a custom column type guarantees it).
- **The audit log is append-only, enforced by database triggers** that reject any `UPDATE` or
  `DELETE`, even from buggy code.

**Dummy data.** The sample data (an EV-charging-station product) was written with AI assistance and is
produced by the script `backend/data/gen_seed.py` into `backend/data/seed_raw.json`. It is
**validated before it is inserted** (`app/db/seed.py`): required fields, ID format,
allowed values, a 1-5 scale for severity and likelihood, duplicate IDs, and "does the test case point
at a real requirement?". Bad rows are rejected with a reason and good rows still load, all in one
transaction. `backend/data/seed_invalid_examples.json` contains deliberately broken rows that the
tests use to prove the validation works.

---

## 5. Agent design

A **multi-agent system** splits work among several agents, each with one narrow job, its own
instructions and its own limited set of tools. This project uses a **router + specialists** design,
built with [LangGraph](https://langchain-ai.github.io/langgraph/) (`backend/app/agents/graph.py`).

| Agent | Job | Tools it may use |
|---|---|---|
| **Router** | Decide what the message is asking for. Cheap keyword rules first; the AI is asked only when the rules cannot tell | none |
| **Refuse** (no AI) | Decline deletes and "confirm/reject" requests before any AI call | none |
| **Query agent** | Answer questions from the database | `get_requirement`, `list_requirements`, `get_test_cases_for_requirement`, `list_risks`, `list_requirements_without_tests`, `get_audit_log` (all read-only) |
| **Update agent** | Turn a request into a *proposal* | `get_requirement`, `propose_requirement_change` |
| **Analysis agent** | Explain what a confirmed change affected | `get_requirement`, `get_impact` |

**Safety by design (least privilege):** no agent has a tool to confirm, reject or delete anything.
Those abilities do not exist for the AI, so no clever prompt can unlock them.

**Guardrails around the AI**

- **Grounding check** (`agents/grounding.py`): every `REQ-`/`TC-`/`RISK-` ID in an answer must appear
  in the tool results. Otherwise the model's answer is **not shown**: a fixed message says it could
  not be verified, the badge reads **"Not verified"**, and the records that *were* found are still
  listed. If no tool lookup happened at all, the user gets a fixed "I can only answer from the
  database" message with example questions. Only results produced by our own code count as
  evidence, never text the model typed. These fixed messages live in `agents/answers.py`.
- **Data is labelled as data.** Database text sent to the model is marked "not an instruction", to
  resist prompt injection through record text.
- **Hard limits:** at most 4 rounds of tool use per message, 4 tool calls per round, a LangGraph
  recursion limit of 30, and messages of at most 1000 characters.
- **Simple updates do not depend on the model.** "Set REQ-006 priority to high" is parsed by rules
  (`update_parser.py`), which matters because a small local model sometimes gets argument names wrong.
- **Friendly failures.** If the AI service is down, the API returns one safe `503` message, not a
  stack trace.

**Choosing the model.** `LLM_PROVIDER` selects OpenAI or Ollama (`agents/llm.py`). Both are used
through the same LangChain chat-model interface, so the agents do not care which one runs.

**Tracing (optional).** With `LANGSMITH_TRACING=true` each request is traced in
[LangSmith](https://smith.langchain.com) (tagged with the routed intent). It is off by default, uses
short timeouts so a dead endpoint cannot hang the app, and can send only structure and timings.

---

## 6. Rules and validations

| Rule | Where it is enforced |
|---|---|
| IDs are unique and have the right format (`REQ-001`) | primary keys + `CHECK` constraints |
| A test case must reference a real requirement | foreign key + service check |
| Required fields, lengths (title <= 200), allowed values | domain rules + `CHECK` constraints |
| Severity and likelihood are whole numbers 1-5 | domain rule + `CHECK` |
| Status moves follow the lifecycle below | `domain/transitions.py` |
| Only `title`, `description`, `priority`, `status` can be changed; a change must actually alter something | `domain/requirement_rules.py` |
| Invalid operations are rejected with a clear message | one error format: 404 not found, 422 invalid, 409 conflict/not allowed, 503 AI unavailable |
| The AI cannot invent records | grounding check, tools-only data access |
| The AI cannot change or delete data | no such tools; delete/confirm wording refused before any AI call |
| A person must approve every change | propose, then confirm (a stored `pending_changes` row) |
| No lost updates | optimistic locking: a proposal remembers the requirement's `version`; if it changed since, confirming fails with `409` and you propose again |
| Safe retries | confirming or rejecting twice does not repeat the effect |
| Every modification is logged | `audit_log`, written in the **same transaction** as the change; append-only (triggers) |
| Rate of AI use is bounded | message length, rounds and tool-call limits (see Limitations for what is *not* limited) |

**Status lifecycle**

```
draft -> approved -> implemented -> verified
   \         \             \            \
    +---------+-------------+------------+--> obsolete   (final, no way back)
```

No backward moves. The UI hides impossible choices, but the backend is the authority.

---

## 7. The automatic impact workflow

When a person **confirms** a change to a requirement, the system analyses the impact **inside the
same database transaction** as the change, stores a report, and writes audit rows (actor
`impact-analysis`, source `system`). If anything fails, **nothing** is applied.

The rules are plain Python in `backend/app/domain/impact.py`:

| The change | Effect |
|---|---|
| Description edited | Passing test cases are reset to `not_run`; linked open risks are flagged for review |
| Priority raised | Linked open risks are flagged (tests unchanged) |
| Status becomes `obsolete` | Linked open risks are flagged; a note that tests may be retired |
| Status becomes `verified` | Warning if linked tests are not all passing, or there are none |
| Title edited, priority lowered, other status moves | Nothing is affected |

Closed risks are never flagged. **Impact level:** `low` if nothing is affected; `high` if something is
affected *and* (the requirement is `critical` *or* its description changed); otherwise `medium`.

**Deliberately rule-based, not AI-written.** An impact report is a statement about your data, so it
must be repeatable and testable. The analysis agent only *reads and explains* the stored report.
A person clears a risk flag with *Mark reviewed*; the AI cannot.

Real example (from the sample data): editing REQ-009's description reset TC-019, TC-020 and TC-030 to
`not_run`, listed TC-021 as already failing, flagged RISK-003, and rated the impact **high**.

---

## 8. Example user queries

Type these into the **Ask** page (or `python -m app.agents.cli "..."`).

| You type | What happens |
|---|---|
| `Show me requirement REQ-001` | Query agent reads it and shows title, status, priority, version |
| `Which test cases are associated with REQ-001?` | Query agent lists them |
| `Show me high-risk items` | Query agent lists risks with level `high`, highest score first |
| `Which requirements don't have test cases?` | Query agent: REQ-012, REQ-013, REQ-014, REQ-015 in the sample data |
| `Which risks need review?` | Query agent lists flagged risks |
| `Set REQ-006 priority to high` | A **proposal** appears; confirm it in the card or on the Pending page |
| `Update the status of REQ-001` | No new value was given, so you get a helpful message showing the exact format, e.g. `Set REQ-001 status to approved` |
| `What is the impact of REQ-009?` | Analysis agent explains the latest stored impact report |
| `Delete REQ-001` | **Refused** (red "Declined" badge). Nothing is deleted |
| `Confirm change 3` | **Refused**: only a person can confirm, in the UI |
| `What is the weather today?` | Question-shaped, so it goes to the query agent, which finds nothing to look up. The grounding rule then returns the fixed "I can only answer from the database" reply with suggested questions |

**What the answer card shows:** the answer, a verdict badge (*Checked against the database* /
*Not verified* / *Declined*), **Records behind this answer**, and **Tools used**, so you can check any
claim yourself.

---

## 9. API overview

Interactive docs with "Try it out": **http://localhost:8000/docs**.

| Method and path | Purpose |
|---|---|
| `GET /health` | Health and database-schema check (reports the exact fix if the database is behind the code) |
| `GET /requirements`, `GET /requirements/{id}` | List / get (IDs look like `REQ-001`) |
| `GET /requirements/without-tests` | Requirements with no test cases |
| `GET /requirements/{id}/test-cases` | Test cases of a requirement |
| `GET /requirements/{id}/impact` | Latest impact report (404 if none yet) |
| `GET /risks?level=high&needs_review=true` | Risks with score and level |
| `POST /risks/{id}/reviewed` | A person clears the review flag |
| `GET /audit-log?limit=50&entity_id=REQ-001` | Audit entries |
| `GET /changes`, `POST /changes` | List pending / propose a change |
| `POST /changes/{id}/confirm`, `POST /changes/{id}/reject` | A person decides (`{"actor": "your name"}`) |
| `POST /chat` | Send a message to the agents |

---

## 10. Tests and CI

```powershell
cd backend ; python -m pytest -q          # 400+ tests
cd frontend ; npm test                    # 25 tests
```

- **Backend** (`backend/tests/`): `unit/` (pure rules: transitions, risk score, impact rules, router,
  grounding), `integration/` (API, services, migrations on a *populated* database, audit log,
  timestamps, impact workflow, tracing against a fake server) and `agents/` (the whole graph run with a
  **scripted fake model**, so tests are free, fast and need no API key).
- **Frontend** (`frontend/src/**/*.test.*`): Vitest + Testing Library against a tiny fake backend.
  They cover chat, confirming (and the impact report appearing), the 409 case, filters, and the
  health banner.
- **CI** (`.github/workflows/ci.yml`): on every pull request and push to `develop`/`main`, GitHub runs
  `ruff` + `pytest`, `eslint` + `vitest` + the production build, and builds both Docker images. These
  checks are **required**: a red pull request cannot be merged. No secrets are involved.

Run the same checks locally before pushing:

```powershell
cd backend ; ruff check . ; ruff format --check . ; pytest -q
cd frontend ; npm run lint ; npm test ; npm run build
```

---

## 11. Project structure and how to change things

```
engineering-knowledge-agent/
├── backend/
│   ├── app/
│   │   ├── domain/        rules: transitions, risk score, impact (pure Python)
│   │   ├── db/            models, session, seed, schema check
│   │   ├── repositories/  all SQL
│   │   ├── services/      use cases: propose, confirm, impact, reviews
│   │   ├── agents/        LangGraph graph, tools, router, grounding, prompts/
│   │   ├── api/           routes, schemas, error handling
│   │   ├── core/          settings, optional tracing
│   │   └── main.py        app start-up and /health
│   ├── migrations/        Alembic (database versions)
│   ├── data/              seed_raw.json (+ invalid examples for tests)
│   ├── tests/             unit, integration, agents
│   └── Dockerfile
├── frontend/
│   ├── src/api/           the only code that calls the backend
│   ├── src/pages/         Ask, Requirements, Risks, Pending, Audit
│   ├── src/components/    badges, diff table, impact card, proposal card
│   ├── Dockerfile, nginx.conf
├── docker-compose.yml
├── .github/workflows/ci.yml
└── plan/                  PLAN.md (design) and GUIDE.md (phase-by-phase build log)
```

**"I want to change X: where do I edit?"**

| Change | Edit | Then |
|---|---|---|
| A new priority or status value | `domain/enums.py` | add an Alembic migration (the `CHECK` constraints come from it); update `frontend/src/lib/transitions.ts` and the Badge colours |
| Which status moves are allowed | `domain/transitions.py` | mirror it in `frontend/src/lib/transitions.ts`; update `tests/unit/test_transitions.py` |
| Risk thresholds (what counts as "high") | `HIGH_THRESHOLD` / `MEDIUM_THRESHOLD` in `domain/risk.py` | update `tests/unit/test_risk.py` |
| What a change affects | `domain/impact.py` | update `tests/unit/test_impact_rules.py` |
| Add or change a database column | `db/models.py` | `alembic revision --autogenerate -m "message"`, review the file, `alembic upgrade head` (test on a database that already has data) |
| What the AI may do | `agents/tools.py` (the `*_TOOLS` tuples) | add tests; never give an agent a delete or confirm tool |
| How the AI behaves | `agents/prompts/*.md` | run the agent tests |
| Words that are refused or routed | `agents/router.py` | update `tests/unit/test_router.py` |
| Look and feel | `frontend/src/styles.css` (colour tokens at the top) | |
| Seed data | `backend/data/seed_raw.json` | `python -m app.db.seed` on an empty database |

After changing the database models always create a migration; after pulling new code run
`alembic upgrade head` (the app's `/health` and start-up log tell you if you forgot).

---

## 12. Technical decisions and why

| Decision | Why | Trade-off |
|---|---|---|
| **Propose, then confirm** | A model can misunderstand. A human in the loop makes wrong AI actions harmless and the audit log meaningful | One extra click per change |
| **Rules first, AI second** (router, simple updates) | Predictable, free, fast, and immune to a small model's mistakes | More code than "ask the model" |
| **LangGraph** | The flow is a graph (route, specialist, tools, check) with explicit limits, and it traces well | A new concept to learn |
| **Tools call services, not SQL** | The AI obeys the same rules, transactions and audit as the UI | One more layer |
| **Grounding check on every answer** | Directly addresses "the AI must not invent records" | Can mark a correct but oddly worded answer "Not verified" |
| **Impact analysis in plain Python** | Repeatable and testable; the AI only explains it | Rules are simple (see limitations) |
| **Risk score derived, not stored** | Cannot become stale | Computed on read |
| **Optimistic locking (`version`)** | Prevents silently overwriting someone else's edit, without database locks | A conflicting confirm must be re-proposed |
| **Append-only audit log via triggers** | Even a bug cannot rewrite history | Corrections are new rows |
| **SQLite + Alembic** | Zero setup, one file, and real migrations (tested on populated data) | Single writer; see limitations |
| **FastAPI + Pydantic** | Typed validation and automatic `/docs` | |
| **Ollama by default, OpenAI optional** | Free and private for development; the code is provider-neutral | A 3B CPU model is slow and less capable |
| **React + plain CSS, no UI library, hash router** | Little to learn, tiny bundle, nothing to configure on a static host | Hand-written styles |
| **One error format** | The frontend shows a readable message for any failure | |
| **Docker + required CI checks** | Same environment everywhere; no red code reaches `develop` or `main` | |

---

## 13. Known limitations

- **Speed and quality depend on the model.** A 3B model on a CPU takes tens of seconds and can
  misread complicated requests. Simple updates are parsed by rules for this reason. A hosted model
  (OpenAI) is much faster.
- **No authentication.** The "Your name" box is self-declared; anyone who can open the app can
  confirm changes. Do not expose it publicly as-is.
- **No rate limiting on the API yet.** Only message length and agent loop limits exist. Add a rate
  limit before putting it on the internet with a paid AI key.
- **Not deployed.** The code is ready for Render (backend) and Vercel (frontend) but this repository does not
  include a live deployment. A deployed backend could not reach an Ollama model on your own PC.
- **SQLite is single-writer.** Fine for a demo and a few users, not for heavy concurrent writes
  (switch `DATABASE_URL` to PostgreSQL and test the migrations first).
- **Limited editing.** Through the UI and the AI you can change only a requirement's title,
  description, priority and status. Creating or deleting records is not exposed on purpose.
- **Simple impact analysis.** It follows direct links (requirement to its tests and risks). It does
  not model dependencies between requirements.
- **The list endpoints are not paginated** (fine for tens of records, not thousands).
- **The status rules exist twice** (backend and `frontend/src/lib/transitions.ts`); the backend is the
  authority, and the frontend copy only hides impossible choices.
- **Tracing sends text to LangSmith** when enabled. Use dummy data or `LANGSMITH_HIDE_DATA=true`.
- **The router is keyword-based.** Any message that *looks* like a question (starts with "what",
  "show", ...) goes to the query agent, even an off-topic one. That is safe (with no database
  lookup the user gets the fixed "I can only answer from the database" reply) but it costs one
  model call. English only.

---

## 14. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The page says *"Cannot reach the backend"* | The backend is not running, or `VITE_API_URL` is wrong. Start it and check http://localhost:8000/health |
| A red banner mentions `alembic upgrade head` | Your database is older than the code. Run `cd backend ; alembic upgrade head` |
| *"The local AI (Ollama...) is not reachable"* | Ollama is not running or the model is missing: `ollama pull qwen2.5:3b`. Check `Invoke-RestMethod http://localhost:11434/api/tags` |
| The first answer takes a minute | Normal on a CPU while the model loads. Later answers are faster |
| `Address already in use` on port 8000 | Another backend is running (a local one *or* Docker). Stop one: `docker compose down` |
| `EPERM` during `npm ci` on Windows | `npm run dev` is still running and locks a file. Stop it first |
| PowerShell: *"`&&` is not a valid statement separator"* | Windows PowerShell 5 does not support `&&`; run the commands on separate lines or separate them with `;` |
| `GET /requirements/5` returns 404 | IDs look like `REQ-005` |
| Confirm says the requirement changed (409) | Someone changed it after the proposal. Propose it again |

---

## 15. Git workflow

- `main` holds finished, released work; `develop` is the integration branch. **Both are protected:**
  changes arrive only through pull requests, and the CI checks must pass.
- Work happens on short-lived branches (`feature/database`, `feature/agents`, `feature/frontend`,
  `feature/docker`, `feature/ci`, `docs/readme`, ...) and merges into `develop` by pull request.
- Commit messages follow a simple convention: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`,
  `chore: ...`, `test: ...`.
- The design lives in [`plan/PLAN.md`](plan/PLAN.md); the phase-by-phase build log, with what was
  verified at each step and the lessons learned, is in [`plan/GUIDE.md`](plan/GUIDE.md).
