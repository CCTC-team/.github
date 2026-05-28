"""When a PQ/QA Signoff Date changes, validate it.

Rules: not in the future, not before the issue was opened, and the PQ
date is not after the QA date (when both are present).
"""

from __future__ import annotations

import datetime


_DATE_FIELDS = {"PQ Signoff Date", "QA Signoff Date"}


def _parse(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None


def check(change, ctx, evidence=None) -> None:
    if change.kind != "field_change" or change.field_name not in _DATE_FIELDS:
        return

    new_date = _parse(change.new_value)
    if new_date is None:
        return  # An invalid format is a parse error, not a drift signal.

    item = (ctx.snapshot or {}).get("items", {}).get(change.item_id, {})
    repo = item.get("source_repo") or change.source_repo
    number = item.get("number")
    if not repo or not number:
        return

    reasons: list[str] = []
    today = datetime.date.today()
    if new_date > today:
        reasons.append(f"`{change.field_name}` `{change.new_value}` is in the future.")

    evidence = evidence if evidence is not None else getattr(ctx, "evidence", None)
    issue = evidence.issue(repo, number) if evidence is not None else None
    if issue is not None:
        opened = _parse(issue.opened_at)
        if opened and new_date < opened:
            reasons.append(
                f"`{change.field_name}` `{change.new_value}` is before the issue was opened "
                f"(`{issue.opened_at}`)."
            )

    other_field = "QA Signoff Date" if change.field_name == "PQ Signoff Date" else "PQ Signoff Date"
    other_value = (item.get("fields") or {}).get(other_field)
    other_date = _parse(other_value)
    if other_date is not None:
        pq_date, qa_date = (
            (new_date, other_date)
            if change.field_name == "PQ Signoff Date"
            else (other_date, new_date)
        )
        if pq_date > qa_date:
            reasons.append(
                f"PQ ≤ QA expected, but `PQ Signoff Date` (`{pq_date.isoformat()}`) is "
                f"after the QA date (`{qa_date.isoformat()}`)."
            )

    if not reasons:
        return

    body = "**Date drift detected**\n\n" + "\n".join(f"- {r}" for r in reasons)
    ctx.actions.post_comment(repo, number, body)


def register(registry):
    registry["drift_date_sanity"] = check
