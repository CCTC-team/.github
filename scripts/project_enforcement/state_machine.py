"""Regulated-feature lifecycle state machine.

The board's Status column is a forward-only chain. Cards move one
column at a time. Backward moves are always allowed — they recover
from a mistaken advance. Two side-exit statuses (Redundant, Archived)
are reachable from anywhere; the only legal restoration target out of
them is Triage, so a card cannot launder its history by being archived
and then dropped back in halfway down the chain.
"""

from __future__ import annotations

from typing import Optional


LIFECYCLE: tuple[str, ...] = (
    "Triage",
    "Risk linked",
    "Requirement defined",
    "In development",
    "Code review",
    "V&V tests pass",
    "User acceptance",
    "QA approved",
    "Released",
)


SIDE_EXITS: tuple[str, ...] = ("Redundant", "Archived")


def legal_transition(old: Optional[str], new: Optional[str]) -> bool:
    if new is None:
        # Clearing the Status field is treated as illegal — the handler
        # would have nothing to anchor a precondition check against.
        return False

    if old == new:
        return True

    if new in SIDE_EXITS:
        return True

    if old in SIDE_EXITS:
        return new == "Triage"

    if old is None:
        # First time a card lands on the board — must enter at Triage.
        return new == "Triage"

    if old not in LIFECYCLE or new not in LIFECYCLE:
        return False

    old_idx = LIFECYCLE.index(old)
    new_idx = LIFECYCLE.index(new)

    if new_idx <= old_idx:
        # Backward (or same) within the chain is legal.
        return True

    return new_idx == old_idx + 1
