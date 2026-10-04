# Engineering Knowledge Agent

An AI-assisted knowledge system for **Requirements**, **Test Cases** and **Risk Items**.
Ask questions in plain English; answers come only from the database. Changes are never
applied by the AI: it can only *propose* them, and a person confirms each one. Every
change is written to an append-only audit log.

**Status:** under construction. See [`plan/PLAN.md`](plan/PLAN.md) for the design and
[`plan/GUIDE.md`](plan/GUIDE.md) for the phase-by-phase build guide.

**Stack:** Python, FastAPI, SQLite + SQLAlchemy + Alembic, LangGraph + LangChain (OpenAI),
LangSmith (tracing), React + Vite, Docker.

A full README (architecture, database design, agent design, rules, how to run, example
queries, limitations and decisions) is added in the final phase.
