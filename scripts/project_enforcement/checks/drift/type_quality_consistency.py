"""When Test Type or Critical-to-Quality changes, check the combination
is consistent (CtQ=Yes + Test Type=N/A is invalid).
"""

from __future__ import annotations


def check(change, ctx, evidence=None) -> None:
    if change.kind != "field_change":
        return
    if change.field_name not in ("Test Type", "Critical-to-Quality"):
        return

    item = (ctx.snapshot or {}).get("items", {}).get(change.item_id, {})
    fields = item.get("fields") or {}

    ctq = (fields.get("Critical-to-Quality") or "").strip().lower()
    test_type = (fields.get("Test Type") or "").strip()

    if ctq == "yes" and test_type in {"N/A", "None", ""}:
        repo = item.get("source_repo") or change.source_repo
        number = item.get("number")
        if not repo or not number:
            return
        body = (
            "**Inconsistent combination — Critical-to-Quality vs Test Type**\n\n"
            f"`Critical-to-Quality=Yes` requires a Test Type that includes PQ "
            f"(currently `{test_type or '_unset_'}`). Either downgrade the CtQ field or "
            "set a Test Type appropriate for a critical feature."
        )
        ctx.actions.post_comment(repo, number, body)


def register(registry):
    registry["drift_type_quality"] = check
