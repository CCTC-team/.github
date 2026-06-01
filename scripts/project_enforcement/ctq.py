"""Single source of truth for the Critical-to-Quality vocabulary.

The board's ``Critical-to-Quality`` field classifies a feature as
``Critical``, ``Important`` or ``No`` (mirroring the CtQ form's
three-way classification). Cards created before the field gained three
options hold the legacy value ``Yes``; it is treated as ``critical`` so
those cards keep their existing behaviour until they are migrated.

``tier`` is the only place that knows these aliases, so every check
that reasons about CtQ shares one definition.
"""

from __future__ import annotations


# Test Types that satisfy a critical feature — i.e. those that include
# performance qualification.
CRITICAL_TEST_TYPES = {"PQ", "OQ+PQ", "IQ+OQ+PQ"}


def tier(value_or_fields) -> str:
    """Normalise a Critical-to-Quality value to a tier.

    Accepts either the raw field value or the card's ``fields`` mapping
    (from which the ``Critical-to-Quality`` entry is read). Returns:

    - ``"critical"`` for ``Critical`` or the legacy ``Yes``;
    - ``"important"`` for ``Important``;
    - ``"no"`` for an explicit ``No``/``None``;
    - ``"unset"`` when the field is empty/whitespace — distinct from a
      deliberate ``No`` so callers can require the field be chosen;
    - the lower-cased value otherwise (unrecognised input passes through).
    """
    if isinstance(value_or_fields, dict):
        raw = value_or_fields.get("Critical-to-Quality")
    else:
        raw = value_or_fields

    norm = (raw or "").strip().lower()
    if not norm:
        return "unset"
    if norm in {"yes", "critical"}:
        return "critical"
    if norm == "important":
        return "important"
    if norm in {"no", "none"}:
        return "no"
    return norm
