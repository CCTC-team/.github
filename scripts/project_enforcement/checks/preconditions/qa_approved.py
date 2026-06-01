"""QA approved precondition.

QA checklist ticked, QA Approver + QA Signoff Date set, date in valid
range, three distinct identities (author / Acceptance Approver / QA
Approver), and Deviation Ref if any prior gxp-traceability run failed.

This is the feature-level QA of the development evidence (URS → V&V →
user-acceptance chain). The final QA of the assembled release — together
with the release-level Performance Qualification — is recorded at the
release-pipeline authorisation gate, not on the board.
"""

from __future__ import annotations

import datetime

from project_enforcement.checkboxes import parse_checklist
from project_enforcement.checks.preconditions.user_acceptance import evidence_user_exists


QA_CHECKLIST_LABELS = (
    "Risk linkage verified against the canonical risk register",
    "URS → V&V evidence chain intact; any deviations are documented",
)


def _parse_qa_checks(body: str) -> dict[str, bool]:
    parsed = dict(parse_checklist(body, "QA review checklist:"))
    return {label: parsed.get(label, False) for label in QA_CHECKLIST_LABELS}


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    fields = item_meta.get("fields") or {}
    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return ["Card has no linked source issue."]

    issue = evidence.issue(repo, number)
    if issue is None:
        return [f"Could not read source issue {repo}#{number}."]

    checks = _parse_qa_checks(issue.body)
    for label, ticked in checks.items():
        if not ticked:
            reasons.append(f"QA review checklist item not ticked: `{label}`.")

    qa_approver = (fields.get("QA Approver") or "").strip().lstrip("@")
    if not qa_approver:
        reasons.append("`QA Approver` field is unset.")
    elif not evidence_user_exists(evidence, qa_approver, ctx):
        reasons.append(f"`QA Approver` `{qa_approver}` is not a known GitHub user.")

    qa_date_raw = (fields.get("QA Signoff Date") or "").strip()
    qa_date = _parse_date(qa_date_raw)
    if not qa_date_raw:
        reasons.append("`QA Signoff Date` is unset.")
    elif qa_date is None:
        reasons.append(f"`QA Signoff Date` `{qa_date_raw}` is not a valid ISO-8601 date.")
    else:
        today = datetime.date.today()
        if qa_date > today:
            reasons.append(f"`QA Signoff Date` `{qa_date_raw}` is in the future.")

    acceptance_date_raw = (fields.get("Acceptance Signoff Date") or "").strip()
    acceptance_date = _parse_date(acceptance_date_raw)
    if qa_date and acceptance_date and qa_date < acceptance_date:
        reasons.append(
            f"`QA Signoff Date` (`{qa_date_raw}`) is earlier than `Acceptance Signoff Date` "
            f"(`{acceptance_date_raw}`)."
        )

    acceptance_approver = (fields.get("Acceptance Approver") or "").strip().lstrip("@")
    if qa_approver:
        commit_authors: set[str] = set()
        for pr in evidence.linked_prs(repo, number):
            commit_authors.update(pr.commit_authors)
        if qa_approver == issue.author:
            reasons.append(
                f"`QA Approver` (`{qa_approver}`) is the issue author — segregation of duties."
            )
        if qa_approver in commit_authors:
            reasons.append(
                f"`QA Approver` (`{qa_approver}`) authored commits on the linked PR — segregation of duties."
            )
        if acceptance_approver and qa_approver == acceptance_approver:
            reasons.append(
                f"`QA Approver` (`{qa_approver}`) is the same as `Acceptance Approver` — segregation of duties."
            )

    # Deviation Ref required when any historical gxp-traceability run failed.
    deviation = (fields.get("Deviation Ref") or "").strip()
    any_failure = any(
        getattr(pr, "failed_check_runs_history", False)
        for pr in evidence.linked_prs(repo, number)
    )
    if any_failure and not deviation:
        reasons.append(
            "Linked PR had a failed gxp-traceability run at some point; `Deviation Ref` must be set."
        )

    return reasons
