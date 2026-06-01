"""Per-project invariants for the nightly audit."""

from __future__ import annotations

import datetime

import pytest

from project_enforcement.audit import (
    Finding,
    REQUIRED_FIELDS_AT_QA,
    audit_project,
    days_since,
)


def _today():
    return datetime.date.today()


def _item(*, status, fields=None, source_repo="CCTC-team/foo", number=1, updated_at=None):
    base = {
        "content_id": f"I_{number}",
        "content_type": "issue",
        "source_repo": source_repo,
        "number": number,
        "title": f"Card {number}",
        "fields": {"Status": status, **(fields or {})},
        "updated_at": updated_at,
    }
    return base


def _snapshot(items):
    return {"items": {f"PVTI_{i}": it for i, it in enumerate(items, 1)}}


def _full_fields(**overrides):
    base = {
        "Risk ID": "RISK-014",
        "Requirement ID": "REQ-024",
        "Test Type": "PQ",
        "Critical-to-Quality": "Yes",
        "Acceptance Approver": "bob",
        "Acceptance Signoff Date": _today().isoformat(),
        "QA Approver": "carol",
        "QA Signoff Date": _today().isoformat(),
    }
    base.update(overrides)
    return base


def test_required_fields_set_at_qa_passes():
    snap = _snapshot([_item(status="QA approved", fields=_full_fields())])
    issue_authors = {("CCTC-team/foo", 1): "alice"}
    findings = audit_project(snap, issue_authors=issue_authors)
    # No hard findings on a healthy QA-approved card.
    assert [f for f in findings if f.severity == "hard"] == []


def test_missing_qa_approver_at_qa_approved_reported():
    snap = _snapshot([_item(status="QA approved", fields=_full_fields(**{"QA Approver": ""}))])
    issue_authors = {("CCTC-team/foo", 1): "alice"}
    findings = audit_project(snap, issue_authors=issue_authors)
    assert any("QA Approver" in f.summary for f in findings)


def test_missing_risk_id_at_released_reported():
    snap = _snapshot([_item(status="Released", fields=_full_fields(**{"Risk ID": ""}))])
    issue_authors = {("CCTC-team/foo", 1): "alice"}
    findings = audit_project(snap, issue_authors=issue_authors)
    assert any("Risk ID" in f.summary for f in findings)


def test_author_equals_qa_approver_reported():
    snap = _snapshot([_item(status="QA approved", fields=_full_fields(**{"QA Approver": "alice"}))])
    issue_authors = {("CCTC-team/foo", 1): "alice"}
    findings = audit_project(snap, issue_authors=issue_authors)
    assert any("three distinct identities" in f.summary.lower() or "author" in f.summary.lower() for f in findings)


def test_card_stuck_in_development_reported_as_soft():
    long_ago = (_today() - datetime.timedelta(days=21)).isoformat()
    snap = _snapshot([_item(status="In development", updated_at=long_ago)])
    findings = audit_project(snap, issue_authors={})
    soft = [f for f in findings if f.severity == "soft"]
    assert any("stuck" in f.summary.lower() or "assignee change" in f.summary.lower() for f in soft)


def test_healthy_in_development_card_not_reported():
    recent = _today().isoformat()
    snap = _snapshot([_item(status="In development", updated_at=recent)])
    findings = audit_project(snap, issue_authors={})
    assert findings == []


def test_days_since_handles_iso():
    assert days_since((_today() - datetime.timedelta(days=5)).isoformat()) == 5
    assert days_since(None) is None
    assert days_since("not-a-date") is None


def test_unticked_acceptance_checklist_at_user_acceptance_is_reported():
    snap = _snapshot([_item(status="User acceptance")])
    body = (
        "### User acceptance checklist:\n\n"
        "- [x] Feature meets the user requirement against the URS in a development/test environment\n"
        "- [ ] Workflow is usable in practice (not just technically passing)\n"
    )
    findings = audit_project(
        snap,
        issue_authors={},
        issue_bodies={("CCTC-team/foo", 1): body},
    )
    assert any(
        f.category == "checklist_unticked" and "user-acceptance checklist" in f.summary
        for f in findings
    )


def test_unticked_qa_checklist_at_qa_approved_is_reported():
    snap = _snapshot([_item(status="QA approved", fields=_full_fields())])
    body = (
        "### QA review checklist:\n\n"
        "- [x] Risk linkage verified against the canonical risk register\n"
        "- [ ] URS → V&V evidence chain intact; any deviations are documented\n"
    )
    findings = audit_project(
        snap,
        issue_authors={("CCTC-team/foo", 1): "alice"},
        issue_bodies={("CCTC-team/foo", 1): body},
    )
    assert any(
        f.category == "checklist_unticked" and "QA checklist" in f.summary
        for f in findings
    )


def test_fully_ticked_checklists_at_qa_approved_is_silent():
    snap = _snapshot([_item(status="QA approved", fields=_full_fields())])
    body = (
        "### User acceptance checklist:\n\n"
        "- [x] Feature meets the user requirement against the URS in a development/test environment\n"
        "- [x] Workflow is usable in practice (not just technically passing)\n\n"
        "### QA review checklist:\n\n"
        "- [x] Risk linkage verified against the canonical risk register\n"
        "- [x] URS → V&V evidence chain intact; any deviations are documented\n"
    )
    findings = audit_project(
        snap,
        issue_authors={("CCTC-team/foo", 1): "alice"},
        issue_bodies={("CCTC-team/foo", 1): body},
    )
    assert [f for f in findings if f.category == "checklist_unticked"] == []


def test_checklist_check_silent_when_body_absent():
    # No issue body fetched — audit should not invent failures.
    snap = _snapshot([_item(status="User acceptance")])
    findings = audit_project(snap, issue_authors={}, issue_bodies={})
    assert [f for f in findings if f.category == "checklist_unticked"] == []


def test_required_fields_constant_matches_design():
    assert REQUIRED_FIELDS_AT_QA == (
        "Risk ID",
        "Requirement ID",
        "Test Type",
        "Critical-to-Quality",
        "Acceptance Approver",
        "Acceptance Signoff Date",
        "QA Approver",
        "QA Signoff Date",
    )
