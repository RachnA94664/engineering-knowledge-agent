"""Ask the agents a question from the terminal.

Uses whichever AI ``LLM_PROVIDER`` selects (Groq, Ollama or OpenAI, with the keys from
``backend/.env``)::

    python -m app.agents.cli "Which requirements have no test cases?"
"""

import sys

from app.agents.llm import build_model_provider
from app.agents.runtime import AgentRuntime
from app.core.tracing import build_tracer, configure_tracing
from app.db.session import SessionLocal


def main() -> None:
    """Run one question through the agents and print the answer, tools used and records.

    The question is taken from the command-line arguments.

    Raises:
        SystemExit: With status 2 (after printing a usage message) when no question is given.
    """
    if len(sys.argv) < 2:
        print('usage: python -m app.agents.cli "your question"')
        raise SystemExit(2)
    message = " ".join(sys.argv[1:])
    configure_tracing()

    tracer = build_tracer()
    runtime = AgentRuntime(build_model_provider(), tracer=tracer)
    with SessionLocal() as session:
        result = runtime.run(session, message)
    if tracer is not None:
        tracer.client.flush()  # send the trace before this short-lived process exits

    print(f"\nANSWER ({result.intent}, grounded={result.grounded}):\n  {result.answer}\n")
    if result.tool_calls:
        print("TOOLS USED:")
        for call in result.tool_calls:
            status = "ok" if call["ok"] else f"error: {call['error']}"
            print(f"  - {call['name']}({call['arguments']}) -> {status}")
    if result.records:
        print("\nRECORDS:")
        for record in result.records:
            print(f"  - {record.get('id')}: {record.get('title', record.get('status', ''))}")
    for proposal in result.pending_changes:
        print(f"\nPENDING CHANGE #{proposal['change']['id']}: {proposal['preview']}")


if __name__ == "__main__":
    main()
