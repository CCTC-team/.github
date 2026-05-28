"""Integration: handler.run() dispatches Status changes through
PRECONDITIONS and emits the comment + label side effects when a
precondition reports a failure reason.

The named-check dispatch loop is already covered by
test_handler_smoke.py; this file exercises the *separate* per-status
precondition loop that handler.run() runs after named checks.
"""

from __future__ import annotations

from unittest.mock import patch

from project_enforcement import handler
from project_enforcement.actions import RecordingActions
from project_enforcement.evidence import StubEvidence


REPO = "CCTC-team/sample"
ITEM_ID = "PVTI_existing"
NUMBER = 11


PRIOR = {
    "items": {
        ITEM_ID: {
            "content_id": "I_1",
            "content_type": "issue",
            "source_repo": REPO,
            "number": NUMBER,
            "title": "Existing feature",
            "updated_at": "2026-05-01",
            "fields": {"Status": "Triage"},
        }
    }
}

NEW_PROJECT = {
    "project_id": "PVT_test",
    "owner": "CCTC-team",
    "number": 31,
    "title": "[TEST] Lifecycle",
    "items": {
        ITEM_ID: {
            "content_id": "I_1",
            "content_type": "issue",
            "source_repo": REPO,
            "number": NUMBER,
            "title": "Existing feature",
            "updated_at": "2026-05-28",
            "fields": {"Status": "Risk linked", "Risk ID": "RISK-014"},
        }
    },
    "fields_meta": {
        "Status": {
            "__typename": "ProjectV2SingleSelectField",
            "id": "PVTSSF_status",
            "name": "Status",
            "dataType": "SINGLE_SELECT",
            "options": [
                {"id": "opt_triage", "name": "Triage"},
                {"id": "opt_risk", "name": "Risk linked"},
            ],
        },
        "Risk ID": {
            "__typename": "ProjectV2Field",
            "id": "PVTF_risk", "name": "Risk ID", "dataType": "TEXT",
        },
    },
}


def _config(precondition_mode="evaluate"):
    return {
        "projects": [{"owner": "CCTC-team", "number": 31, "name": "[TEST] Lifecycle"}],
        "preconditions": {"Risk linked": precondition_mode},
    }


def _run(*, config, fake_precondition, actions=None):
    actions = actions or RecordingActions()
    evidence = StubEvidence()

    with patch.dict(
        "project_enforcement.checks.preconditions.PRECONDITIONS",
        {"Risk linked": fake_precondition},
        clear=False,
    ), patch.dict(
        "project_enforcement.handler.PRECONDITIONS",
        {"Risk linked": fake_precondition},
        clear=False,
    ):
        rc = handler.run(
            config,
            state_dir="/tmp/handler-precondition-test",
            fetch_project=lambda owner, number: NEW_PROJECT,
            load_snapshot=lambda path: PRIOR,
            write_snapshot=lambda path, snap: None,
            checks={},  # no named checks — we want the precondition path only
            actions=actions,
            evidence=evidence,
        )
    return rc, actions


def test_passing_precondition_emits_no_comment_no_label():
    rc, actions = _run(
        config=_config("evaluate"),
        fake_precondition=lambda item, ctx, ev: [],
    )
    assert rc == 0
    assert actions.comments == []
    assert actions.labels_added == []


def test_failing_precondition_in_evaluate_emits_one_comment_one_label():
    rc, actions = _run(
        config=_config("evaluate"),
        fake_precondition=lambda item, ctx, ev: ["Risk ID does not match"],
    )
    assert rc == 0
    assert len(actions.comments) == 1
    repo, number, body = actions.comments[0]
    assert repo == REPO
    assert number == NUMBER
    assert "Risk linked" in body
    assert "Risk ID does not match" in body
    assert actions.labels_added == [(REPO, NUMBER, "process-violation")]


def test_off_precondition_does_not_run():
    seen = []
    def recorder(item, ctx, ev):
        seen.append(item)
        return ["should never appear"]

    rc, actions = _run(
        config=_config("off"),
        fake_precondition=recorder,
    )
    assert rc == 0
    assert seen == []
    assert actions.comments == []


def test_active_mode_precondition_reverts_to_old_status():
    rc, actions = _run(
        config=_config("active"),
        fake_precondition=lambda item, ctx, ev: ["broken"],
    )
    assert rc == 0
    # Revert wrote the Triage option id back.
    assert actions.field_writes == [
        ("PVT_test", ITEM_ID, "PVTSSF_status", "opt_triage"),
    ]


def test_active_mode_honours_bypass_label():
    from project_enforcement.evidence import IssueMeta

    actions = RecordingActions()
    evidence = StubEvidence()
    evidence.issues[(REPO, NUMBER)] = IssueMeta(
        body="", author="alice", labels=["process-override:approved"],
    )

    def fake_precondition(item, ctx, ev):
        return ["broken"]

    config = _config("active")
    config["bypass_label"] = "process-override:approved"

    with patch.dict(
        "project_enforcement.checks.preconditions.PRECONDITIONS",
        {"Risk linked": fake_precondition},
        clear=False,
    ), patch.dict(
        "project_enforcement.handler.PRECONDITIONS",
        {"Risk linked": fake_precondition},
        clear=False,
    ):
        rc = handler.run(
            config,
            state_dir="/tmp/handler-precondition-test",
            fetch_project=lambda o, n: NEW_PROJECT,
            load_snapshot=lambda p: PRIOR,
            write_snapshot=lambda p, s: None,
            checks={},
            actions=actions,
            evidence=evidence,
        )
    assert rc == 0
    # No revert — bypass honoured.
    assert actions.field_writes == []
    # Bypass label was cleared so it can't be reused.
    assert (REPO, NUMBER, "process-override:approved") in actions.labels_removed
