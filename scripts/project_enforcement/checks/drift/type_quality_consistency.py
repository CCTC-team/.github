"""When Test Type or Critical-to-Quality changes, check the combination
is consistent. A Critical factor needs a Test Type that includes PQ; an
Important factor needs some Test Type (PQ not required); both are
inconsistent with N/A. A No factor carries no constraint.
"""

from __future__ import annotations

from project_enforcement import ctq


_MISSING_TEST_TYPES = {"N/A", "None", ""}


def check(change, ctx, evidence=None) -> None:
    if change.kind != "field_change":
        return
    if change.field_name not in ("Test Type", "Critical-to-Quality"):
        return

    item = (ctx.snapshot or {}).get("items", {}).get(change.item_id, {})
    fields = item.get("fields") or {}

    tier = ctq.tier(fields)
    test_type = (fields.get("Test Type") or "").strip()
    shown = test_type or "_unset_"

    if tier == "critical":
        # A Critical factor needs a Test Type that includes PQ. A present
        # but non-PQ type (e.g. OQ) is just as inconsistent as N/A.
        if test_type in ctq.CRITICAL_TEST_TYPES:
            return
        body = (
            "**Inconsistent combination — Critical-to-Quality vs Test Type**\n\n"
            f"A Critical `Critical-to-Quality` factor requires a Test Type that includes PQ "
            f"(currently `{shown}`). Either lower the Critical-to-Quality tier or "
            "set a Test Type appropriate for a critical feature."
        )
    elif tier == "important":
        # An Important factor needs *some* Test Type (PQ not required);
        # only a missing/N/A type is inconsistent.
        if test_type not in _MISSING_TEST_TYPES:
            return
        body = (
            "**Inconsistent combination — Critical-to-Quality vs Test Type**\n\n"
            f"An Important `Critical-to-Quality` factor still requires a Test Type "
            f"(currently `{shown}`). PQ is not required, but N/A is not appropriate "
            "for an Important factor — set a verification Test Type."
        )
    else:
        return

    repo = item.get("source_repo") or change.source_repo
    number = item.get("number")
    if not repo or not number:
        return
    ctx.actions.post_comment(repo, number, body)


def register(registry):
    registry["drift_type_quality"] = check
