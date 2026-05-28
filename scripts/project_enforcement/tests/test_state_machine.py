"""Behaviour of legal_transition(old, new) -> bool.

The lifecycle is a forward-only chain with one-step increments. Backward
moves are always legal (recovery from an over-eager human). The two
side-exit statuses (Redundant, Archived) are reachable from anywhere;
the only legal restoration target from them is Triage.
"""

import pytest

from project_enforcement.state_machine import LIFECYCLE, SIDE_EXITS, legal_transition


# ---- forward path ----

@pytest.mark.parametrize(
    "old,new",
    [
        ("Triage", "Risk linked"),
        ("Risk linked", "Requirement defined"),
        ("Requirement defined", "In development"),
        ("In development", "Code review"),
        ("Code review", "V&V tests pass"),
        ("V&V tests pass", "PQ review"),
        ("PQ review", "QA approved"),
        ("QA approved", "Released"),
    ],
)
def test_one_step_forward_is_legal(old, new):
    assert legal_transition(old, new) is True


@pytest.mark.parametrize(
    "old,new",
    [
        ("Triage", "QA approved"),
        ("Triage", "In development"),
        ("Code review", "Released"),
        ("Risk linked", "PQ review"),
    ],
)
def test_skipping_forward_is_illegal(old, new):
    assert legal_transition(old, new) is False


# ---- backward path ----

@pytest.mark.parametrize(
    "old,new",
    [
        ("Released", "Triage"),
        ("PQ review", "In development"),
        ("QA approved", "Risk linked"),
        ("Released", "QA approved"),
    ],
)
def test_backward_is_always_legal(old, new):
    assert legal_transition(old, new) is True


# ---- side exits ----

@pytest.mark.parametrize("old", LIFECYCLE)
@pytest.mark.parametrize("new", SIDE_EXITS)
def test_anything_to_side_exit_is_legal(old, new):
    assert legal_transition(old, new) is True


@pytest.mark.parametrize("from_exit", SIDE_EXITS)
def test_restore_from_side_exit_to_triage_is_legal(from_exit):
    assert legal_transition(from_exit, "Triage") is True


@pytest.mark.parametrize("from_exit", SIDE_EXITS)
@pytest.mark.parametrize(
    "new",
    ["Risk linked", "In development", "Code review", "QA approved", "Released"],
)
def test_restore_from_side_exit_to_past_triage_is_illegal(from_exit, new):
    assert legal_transition(from_exit, new) is False


# ---- edge cases ----

def test_same_status_is_legal_noop():
    assert legal_transition("Triage", "Triage") is True


def test_unknown_status_is_illegal():
    assert legal_transition("Triage", "Atlantis") is False
    assert legal_transition("Atlantis", "Triage") is False


def test_blank_old_is_treated_as_triage_entry():
    # First time a card lands in Triage (no prior status) is legal.
    assert legal_transition(None, "Triage") is True
    # Jumping straight from no-status into a later state is not.
    assert legal_transition(None, "QA approved") is False
