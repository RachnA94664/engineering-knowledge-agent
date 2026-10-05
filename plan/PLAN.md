# Engineering Knowledge Agent: Implementation Plan

An AI-assisted knowledge system for **Requirements**, **Test Cases** and **Risk Items**.
Users ask questions in plain English and get answers only from the database. Agents can
**propose** changes, never apply them: a person confirms each change, and every change is
written to an append-only audit log.

Status legend: ✅ done, 🔄 in progress, ⬜ not started.

## 1. Stack and why

| Layer | Choice | Why | Alternatives |
|---|---|---|---|
| Language | Python 3.12 | Best LLM ecosystem; readable | Node/TypeScript, Java |
| API | FastAPI + Pydantic v2 | Validation from type hints; auto `/docs` | Flask, Django |
| Database | SQLite + SQLAlchemy 2 + Alembic | Zero setup; real constraints; versioned migrations | PostgreSQL (production), MySQL |
| Agent orchestration | **LangGraph** | Our flow *is* a graph: router, agents, tools, checks. Built-in loop limits, conditional edges, tracing | Plain code, full LangChain agents, CrewAI |
| LLM and tools | **langchain-core**, with **langchain-openai** or **langchain-ollama** | Standard chat-model and tool interfaces. The AI is chosen by one setting (`LLM_PROVIDER`): OpenAI (paid API) or Ollama (a free model on your own PC, no key) | OpenAI SDK directly, Anthropic, Groq, Gemini |
| Tracing and evals | **LangSmith** | Switched on with environment variables; shows every prompt, tool call, token and latency | Langfuse (open source), none |
| Frontend | React + Vite + TypeScript | Common, typed | Vue, Svelte |
| Tests | pytest, httpx, a fake chat model | Fast, no key, deterministic | unittest |
| Quality | ruff, GitHub Actions | One fast tool; free CI | flake8 + black |
| Packaging | Docker + docker-compose | Same container locally and in the cloud | none |
| Hosting (free) | Vercel (frontend), Render (backend Docker) | Free tiers; deploy from GitHub | Netlify, Koyeb, Hugging Face Spaces |

**What LangGraph does and does not replace.** LangGraph replaces our hand-written loop and
routing plumbing. It does **not** replace the safety design, which stays our own code:
the grounding check, the tool allow-lists, rule-based refusals, the services layer as the
only path to the database, and propose-then-confirm. Frameworks orchestrate; our rules guard.

## 2. Architecture (layers; dependencies point inward)

```
React UI ──HTTP──► FastAPI routers ──► LangGraph agent graph ──► Tools ──► Services ──► Domain rules
                        │                     │                                │
                        │                  OpenAI                       Repositories ──► SQLite
                        └───────────────► Services (reads/changes) ────────────┘
                                              LangSmith traces every graph run
```

- **Domain** (`domain/`): pure Python: enums, ID rules, status state machine, risk scoring.
- **Repositories** (`repositories/`): all SQL.
- **Services** (`services/`): use cases, transactions, audit writes, impact analysis.
- **Agents** (`agents/`): the LangGraph graph. Tools are thin adapters over **services**.
  Agents never import repositories or the database.
- **API** (`api/`): HTTP only; maps domain errors to 404 / 409 / 422 / 503.

```
backend/app/{api,agents,services,repositories,domain,db,core}/
backend/migrations/  backend/data/  backend/tests/{unit,integration,agents}/
frontend/src/{api,components,pages}/        plan/        .github/workflows/
```

## 3. Database design ✅

Tables: `requirements`, `test_cases`, `risk_items`, `requirement_risks` (many-to-many),
`audit_log`, `pending_changes`, `impact_reports`.

- IDs are `REQ-###`, `TC-###`, `RISK-###` (CHECK constraints plus domain validation).
- Foreign keys on, `ON DELETE RESTRICT`; `PRAGMA foreign_keys=ON` on every connection.
- `requirements.version` for optimistic locking.
- Risk **score and level are derived in code** (severity × likelihood; ≥15 high, 8–14 medium,
  below 8 low), never stored, so they cannot drift.
- `audit_log` is **append-only**, enforced by database triggers.
- `pending_changes` holds proposals awaiting a human decision.
- `impact_reports` holds one report per applied change (`change_id` is UNIQUE, so confirming
  twice cannot make a second one). `risk_items.needs_review` is the flag a person clears.
- Every timestamp is stored and returned as UTC with its timezone (SQLite drops it, so a
  custom column type puts it back; naive datetimes are refused).
- Seed data is validated by the same rules before insertion; bad rows are reported and skipped.

## 4. Rules and guardrails ✅

| Layer | Rules |
|---|---|
| Database | Unique primary keys, foreign keys, CHECKs, NOT NULL, append-only audit triggers |
| Domain | ID formats; status machine draft → approved → implemented → verified, any → obsolete, obsolete final; derived risk level |
| Service | Referenced records must exist; version must match; confirm/reject are idempotent; audit row in the same transaction; rollback on failure |
| API | No PUT/PATCH/DELETE on records; unknown fields rejected; audit `source` set by the server |
| Agent | Read/propose only; no confirm/reject/delete tool exists; grounding check; step and token limits; rule-based refusals before any AI call |
| Seed | Every row validated; bad rows reported and skipped |

## 5. Agent architecture (LangGraph) ✅ (analysis lane arrives with the impact workflow)

One compiled graph, one run per chat message. State carries the messages plus the intent,
the evidence (raw tool output), the final answer and any pending proposals.

```
START ─► route ─┬─► refuse ─────────────────────────────────────────────► END
                ├─► query_agent ◄─► query_tools ─► finalize_query ──────────► END
                ├─► update_prepare ─► update_tools ─► finalize_update ───────► END   (simple command: rules)
                │        └─► update_agent ◄─► update_tools ─► finalize_update   (unusual wording: AI)
                └─► analysis_agent ◄─► analysis_tools ─► finalize_analysis ─► END
```

| Node | Job |
|---|---|
| `route` | Rules first (free, predictable); a small AI classification only for unclear messages |
| `refuse` | Delete/remove, confirm/reject-by-chat, off-topic: answered by code, no AI call |
| `update_prepare` | Reads simple change commands ("Set REQ-006 priority to high", "Mark REQ-002 as obsolete") with plain rules and builds the proposal directly: instant, free and exact. Anything unusual goes to the AI. The result is still only a *proposal* through the same tool and checks |
| `*_agent` | The chat model, bound to **only that agent's tools** |
| `*_tools` | LangGraph `ToolNode` running our tools (each tool wraps a service) |
| `finalize_query` | Grounding check: every `REQ/TC/RISK` id in the answer must appear in tool output, else the answer is blocked and only the real records are shown. No tool call ⇒ no answer |
| `analysis_prepare` | "What is the impact of REQ-009?" names one requirement: the stored report is read directly (no AI). Several requirements or unusual wording go to the analysis agent |
| `finalize_analysis` | Rules path: the answer is the report's own summary sentence, so nothing can be invented. AI path: the same grounding check as a query |
| `finalize_update` | Reply written **by code** from the proposal result, so it can never claim a change was applied |
| `finalize_analysis` | Impact summary from the deterministic impact report |

**Tool sets (least privilege)**

| Agent | Tools | Can write? |
|---|---|---|
| Query | get_requirement, list_requirements, get_test_cases_for_requirement, list_risks, list_requirements_without_tests, get_audit_log | No |
| Update | get_requirement, propose_requirement_change | Only creates a pending proposal |
| Analysis | get_requirement, get_impact | No |

**Limits (in code, not in prompts):** `recursion_limit` on every graph run (a
`GraphRecursionError` becomes a friendly message); at most 4 tool calls per step; model
`timeout`, `max_retries` and `max_completion_tokens`; temperature 0; message length cap.

**Rules first, AI second.** A 3B local model sometimes called the propose tool with wrong
argument names (found while testing `/docs`). Simple commands are therefore read by rules
(`agents/update_parser.py`); when the AI's call is rejected anyway, the user sees one friendly
sentence, never the framework's error text.

**Two lessons from building it** (both now covered by tests):
- LangGraph runs the several tool calls of one AI message in *parallel threads*, but a
  database session is not thread-safe. The tools therefore take turns using it via a lock
  passed in the run config.
- Only tool results that really ran our code count as evidence. A call the framework
  rejects (bad arguments, unknown tool) never touched the database, so it cannot make an
  answer pass the grounding check.

**Prompt-injection defence:** database text returns to the model labelled as data; each
agent can only call its own tools; nothing the model says can confirm or delete.

**Human approval** is handled by our `pending_changes` table and the confirm/reject API,
not by LangGraph interrupts. This keeps approval durable across restarts and visible in
the UI, without needing a graph checkpointer.

**Choosing the AI:** `LLM_PROVIDER=openai|ollama`. The model is created in one file
(`agents/llm.py`) and everything else receives a factory, so the agents do not know which
AI they use. Provider failures (network, rate limit, billing, a stopped local server, an
unknown model) all become one safe "service unavailable" answer; a local provider adds a
helpful hint ("is Ollama running?"). Local models on a CPU are slow (long timeout) and less
reliable at calling tools, but every safety check still applies to whatever they produce.

**Tracing (LangSmith, optional, off by default):** a dashboard of every chat message: the
router's decision, each tool call and its arguments, the prompts sent to the AI, timings and
errors. Design (`core/tracing.py`):
- **Two things are required to turn it on**: `LANGSMITH_TRACING=true` and a real key (the
  placeholder from `.env.example` does not count).
- **We build the tracer and pass it to each run**, instead of switching LangSmith on through
  environment variables. So the timeouts (2 s connect, 5 s read) and the retry limit (one) are
  ours, the privacy switch is an argument, the API key never enters the process environment,
  and nothing is cached per process. Every implicit switch (`LANGSMITH_TRACING`,
  `LANGCHAIN_TRACING_V2`) is forced off so nothing else can trace.
- **Never breaks or slows a request:** a dead or rejecting LangSmith is tested; the chat is not
  held up. Honest cost: when the endpoint is dead, start-up waits a few seconds (the tracer's
  handshake, capped by the short timeout).
- **Privacy:** traces contain the text of questions and records. `LANGSMITH_HIDE_DATA=true`
  sends only the structure and timings. The test suite is forced offline in `conftest.py`.
- Each trace's root run is tagged `intent:<intent>` with metadata `routed_by: rules|ai`.

## 6. Automated workflow: impact analysis ✅

When a change is **confirmed**, the system analyses what it affected, in the same all-or-nothing
transaction as the change (`services/changes.py` calls `services/impact.py`). The rules are in
one pure file, `domain/impact.py`:

| Change | Test cases | Linked risks |
|---|---|---|
| description edited | passing tests reset to `not_run` | flagged for review |
| priority raised | unchanged | flagged for review |
| status becomes obsolete | unchanged (note: may be retired) | flagged for review |
| status becomes verified | unchanged | warning if tests are not all passing (or there are none) |
| title edited, priority lowered, other status moves | unchanged | nothing |

Closed risks are never flagged. A failing test is reported but never "improved" to `not_run`.

**Impact level:** *low* if nothing is affected; *high* if something is affected and (the
requirement is critical or its description changed); otherwise *medium*.

**Records everything:** a stored `impact_report` (with a plain summary sentence), and one audit
row for every automatic modification (each test reset, each risk flag, the report), attributed
to `impact-analysis` with source `system` and `caused_by_change`, so it is traceable.

**Safe by design:** atomic (a failure anywhere undoes the whole confirm, including the change);
idempotent (confirming twice returns the same report and resets nothing again); a rejected or
stale change creates no report. A person clears a risk's flag with `POST /risks/{id}/reviewed`.

**Analysis agent:** rules read the stored report; the AI never decides the impact. The answer
says "Latest confirmed change to REQ-009 (change #N)", because a report describes the last
confirmed change and cannot predict a hypothetical one.

## 7. Write flow ✅

1. **Propose** (UI or agent): validated, saved as `pending`, nothing applied.
2. **Confirm** (person): one transaction: version check, rule re-check, apply, bump version,
   impact analysis, audit row. A stale proposal expires with a conflict.
3. **Reject**: closes the proposal. Both are idempotent.

## 8. API ✅

`GET /health`, `/requirements`, `/requirements/{id}`, `/requirements/without-tests`,
`/requirements/{id}/test-cases`, `/requirements/{id}/impact`, `/risks?level=&needs_review=`,
`/audit-log`, `/changes`; `POST /changes`, `/changes/{id}/confirm`, `/changes/{id}/reject`,
`/risks/{id}/reviewed`, `/chat`.
One error shape: `{"error": {"code", "message", "details"}}`.

## 9. Frontend ⬜

Chat (answer, evidence table, tool trace), Browse, Pending changes (diff, confirm/reject),
Impact report, Audit log. Loading, error and empty states everywhere.

## 10. Testing

- **Unit:** domain rules, router rules, grounding check (milliseconds).
- **Integration:** services, API (temporary migrated SQLite), tools.
- **Agent graph:** a scripted **fake chat model** (LangChain's built-in fakes cannot bind
  tools, so we use our own) drives the real graph: the five sample questions, grounding
  blocks, limits, injection, least privilege. No key, no network, no cost.
- **Live checks:** run manually with a real key; optional LangSmith dataset for evals.

## 11. Git workflow (fresh repository)

- `main` and `develop` are both **protected**: pull request required, no force-push, no
  deletion. All work happens on `feature/*`, `chore/*`, `docs/*` branches.
- Feature branch → PR into `develop` → merge → delete only the feature branch.
  `develop` → `main` by a release PR (do **not** delete `develop`).
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- CI on every PR: ruff, pytest (no API key needed), frontend build.
- The history was rebuilt as clean PRs from the first version of this project.

## 12. Milestones

| # | Branch | Deliverable | Status |
|---|---|---|---|
| 0 | `chore/skeleton` | Repo, protection rules, gitignore, env example, seed data | ✅ |
| 1 | `feature/database` | Models, Alembic, validating seed loader | ✅ |
| 2 | `feature/domain-rules` | IDs, state machine, risk scoring | ✅ |
| 3 | `feature/services-audit` | Repositories, propose/confirm/reject, audit log | ✅ |
| 4 | `feature/api` | FastAPI app, errors, tests (+ docstrings PR) | ✅ |
| 5 | `feature/langgraph-agents` | LangGraph graph, tools, grounding, `/chat`, fake-model tests, Ollama | ✅ |
| 5b | `fix/update-agent-reliability` | Rules-first simple updates, friendly errors | ✅ |
| 6 | `feature/langsmith-tracing` | LangSmith tracing (optional, off by default) | ✅ |
| 7 | `feature/impact-workflow` | Impact analysis, report, review flag, analysis lane, UTC timestamps | ✅ |
| 8 | `feature/frontend` | React UI | ⬜ |
| 9 | `feature/docker` | Dockerfiles, compose | ⬜ |
| 10 | `feature/ci` | GitHub Actions | ⬜ |
| 11 | `feature/deploy` | Render + Vercel, rate limiting | ⬜ |
| 12 | `docs/readme` | README, screenshots, decisions | ⬜ |

## 13. Failure modes

| Failure | Handling |
|---|---|
| AI down / no key / timeout | Retries with backoff, then a clean 503; rule-based refusals still work; browse endpoints unaffected |
| AI invents an id | Grounding check blocks it; real records still shown |
| Invalid tool arguments | Validated before running; the error is returned to the model as data |
| Runaway tool loop | `recursion_limit` and per-step call cap |
| Concurrent edit | Version mismatch ⇒ 409; the stale proposal expires |
| Partial write | Single transaction with rollback |
| Prompt injection in records | Data labelled as data; least-privilege tools; tested |
| Bad seed data | Validator rejects and reports |
| Tracing outage | Tracing is optional and must never break a request |

## 14. Definition of done

- [ ] Application runs from the README on a clean machine
- [ ] Schema, migrations and seed data (valid plus rejected examples)
- [ ] Multi-agent LangGraph system answering the five sample queries from data only
- [ ] Rules enforced and tested; every change in the audit log
- [ ] Impact workflow demonstrable from the UI
- [ ] CI green; deployed frontend and backend
- [ ] README: what, architecture, database, agents, rules, run steps, example queries,
      limitations, decisions and why

## 15. Known limitations

No authentication (actor names are free text); SQLite on free hosts resets on restart
(data is re-seeded); free hosts sleep when idle; the OpenAI API is not free (Ollama is, but slow on a CPU); no chat
history across messages; no rate limiting until deployment.
