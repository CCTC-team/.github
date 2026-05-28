"""Code review precondition: at least one open linked PR on the source repo."""

from __future__ import annotations


def check(item_meta, ctx, evidence) -> list[str]:
    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return ["Card has no linked source issue, so no PR can be located."]

    prs = evidence.linked_prs(repo, number)
    open_prs = [p for p in prs if p.state == "OPEN"]
    if not open_prs:
        return [
            f"No open PR on `{repo}` linked to issue #{number}. Open a PR with "
            "`Closes #N` before moving the card to Code review."
        ]
    return []
