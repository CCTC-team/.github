"""Behaviour of the transition check on its own."""

from project_enforcement.actions import RecordingActions
from project_enforcement.checks.transition import VIOLATION_LABEL, check
from project_enforcement.handler import CheckContext
from project_enforcement.snapshot import CardChange


def _ctx(mode="evaluate", item=None, config=None):
    item = item or {
        "content_id": "I_1",
        "content_type": "issue",
        "source_repo": "CCTC-team/some-repo",
        "number": 11,
        "title": "Some feature",
        "fields": {"Status": "Risk linked"},
    }
    return CheckContext(
        project_cfg={"owner": "CCTC-team", "number": 31},
        fields={},
        config=config or {"bypass_label": "process-override:approved"},
        mode=mode,
        snapshot={"items": {"PVTI_1": item}},
        actions=RecordingActions(),
    )


def _change(old, new, kind="field_change", field_name="Status"):
    return CardChange(
        item_id="PVTI_1",
        content_id="I_1",
        content_type="issue",
        source_repo="CCTC-team/some-repo",
        kind=kind,
        field_name=field_name,
        old_value=old,
        new_value=new,
    )


def test_legal_forward_step_is_silent():
    ctx = _ctx()
    check(_change("Triage", "Risk linked"), ctx)
    assert ctx.actions.comments == []
    assert ctx.actions.labels_added == []


def test_backward_move_is_silent():
    ctx = _ctx()
    check(_change("QA approved", "Risk linked"), ctx)
    assert ctx.actions.comments == []
    assert ctx.actions.labels_added == []


def test_illegal_forward_skip_comments_and_labels_without_reverting():
    ctx = _ctx()
    check(_change("Triage", "QA approved"), ctx)

    assert len(ctx.actions.comments) == 1
    repo, number, body = ctx.actions.comments[0]
    assert repo == "CCTC-team/some-repo"
    assert number == 11
    assert "Triage" in body
    assert "QA approved" in body

    assert ctx.actions.labels_added == [("CCTC-team/some-repo", 11, VIOLATION_LABEL)]
    # Phase 1 must not revert — that's Phase 8.
    assert ctx.actions.field_writes == []


def test_ignores_non_status_field_change():
    ctx = _ctx()
    check(_change("RISK-001", "RISK-014", field_name="Risk ID"), ctx)
    assert ctx.actions.comments == []
    assert ctx.actions.labels_added == []


def test_ignores_added_and_removed_cards():
    ctx = _ctx()
    check(_change(None, None, kind="added", field_name=None), ctx)
    check(_change(None, None, kind="removed", field_name=None), ctx)
    assert ctx.actions.comments == []


def test_skips_when_no_source_repo_or_number():
    ctx = _ctx(item={
        "content_id": "DI_1",
        "content_type": "draft",
        "source_repo": None,
        "number": None,
        "fields": {"Status": "QA approved"},
    })
    check(_change("Triage", "QA approved"), ctx)
    assert ctx.actions.comments == []
    assert ctx.actions.labels_added == []


def test_evaluate_mode_message_says_evaluate():
    ctx = _ctx(mode="evaluate")
    check(_change("Triage", "Released"), ctx)
    _, _, body = ctx.actions.comments[0]
    assert "evaluate" in body
    assert "single-use" not in body


def test_active_mode_message_mentions_bypass_label():
    ctx = _ctx(mode="active", config={"bypass_label": "process-override:approved"})
    check(_change("Triage", "Released"), ctx)
    _, _, body = ctx.actions.comments[0]
    assert "process-override:approved" in body
    assert "single-use" in body


def test_evaluate_mode_does_not_revert():
    ctx = _ctx(mode="evaluate")
    check(_change("Triage", "QA approved"), ctx)
    assert ctx.actions.field_writes == []
