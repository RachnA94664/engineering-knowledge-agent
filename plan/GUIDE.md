# Build Guide: Engineering Knowledge Agent

How to use this guide: work through the phases in order. Each phase has **mini steps**, a
**why** (the idea you are learning) and a **"done when"** checklist. A phase is complete
only when every box is ticked. Design reference: [PLAN.md](PLAN.md).

Status: ✅ done, 🔄 in progress, ⬜ not started.

| Phase | Topic | Status |
|---|---|---|
| 0 | Tools and accounts | ✅ |
| 1 | Repository, protection rules, Git workflow | ✅ |
| 2 | Python project and database | ⬜ replay as PR |
| 3 | Domain rules | ⬜ replay as PR |
| 4 | Repositories, services, audit log | ⬜ replay as PR |
| 5 | REST API | ⬜ replay as PR |
| 6 | LangGraph agents and `/chat` | 🔄 |
| 7 | LangSmith tracing | ⬜ |
| 8 | Automated impact workflow | ⬜ |
| 9 | Frontend | ⬜ |
| 10 | Docker | ⬜ |
| 11 | CI | ⬜ |
| 12 | Deployment | ⬜ |
| 13 | README and polish | ⬜ |
| 14 | Change-it-later cheat sheet | reference |

**Free hosting** (check current limits before you start, free tiers change):
frontend on Vercel/Netlify/Cloudflare Pages; backend (Docker) on Render. SQLite lives
inside the container and is wiped on restart, so the app re-seeds on startup. The OpenAI
API is **not free**: set a monthly spending limit (about $5) and keep keys only in
environment variables.

**Rules for the whole project**
1. Never commit `.env` or any key. If you ever do, rotate the key immediately.
2. Never push to `main` or `develop`: both are protected. Branch, commit, PR, merge.
3. Delete only *feature* branches after a merge. Never delete `develop`.
4. Check the PR's **base branch** says `develop` before merging.
5. Run the tests before every commit. Check `git status` before `git add`.
6. Work from `C:\dev\engineering-knowledge-agent` (outside OneDrive).

---

## Phase 0: Tools and accounts ✅

**Why:** a consistent setup removes most "works on my machine" problems.

Mini steps
- 0.1 Install Git, Python **3.12**, Node 20+, Docker Desktop (with WSL 2), and an editor.
- 0.2 Verify: `git --version`, `py -3.12 --version`, `node --version`, `docker run hello-world`.
- 0.3 `git config --global user.name "..."` and `user.email "..."`.
- 0.4 Accounts: GitHub, OpenAI (add a small balance, set a **monthly limit**, create a key),
  **LangSmith** (free, for tracing), Render, Vercel. Store keys privately, never in chat or git.

Done when
- [x] All version commands work and `hello-world` runs
- [x] OpenAI key created, spending limit set, key stored privately
- [x] LangSmith, Render and Vercel accounts exist
- [x] You can explain PATH and an environment variable

## Phase 1: Repository and Git workflow ✅

**Why:** professional work is traceable; protected branches and PRs are how teams review.

Mini steps
- 1.1 Create the repo and clone it into `C:\dev` (not OneDrive):
  `gh repo create <name> --public --add-readme` then `gh repo clone <name>`.
- 1.2 Create `develop`: `git checkout -b develop` then `git push -u origin develop`.
- 1.3 **Protect `main` and `develop`** with rulesets: pull request required, no force-push,
  no deletion, empty bypass list. Prove it: try a direct push; it must be rejected.
- 1.4 Skeleton PR: `.gitignore`, `.env.example`, README stub, seed data.
- 1.5 The loop you will repeat: `git checkout develop` → `git pull origin develop` →
  `git checkout -b feature/x` → edit → `git add <files>` → `git commit` →
  `git push -u origin feature/x` → PR into `develop` → merge → delete the feature branch.

Done when
- [x] `main` and `develop` reject direct pushes and cannot be deleted
- [x] Skeleton PR merged into `develop`
- [x] `git ls-files` shows `.env.example` but no `.env`

## Phase 2: Python project and database ⬜

**Why:** the database is the source of truth; the AI must read from it, never invent.

Mini steps
- 2.1 `py -3.12 -m venv .venv` inside `backend/`, activate it, install pinned dependencies
  (`requirements.txt` for runtime, `requirements-dev.txt` for tools).
- 2.2 Folder layout under `backend/app/`: `api agents services repositories domain db core`.
- 2.3 `core/config.py`: settings from environment variables (`pydantic-settings`).
- 2.4 `db/models.py`: six tables with primary keys, foreign keys, CHECK constraints, `version`.
- 2.5 `db/session.py`: engine; turn on `PRAGMA foreign_keys=ON` for every connection.
- 2.6 Alembic: initial migration; `alembic upgrade head` builds the schema from nothing.
- 2.7 `db/seed.py`: validate every row (format, enums, ranges, duplicates, missing
  references) before inserting; report and skip bad rows; safe to run twice.
- 2.8 Tests: valid seed loads 15/30/12/16; all 7 invalid rows rejected; constraints refuse
  orphans, bad ids, bad severity, and deleting a requirement that has test cases.

Done when
- [ ] `alembic upgrade head` builds the DB on a fresh clone
- [ ] Seed gives 15/30/12/16; the 7 invalid rows are rejected with reasons; re-running is safe
- [ ] Tests pass; PR merged into `develop`
- [ ] You can explain primary key, foreign key and migration

## Phase 3: Domain rules ⬜

**Why:** business rules in plain Python are easy to test and change.

Mini steps: `errors.py`, `ids.py` (fullmatch ID formats), `transitions.py` (status state
machine, no backward moves, obsolete is final), `risk.py` (score and level, thresholds in
one place), tests for every rule.

Done when
- [ ] Every rule has a passing and a failing test; the suite runs in milliseconds
- [ ] Thresholds live only in `risk.py`, transitions only in `transitions.py`
- [ ] PR merged. Try changing `HIGH_THRESHOLD` and watch the tests catch it

## Phase 4: Repositories, services, audit log ⬜

**Why:** separating "how to store" from "what to do" keeps the rules in one place.

Mini steps
- 4.1 Repositories: the only files with SQL.
- 4.2 `propose` → saves a *pending* change, applies nothing.
- 4.3 `confirm` → one transaction: version check (`UPDATE … WHERE version = base`), rule
  re-check, apply, bump version, audit row. Stale change ⇒ expires + conflict.
- 4.4 `reject`; both `confirm` and `reject` are idempotent.
- 4.5 Migration with triggers making `audit_log` append-only.
- 4.6 Integration tests (migrated temporary DB): success, invalid move, stale version,
  rollback on failure, audit cannot be edited.

Done when
- [ ] All the cases above are tested and green
- [ ] Agents will only touch `services`, never `repositories`
- [ ] PR merged; you can explain a transaction and optimistic locking

## Phase 5: REST API ⬜

**Why:** the frontend and agents talk to the backend through a contract.

Mini steps: FastAPI app, CORS, `/health`; request/response schemas (unknown fields
rejected); read endpoints; `POST /changes`, `/confirm`, `/reject`; one error shape with
404/409/422/503; no PUT/PATCH/DELETE on records; API tests; try everything on `/docs`.

Done when
- [ ] `/docs` lists every endpoint and each works
- [ ] Errors share one JSON shape; the audit `source` is set by the server
- [ ] PR merged

## Phase 6: LangGraph agents and `/chat` 🔄

**Why:** the AI part. The model chooses tools; **our code does the work and enforces the
rules**. LangGraph runs the graph; our safety code stays ours.

Mini steps
- 6.1 Add dependencies: `langgraph`, `langchain-core`, `langchain-openai`, `langsmith`.
- 6.2 **Tools:** wrap each service as a LangChain tool with validated arguments. Read
  tools for the Query agent; one `propose_requirement_change` for the Update agent. No
  confirm / reject / delete tool exists.
- 6.3 **State and graph:** messages + intent + evidence + answer + pending proposals.
  Nodes: `route`, `refuse`, `query_agent`, `query_tools`, `finalize_query`, `update_agent`,
  `update_tools`, `finalize_update`. Conditional edges choose the path.
- 6.4 **Router node:** rules first (delete/confirm ⇒ refused before any AI call); the AI
  classifies only unclear messages.
- 6.5 **Grounding node:** every `REQ/TC/RISK` id in an answer must appear in tool output;
  no tool call ⇒ no answer shown.
- 6.6 **Limits:** `recursion_limit`, per-step tool-call cap, model `timeout`,
  `max_retries`, `max_completion_tokens`, temperature 0; `GraphRecursionError` ⇒ friendly
  message.
- 6.7 **Model wrapper:** `ChatOpenAI` behind a small factory; missing key or provider
  outage ⇒ clean 503, never a leak.
- 6.8 **`POST /chat`** and a command-line tool (`python -m app.agents.cli "question"`).
- 6.9 **Tests with a scripted fake chat model** (it must support `bind_tools`): the five
  sample questions, unknown id ⇒ "not found", invented id blocked, loop limit,
  injection text not obeyed, delete refused without any AI call, least-privilege tool sets.
- 6.10 Live check with your real key (the five sample questions + three attempts to break it).

Done when
- [ ] All five sample questions answer correctly from the database with a real key
- [ ] The agent tests pass with the fake model and no key
- [ ] Unknown id ⇒ not found; delete refused; instruction-like record text not obeyed
- [ ] The Update agent only creates a pending proposal
- [ ] No key in code or git history; PR merged

## Phase 7: LangSmith tracing ⬜

**Why:** you cannot improve what you cannot see. Traces show every prompt, tool call,
token count and latency.

Mini steps: put `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` in
`backend/.env` and make sure they reach the process environment; tag each graph run with
its intent; run a few questions and read the traces; make tracing **optional** (off by
default) so it can never break a request; add a test that the app works with tracing off.

Done when
- [ ] With tracing on, a chat run appears in LangSmith with the tool calls inside it
- [ ] With tracing off or the key missing, everything still works
- [ ] You can find the prompt, the tool arguments and the token usage of one run

## Phase 8: Automated impact workflow ⬜

**Why:** shows a system acting on its own after an event.

Mini steps: `services/impact.py` (linked tests → `not_run`, linked risks flagged, impact
level); call it inside `confirm` in the same transaction; save the report and link it to
the audit entry; `GET /requirements/{id}/impact`; add an Analysis agent node that
summarises the stored report (the model never decides the impact); tests (REQ-009 affects
its 4 tests and RISK-003; confirming twice does nothing).

Done when
- [ ] Confirming a change produces a correct impact report, atomically with the audit row
- [ ] Re-confirming repeats nothing; the summary mentions only real ids

## Phase 9: Frontend ⬜

Mini steps: Vite + React + TypeScript; one `api/client.ts` using `VITE_API_URL`;
components: ChatPanel (answer, evidence table, tool trace), RequirementsTable,
PendingChanges (diff, confirm/reject), ImpactReport, AuditLog; loading, error and empty
states; manual test of the whole flow.

Done when
- [ ] Ask, view evidence, propose, confirm, see impact and audit: all in the browser
- [ ] `npm run build` succeeds; the API URL is not hard-coded

## Phase 10: Docker ⬜

Mini steps: backend Dockerfile (slim Python, pinned requirements, runs migrations and
seeds on start, binds `$PORT`); frontend multi-stage Dockerfile (build with Node, serve
with nginx); `.dockerignore` excludes `.env`; `docker-compose.yml`; `docker compose up
--build`.

Done when
- [ ] One command starts everything from scratch and the sample questions work
- [ ] No secrets baked into an image; you can read `docker logs`

## Phase 11: CI ⬜

Mini steps: `ruff check` and `ruff format --check`; GitHub Actions on every PR (Python
tests with no API key, frontend build); status badge in the README.

Done when
- [ ] A PR shows green checks; a deliberately broken test turns it red, then you fix it

## Phase 12: Deployment ⬜

Mini steps: Render web service (Docker, root `backend`, health check `/health`, env vars
`OPENAI_API_KEY`, `OPENAI_MODEL`, `ALLOWED_ORIGINS`, optional `LANGSMITH_*`); Vercel project
(root `frontend`, `VITE_API_URL`); set `ALLOWED_ORIGINS` to the Vercel URL; **add simple
rate limiting**, because a public URL can spend your OpenAI credit; spending limit set.

Done when
- [ ] The public site answers the five sample questions
- [ ] No CORS errors; keys only in host environment variables; `/health` is OK

## Phase 13: README and polish ⬜

Mini steps: README (what it does, architecture, database design, agent design, rules,
how to run locally and with Docker, example queries, limitations, decisions and why, live
URLs, screenshots); release PR `develop` → `main` (do not delete `develop`); tag `v1.0`;
5-minute demo script.

Done when
- [ ] A stranger can run it from the README alone
- [ ] The Definition of Done in PLAN.md is fully ticked

## Phase 14: Change-it-later cheat sheet

| I want to… | Change this | Then |
|---|---|---|
| Add a status or priority | `domain/enums.py` + DB CHECK | new migration, update tests |
| Change allowed status moves | `domain/transitions.py` | update tests |
| Change risk thresholds | `domain/risk.py` | update tests |
| Add a field to requirements | `db/models.py`, schemas, repo, UI | migration, seed |
| Give an agent a new ability | new tool in `agents/tools.py`, add to that agent's tool set | add a test |
| Change how an agent talks | `agents/prompts/*.md` | run agent tests |
| Add a new agent | new nodes + edge in `agents/graph.py`, new tool set | add a test |
| Use a different model | `OPENAI_MODEL` | nothing else |
| Turn tracing on/off | `LANGSMITH_TRACING` | nothing else |
| Add an endpoint | `api/`, `services/`, `repositories/`, schema | API test |
| Change the dummy data | `backend/data/gen_seed.py` | rerun seed |
| Move to Postgres | `DATABASE_URL`, driver | rerun migrations |

Loop for every change: **branch, change, test, commit, PR, merge, deploy.**

## Where things usually go wrong

- **`git push` rejected:** you pushed `main` or `develop`. Push a feature branch and open a PR.
- **`git push develop` fails:** wrong syntax; it is `git push origin <branch>`.
- **"No module named pytest":** you used the global Python; use the venv (`.venv\Scripts\python.exe`).
- **A branch vanished after merge:** you deleted `develop`; never tick "delete branch" on a release PR.
- **Merge button missing:** you are not signed in to GitHub in that browser.
- **PR base is `main`:** GitHub's yellow banner defaults to it. Change base to `develop`.
- **Docker "daemon not running":** start Docker Desktop and wait for "Engine running".
- **CORS error:** `ALLOWED_ORIGINS` must contain the frontend URL exactly (no trailing slash).
- **Agent invents things:** the grounding check must run and the prompt must say "tool results only".
- **LangSmith shows nothing:** the variables must be in the process environment, not only in a file.
- **Key leaked:** revoke it immediately, then remove it from git history.
