"""When the Acceptance/QA Approver changes on a card past that column, log
an audit comment. Does not revert — the change might be a legitimate
correction; the goal is the audit trail.
"""

from __future__ import annotations


_ACCEPTANCE_STATUSES_OR_LATER = {"User acceptance", "QA approved", "Released"}
_QA_APPROVED_STATUSES_OR_LATER = {"QA approved", "Released"}


def check(change, ctx, evidence=None) -> None:
    if change.kind != "field_change":
        return
    if change.field_name not in ("Acceptance Approver", "QA Approver"):
        return

    item = (ctx.snapshot or {}).get("items", {}).get(change.item_id, {})
    status = (item.get("fields") or {}).get("Status")
    if change.field_name == "Acceptance Approver":
        relevant = status in _ACCEPTANCE_STATUSES_OR_LATER
    else:
        relevant = status in _QA_APPROVED_STATUSES_OR_LATER

    if not relevant:
        return

    repo = item.get("source_repo") or change.source_repo
    number = item.get("number")
    if not repo or not number:
        return

    body = (
        f"**Approver drift — `{change.field_name}` changed on a card past its review column**\n\n"
        f"Card status: `{status}`\n"
        f"Previous approver: `{change.old_value or '_unset_'}`\n"
        f"New approver: `{change.new_value or '_unset_'}`\n\n"
        "Logging this for the audit trail. If the change is legitimate, no further action is "
        "needed; if it isn't, revert it on the card and follow up with the new approver."
    )
    ctx.actions.post_comment(repo, number, body)


def register(registry):
    registry["drift_approver_identity"] = check
