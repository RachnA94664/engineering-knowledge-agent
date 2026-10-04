"""The analysis lane: explaining what a confirmed change affected, from the stored report."""

from app.agents import answers
from app.services import changes, knowledge
from tests.agents.fakes import calls, runtime_with, say

NEW_TEXT = "Energy measurement shall be accurate to within 0.5 percent of the delivered kWh."


def confirm(session, req_id, patch):
    pid = changes.propose_requirement_change(session, req_id, patch, proposed_by="rachna")[
        "change"
    ]["id"]
    return changes.confirm_change(session, pid, actor="rachna")


# ---------- the common questions need no AI at all ----------


def test_the_impact_question_is_answered_from_the_stored_report_without_the_ai(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    runtime, model = runtime_with()  # an empty script fails the test if the AI is called

    result = runtime.run(seeded, "What is the impact of REQ-009?")

    assert model.calls == []
    assert result.intent == "analysis" and result.grounded and not result.refused
    assert result.answer.startswith("Latest confirmed change to REQ-009 (change #")
    assert "3 passing test cases reset to not_run (TC-019, TC-020, TC-030)" in result.answer
    assert "1 risk flagged for review (RISK-003)" in result.answer
    assert result.answer.endswith("Impact level: high.")
    assert result.records[0]["level"] == "high"
    assert [c["name"] for c in result.tool_calls] == ["get_impact"]


def test_the_wording_may_vary(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    for question in (
        "Which tests are affected by REQ-009?",
        "how did the change to REQ-009 affect things",
        "Show the impact on req-009",
    ):
        runtime, model = runtime_with()
        result = runtime.run(seeded, question)
        assert model.calls == [] and result.intent == "analysis" and "REQ-009" in result.answer


def test_before_any_confirmed_change_it_says_so_and_invents_nothing(seeded):
    runtime, model = runtime_with()
    result = runtime.run(seeded, "What is the impact of REQ-009?")

    assert model.calls == []
    assert "no impact report exists for REQ-009 yet" in result.answer
    assert result.records == [] and result.grounded is True


def test_an_unknown_requirement_is_reported_as_not_found(seeded):
    runtime, _ = runtime_with()
    result = runtime.run(seeded, "What is the impact of REQ-099?")
    assert result.answer == "requirement REQ-099 does not exist."


def test_only_the_latest_change_is_described(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    confirm(seeded, "REQ-009", {"priority": "medium"})  # lowered: nothing affected
    runtime, _ = runtime_with()

    result = runtime.run(seeded, "What is the impact of REQ-009?")

    assert "priority changed" in result.answer and "Impact level: low." in result.answer


def test_the_report_text_matches_what_the_workflow_stored(seeded):
    stored = confirm(seeded, "REQ-004", {"status": "verified"})["impact"]
    runtime, _ = runtime_with()

    result = runtime.run(seeded, "What is the impact of REQ-004?")

    assert stored["summary"] in result.answer  # the exact sentence, not a paraphrase
    assert "TC-008" in result.answer


# ---------- unusual questions use the AI, with the same safety checks ----------


def test_a_question_about_two_requirements_goes_to_the_ai_and_is_grounded(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    confirm(seeded, "REQ-004", {"status": "verified"})
    runtime, model = runtime_with(
        calls(
            ("get_impact", {"requirement_id": "REQ-009"}),
            ("get_impact", {"requirement_id": "REQ-004"}),
        ),
        say("REQ-009 had a high impact; REQ-004 had a medium impact."),
    )

    result = runtime.run(seeded, "Compare the impact on REQ-009 and REQ-004")

    assert len(model.calls) == 2  # the AI really was used
    assert result.grounded and len(result.records) == 2
    assert model.calls[0]["tools"] == ["get_requirement", "get_impact"]  # reading tools only


def test_an_ai_answer_that_cites_an_id_not_in_the_report_is_blocked(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    runtime, _ = runtime_with(
        calls(("get_impact", {"requirement_id": "REQ-009"})),
        say("REQ-009 reset TC-019 and also broke TC-099."),  # TC-099 does not exist
    )

    result = runtime.run(seeded, "Compare the impact on REQ-009 and REQ-004")

    assert result.answer == answers.UNVERIFIED_ANSWER and result.grounded is False


def test_the_analysis_agent_cannot_write(seeded):
    runtime, model = runtime_with(say("Which requirement?"))
    runtime.run(seeded, "Compare the impact on REQ-009 and REQ-004")

    offered = model.calls[0]["tools"]
    assert "propose_requirement_change" not in offered and offered == [
        "get_requirement",
        "get_impact",
    ]


def test_an_impact_question_without_a_requirement_is_an_ordinary_question(seeded):
    runtime, model = runtime_with(say("Which requirement do you mean?"))
    result = runtime.run(seeded, "What is the impact?")

    assert result.intent == "query"  # no requirement named: nothing to look up
    assert len(model.calls) == 1  # the ordinary query agent asked the AI once
    assert result.answer == answers.NO_DATA_ANSWER  # and no lookup means no answer is shown


# ---------- the whole story through the chat ----------


def test_propose_by_chat_confirm_by_a_person_then_ask_about_the_impact(seeded):
    runtime, model = runtime_with()  # all three steps are simple: no AI needed
    proposal = runtime.run(seeded, "Set REQ-006 priority to high")
    change_id = proposal.pending_changes[0]["change"]["id"]
    assert knowledge.get_requirement(seeded, "REQ-006")["priority"] == "medium"  # not applied

    changes.confirm_change(seeded, change_id, actor="rachna")  # a person, not the chat
    answer = runtime.run(seeded, "What is the impact of REQ-006?")

    assert model.calls == []
    assert "REQ-006: priority changed." in answer.answer
    assert "1 risk flagged for review (RISK-011)" in answer.answer
    assert "Impact level: medium." in answer.answer


# ---------- "which risks need review?" ----------


def test_the_risk_review_list_comes_from_the_flags(seeded):
    assert knowledge.list_risks(seeded, needs_review=True) == []
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})

    assert [r["id"] for r in knowledge.list_risks(seeded, needs_review=True)] == ["RISK-003"]
    assert "RISK-003" not in [r["id"] for r in knowledge.list_risks(seeded, needs_review=False)]
    assert knowledge.list_risks(seeded, level="high", needs_review=True) == []  # RISK-003 is medium


def test_the_query_agent_can_list_risks_needing_review(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    runtime, _ = runtime_with(
        calls(("list_risks", {"needs_review": True})),
        say("RISK-003 (Inaccurate billing) needs review."),
    )

    result = runtime.run(seeded, "Which risks need review?")

    assert result.intent == "query" and result.grounded
    assert [r["id"] for r in result.records] == ["RISK-003"]
