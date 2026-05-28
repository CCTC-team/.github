"""End-to-end smoke test for the handler.

Drives the handler against a recorded project_json fixture, with the
GraphQL fetcher, snapshot reader, and snapshot writer all stubbed out.
Asserts that the (otherwise empty) check registry is invoked with the
expected CardChange objects, and that the snapshot writer is called
with the expected new state.
"""

from project_enforcement import handler
from project_enforcement.snapshot import CardChange


# A small recorded project_json — what fetch_project would return.
FIXTURE_PROJECT = {
    "project_id": "PVT_test",
    "owner": "CCTC-team",
    "number": 31,
    "title": "[TEST] Regulated Feature Lifecycle",
    "items": {
        "PVTI_existing": {
            "content_id": "I_1",
            "content_type": "issue",
            "source_repo": "CCTC-team/some-repo",
            "number": 11,
            "title": "Existing feature",
            "fields": {"Status": "Risk linked"},
        },
        "PVTI_new": {
            "content_id": "I_2",
            "content_type": "issue",
            "source_repo": "CCTC-team/other-repo",
            "number": 22,
            "title": "Brand new feature",
            "fields": {"Status": "Triage"},
        },
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
                {"id": "opt_qa", "name": "QA approved"},
            ],
        }
    },
}


# Prior snapshot — PVTI_existing was at Triage, PVTI_new didn't exist.
PRIOR_SNAPSHOT = {
    "items": {
        "PVTI_existing": {
            "content_id": "I_1",
            "content_type": "issue",
            "source_repo": "CCTC-team/some-repo",
            "fields": {"Status": "Triage"},
        }
    }
}


def _config():
    return {
        "projects": [
            {"owner": "CCTC-team", "number": 31, "name": "[TEST] Lifecycle"},
        ],
        "checks": {"recorder": "evaluate"},
    }


def test_handler_dispatches_diff_to_registered_check(tmp_path):
    seen: list = []

    def recorder(change, ctx):
        seen.append((change, ctx.mode))

    written: list = []

    def write_snapshot(path, snap):
        written.append((path, snap))

    rc = handler.run(
        _config(),
        state_dir=str(tmp_path),
        fetch_project=lambda owner, number: FIXTURE_PROJECT,
        load_snapshot=lambda path: PRIOR_SNAPSHOT,
        write_snapshot=write_snapshot,
        checks={"recorder": recorder},
    )

    assert rc == 0

    kinds = sorted(c.kind for c, _ in seen)
    assert kinds == ["added", "field_change"]

    added = next(c for c, _ in seen if c.kind == "added")
    assert added.item_id == "PVTI_new"
    assert added.source_repo == "CCTC-team/other-repo"

    field_change = next(c for c, _ in seen if c.kind == "field_change")
    assert field_change == CardChange(
        item_id="PVTI_existing",
        content_id="I_1",
        content_type="issue",
        source_repo="CCTC-team/some-repo",
        kind="field_change",
        field_name="Status",
        old_value="Triage",
        new_value="Risk linked",
    )

    # Every dispatch carries the configured mode.
    assert {mode for _, mode in seen} == {"evaluate"}

    # Snapshot writer saw the new state with both items present.
    assert len(written) == 1
    written_path, written_snap = written[0]
    assert str(tmp_path) in written_path
    assert set(written_snap["items"]) == {"PVTI_existing", "PVTI_new"}
    assert written_snap["items"]["PVTI_existing"]["fields"]["Status"] == "Risk linked"


def test_handler_with_off_check_does_not_invoke_it(tmp_path):
    seen: list = []

    def recorder(change, ctx):
        seen.append(change)

    rc = handler.run(
        {**_config(), "checks": {"recorder": "off"}},
        state_dir=str(tmp_path),
        fetch_project=lambda owner, number: FIXTURE_PROJECT,
        load_snapshot=lambda path: PRIOR_SNAPSHOT,
        write_snapshot=lambda path, snap: None,
        checks={"recorder": recorder},
    )

    assert rc == 0
    assert seen == []


def test_handler_writes_snapshot_even_when_nothing_changed(tmp_path):
    write_called = []

    rc = handler.run(
        _config(),
        state_dir=str(tmp_path),
        fetch_project=lambda owner, number: FIXTURE_PROJECT,
        load_snapshot=lambda path: handler.to_snapshot(FIXTURE_PROJECT),
        write_snapshot=lambda path, snap: write_called.append(path),
        checks={},
    )

    assert rc == 0
    assert len(write_called) == 1


def test_all_checks_off_helper():
    assert handler.all_checks_off({"checks": {"a": "off"}, "preconditions": {"b": "off"}}) is True
    assert handler.all_checks_off({"checks": {"a": "evaluate"}}) is False
    assert handler.all_checks_off({"preconditions": {"b": "active"}}) is False
    assert handler.all_checks_off({}) is True
