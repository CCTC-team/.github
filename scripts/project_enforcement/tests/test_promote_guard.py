"""Promote-guard + allowlist tests for the PR-driven card promoter."""

from project_enforcement.promote import decide


ALLOWED = ["PVT_test"]


# ---- guard: project_number missing ----

def test_empty_project_number_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="In development",
    )
    assert d.action == "skip"
    assert "no LIFECYCLE_PROJECT_NUMBER" in d.reason


def test_zero_project_number_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="0",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="In development",
    )
    assert d.action == "skip"
    assert "no LIFECYCLE_PROJECT_NUMBER" in d.reason


# ---- allowlist ----

def test_project_not_in_allowlist_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="42",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_other",
        current_status="In development",
    )
    assert d.action == "skip"
    assert "not in" in d.reason


def test_resolution_failure_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="42",
        allowed_project_ids=ALLOWED,
        resolved_project_id=None,
        current_status="In development",
    )
    assert d.action == "skip"
    assert "did not resolve" in d.reason


# ---- pull_request_opened ----

def test_pr_opened_when_card_in_development_moves_to_code_review():
    d = decide(
        event="pull_request_opened",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="In development",
    )
    assert d.action == "move"
    assert d.target_status == "Code review"


def test_pr_opened_when_card_already_in_code_review_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="Code review",
    )
    assert d.action == "skip"
    assert "already" in d.reason


def test_pr_opened_when_card_past_code_review_is_skipped():
    d = decide(
        event="pull_request_opened",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="V&V tests pass",
    )
    assert d.action == "skip"


# ---- check_suite_completed ----

def test_check_suite_success_moves_to_vv():
    d = decide(
        event="check_suite_completed",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="Code review",
        check_conclusion="success",
    )
    assert d.action == "move"
    assert d.target_status == "V&V tests pass"


def test_check_suite_failure_skips():
    d = decide(
        event="check_suite_completed",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="Code review",
        check_conclusion="failure",
    )
    assert d.action == "skip"
    assert "failure" in d.reason


def test_check_suite_does_not_promote_past_vv():
    d = decide(
        event="check_suite_completed",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="User acceptance",
        check_conclusion="success",
    )
    assert d.action == "skip"


# ---- pull_request_closed ----

def test_pr_merge_does_nothing_automatic():
    d = decide(
        event="pull_request_closed",
        project_number="31",
        allowed_project_ids=ALLOWED,
        resolved_project_id="PVT_test",
        current_status="V&V tests pass",
        pr_merged=True,
    )
    assert d.action == "skip"
    assert "no automatic promotion" in d.reason
