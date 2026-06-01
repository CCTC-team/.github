"""In development precondition.

Assignee present, Iteration set, Test Type set. A Critical
Critical-to-Quality factor must have a Test Type that includes PQ;
Important and No factors carry no PQ constraint (Important still needs
a Test Type, caught by the generic "Test Type unset" rule).
"""

from __future__ import annotations

from project_enforcement import ctq


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

    if ctq.tier(fields) == "critical" and test_type and test_type not in ctq.CRITICAL_TEST_TYPES:
        reasons.append(
            f"A Critical `Critical-to-Quality` factor requires `Test Type` to include PQ "
            f"(one of: {', '.join(sorted(ctq.CRITICAL_TEST_TYPES))}); got `{test_type}`."
        )

    return reasons
