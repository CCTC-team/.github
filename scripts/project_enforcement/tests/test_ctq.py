"""Coverage for the Critical-to-Quality tier vocabulary — the single
place that defines how a board ``Critical-to-Quality`` value maps onto
the three tiers (critical / important / no) and the PQ-required test set.

The mapping carries a legacy alias: cards predating the three-tier field
hold ``Yes``, which must continue to mean ``critical`` so existing cards
keep their behaviour during the board migration.
"""

from __future__ import annotations

from project_enforcement import ctq


class TestTier:
    def test_yes_and_critical_map_to_critical(self):
        assert ctq.tier("Yes") == "critical"
        assert ctq.tier("yes") == "critical"
        assert ctq.tier("Critical") == "critical"
        assert ctq.tier("critical") == "critical"

    def test_important_maps_to_important(self):
        assert ctq.tier("Important") == "important"
        assert ctq.tier("important") == "important"

    def test_no_and_none_map_to_no(self):
        assert ctq.tier("No") == "no"
        assert ctq.tier("none") == "no"

    def test_empty_or_whitespace_is_unset(self):
        # An unset field is distinct from a deliberate "No": the
        # requirement-defined precondition needs to tell them apart.
        assert ctq.tier("") == "unset"
        assert ctq.tier("   ") == "unset"
        assert ctq.tier(None) == "unset"

    def test_unknown_value_passes_through_lowercased(self):
        assert ctq.tier("Bogus") == "bogus"

    def test_accepts_a_fields_mapping(self):
        # Call sites pass the card's whole fields dict; the helper reads
        # the Critical-to-Quality entry itself.
        assert ctq.tier({"Critical-to-Quality": "Important"}) == "important"
        assert ctq.tier({"Critical-to-Quality": ""}) == "unset"
        assert ctq.tier({}) == "unset"


def test_critical_test_types_require_pq():
    # The PQ-required set lives here so every check shares one definition.
    assert ctq.CRITICAL_TEST_TYPES == {"PQ", "OQ+PQ", "IQ+OQ+PQ"}
