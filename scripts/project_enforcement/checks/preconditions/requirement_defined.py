"""Requirement defined precondition.

Requirement ID field non-empty and matches the issue body, plus
Critical-to-Quality chosen on the card.
"""

from __future__ import annotations

from project_enforcement.body_parser import extract_field


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    fields = item_meta.get("fields") or {}

    requirement = (fields.get("Requirement ID") or "").strip()
    if not requirement:
        reasons.append("`Requirement ID` field on the card is empty.")

    ctq = (fields.get("Critical-to-Quality") or "").strip()
    if not ctq:
        reasons.append("`Critical-to-Quality` field on the card is unset.")

    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return reasons

    issue = evidence.issue(repo, number)
    if issue is None:
        reasons.append(f"Could not read source issue {repo}#{number}.")
        return reasons

    body_value = (extract_field(issue.body, "Requirement ID:") or "").strip()
    if not body_value:
        reasons.append("`Requirement ID:` line on the linked issue is empty.")
    elif requirement and body_value != requirement:
        reasons.append(
            f"`Requirement ID` on the card (`{requirement}`) does not match the issue "
            f"body (`{body_value}`). The issue body is canonical."
        )

    return reasons
