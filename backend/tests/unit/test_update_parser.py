import pytest

from app.agents.events import clean_framework_error
from app.agents.update_parser import parse_simple_update


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Set REQ-006 priority to high", {"requirement_id": "REQ-006", "priority": "high"}),
        ("Set REQ-006 priority to high.", {"requirement_id": "REQ-006", "priority": "high"}),
        ("set req-006 PRIORITY to HIGH", {"requirement_id": "REQ-006", "priority": "high"}),
        ("please set REQ-006 priority to low!", {"requirement_id": "REQ-006", "priority": "low"}),
        (
            "Set REQ-007 status to implemented",
            {"requirement_id": "REQ-007", "status": "implemented"},
        ),
        (
            "Set REQ-007's status to verified",
            {"requirement_id": "REQ-007", "status": "verified"},
        ),
        (
            "Change the priority of REQ-003 to medium",
            {"requirement_id": "REQ-003", "priority": "medium"},
        ),
        (
            "Update the status of REQ-007 to implemented.",
            {"requirement_id": "REQ-007", "status": "implemented"},
        ),
        ("Mark REQ-002 as obsolete", {"requirement_id": "REQ-002", "status": "obsolete"}),
        ("mark REQ-013 as approved", {"requirement_id": "REQ-013", "status": "approved"}),
    ],
)
def test_simple_commands_are_read_exactly(message, expected):
    assert parse_simple_update(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "Update REQ-007",  # no value
        "Update the status of REQ-001.",  # no value
        "Set REQ-007 status to banana",  # not a valid value: the normal path explains
        "Set REQ-006 priority to urgent",
        "Set REQ-006 priority to high and REQ-007 status to verified",  # several changes
        "Change the title of REQ-001 to Something new",  # free text is left to the AI
        "Please move REQ-007 on to the implemented status",  # unusual wording
        "Show me REQ-001",
        "Delete REQ-001",
        "REQ-001 priority high",
        "",
    ],
)
def test_anything_not_exact_is_left_to_the_ai(message):
    assert parse_simple_update(message) is None


def test_the_parsed_arguments_never_contain_extra_fields():
    args = parse_simple_update("Set REQ-006 priority to high")
    assert set(args) == {"requirement_id", "priority"}


# ---------- cleaning the framework's rejection text ----------

REAL_REJECTION = (
    "Error: ToolInvocationError(\"Error invoking tool 'propose_requirement_change' with kwargs "
    "{'new_priority': 'high', 'requirement_id': 'REQ-006'} with error:\n new_priority: Extra "
    'inputs are not permitted\n Please fix the error and try again.")\n Please fix your mistakes.'
)


def test_a_real_framework_rejection_is_reduced_to_the_useful_part():
    assert clean_framework_error(REAL_REJECTION) == "new_priority: Extra inputs are not permitted"


def test_the_rejection_text_as_it_really_arrives_with_escaped_line_breaks():
    # Copied from a real run: the line breaks are the two characters backslash + n.
    real = (
        "Error: ToolInvocationError(\"Error invoking tool 'propose_requirement_change' with "
        "kwargs {'new_priority': 'high', 'requirement_id': 'REQ-006'} with error:\\n "
        'new_priority: Extra inputs are not permitted\\n Please fix the error and try again.")\\n '
        "Please fix your mistakes."
    )
    assert "\\n" in real and "\n" not in real
    assert clean_framework_error(real) == "new_priority: Extra inputs are not permitted"


def test_an_unknown_tool_rejection_is_reduced_too():
    text = "Error: delete_everything is not a valid tool, try one of [get_requirement]."
    assert clean_framework_error(text) == "delete_everything is not a valid tool"


def test_unrecognised_text_is_shortened_not_dumped():
    assert len(clean_framework_error("x " * 500)) <= 200
