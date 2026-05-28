"""Behaviour of compute_diff(old, new) -> list[CardChange].

A snapshot is a dict of the shape:

    {
      "items": {
        "<item_id>": {
          "content_id": "<gid>",
          "content_type": "issue" | "pull_request" | "draft",
          "source_repo": "owner/repo" | None,
          "fields": { "<name>": "<value>", ... }
        },
        ...
      }
    }

compute_diff yields one CardChange per added/removed item and one per
changed field on items present in both.
"""

import pytest

from project_enforcement.snapshot import CardChange, compute_diff


def _item(content_id="I_1", content_type="issue", source_repo="CCTC-team/foo", fields=None):
    return {
        "content_id": content_id,
        "content_type": content_type,
        "source_repo": source_repo,
        "fields": fields or {},
    }


def test_added_card_emits_added_change():
    old = {"items": {}}
    new = {"items": {"PVTI_1": _item(fields={"Status": "Triage"})}}

    changes = compute_diff(old, new)

    assert changes == [
        CardChange(
            item_id="PVTI_1",
            content_id="I_1",
            content_type="issue",
            source_repo="CCTC-team/foo",
            kind="added",
            field_name=None,
            old_value=None,
            new_value=None,
        )
    ]


def test_removed_card_emits_removed_change():
    old = {"items": {"PVTI_1": _item(fields={"Status": "Triage"})}}
    new = {"items": {}}

    changes = compute_diff(old, new)

    assert len(changes) == 1
    assert changes[0].kind == "removed"
    assert changes[0].item_id == "PVTI_1"
    assert changes[0].field_name is None


def test_status_field_change_emits_field_change():
    old = {"items": {"PVTI_1": _item(fields={"Status": "Triage"})}}
    new = {"items": {"PVTI_1": _item(fields={"Status": "Risk linked"})}}

    changes = compute_diff(old, new)

    assert changes == [
        CardChange(
            item_id="PVTI_1",
            content_id="I_1",
            content_type="issue",
            source_repo="CCTC-team/foo",
            kind="field_change",
            field_name="Status",
            old_value="Triage",
            new_value="Risk linked",
        )
    ]


def test_custom_field_change_emits_field_change():
    old = {"items": {"PVTI_1": _item(fields={"Risk ID": ""})}}
    new = {"items": {"PVTI_1": _item(fields={"Risk ID": "RISK-014"})}}

    changes = compute_diff(old, new)

    assert len(changes) == 1
    assert changes[0].kind == "field_change"
    assert changes[0].field_name == "Risk ID"
    assert changes[0].old_value == ""
    assert changes[0].new_value == "RISK-014"


def test_unchanged_card_emits_nothing():
    snap = {"items": {"PVTI_1": _item(fields={"Status": "Triage", "Risk ID": "RISK-014"})}}
    assert compute_diff(snap, snap) == []


def test_multiple_cards_changed_in_one_run():
    old = {
        "items": {
            "PVTI_1": _item(content_id="I_1", fields={"Status": "Triage"}),
            "PVTI_2": _item(content_id="I_2", fields={"Status": "In development"}),
            "PVTI_3": _item(content_id="I_3", fields={"Status": "Code review"}),
        }
    }
    new = {
        "items": {
            "PVTI_1": _item(content_id="I_1", fields={"Status": "Risk linked"}),
            "PVTI_3": _item(content_id="I_3", fields={"Status": "Code review"}),
            "PVTI_4": _item(content_id="I_4", fields={"Status": "Triage"}),
        }
    }

    changes = compute_diff(old, new)
    by_kind = {c.kind for c in changes}
    assert by_kind == {"added", "removed", "field_change"}
    assert len(changes) == 3

    field_change = next(c for c in changes if c.kind == "field_change")
    assert field_change.item_id == "PVTI_1"
    assert field_change.old_value == "Triage"
    assert field_change.new_value == "Risk linked"

    removed = next(c for c in changes if c.kind == "removed")
    assert removed.item_id == "PVTI_2"

    added = next(c for c in changes if c.kind == "added")
    assert added.item_id == "PVTI_4"


def test_added_field_on_existing_card_treated_as_field_change():
    old = {"items": {"PVTI_1": _item(fields={"Status": "Triage"})}}
    new = {"items": {"PVTI_1": _item(fields={"Status": "Triage", "Risk ID": "RISK-014"})}}

    changes = compute_diff(old, new)

    assert len(changes) == 1
    assert changes[0].field_name == "Risk ID"
    assert changes[0].old_value is None
    assert changes[0].new_value == "RISK-014"


def test_removed_field_on_existing_card_treated_as_field_change():
    old = {"items": {"PVTI_1": _item(fields={"Status": "Triage", "Risk ID": "RISK-014"})}}
    new = {"items": {"PVTI_1": _item(fields={"Status": "Triage"})}}

    changes = compute_diff(old, new)

    assert len(changes) == 1
    assert changes[0].field_name == "Risk ID"
    assert changes[0].old_value == "RISK-014"
    assert changes[0].new_value is None
