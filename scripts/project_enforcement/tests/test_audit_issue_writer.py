"""Behaviour of update_audit_issue — creates / updates / closes / reopens
the rolling drift issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from project_enforcement.audit import (
    Finding,
    audit_issue_title,
    update_audit_issue,
)


@dataclass
class FakeIssue:
    number: int
    title: str
    body: str
    state: str = "open"


@dataclass
class FakeGh:
    repo: str = "CCTC-team/.github"
    issues: list[FakeIssue] = field(default_factory=list)
    next_number: int = 100

    def find_open(self, title):
        for issue in self.issues:
            if issue.title == title and issue.state == "open":
                return issue
        return None

    def find_any(self, title):
        for issue in self.issues:
            if issue.title == title:
                return issue
        return None

    def create_issue(self, title, body):
        issue = FakeIssue(number=self.next_number, title=title, body=body)
        self.next_number += 1
        self.issues.append(issue)
        return issue

    def update_issue(self, number, body=None, state=None):
        for issue in self.issues:
            if issue.number == number:
                if body is not None:
                    issue.body = body
                if state is not None:
                    issue.state = state
                return issue
        raise KeyError(number)


def _finding(summary="missing field"):
    return Finding(
        severity="hard",
        category="required_field",
        item_label="PVTI_x",
        summary=summary,
    )


PROJECT_LABEL = "[TEST] Regulated Feature Lifecycle"
TITLE = audit_issue_title(PROJECT_LABEL)


def test_creates_issue_when_none_exists():
    gh = FakeGh()
    update_audit_issue(gh, PROJECT_LABEL, [_finding("X")], unmonitored=[])
    assert len(gh.issues) == 1
    assert gh.issues[0].title == TITLE
    assert "X" in gh.issues[0].body


def test_updates_existing_issue_body():
    gh = FakeGh()
    gh.issues.append(FakeIssue(number=42, title=TITLE, body="old"))
    update_audit_issue(gh, PROJECT_LABEL, [_finding("Y")], unmonitored=[])
    assert len(gh.issues) == 1
    assert "Y" in gh.issues[0].body
    assert gh.issues[0].state == "open"


def test_closes_issue_when_findings_empty():
    gh = FakeGh()
    gh.issues.append(FakeIssue(number=42, title=TITLE, body="old"))
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[])
    assert gh.issues[0].state == "closed"
    assert "no drift" in gh.issues[0].body.lower()


def test_reopens_closed_issue_when_findings_reappear():
    gh = FakeGh()
    gh.issues.append(FakeIssue(number=42, title=TITLE, body="resolved", state="closed"))
    update_audit_issue(gh, PROJECT_LABEL, [_finding("Z")], unmonitored=[])
    assert gh.issues[0].state == "open"
    assert "Z" in gh.issues[0].body


def test_no_action_when_no_findings_and_no_prior_issue():
    gh = FakeGh()
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[])
    assert gh.issues == []


def test_bypass_section_rendered():
    gh = FakeGh()
    bypass = [{
        "ts": "2026-05-20T10:00:00+00:00",
        "repo": "CCTC-team/foo",
        "number": 11,
        "item_id": "PVTI_x",
        "old_status": "Triage",
        "new_status": "QA approved",
    }]
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[], bypass_events=bypass)
    body = gh.issues[0].body
    assert "Recent bypasses honoured" in body
    assert "CCTC-team/foo#11" in body
    assert "Triage" in body and "QA approved" in body


def test_stale_bypass_events_aged_out_at_render_time():
    """A bypass event older than 30 days must not appear in the body, even
    if the poller has been paused and not refreshed the snapshot."""
    gh = FakeGh()
    old_ts = (
        __import__("datetime").datetime.now(__import__("datetime").UTC)
        - __import__("datetime").timedelta(days=45)
    ).isoformat()
    stale = [{
        "ts": old_ts,
        "repo": "CCTC-team/foo",
        "number": 11,
        "item_id": "PVTI_x",
        "old_status": "Triage",
        "new_status": "QA approved",
    }]
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[], bypass_events=stale)
    # With nothing else to report and all bypass events aged out, the
    # rolling issue must not be created.
    assert gh.issues == []


def test_bypass_alone_keeps_issue_open():
    # A bypass with no other findings should still leave the rolling issue open.
    gh = FakeGh()
    gh.issues.append(FakeIssue(number=42, title=TITLE, body="old"))
    bypass = [{
        "ts": "2026-05-20T10:00:00+00:00",
        "repo": "CCTC-team/foo", "number": 11,
        "item_id": "PVTI_x", "old_status": "Triage", "new_status": "QA approved",
    }]
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[], bypass_events=bypass)
    assert gh.issues[0].state == "open"


def test_unmonitored_section_rendered():
    gh = FakeGh()
    unmonitored_finding = Finding(
        severity="soft",
        category="unmonitored_clone",
        item_label="PVT_x",
        summary="Project 99 [Other Lifecycle] looks like a lifecycle board but is not in config.",
    )
    update_audit_issue(gh, PROJECT_LABEL, [], unmonitored=[unmonitored_finding])
    body = gh.issues[0].body
    assert "Unmonitored lifecycle boards" in body
    assert "Other Lifecycle" in body
