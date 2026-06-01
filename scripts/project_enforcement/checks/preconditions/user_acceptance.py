"""User acceptance precondition.

Acceptance checklist ticked, Acceptance Approver set and valid,
segregation of duties against issue author and PR commit authors.

This is the feature-level acceptance sign-off done during development in
a dev/test environment — an end-user representative confirms the feature
meets the URS. It is NOT the formal Performance Qualification (PQ): the
genuine PQ is performed on the built release candidate in a qualified
environment at the release-pipeline authorisation gate, not on the board.
"""

from __future__ import annotations

from project_enforcement.checkboxes import parse_checklist


ACCEPTANCE_CHECKLIST_LABELS = (
    "Feature meets the user requirement against the URS in a development/test environment",
    "Workflow is usable in practice (not just technically passing)",
)


def _parse_acceptance_checks(body: str) -> dict[str, bool]:
    parsed = dict(parse_checklist(body, "User acceptance checklist:"))
    return {label: parsed.get(label, False) for label in ACCEPTANCE_CHECKLIST_LABELS}


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    fields = item_meta.get("fields") or {}
    repo = item_meta.get("source_repo")
    number = item_meta.get("number")

    if not repo or not number:
        return ["Card has no linked source issue."]

    issue = evidence.issue(repo, number)
    if issue is None:
        return [f"Could not read source issue {repo}#{number}."]

    checks = _parse_acceptance_checks(issue.body)
    unticked = [label for label, ticked in checks.items() if not ticked]
    for label in unticked:
        reasons.append(f"User acceptance checklist item not ticked: `{label}`.")

    approver = (fields.get("Acceptance Approver") or "").strip().lstrip("@")
    if not approver:
        reasons.append("`Acceptance Approver` field is unset.")
    else:
        if not evidence_user_exists(evidence, approver, ctx):
            reasons.append(f"`Acceptance Approver` `{approver}` is not a known GitHub user.")
        if approver == issue.author:
            reasons.append(
                f"`Acceptance Approver` (`{approver}`) is the issue author — segregation of duties."
            )
        commit_authors: set[str] = set()
        for pr in evidence.linked_prs(repo, number):
            commit_authors.update(pr.commit_authors)
        if approver in commit_authors:
            reasons.append(
                f"`Acceptance Approver` (`{approver}`) authored commits on the linked PR — segregation of duties."
            )

    return reasons


def evidence_user_exists(evidence, login: str, ctx=None) -> bool:
    actions = getattr(ctx, "actions", None) if ctx else None
    if actions is not None and hasattr(actions, "user_exists"):
        return actions.user_exists(login)
    return True
