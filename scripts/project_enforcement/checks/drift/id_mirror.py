"""When Risk ID or Requirement ID changes on the card, compare to the
issue body. Mismatch → comment naming both values and flag the body as
canonical.
"""

from __future__ import annotations

from project_enforcement.body_parser import extract_field


_MIRRORED_FIELDS = {"Risk ID", "Requirement ID"}


def _normalise(value):
    return ",".join(sorted(p.strip() for p in (value or "").split(",") if p.strip()))


def check(change, ctx, evidence=None) -> None:
    if change.kind != "field_change" or change.field_name not in _MIRRORED_FIELDS:
        return

    item = (ctx.snapshot or {}).get("items", {}).get(change.item_id, {})
    repo = item.get("source_repo") or change.source_repo
    number = item.get("number")
    if not repo or not number:
        return

    evidence = evidence if evidence is not None else getattr(ctx, "evidence", None)
    if evidence is None:
        return
    issue = evidence.issue(repo, number)
    if issue is None:
        return

    body_value = (extract_field(issue.body, f"{change.field_name}:") or "").strip()
    card_value = (change.new_value or "").strip()

    if not body_value and not card_value:
        return
    if _normalise(body_value) == _normalise(card_value):
        return

    body = (
        f"**Field drift detected — `{change.field_name}`**\n\n"
        f"Card now reads: `{card_value or '_empty_'}`\n"
        f"Issue body reads: `{body_value or '_empty_'}`\n\n"
        "The issue body is the canonical source. Either edit the issue body to "
        "match the card, or revert the card to match the issue."
    )
    ctx.actions.post_comment(repo, number, body)


def register(registry):
    registry["drift_id_mirror"] = check
