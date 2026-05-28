"""Behaviour of resolve_fields(project_json, required=...) -> dict[str, FieldRef].

The handler resolves field IDs by **name** at the start of each run so the
config doesn't have to encode project-specific IDs. Single-select fields
also carry an option name→id map so the handler can write values back.
"""

import pytest

from project_enforcement.fields import FieldRef, resolve_fields


def _project(fields_meta):
    return {"fields_meta": fields_meta}


def test_returns_name_to_field_ref_mapping():
    project = _project(
        {
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
                "id": "PVTF_risk",
                "name": "Risk ID",
                "dataType": "TEXT",
            },
        }
    )

    fields = resolve_fields(project)

    assert set(fields) == {"Status", "Risk ID"}
    assert fields["Status"].id == "PVTSSF_status"
    assert fields["Risk ID"].id == "PVTF_risk"


def test_single_select_field_carries_options_map():
    project = _project(
        {
            "Status": {
                "__typename": "ProjectV2SingleSelectField",
                "id": "PVTSSF_status",
                "name": "Status",
                "dataType": "SINGLE_SELECT",
                "options": [
                    {"id": "opt_triage", "name": "Triage"},
                    {"id": "opt_risk", "name": "Risk linked"},
                ],
            }
        }
    )

    fields = resolve_fields(project)

    assert fields["Status"].data_type == "SINGLE_SELECT"
    assert fields["Status"].options == {"Triage": "opt_triage", "Risk linked": "opt_risk"}


def test_plain_text_field_has_no_options():
    project = _project(
        {
            "Risk ID": {
                "__typename": "ProjectV2Field",
                "id": "PVTF_risk",
                "name": "Risk ID",
                "dataType": "TEXT",
            },
        }
    )

    fields = resolve_fields(project)

    assert fields["Risk ID"].data_type == "TEXT"
    assert fields["Risk ID"].options is None


def test_missing_required_field_raises():
    project = _project(
        {
            "Risk ID": {
                "__typename": "ProjectV2Field",
                "id": "PVTF_risk",
                "name": "Risk ID",
                "dataType": "TEXT",
            },
        }
    )

    with pytest.raises(KeyError) as excinfo:
        resolve_fields(project, required=["Status", "Risk ID"])

    assert "Status" in str(excinfo.value)


def test_all_required_fields_present_does_not_raise():
    project = _project(
        {
            "Status": {
                "__typename": "ProjectV2SingleSelectField",
                "id": "PVTSSF_status",
                "name": "Status",
                "dataType": "SINGLE_SELECT",
                "options": [{"id": "opt_triage", "name": "Triage"}],
            },
            "Risk ID": {
                "__typename": "ProjectV2Field",
                "id": "PVTF_risk",
                "name": "Risk ID",
                "dataType": "TEXT",
            },
        }
    )

    fields = resolve_fields(project, required=["Status", "Risk ID"])
    assert "Status" in fields
    assert "Risk ID" in fields


def test_field_ref_is_a_dataclass_like_object():
    ref = FieldRef(id="X", name="Status", data_type="SINGLE_SELECT", options={"A": "1"})
    assert ref.id == "X"
    assert ref.options == {"A": "1"}
