"""Precondition coverage — one passing case and at least one failing case
per individual rule. Stubs evidence with the dataclasses from
``project_enforcement.evidence``.
"""

from __future__ import annotations

import datetime

import pytest

from project_enforcement.actions import RecordingActions
from project_enforcement.checks.preconditions import (
    PRECONDITIONS,
    code_review,
    in_development,
    user_acceptance,
    qa_approved,
    released,
    requirement_defined,
    risk_linked,
    vv_tests_pass,
)
from project_enforcement.evidence import IssueMeta, LinkedPR, StubEvidence
from project_enforcement.handler import CheckContext


REPO = "CCTC-team/sample"
NUMBER = 42
PROJECT = {"owner": "CCTC-team", "number": 31}


def _ctx(actions=None):
    return CheckContext(
        project_cfg=PROJECT,
        fields={},
        config={},
        mode="evaluate",
        snapshot={},
        actions=actions or RecordingActions(known_users={"alice", "bob", "carol", "dave"}),
    )


def _item(fields=None):
    return {
        "content_id": "I_1",
        "content_type": "issue",
        "source_repo": REPO,
        "number": NUMBER,
        "title": "Sample feature",
        "fields": fields or {},
    }


# ============================== Risk linked ==============================

class TestRiskLinked:
    def _evidence(self, body):
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body=body, author="alice")
        return ev

    def test_passes_when_field_and_body_match(self):
        item = _item({"Risk ID": "RISK-014"})
        ev = self._evidence("### Risk ID:\n\nRISK-014\n\n")
        assert risk_linked.check(item, _ctx(), ev) == []

    def test_fails_when_field_empty(self):
        item = _item({"Risk ID": ""})
        ev = self._evidence("### Risk ID:\n\nRISK-014\n\n")
        reasons = risk_linked.check(item, _ctx(), ev)
        assert any("empty" in r and "card" in r for r in reasons)

    def test_fails_when_body_empty(self):
        item = _item({"Risk ID": "RISK-014"})
        ev = self._evidence("### Risk ID:\n\n\n\n")
        reasons = risk_linked.check(item, _ctx(), ev)
        assert any("issue" in r for r in reasons)

    def test_fails_when_values_differ(self):
        item = _item({"Risk ID": "RISK-014"})
        ev = self._evidence("### Risk ID:\n\nRISK-099\n\n")
        reasons = risk_linked.check(item, _ctx(), ev)
        assert any("does not match" in r for r in reasons)

    def test_passes_with_unordered_csv(self):
        item = _item({"Risk ID": "RISK-022, RISK-014"})
        ev = self._evidence("### Risk ID:\n\nRISK-014, RISK-022\n")
        assert risk_linked.check(item, _ctx(), ev) == []


# ============================== Requirement defined ==============================

class TestRequirementDefined:
    def _evidence(self, body):
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body=body, author="alice")
        return ev

    def test_passes(self):
        item = _item({"Requirement ID": "REQ-024", "Critical-to-Quality": "Yes"})
        ev = self._evidence("### Requirement ID:\n\nREQ-024\n")
        assert requirement_defined.check(item, _ctx(), ev) == []

    def test_fails_when_requirement_empty(self):
        item = _item({"Requirement ID": "", "Critical-to-Quality": "Yes"})
        ev = self._evidence("### Requirement ID:\n\nREQ-024\n")
        reasons = requirement_defined.check(item, _ctx(), ev)
        assert any("Requirement ID" in r for r in reasons)

    def test_fails_when_ctq_unset(self):
        item = _item({"Requirement ID": "REQ-024", "Critical-to-Quality": ""})
        ev = self._evidence("### Requirement ID:\n\nREQ-024\n")
        reasons = requirement_defined.check(item, _ctx(), ev)
        assert any("Critical-to-Quality" in r for r in reasons)

    def test_fails_when_mismatch(self):
        item = _item({"Requirement ID": "REQ-024", "Critical-to-Quality": "Yes"})
        ev = self._evidence("### Requirement ID:\n\nREQ-999\n")
        reasons = requirement_defined.check(item, _ctx(), ev)
        assert any("does not match" in r for r in reasons)


# ============================== In development ==============================

class TestInDevelopment:
    def _evidence(self, assignees=None):
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body="", author="alice", assignees=assignees or [])
        return ev

    def test_passes(self):
        item = _item({
            "Assignees": "alice",
            "Iteration": "Sprint 12",
            "Test Type": "OQ+PQ",
            "Critical-to-Quality": "Yes",
        })
        assert in_development.check(item, _ctx(), self._evidence()) == []

    def test_passes_with_assignee_on_issue(self):
        item = _item({"Iteration": "Sprint 12", "Test Type": "PQ", "Critical-to-Quality": "Yes"})
        assert in_development.check(item, _ctx(), self._evidence(assignees=["alice"])) == []

    def test_fails_without_assignee(self):
        item = _item({"Iteration": "Sprint 12", "Test Type": "PQ"})
        reasons = in_development.check(item, _ctx(), self._evidence())
        assert any("assignee" in r.lower() for r in reasons)

    def test_fails_without_iteration(self):
        item = _item({"Assignees": "alice", "Test Type": "PQ"})
        reasons = in_development.check(item, _ctx(), self._evidence())
        assert any("Iteration" in r for r in reasons)

    def test_fails_without_test_type(self):
        item = _item({"Assignees": "alice", "Iteration": "Sprint 1"})
        reasons = in_development.check(item, _ctx(), self._evidence())
        assert any("Test Type" in r for r in reasons)

    def test_fails_when_ctq_yes_and_test_type_excludes_pq(self):
        item = _item({
            "Assignees": "alice", "Iteration": "Sprint 1",
            "Test Type": "OQ", "Critical-to-Quality": "Yes",
        })
        reasons = in_development.check(item, _ctx(), self._evidence())
        assert any("include PQ" in r for r in reasons)


# ============================== Code review ==============================

class TestCodeReview:
    def test_passes_with_open_pr(self):
        ev = StubEvidence()
        ev.prs[(REPO, NUMBER)] = [
            LinkedPR(repo=REPO, number=99, head_sha="abc", base_ref="main", state="OPEN", merged=False, merge_commit_sha=None),
        ]
        assert code_review.check(_item(), _ctx(), ev) == []

    def test_fails_with_no_pr(self):
        ev = StubEvidence()
        reasons = code_review.check(_item(), _ctx(), ev)
        assert any("No open PR" in r for r in reasons)

    def test_fails_with_only_closed_pr(self):
        ev = StubEvidence()
        ev.prs[(REPO, NUMBER)] = [
            LinkedPR(repo=REPO, number=99, head_sha="abc", base_ref="main", state="CLOSED", merged=False, merge_commit_sha=None),
        ]
        assert code_review.check(_item(), _ctx(), ev) != []


# ============================== V&V tests pass ==============================

class TestVvTestsPass:
    def _evidence(self, *, rollup="SUCCESS", url_exists=True, default_branch="main", feature_link=None, has_pr=True):
        ev = StubEvidence()
        link = feature_link if feature_link is not None else f"https://github.com/{REPO}/blob/{default_branch}/features/sample.feature"
        ev.issues[(REPO, NUMBER)] = IssueMeta(
            body=f"### Feature link:\n\n{link}\n",
            author="alice",
        )
        ev.branches[REPO] = default_branch
        if has_pr:
            ev.prs[(REPO, NUMBER)] = [
                LinkedPR(repo=REPO, number=99, head_sha="abc", base_ref=default_branch, state="OPEN", merged=False, merge_commit_sha=None, check_runs={"rollup": rollup}),
            ]
        if url_exists:
            ev.urls.add(link)
        return ev

    def test_passes(self):
        ev = self._evidence()
        assert vv_tests_pass.check(_item(), _ctx(), ev) == []

    def test_fails_with_failing_rollup(self):
        ev = self._evidence(rollup="FAILURE")
        reasons = vv_tests_pass.check(_item(), _ctx(), ev)
        assert any("check status" in r for r in reasons)

    def test_fails_when_feature_link_unreachable(self):
        ev = self._evidence(url_exists=False)
        reasons = vv_tests_pass.check(_item(), _ctx(), ev)
        assert any("does not resolve" in r for r in reasons)

    def test_fails_when_feature_link_not_on_default_branch(self):
        ev = self._evidence(
            feature_link=f"https://github.com/{REPO}/blob/feature-branch/features/sample.feature",
        )
        reasons = vv_tests_pass.check(_item(), _ctx(), ev)
        assert any("default branch" in r for r in reasons)

    def test_fails_when_feature_link_missing(self):
        ev = self._evidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body="### Feature link:\n\n", author="alice")
        reasons = vv_tests_pass.check(_item(), _ctx(), ev)
        assert any("Feature link" in r for r in reasons)


# ============================== User acceptance ==============================

class TestUserAcceptance:
    def _evidence(self, *, body_checks=(True, True), author="alice", pr_authors=("bob",)):
        body = "### User acceptance checklist:\n\n"
        labels = user_acceptance.ACCEPTANCE_CHECKLIST_LABELS
        for ticked, label in zip(body_checks, labels):
            body += f"- [{'x' if ticked else ' '}] {label}\n"
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body=body, author=author)
        ev.prs[(REPO, NUMBER)] = [
            LinkedPR(repo=REPO, number=99, head_sha="abc", base_ref="main", state="OPEN", merged=False, merge_commit_sha=None, commit_authors=list(pr_authors)),
        ]
        return ev

    def test_passes(self):
        item = _item({"Acceptance Approver": "carol"})
        ev = self._evidence(author="alice", pr_authors=("bob",))
        assert user_acceptance.check(item, _ctx(), ev) == []

    def test_fails_when_checklist_unticked(self):
        item = _item({"Acceptance Approver": "carol"})
        ev = self._evidence(body_checks=(True, False))
        reasons = user_acceptance.check(item, _ctx(), ev)
        assert any("not ticked" in r for r in reasons)

    def test_fails_when_approver_missing(self):
        item = _item({"Acceptance Approver": ""})
        ev = self._evidence()
        reasons = user_acceptance.check(item, _ctx(), ev)
        assert any("Acceptance Approver" in r and "unset" in r for r in reasons)

    def test_fails_when_approver_is_issue_author(self):
        item = _item({"Acceptance Approver": "alice"})
        ev = self._evidence(author="alice")
        reasons = user_acceptance.check(item, _ctx(), ev)
        assert any("issue author" in r for r in reasons)

    def test_fails_when_approver_authored_commits(self):
        item = _item({"Acceptance Approver": "bob"})
        ev = self._evidence(pr_authors=("bob",))
        reasons = user_acceptance.check(item, _ctx(), ev)
        assert any("commits" in r for r in reasons)

    def test_fails_when_approver_not_a_user(self):
        item = _item({"Acceptance Approver": "ghost"})
        ev = self._evidence()
        actions = RecordingActions(known_users={"alice", "bob", "carol"})
        reasons = user_acceptance.check(item, _ctx(actions), ev)
        assert any("not a known GitHub user" in r for r in reasons)


# ============================== QA approved ==============================

class TestQaApproved:
    def _evidence(self, *, body_checks=(True, True), pr_authors=("bob",), has_failure=False):
        body = "### QA review checklist:\n\n"
        for ticked, label in zip(body_checks, qa_approved.QA_CHECKLIST_LABELS):
            body += f"- [{'x' if ticked else ' '}] {label}\n"
        ev = StubEvidence()
        ev.issues[(REPO, NUMBER)] = IssueMeta(body=body, author="alice")
        ev.prs[(REPO, NUMBER)] = [
            LinkedPR(repo=REPO, number=99, head_sha="abc", base_ref="main", state="OPEN", merged=False, merge_commit_sha=None, commit_authors=list(pr_authors), failed_check_runs_history=has_failure),
        ]
        return ev

    def _fields(self, **kwargs):
        today = datetime.date.today().isoformat()
        defaults = {
            "QA Approver": "dave",
            "Acceptance Approver": "carol",
            "QA Signoff Date": today,
            "Acceptance Signoff Date": today,
        }
        defaults.update(kwargs)
        return defaults

    def test_passes(self):
        item = _item(self._fields())
        assert qa_approved.check(item, _ctx(), self._evidence()) == []

    def test_fails_when_checklist_unticked(self):
        item = _item(self._fields())
        reasons = qa_approved.check(item, _ctx(), self._evidence(body_checks=(False, True)))
        assert any("not ticked" in r for r in reasons)

    def test_fails_when_qa_approver_unset(self):
        item = _item(self._fields(**{"QA Approver": ""}))
        reasons = qa_approved.check(item, _ctx(), self._evidence())
        assert any("QA Approver" in r and "unset" in r for r in reasons)

    def test_fails_when_qa_signoff_future(self):
        future = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        item = _item(self._fields(**{"QA Signoff Date": future}))
        reasons = qa_approved.check(item, _ctx(), self._evidence())
        assert any("future" in r for r in reasons)

    def test_fails_when_qa_before_acceptance(self):
        today = datetime.date.today()
        item = _item(self._fields(**{
            "QA Signoff Date": today.isoformat(),
            "Acceptance Signoff Date": (today + datetime.timedelta(days=1)).isoformat(),
        }))
        # Acceptance in the future is its own problem, but we also expect the QA<Acceptance message.
        reasons = qa_approved.check(item, _ctx(), self._evidence())
        assert any("earlier than" in r for r in reasons)

    def test_fails_when_qa_equals_acceptance_approver(self):
        item = _item(self._fields(**{"QA Approver": "carol", "Acceptance Approver": "carol"}))
        reasons = qa_approved.check(item, _ctx(), self._evidence())
        assert any("same as `Acceptance Approver`" in r for r in reasons)

    def test_fails_when_qa_is_issue_author(self):
        item = _item(self._fields(**{"QA Approver": "alice"}))
        reasons = qa_approved.check(item, _ctx(), self._evidence())
        assert any("issue author" in r for r in reasons)

    def test_fails_when_deviation_required(self):
        item = _item(self._fields(**{"Deviation Ref": ""}))
        reasons = qa_approved.check(item, _ctx(), self._evidence(has_failure=True))
        assert any("Deviation Ref" in r for r in reasons)


# ============================== Released ==============================

class TestReleased:
    def _evidence(self, *, merged=True, base="main", merge_sha="abc123", default="main", released=True):
        ev = StubEvidence()
        ev.branches[REPO] = default
        ev.prs[(REPO, NUMBER)] = [
            LinkedPR(repo=REPO, number=99, head_sha="head", base_ref=base, state="MERGED" if merged else "OPEN", merged=merged, merge_commit_sha=merge_sha),
        ]
        if released:
            ev.releases.add((REPO, merge_sha))
        return ev

    def test_passes(self):
        assert released.check(_item(), _ctx(), self._evidence()) == []

    def test_fails_when_not_merged(self):
        reasons = released.check(_item(), _ctx(), self._evidence(merged=False))
        assert any("default branch" in r for r in reasons)

    def test_fails_when_merged_to_non_default(self):
        reasons = released.check(_item(), _ctx(), self._evidence(base="develop"))
        assert any("default branch" in r for r in reasons)

    def test_fails_when_no_release_tag(self):
        reasons = released.check(_item(), _ctx(), self._evidence(released=False))
        assert any("No release or tag" in r for r in reasons)


def test_preconditions_registry_complete():
    assert set(PRECONDITIONS) == {
        "Risk linked", "Requirement defined", "In development", "Code review",
        "V&V tests pass", "User acceptance", "QA approved", "Released",
    }
