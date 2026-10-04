"""Ask the agents a question from the terminal (uses your OPENAI_API_KEY from .env).

python -m app.agents.cli "Which requirements have no test cases?"
"""

import sys

from app.agents.llm import build_model_provider
from app.agents.runtime import AgentRuntime
from app.db.session import SessionLocal


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m app.agents.cli "your question"')
        raise SystemExit(2)
    message = " ".join(sys.argv[1:])

    runtime = AgentRuntime(build_model_provider())
    with SessionLocal() as session:
        result = runtime.run(session, message)

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
