"""State-machine transition check.

Fires on Status field changes. Forward skips and post-side-exit jumps
fail the gate — see ``project_enforcement.state_machine`` for the rules.
In evaluate mode the check only comments and labels; the revert step is
added under Phase 8 once telemetry shows the gate is well-calibrated.
"""

from __future__ import annotations

from project_enforcement.enforcement import clear_bypass, has_bypass, revert_status
from project_enforcement.snapshot import CardChange
from project_enforcement.state_machine import legal_transition


VIOLATION_LABEL = "process-violation"


def _format_value(value):
    if value is None:
        return "_unset_"
    return f"`{value}`"


def check(change: CardChange, ctx) -> None:
    if change.kind != "field_change" or change.field_name != "Status":
        return
    if legal_transition(change.old_value, change.new_value):
        return

    items = (ctx.snapshot or {}).get("items") or {}
    item_meta = items.get(change.item_id) or {}
    number = item_meta.get("number")
    repo = item_meta.get("source_repo") or change.source_repo

    if not number or not repo:
        # Draft issue, or a card that lost its content link — nothing to
        # comment on. The audit phase will surface it via a different
        # route.
        return

    bypass_label = (ctx.config or {}).get("bypass_label", "process-override:approved")
    body = (
        "**Process violation — illegal status transition**\n\n"
        f"This card moved from {_format_value(change.old_value)} "
        f"to {_format_value(change.new_value)}. "
        "That skip is not permitted by the regulated lifecycle: forward moves "
        "must advance one column at a time so each gate (Code review, V&V, PQ, "
        "QA) has a chance to fire.\n\n"
        f"Mode: `{ctx.mode}`. "
        + (
            "The card has been left where it is for now — this gate is in "
            "evaluate mode while telemetry is gathered."
            if ctx.mode != "active"
            else "If this transition is intentional, ask an org admin to apply "
                 f"`{bypass_label}` and try again — the bypass is single-use."
        )
    )
    ctx.actions.post_comment(repo, number, body)
    ctx.actions.apply_label(repo, number, VIOLATION_LABEL)

    if ctx.mode != "active":
        return

    if has_bypass(ctx, repo, number):
        clear_bypass(
            ctx, repo, number,
            item_id=change.item_id,
            old_status=change.old_value,
            new_status=change.new_value,
        )
        return

    revert_status(ctx, change.item_id, change.old_value)


def register(registry: dict) -> None:
    registry["transition"] = check
