"""Shared enforcement helpers — revert logic + bypass-label handling.

Called from the transition check and the precondition dispatcher when
their mode is ``active``. Keeps the side-effect ordering identical
across both call sites.
"""

from __future__ import annotations

import datetime
from typing import Optional


def has_bypass(ctx, repo: str, number: int) -> bool:
    """Return True iff the linked issue carries the configured bypass label."""

    label = (ctx.config or {}).get("bypass_label", "process-override:approved")
    evidence = getattr(ctx, "evidence", None)
    if evidence is None:
        return False
    issue = evidence.issue(repo, number)
    if issue is None:
        return False
    return label in (issue.labels or [])


def clear_bypass(ctx, repo: str, number: int, *, item_id: Optional[str] = None,
                 old_status: Optional[str] = None,
                 new_status: Optional[str] = None) -> None:
    label = (ctx.config or {}).get("bypass_label", "process-override:approved")
    ctx.actions.remove_label(repo, number, label)
    events = getattr(ctx, "bypass_events", None)
    if events is not None:
        events.append({
            "ts": datetime.datetime.now(datetime.UTC).isoformat(),
            "repo": repo,
            "number": number,
            "item_id": item_id,
            "old_status": old_status,
            "new_status": new_status,
        })


def revert_status(ctx, item_id: str, target_status: Optional[str]) -> bool:
    """Revert the card's Status to ``target_status``. Returns True on success.

    Logs (does not raise) when project_id / field / option id can't be
    resolved — the nightly audit picks up the inconsistency.
    """

    if target_status is None:
        return False

    project_id = (ctx.snapshot or {}).get("project_id")
    if not project_id:
        return False

    status_field = (ctx.fields or {}).get("Status")
    if status_field is None:
        return False

    options = status_field.options or {}
    option_id = options.get(target_status)
    if not option_id:
        return False

    try:
        ctx.actions.revert_single_select(project_id, item_id, status_field.id, option_id)
    except Exception:
        return False
    return True
