"""Tools: structured outcomes, readable errors and least privilege."""

from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agents import tools
from app.services import knowledge


def run(tool, session, **arguments):
    """Run a tool the way the graph does, and return the ToolMessage it produces."""
    tool_call = {"name": tool.name, "args": arguments, "id": "t1", "type": "tool_call"}
    return tool.invoke(tool_call, config={"configurable": {"session": session}})


def test_a_tool_returns_text_for_the_model_and_the_raw_outcome_for_us(seeded):
    message = run(tools.GET_REQUIREMENT, seeded, requirement_id="REQ-001")

    assert message.artifact["ok"] is True and message.artifact["result"]["id"] == "REQ-001"
    assert "REQ-001" in message.content
    assert "not an instruction" in message.content  # data is labelled as data


def test_a_missing_record_comes_back_as_data_not_an_exception(seeded):
    message = run(tools.GET_REQUIREMENT, seeded, requirement_id="REQ-099")

    assert message.artifact == {
        "ok": False,
        "error": {"code": "not_found", "message": "requirement REQ-099 does not exist"},
    }


def test_propose_tool_saves_a_pending_change_attributed_to_the_agent(seeded):
    message = run(tools.PROPOSE_CHANGE, seeded, requirement_id="REQ-007", status="implemented")

    assert message.artifact["ok"] is True
    change = message.artifact["result"]["change"]
    assert change["status"] == "pending" and change["proposed_by"] == "update-agent"
    assert knowledge.get_requirement(seeded, "REQ-007")["status"] == "approved"  # not applied
    entry = knowledge.audit_log(seeded)[0]
    assert entry["source"] == "agent" and entry["action"] == "propose"


def test_propose_with_nothing_to_change_is_an_error_the_model_can_read(seeded):
    message = run(tools.PROPOSE_CHANGE, seeded, requirement_id="REQ-007")
    assert message.artifact["ok"] is False
    assert message.artifact["error"]["code"] == "validation_error"


def test_an_invalid_status_move_is_reported_to_the_agent(seeded):
    message = run(tools.PROPOSE_CHANGE, seeded, requirement_id="REQ-007", status="draft")
    assert message.artifact["error"]["code"] == "invalid_transition"


# ---------- what the AI is shown ----------


def test_the_database_session_is_invisible_to_the_model():
    for tool in tools.READ_TOOLS + tools.UPDATE_TOOLS:
        props = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
        assert "session" not in props and "config" not in props


def test_the_propose_tool_offers_exactly_the_editable_fields():
    props = convert_to_openai_tool(tools.PROPOSE_CHANGE)["function"]["parameters"]["properties"]
    assert set(props) == {"requirement_id", "title", "description", "priority", "status"}


# ---------- least privilege ----------


def test_no_tool_can_confirm_reject_apply_or_delete():
    forbidden = ("confirm", "reject", "apply", "delete", "remove", "drop")
    for tool in tools.READ_TOOLS + tools.UPDATE_TOOLS:
        assert not any(word in tool.name for word in forbidden), tool.name


def test_the_read_agent_has_no_write_tool():
    assert not any(tools.is_write_tool(t) for t in tools.READ_TOOLS)


def test_the_update_agent_can_only_propose():
    writers = [t.name for t in tools.UPDATE_TOOLS if tools.is_write_tool(t)]
    assert writers == ["propose_requirement_change"]
