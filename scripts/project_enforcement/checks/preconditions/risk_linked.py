"""Risk linked precondition: Risk ID field non-empty and matches issue body."""

from __future__ import annotations

from project_enforcement.body_parser import extract_field


def _normalise(value: str) -> str:
    return ",".join(sorted(p.strip() for p in (value or "").split(",") if p.strip()))


def check(item_meta: dict, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    fields = item_meta.get("fields") or {}
    field_value = (fields.get("Risk ID") or "").strip()
    if not field_value:
        reasons.append("`Risk ID` field on the card is empty.")

    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return reasons

    issue = evidence.issue(repo, number)
    if issue is None:
        reasons.append(f"Could not read source issue {repo}#{number}.")
        return reasons

    body_value = extract_field(issue.body, "Risk ID:") or ""
    if not body_value.strip():
        reasons.append("`Risk ID:` line on the linked issue is empty.")

    if field_value and body_value and _normalise(field_value) != _normalise(body_value.strip()):
        reasons.append(
            f"`Risk ID` on the card (`{field_value}`) does not match the issue body "
            f"(`{body_value.strip()}`). The issue body is canonical."
        )

    return reasons
