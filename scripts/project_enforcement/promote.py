"""Decision logic for the PR-driven card promoter.

The reusable workflow shells into this module so the choice of "move
the card forward / skip and explain why" stays unit-testable. Side
effects (the GraphQL mutation) remain in the workflow.

Forward-only states: ``Code review``, ``V&V tests pass``. Everything
beyond that is human-attested and must never be reached by automation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Optional


# Forward chain — used to decide whether moving to a target is a
# forward move from the current state.
_LIFECYCLE = (
    "Triage",
    "Risk linked",
    "Requirement defined",
    "In development",
    "Code review",
    "V&V tests pass",
)


@dataclass
class Decision:
    action: str         # "skip" | "move"
    reason: str
    target_status: Optional[str] = None


def _is_forward(current: Optional[str], target: str) -> bool:
    if current is None:
        return True
    if current not in _LIFECYCLE or target not in _LIFECYCLE:
        return False
    return _LIFECYCLE.index(target) > _LIFECYCLE.index(current)


def decide(
    *,
    event: str,
    project_number,
    allowed_project_ids,
    resolved_project_id: Optional[str],
    current_status: Optional[str],
    pr_state: Optional[str] = None,
    pr_merged: bool = False,
    check_conclusion: Optional[str] = None,
) -> Decision:
    # Guard: no LIFECYCLE_PROJECT_NUMBER on the repo.
    if project_number in (None, "", 0, "0"):
        return Decision("skip", "no LIFECYCLE_PROJECT_NUMBER set on this repo — promotion skipped.")

    # Allowlist: only promote on projects this org tracks.
    if not resolved_project_id:
        return Decision("skip", "project number did not resolve to a project id — promotion skipped.")
    if resolved_project_id not in allowed_project_ids:
        return Decision(
            "skip",
            f"project `{resolved_project_id}` is not in `.github/project-enforcement.yml` — "
            "refusing to write to an unmonitored board.",
        )

    if event == "pull_request_opened":
        if pr_state == "closed" or pr_merged:
            return Decision("skip", "PR is no longer open — nothing to promote.")
        if _is_forward(current_status, "Code review"):
            return Decision("move", "PR opened on regulated issue.", target_status="Code review")
        return Decision("skip", f"card is already at or past `Code review` (currently `{current_status}`).")

    if event == "check_suite_completed":
        if check_conclusion != "success":
            return Decision(
                "skip",
                f"check_suite conclusion `{check_conclusion}` is not `success` — not promoting.",
            )
        if _is_forward(current_status, "V&V tests pass"):
            return Decision("move", "Required checks went green.", target_status="V&V tests pass")
        return Decision(
            "skip",
            f"card is already at or past `V&V tests pass` (currently `{current_status}`).",
        )

    if event == "pull_request_closed":
        # Decision 6: merging does nothing automatic.
        return Decision("skip", "PR closed — no automatic promotion past V&V tests pass.")

    return Decision("skip", f"unrecognised event `{event}`.")


def _emit(decision: Decision):
    print(json.dumps({
        "action": decision.action,
        "reason": decision.reason,
        "target_status": decision.target_status,
    }))


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--project-number", default="")
    parser.add_argument("--resolved-project-id", default="")
    parser.add_argument("--allowed-project-ids", default="", help="comma-separated")
    parser.add_argument("--current-status", default="")
    parser.add_argument("--pr-state", default="")
    parser.add_argument("--pr-merged", default="false")
    parser.add_argument("--check-conclusion", default="")
    args = parser.parse_args(argv)

    allowed = [p.strip() for p in args.allowed_project_ids.split(",") if p.strip()]
    decision = decide(
        event=args.event,
        project_number=args.project_number or None,
        allowed_project_ids=allowed,
        resolved_project_id=args.resolved_project_id or None,
        current_status=args.current_status or None,
        pr_state=args.pr_state or None,
        pr_merged=args.pr_merged.lower() == "true",
        check_conclusion=args.check_conclusion or None,
    )
    _emit(decision)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
