"""Behaviour of parse_checklist(body, header) and all_ticked()."""

from project_enforcement.checkboxes import all_ticked, parse_checklist


ACCEPTANCE_BODY = """\
### Risk ID:

RISK-014

### User acceptance checklist:

- [x] Feature meets the user requirement against the URS in a development/test environment
- [ ] Workflow is usable in practice (not just technically passing)

### QA review checklist:

- [ ] Risk linkage verified against the canonical risk register
- [ ] URS → V&V evidence chain intact; any deviations are documented
"""


def test_recognises_acceptance_checklist_header():
    items = parse_checklist(ACCEPTANCE_BODY, "User acceptance checklist:")
    labels = [label for label, _ in items]
    assert labels == [
        "Feature meets the user requirement against the URS in a development/test environment",
        "Workflow is usable in practice (not just technically passing)",
    ]


def test_picks_up_checked_and_unchecked_marks():
    items = dict(parse_checklist(ACCEPTANCE_BODY, "User acceptance checklist:"))
    assert items["Feature meets the user requirement against the URS in a development/test environment"] is True
    assert items["Workflow is usable in practice (not just technically passing)"] is False


def test_does_not_bleed_into_next_header():
    items = parse_checklist(ACCEPTANCE_BODY, "User acceptance checklist:")
    labels = [label for label, _ in items]
    # The QA list items must not leak into the acceptance result.
    assert "Risk linkage verified against the canonical risk register" not in labels


def test_qa_checklist_isolated_from_acceptance():
    items = parse_checklist(ACCEPTANCE_BODY, "QA review checklist:")
    labels = [label for label, _ in items]
    assert labels == [
        "Risk linkage verified against the canonical risk register",
        "URS → V&V evidence chain intact; any deviations are documented",
    ]


def test_capital_x_counts_as_ticked():
    body = "### User acceptance checklist:\n\n- [X] One\n- [x] Two\n- [ ] Three\n"
    items = dict(parse_checklist(body, "User acceptance checklist:"))
    assert items["One"] is True
    assert items["Two"] is True
    assert items["Three"] is False


def test_trailing_whitespace_tolerated():
    body = "### User acceptance checklist:\n\n- [x] A label   \n- [ ] Another label \n"
    items = parse_checklist(body, "User acceptance checklist:")
    labels = [label for label, _ in items]
    assert labels == ["A label", "Another label"]


def test_missing_header_returns_empty_list():
    body = "### Risk ID:\n\nRISK-014\n"
    assert parse_checklist(body, "User acceptance checklist:") == []


def test_all_ticked_true():
    items = [("A", True), ("B", True)]
    assert all_ticked(items) is True


def test_all_ticked_false_when_any_unticked():
    items = [("A", True), ("B", False)]
    assert all_ticked(items) is False


def test_all_ticked_false_when_empty():
    assert all_ticked([]) is False
