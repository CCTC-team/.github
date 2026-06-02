"""Milestone-scoped release notes with a CtQ-anchored traceability matrix.

A regulated Release is judged on its notes: a categorised changelog, a matrix
threading **CtQ factor (FRM129 ref + tier) → Risk ID → Requirement ID →
`.feature` evidence → acceptance approver → QA approver** for every requirement
in the milestone, the governing QMS documents, and a release-authorisation block
the workflow fills from the production Environment approval.

The CtQ *tier* and the governing documents are read from the repo's parsed
``.compliance.yml`` — never assumed. The per-requirement fields (Risk ID,
Requirement ID, Feature link, CtQ factor) are parsed from each issue's body with
the same form-aware extractor the board automation uses, so a value reads the
same here as it does at the PR gate. Approver identities and signoff dates come
from the board card and are carried on the milestone item.

Security posture mirrors ``gxp-traceability.yml``: issue/PR bodies are untrusted
data. They are parsed as strings and never interpolated into a shell or into
Python source; this module performs no shell-out at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from project_enforcement.body_parser import extract_field


# Marker rendered wherever a required value is absent, so a gap is visible in the
# notes rather than silently blank.
MISSING = "_missing_"

# Label marking an issue as a regulated requirement — only these get a matrix row.
# Matches the default ``regulated_label`` of the traceability gate.
REGULATED_LABEL = "regulated"

# Changelog grouping. An item joins the first category whose labels it carries;
# anything unmatched falls to "Other changes". Order here is the render order.
CHANGELOG_CATEGORIES = (
    ("⚕️ Validated requirements", {"validation", "compliance", "enhancement"}),
    ("🐛 Fixes", {"bug"}),
    ("🔒 Security", {"security"}),
    ("⚠️ Breaking changes", {"breaking-change"}),
)
OTHER_CATEGORY = "📝 Other changes"


@dataclass
class MilestoneItem:
    """One closed issue (or PR) in the release milestone.

    ``body`` is the raw issue body; the per-requirement fields are parsed from
    it. The approver fields come from the board card, not the body.
    """

    number: int
    title: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    is_pr: bool = False
    acceptance_approver: Optional[str] = None
    acceptance_date: Optional[str] = None
    qa_approver: Optional[str] = None
    qa_date: Optional[str] = None

    @property
    def is_regulated(self) -> bool:
        return REGULATED_LABEL in self.labels


class NotesEvidence(Protocol):
    def milestone_items(self, repo: str, milestone: str) -> list["MilestoneItem"]: ...


def _ctq_tiers(compliance: dict) -> dict[str, str]:
    """Map each declared CtQ factor's FRM129 ref to its tier."""
    out: dict[str, str] = {}
    for factor in (compliance or {}).get("ctq_factors") or []:
        ref = (factor.get("frm129_ref") or "").strip()
        if ref:
            out[ref] = (factor.get("tier") or "").strip()
    return out


def _feature_urls(item_body: str) -> list[str]:
    """Every non-blank line of the ``Feature link:`` section."""
    section = extract_field(item_body, "Feature link") or ""
    return [line.strip() for line in section.splitlines() if line.strip()]


def _ctq_cell(item_body: str, tiers: dict[str, str]) -> str:
    ref = (extract_field(item_body, "CtQ factor") or "").strip()
    if not ref:
        return MISSING
    tier = tiers.get(ref)
    return f"{ref} ({tier})" if tier else f"{ref} (unknown)"


def _approver_cell(approver: Optional[str], date: Optional[str]) -> str:
    if not approver:
        return MISSING
    return f"{approver} ({date})" if date else f"{approver} ({MISSING})"


def _changelog(items: list[MilestoneItem]) -> list[str]:
    lines = ["## Changes", ""]
    buckets: dict[str, list[MilestoneItem]] = {}
    for item in items:
        label_set = set(item.labels)
        title = next(
            (name for name, cat in CHANGELOG_CATEGORIES if label_set & cat),
            OTHER_CATEGORY,
        )
        buckets.setdefault(title, []).append(item)

    ordered = [name for name, _ in CHANGELOG_CATEGORIES] + [OTHER_CATEGORY]
    for title in ordered:
        bucket = buckets.get(title)
        if not bucket:
            continue
        lines.append(f"### {title}")
        for item in sorted(bucket, key=lambda i: i.number):
            lines.append(f"- #{item.number} {item.title}")
        lines.append("")
    return lines


def _traceability_matrix(items: list[MilestoneItem], compliance: dict) -> list[str]:
    tiers = _ctq_tiers(compliance)
    regulated = sorted(
        (i for i in items if i.is_regulated), key=lambda i: i.number
    )

    lines = ["## Traceability matrix", ""]
    if not regulated:
        lines += ["_No regulated requirements in this milestone._", ""]
        return lines

    lines += [
        "| CtQ factor | Issue | Risk ID | Requirement ID | Feature evidence | Acceptance | QA |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in regulated:
        risk = (extract_field(item.body, "Risk ID") or "").strip() or MISSING
        req = (extract_field(item.body, "Requirement ID") or "").strip() or MISSING
        features = _feature_urls(item.body)
        feature_cell = "<br>".join(features) if features else MISSING
        lines.append(
            f"| {_ctq_cell(item.body, tiers)} "
            f"| #{item.number} {item.title} "
            f"| {risk} | {req} | {feature_cell} "
            f"| {_approver_cell(item.acceptance_approver, item.acceptance_date)} "
            f"| {_approver_cell(item.qa_approver, item.qa_date)} |"
        )
    lines.append("")
    return lines


def _governing_documents(compliance: dict) -> list[str]:
    lines = ["## Governing documents", ""]
    docs = (compliance or {}).get("governing_documents") or []
    if not docs:
        lines += ["_None declared._", ""]
        return lines
    for doc in sorted(docs, key=lambda d: (d.get("ref") or "")):
        ref = doc.get("ref") or MISSING
        label = doc.get("title") or doc.get("role") or ""
        role = doc.get("role") or ""
        lines.append(f"- **{ref}** — {label} ({role})")
    lines.append("")
    return lines


def build_notes(repo, milestone, tag, prev_tag, compliance, evidence) -> str:
    """Render the full markdown release notes for ``milestone``.

    ``compliance`` is the parsed ``.compliance.yml`` (or ``{}``); ``evidence``
    supplies the milestone's items via ``milestone_items(repo, milestone)``.
    """
    items = list(evidence.milestone_items(repo, milestone))

    summary = f"Release **{tag}** of `{repo}` — milestone **{milestone}**."
    if prev_tag:
        summary += f" Changes since **{prev_tag}**."

    lines = [f"# {repo} {tag}", "", summary, ""]
    lines += _changelog(items)
    lines += _traceability_matrix(items, compliance or {})
    lines += _governing_documents(compliance or {})
    lines += [
        "## Release authorisation",
        "",
        "_To be completed at the `production` Environment approval: approver "
        "identity, UTC timestamp, and the released image digest "
        "(`ghcr.io/…@sha256:…`)._",
        "",
    ]
    return "\n".join(lines)
