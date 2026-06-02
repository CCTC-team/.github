"""Behaviour of the field-drift checks.

Each drift check is independent of status transitions — it fires on a
specific field_change and decides whether the new value is consistent
with the rest of the world.
"""

from __future__ import annotations

import datetime

import pytest

from project_enforcement.actions import RecordingActions
from project_enforcement.checks.drift import (
    approver_identity_drift,
    date_sanity,
    id_mirror,
    type_quality_consistency,
)
from project_enforcement.evidence import IssueMeta, StubEvidence
from project_enforcement.handler import CheckContext
from project_enforcement.snapshot import CardChange


REPO = "CCTC-team/sample"
NUMBER = 7


def _ctx(actions=None, item_fields=None):
    item = {
        "content_id": "I_1",
        "content_type": "issue",
        "source_repo": REPO,
        "number": NUMBER,
        "title": "Sample",
        "fields": item_fields or {},
    }
    return CheckContext(
        project_cfg={"owner": "CCTC-team", "number": 31},
        fields={},
        config={},
        mode="evaluate",
        snapshot={"items": {"PVTI_1": item}},
        actions=actions or RecordingActions(),
    )


def _change(field, old, new):
    return CardChange(
        item_id="PVTI_1",
        content_id="I_1",
        content_type="issue",
        source_repo=REPO,
        kind="field_change",
        field_name=field,
        old_value=old,
        new_value=new,
    )


# ============================== id_mirror ==============================

class TestIdMirror:
    def _evidence(self, body):
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body=body, author="alice")
        return ev

    def test_matching_value_does_not_comment(self):
        ctx = _ctx()
        ev = self._evidence("### Risk ID:\n\nRISK-014\n")
        id_mirror.check(_change("Risk ID", "RISK-009", "RISK-014"), ctx, ev)
        assert ctx.actions.comments == []

    def test_mismatch_emits_comment_naming_canonical_body(self):
        ctx = _ctx()
        ev = self._evidence("### Risk ID:\n\nRISK-099\n")
        id_mirror.check(_change("Risk ID", "RISK-009", "RISK-014"), ctx, ev)
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "RISK-099" in body
        assert "RISK-014" in body
        assert "issue body" in body.lower()

    def test_ignores_other_fields(self):
        ctx = _ctx()
        ev = self._evidence("### Risk ID:\n\nRISK-099\n")
        id_mirror.check(_change("Test Type", "PQ", "OQ"), ctx, ev)
        assert ctx.actions.comments == []


# ============================== date_sanity ==============================

class TestDateSanity:
    def _evidence(self, opened_days_ago=30):
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(
            body="",
            author="alice",
            assignees=[],
        )
        ev.issues[(REPO, NUMBER)].opened_at = (
            datetime.date.today() - datetime.timedelta(days=opened_days_ago)
        ).isoformat()
        return ev

    def test_valid_date_does_not_comment(self):
        ctx = _ctx(item_fields={"Acceptance Signoff Date": ""})
        ev = self._evidence()
        date_sanity.check(_change("Acceptance Signoff Date", "", datetime.date.today().isoformat()), ctx, ev)
        assert ctx.actions.comments == []

    def test_future_date_comments(self):
        future = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        ctx = _ctx()
        ev = self._evidence()
        date_sanity.check(_change("QA Signoff Date", "", future), ctx, ev)
        assert any("future" in b for _, _, b in ctx.actions.comments)

    def test_before_issue_opened_comments(self):
        ev = self._evidence(opened_days_ago=2)
        too_early = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        ctx = _ctx()
        date_sanity.check(_change("QA Signoff Date", "", too_early), ctx, ev)
        assert any("before the issue was opened" in b for _, _, b in ctx.actions.comments)

    def test_acceptance_after_qa_comments(self):
        today = datetime.date.today()
        ev = self._evidence()
        ctx = _ctx(item_fields={"QA Signoff Date": today.isoformat()})
        # Acceptance being set to the day after an already-recorded QA date.
        acceptance_new = (today + datetime.timedelta(days=1)).isoformat()
        date_sanity.check(_change("Acceptance Signoff Date", "", acceptance_new), ctx, ev)
        assert any("Acceptance ≤ QA" in b or "after the QA" in b.lower() for _, _, b in ctx.actions.comments)


# ============================== approver_identity_drift ==============================

class TestApproverIdentityDrift:
    def test_change_to_existing_approver_below_column_audit_logs(self):
        # A card moved back below its review column, then the approver swapped.
        # The previous approver value proves the card had been reviewed, so the
        # swap must still be logged even though the current status is below the
        # column.
        ctx = _ctx(item_fields={"Status": "In development"})
        ev = StubEvidence()
        approver_identity_drift.check(
            _change("Acceptance Approver", "alice", "bob"), ctx, ev,
        )
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "alice" in body and "bob" in body

    def test_first_set_below_column_silent(self):
        # An approver set for the first time before the card reaches its review
        # column (empty previous value) is ordinary setup, not drift.
        ev = StubEvidence()
        for status in ("In development", "Triage"):
            ctx = _ctx(item_fields={"Status": status})
            approver_identity_drift.check(
                _change("Acceptance Approver", "", "alice"), ctx, ev,
            )
            assert ctx.actions.comments == []

    def test_first_set_below_qa_column_silent(self):
        # A QA approver first-set at User acceptance is below the QA column and
        # has no previous value, so it stays silent.
        ctx = _ctx(item_fields={"Status": "User acceptance"})
        ev = StubEvidence()
        approver_identity_drift.check(
            _change("QA Approver", "", "carol"), ctx, ev,
        )
        assert ctx.actions.comments == []

    def test_clearing_existing_approver_below_column_audit_logs(self):
        # Clearing a previously-set approver after a move-back must be logged —
        # the non-empty previous value means the card had been reviewed.
        ctx = _ctx(item_fields={"Status": "Requirement defined"})
        ev = StubEvidence()
        approver_identity_drift.check(
            _change("QA Approver", "carol", ""), ctx, ev,
        )
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "carol" in body

    def test_change_after_acceptance_audit_logs(self):
        ctx = _ctx(item_fields={"Status": "QA approved"})
        ev = StubEvidence()
        approver_identity_drift.check(
            _change("Acceptance Approver", "alice", "bob"), ctx, ev,
        )
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "alice" in body and "bob" in body

    def test_no_revert(self):
        ctx = _ctx(item_fields={"Status": "Released"})
        ev = StubEvidence()
        approver_identity_drift.check(_change("QA Approver", "carol", "dave"), ctx, ev)
        assert ctx.actions.field_writes == []


# ============================== type_quality_consistency ==============================

class TestTypeQualityConsistency:
    def test_consistent_combination_silent(self):
        # Legacy alias: "Yes" behaves as Critical, PQ satisfies it.
        ctx = _ctx(item_fields={"Critical-to-Quality": "Yes", "Test Type": "PQ"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "OQ", "PQ"), ctx, ev)
        assert ctx.actions.comments == []

    def test_inconsistent_combination_comments(self):
        # Legacy alias: "Yes" + N/A is inconsistent.
        ctx = _ctx(item_fields={"Critical-to-Quality": "Yes", "Test Type": "N/A"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "PQ", "N/A"), ctx, ev)
        assert any("inconsistent" in b.lower() or "Critical-to-Quality" in b for _, _, b in ctx.actions.comments)

    def test_critical_with_na_comments_requiring_pq(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "Critical", "Test Type": "N/A"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "PQ", "N/A"), ctx, ev)
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "PQ" in body

    def test_critical_with_pq_silent(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "Critical", "Test Type": "PQ"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "OQ", "PQ"), ctx, ev)
        assert ctx.actions.comments == []

    def test_critical_with_present_non_pq_comments_requiring_pq(self):
        # A present-but-non-PQ Test Type (e.g. OQ) does not satisfy a
        # Critical factor: the check must still flag it, not just the N/A case.
        ctx = _ctx(item_fields={"Critical-to-Quality": "Critical", "Test Type": "OQ"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "PQ", "OQ"), ctx, ev)
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "PQ" in body
        assert "OQ" in body

    def test_important_with_na_comments_requiring_test_type_not_pq(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "Important", "Test Type": "N/A"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "OQ", "N/A"), ctx, ev)
        assert len(ctx.actions.comments) == 1
        _, _, body = ctx.actions.comments[0]
        assert "Test Type" in body
        assert "includes PQ" not in body

    def test_important_with_oq_silent(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "Important", "Test Type": "OQ"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "N/A", "OQ"), ctx, ev)
        assert ctx.actions.comments == []

    def test_no_tier_with_na_silent(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "No", "Test Type": "N/A"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Test Type", "OQ", "N/A"), ctx, ev)
        assert ctx.actions.comments == []

    def test_ignores_unrelated_field(self):
        ctx = _ctx(item_fields={"Critical-to-Quality": "Yes", "Test Type": "N/A"})
        ev = StubEvidence()
        type_quality_consistency.check(_change("Risk ID", "X", "Y"), ctx, ev)
        assert ctx.actions.comments == []
