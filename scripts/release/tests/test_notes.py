"""Tests for the milestone-scoped release-notes generator.

The generator turns a milestone's closed issues plus the repo's
``.compliance.yml`` into inspector-facing notes: a categorised changelog, a
CtQ-anchored traceability matrix (one row per regulated requirement), the list
of governing QMS documents, and a release-authorisation placeholder the workflow
fills from the production approval.

Issue bodies here are written the way GitHub's issue forms render them — a
``### Label:`` heading followed by the value — because that is what the
generator parses in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from release import notes
from release.notes import MilestoneItem


@dataclass
class StubNotesEvidence:
    """Scripted milestone items for tests."""

    items: dict[tuple[str, str], list[MilestoneItem]] = field(default_factory=dict)

    def milestone_items(self, repo: str, milestone: str) -> list[MilestoneItem]:
        return self.items.get((repo, milestone), [])


def body(risk="RISK-014", req="REQ-024", features=("https://x/a.feature",), ctq="FRM129-XYZ-001#3"):
    """A form-rendered regulated-feature issue body. Pass None to omit a field."""
    parts = []
    if risk is not None:
        parts.append(f"### Risk ID:\n\n{risk}\n")
    if req is not None:
        parts.append(f"### Requirement ID:\n\n{req}\n")
    if features is not None:
        parts.append("### Feature link:\n\n" + "\n".join(features) + "\n")
    if ctq is not None:
        parts.append(f"### CtQ factor:\n\n{ctq}\n")
    return "\n".join(parts)


def compliance():
    return {
        "ctq_factors": [
            {"frm129_ref": "FRM129-XYZ-001#3", "tier": "critical"},
            {"frm129_ref": "FRM129-XYZ-002#1", "tier": "important"},
        ],
        "governing_documents": [
            {"ref": "CCTU/SOP040", "title": "Computer System Validation", "role": "csv"},
            {"ref": "CCTU/GD073", "title": "Risk Assessment", "role": "risk-assessment"},
        ],
    }


def regulated_item(number, title, **kw):
    return MilestoneItem(
        number=number,
        title=title,
        body=body(**{k: v for k, v in kw.items() if k in ("risk", "req", "features", "ctq")}),
        labels=["regulated", "validation"],
        acceptance_approver=kw.get("acceptance_approver", "alice"),
        acceptance_date=kw.get("acceptance_date", "2026-05-01"),
        qa_approver=kw.get("qa_approver", "bob"),
        qa_date=kw.get("qa_date", "2026-05-02"),
    )


def build(items, comp=None, images=None):
    ev = StubNotesEvidence(items={("CCTC-team/trialview", "v1.4.0"): items})
    return notes.build_notes(
        repo="CCTC-team/trialview",
        milestone="v1.4.0",
        tag="v1.4.0",
        prev_tag="v1.3.0",
        compliance=comp if comp is not None else compliance(),
        evidence=ev,
        images=images,
    )


TWO_IMAGES = {
    "trialview": "ghcr.io/cctc-team/trialview@sha256:" + "a" * 64,
    "trialview-api": "ghcr.io/cctc-team/trialview-api@sha256:" + "b" * 64,
}
ONE_IMAGE = {"gtg-web": "ghcr.io/cctc-team/gtg-web@sha256:" + "c" * 64}


class TestReleasedImages:
    def test_two_image_table_lists_every_component(self):
        md = build([regulated_item(24, "Feature")], images=TWO_IMAGES)
        section = md.split("## Released images", 1)[1].split("##", 1)[0]
        assert "trialview" in section and "trialview-api" in section
        assert "sha256:" + "a" * 64 in section
        assert "sha256:" + "b" * 64 in section

    def test_single_image_table(self):
        md = build([regulated_item(24, "Feature")], images=ONE_IMAGE)
        section = md.split("## Released images", 1)[1].split("##", 1)[0]
        assert "gtg-web" in section
        assert "sha256:" + "c" * 64 in section

    def test_components_sorted_by_name(self):
        md = build([regulated_item(24, "Feature")], images=TWO_IMAGES)
        assert md.index("| trialview ") < md.index("| trialview-api ")

    def test_no_images_arg_omits_the_section(self):
        md = build([regulated_item(24, "Feature")])
        assert "## Released images" not in md


class TestChangelog:
    def test_groups_items_by_label_category(self):
        items = [
            regulated_item(24, "Add randomisation endpoint"),
            MilestoneItem(31, "Fix off-by-one in dosing", body="", labels=["bug"]),
            MilestoneItem(40, "Patch deserialisation CVE", body="", labels=["security"]),
        ]
        md = build(items)
        assert "Validated requirements" in md
        assert "#24" in md
        assert "Fixes" in md and "#31" in md
        assert "Security" in md and "#40" in md

    def test_uncategorised_item_falls_to_other(self):
        items = [MilestoneItem(50, "Tidy docs", body="", labels=["documentation"])]
        md = build(items)
        assert "Other changes" in md
        assert "#50" in md


class TestTraceabilityMatrix:
    def test_one_row_per_regulated_requirement_threaded_ctq_to_qa(self):
        md = build([regulated_item(24, "Add randomisation endpoint")])
        # CtQ factor resolved against compliance for its tier, threaded to approvers.
        assert "FRM129-XYZ-001#3 (critical)" in md
        assert "RISK-014" in md
        assert "REQ-024" in md
        assert "a.feature" in md
        assert "alice" in md and "2026-05-01" in md
        assert "bob" in md and "2026-05-02" in md

    def test_non_regulated_issue_excluded_from_matrix_but_listed(self):
        items = [
            regulated_item(24, "Regulated feature"),
            MilestoneItem(31, "Plain bug", body="", labels=["bug"]),
        ]
        md = build(items)
        matrix = md.split("## Traceability matrix", 1)[1].split("##", 1)[0]
        assert "#24" in matrix
        assert "#31" not in matrix  # non-regulated: in changelog, not the matrix
        assert "#31" in md  # but still listed somewhere

    def test_missing_fields_flagged(self):
        item = regulated_item(24, "Incomplete", risk=None, features=None)
        item.qa_approver = None
        md = build([item])
        assert "_missing_" in md

    def test_unknown_ctq_ref_marked_unknown(self):
        item = regulated_item(24, "Bad ref", ctq="FRM129-NOPE-999#9")
        md = build([item])
        assert "FRM129-NOPE-999#9 (unknown)" in md

    def test_multiple_feature_urls_all_present(self):
        item = regulated_item(
            24, "Two features",
            features=("https://x/a.feature", "https://x/b.feature"),
        )
        md = build([item])
        assert "a.feature" in md and "b.feature" in md


class TestGoverningDocuments:
    def test_lists_governing_documents_sorted_by_ref(self):
        md = build([regulated_item(24, "Feature")])
        section = md.split("## Governing documents", 1)[1]
        gd73 = section.index("CCTU/GD073")
        sop40 = section.index("CCTU/SOP040")
        assert gd73 < sop40  # GD073 sorts before SOP040
        assert "csv" in section and "risk-assessment" in section

    def test_no_governing_documents_states_none(self):
        comp = {"ctq_factors": compliance()["ctq_factors"], "governing_documents": []}
        md = build([regulated_item(24, "Feature")], comp=comp)
        assert "## Governing documents" in md
        assert "None declared" in md


class TestStructureAndDeterminism:
    def test_has_authorisation_placeholder_and_milestone(self):
        md = build([regulated_item(24, "Feature")])
        assert "## Release authorisation" in md
        assert "v1.4.0" in md
        assert "v1.3.0" in md  # prev_tag referenced in the summary

    def test_output_is_deterministic_and_orders_rows_by_issue_number(self):
        items = [
            regulated_item(40, "Later"),
            regulated_item(24, "Earlier"),
        ]
        first = build(items)
        second = build(items)
        assert first == second
        assert first.index("#24") < first.index("#40")
