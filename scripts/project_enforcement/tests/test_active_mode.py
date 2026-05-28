"""Active-mode behaviour — revert + bypass-label handling."""

from __future__ import annotations

import pytest

from project_enforcement.actions import RecordingActions
from project_enforcement.checks.transition import check as transition_check
from project_enforcement.evidence import IssueMeta, StubEvidence
from project_enforcement.fields import FieldRef
from project_enforcement.handler import CheckContext
from project_enforcement.snapshot import CardChange


REPO = "CCTC-team/sample"


def _fields():
    return {
        "Status": FieldRef(
            id="PVTSSF_status",
            name="Status",
            data_type="SINGLE_SELECT",
            options={
                "Triage": "opt_triage",
                "Risk linked": "opt_risk",
                "QA approved": "opt_qa",
                "Released": "opt_released",
            },
        ),
    }


def _ctx(mode, *, labels=None, actions=None):
    item = {
        "content_id": "I_1",
        "content_type": "issue",
        "source_repo": REPO,
        "number": 11,
        "fields": {"Status": "QA approved"},
    }
    snapshot = {"project_id": "PVT_test", "items": {"PVTI_1": item}}
    evidence = StubEvidence()
    evidence.issues[(REPO, 11)] = IssueMeta(body="", author="alice", labels=list(labels or []))
    return CheckContext(
        project_cfg={"owner": "CCTC-team", "number": 31},
        fields=_fields(),
        config={"bypass_label": "process-override:approved"},
        mode=mode,
        snapshot=snapshot,
        actions=actions or RecordingActions(),
        evidence=evidence,
    )


def _change(old="Triage", new="QA approved"):
    return CardChange(
        item_id="PVTI_1",
        content_id="I_1",
        content_type="issue",
        source_repo=REPO,
        kind="field_change",
        field_name="Status",
        old_value=old,
        new_value=new,
    )


def test_evaluate_mode_never_reverts():
    ctx = _ctx("evaluate")
    transition_check(_change(), ctx)
    assert ctx.actions.field_writes == []


def test_active_mode_reverts_to_old_status_on_violation():
    ctx = _ctx("active")
    transition_check(_change("Triage", "QA approved"), ctx)
    assert ctx.actions.field_writes == [
        ("PVT_test", "PVTI_1", "PVTSSF_status", "opt_triage"),
    ]


def test_active_mode_does_not_revert_legal_move():
    ctx = _ctx("active")
    transition_check(_change("Triage", "Risk linked"), ctx)
    assert ctx.actions.field_writes == []
    assert ctx.actions.comments == []


def test_active_mode_skips_revert_when_bypass_label_present():
    ctx = _ctx("active", labels=["process-override:approved"])
    transition_check(_change("Triage", "QA approved"), ctx)
    # No field write — bypass honoured.
    assert ctx.actions.field_writes == []
    # Bypass label was cleared after honouring.
    assert ("CCTC-team/sample", 11, "process-override:approved") in ctx.actions.labels_removed


def test_active_mode_bypass_records_audit_event():
    ctx = _ctx("active", labels=["process-override:approved"])
    transition_check(_change("Triage", "QA approved"), ctx)
    assert len(ctx.bypass_events) == 1
    event = ctx.bypass_events[0]
    assert event["repo"] == "CCTC-team/sample"
    assert event["number"] == 11
    assert event["item_id"] == "PVTI_1"
    assert event["old_status"] == "Triage"
    assert event["new_status"] == "QA approved"
    assert event["ts"]  # ISO timestamp set


def test_evaluate_mode_does_not_record_bypass_event():
    ctx = _ctx("evaluate", labels=["process-override:approved"])
    transition_check(_change("Triage", "QA approved"), ctx)
    # Evaluate mode never reverts and never honours a bypass either.
    assert ctx.bypass_events == []


def test_active_mode_revert_failure_does_not_raise():
    class ExplodingActions(RecordingActions):
        def revert_single_select(self, *args, **kwargs):
            raise RuntimeError("project moved on under us")

    actions = ExplodingActions()
    ctx = _ctx("active", actions=actions)
    # Should not raise — the failure is logged for the audit to pick up.
    transition_check(_change("Triage", "QA approved"), ctx)
    assert actions.field_writes == []
    # Comment + label still applied.
    assert len(actions.comments) == 1
    assert len(actions.labels_added) == 1


def test_active_mode_revert_when_option_missing_is_a_noop():
    ctx = _ctx("active")
    # Override Status field to drop the "Triage" option.
    ctx.fields["Status"] = FieldRef(
        id="PVTSSF_status", name="Status", data_type="SINGLE_SELECT",
        options={"QA approved": "opt_qa"},
    )
    transition_check(_change("Triage", "QA approved"), ctx)
    assert ctx.actions.field_writes == []
