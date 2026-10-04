"""The impact workflow over HTTP."""

NEW_TEXT = "Energy measurement shall be accurate to within 0.5 percent of the delivered kWh."


def propose_and_confirm(api, req_id, patch, actor="rachna"):
    proposal = api.post(
        "/changes", json={"requirement_id": req_id, "patch": patch, "proposed_by": actor}
    )
    change_id = proposal.json()["change"]["id"]
    return api.post(f"/changes/{change_id}/confirm", json={"actor": actor})


def risks_by_id(api):
    return {r["id"]: r for r in api.get("/risks").json()}


# ---------- reading the report ----------


def test_there_is_no_report_before_a_confirmed_change(api):
    r = api.get("/requirements/REQ-009/impact")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert "confirmed change" in r.json()["error"]["message"]


def test_confirm_returns_the_impact_and_the_endpoint_returns_the_same_report(api):
    confirm = propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})

    assert confirm.status_code == 200
    impact = confirm.json()["impact"]
    assert impact["level"] == "high"
    assert [t["id"] for t in impact["tests_to_reset"]] == ["TC-019", "TC-020", "TC-030"]
    assert [t["id"] for t in impact["tests_failing"]] == ["TC-021"]
    assert [r["id"] for r in impact["risks_to_flag"]] == ["RISK-003"]
    assert impact["summary"].startswith("REQ-009: description changed.")

    got = api.get("/requirements/REQ-009/impact")
    assert got.status_code == 200 and got.json() == impact


def test_the_test_cases_really_changed_and_the_failing_one_did_not(api):
    propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})

    statuses = {t["id"]: t["status"] for t in api.get("/requirements/REQ-009/test-cases").json()}

    assert statuses == {
        "TC-019": "not_run",
        "TC-020": "not_run",
        "TC-021": "fail",
        "TC-030": "not_run",
    }


def test_confirming_twice_returns_the_same_report(api):
    proposal = api.post(
        "/changes",
        json={
            "requirement_id": "REQ-009",
            "patch": {"description": NEW_TEXT},
            "proposed_by": "rachna",
        },
    ).json()
    cid = proposal["change"]["id"]
    first = api.post(f"/changes/{cid}/confirm", json={"actor": "rachna"}).json()
    second = api.post(f"/changes/{cid}/confirm", json={"actor": "rachna"}).json()

    assert second["already_applied"] is True
    assert second["impact"] == first["impact"]


def test_a_harmless_change_still_gets_a_low_impact_report(api):
    impact = propose_and_confirm(api, "REQ-007", {"status": "implemented"}).json()["impact"]

    assert impact["level"] == "low"
    assert impact["tests_to_reset"] == [] and impact["risks_to_flag"] == []


def test_report_lookup_errors(api):
    assert api.get("/requirements/REQ-099/impact").status_code == 404
    assert api.get("/requirements/banana/impact").status_code == 422


# ---------- the risk review flag ----------


def test_risks_carry_a_review_flag_that_starts_false(api):
    assert all(r["needs_review"] is False for r in api.get("/risks").json())


def test_a_confirmed_change_flags_the_linked_risk(api):
    propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})

    risks = risks_by_id(api)

    assert risks["RISK-003"]["needs_review"] is True
    assert [rid for rid, r in risks.items() if r["needs_review"]] == ["RISK-003"]


def test_a_person_clears_the_flag(api):
    propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})

    r = api.post("/risks/RISK-003/reviewed", json={"actor": "rachna"})

    assert r.status_code == 200 and r.json()["needs_review"] is False
    assert risks_by_id(api)["RISK-003"]["needs_review"] is False
    audit = api.get("/audit-log", params={"entity_id": "RISK-003"}).json()
    assert [(e["action"], e["source"]) for e in audit] == [
        ("review", "ui"),
        ("flag_review", "system"),
    ]


def test_reviewing_twice_is_harmless(api):
    propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})
    api.post("/risks/RISK-003/reviewed", json={"actor": "rachna"})

    again = api.post("/risks/RISK-003/reviewed", json={"actor": "rachna"})

    assert again.status_code == 200 and again.json()["needs_review"] is False
    audit = api.get("/audit-log", params={"entity_id": "RISK-003"}).json()
    assert [e["action"] for e in audit].count("review") == 1


def test_review_endpoint_errors(api):
    assert api.post("/risks/RISK-099/reviewed", json={"actor": "x"}).status_code == 404
    assert api.post("/risks/banana/reviewed", json={"actor": "x"}).status_code == 422
    assert api.post("/risks/RISK-003/reviewed", json={"actor": "  "}).status_code == 422
    assert api.post("/risks/RISK-003/reviewed", json={}).status_code == 422
    extra = api.post("/risks/RISK-003/reviewed", json={"actor": "x", "source": "agent"})
    assert extra.status_code == 422  # a client cannot choose the audit source


def test_the_new_endpoints_are_documented(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert "get" in paths["/requirements/{requirement_id}/impact"]
    assert "post" in paths["/risks/{risk_id}/reviewed"]


# ---------- filtering risks by the review flag ----------


def test_risks_can_be_filtered_by_the_review_flag(api):
    assert api.get("/risks", params={"needs_review": "true"}).json() == []
    propose_and_confirm(api, "REQ-009", {"description": NEW_TEXT})

    flagged = api.get("/risks", params={"needs_review": "true"}).json()
    unflagged = api.get("/risks", params={"needs_review": "false"}).json()

    assert [r["id"] for r in flagged] == ["RISK-003"]
    assert len(unflagged) == 11 and "RISK-003" not in [r["id"] for r in unflagged]


def test_a_bad_review_filter_value_is_422(api):
    assert api.get("/risks", params={"needs_review": "maybe"}).status_code == 422
