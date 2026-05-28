"""In development precondition.

Assignee present, Iteration set, Test Type set. If Critical-to-Quality
is Yes, Test Type must include PQ.
"""

from __future__ import annotations


_CTQ_TEST_TYPES = {"PQ", "OQ+PQ", "IQ+OQ+PQ"}


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    fields = item_meta.get("fields") or {}

    assignees = (fields.get("Assignees") or "").strip()
    if not assignees:
        repo = item_meta.get("source_repo")
        number = item_meta.get("number")
        if repo and number:
            issue = evidence.issue(repo, number)
            if issue is not None and issue.assignees:
                assignees = ",".join(issue.assignees)

    if not assignees:
        reasons.append("Card has no assignee.")

    if not (fields.get("Iteration") or "").strip():
        reasons.append("`Iteration` field is unset.")

    test_type = (fields.get("Test Type") or "").strip()
    if not test_type:
        reasons.append("`Test Type` field is unset.")

    ctq = (fields.get("Critical-to-Quality") or "").strip().lower()
    if ctq == "yes" and test_type and test_type not in _CTQ_TEST_TYPES:
        reasons.append(
            f"`Critical-to-Quality=Yes` requires `Test Type` to include PQ "
            f"(one of: {', '.join(sorted(_CTQ_TEST_TYPES))}); got `{test_type}`."
        )

    return reasons
