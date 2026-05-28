"""Per-status precondition checks.

Each module exports ``check(item_meta, ctx, evidence) -> list[str]``
returning the list of failure reasons (empty = pass). The handler
runs the function for the new Status value on every Status change.
"""

from project_enforcement.checks.preconditions import (
    code_review,
    in_development,
    pq_review,
    qa_approved,
    released,
    requirement_defined,
    risk_linked,
    vv_tests_pass,
)


PRECONDITIONS = {
    "Risk linked": risk_linked.check,
    "Requirement defined": requirement_defined.check,
    "In development": in_development.check,
    "Code review": code_review.check,
    "V&V tests pass": vv_tests_pass.check,
    "PQ review": pq_review.check,
    "QA approved": qa_approved.check,
    "Released": released.check,
}
