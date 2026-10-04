"""Fixed answers written by code (never by the AI) for situations where we must not guess."""

NO_DATA_ANSWER = (
    "I can only answer from the database, and I did not look anything up for that. "
    "Try: 'Show me REQ-001', 'Which test cases belong to REQ-001?', "
    "'Show me high-risk items' or 'Which requirements have no test cases?'"
)
UNVERIFIED_ANSWER = (
    "I could not verify my answer against the database, so I am not showing it. "
    "The records I did find are listed below."
)
TOO_MANY_STEPS_ANSWER = "I could not finish looking that up. Please try a simpler question."
NEEDS_DETAILS_ANSWER = (
    "I need a requirement id and the new value. For example: "
    "'Set REQ-007 status to implemented' or 'Change the priority of REQ-003 to high'."
)
OUT_OF_SCOPE_ANSWER = (
    "I can only help with the requirements, test cases and risk items in this database. "
    "Try: 'Show me REQ-001', 'Which requirements have no test cases?' or "
    "'Set REQ-007 status to implemented'."
)
TOO_MANY_STEPS_UPDATE_ANSWER = (
    "I could not finish preparing that change. Please try a simpler request."
)
UPDATE_NOT_UNDERSTOOD_ANSWER = (
    "I could not turn that into a valid change. Try: 'Set REQ-007 status to implemented' "
    "or 'Change the priority of REQ-003 to high'."
)
