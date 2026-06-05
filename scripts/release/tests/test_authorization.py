"""Tests for the release-authorisation decision core.

The ChatOps release gate works by a member of the QA-approver team commenting
`/approve` (or `/deny`) on a machine-generated authorisation issue. This module
is the pure part: given the comment, who wrote it, who authored the release,
whether the commenter is a verified team member, and whether the issue is still
open business, decide whether to publish (`approve`), close-unpublished
(`deny`), or do nothing (`ignore`). Looking up team membership, publishing the
draft, and closing the issue stay in the workflow.
"""

from __future__ import annotations

from release import authorization


def decide(
    comment_body,
    *,
    commenter="reviewer",
    author="releaser",
    is_team_member=True,
    issue_is_authorisation=True,
    already_resolved=False,
):
    """`authorization.decide` with sensible defaults for the common case.

    Default is a team member (`reviewer`) who is not the release author
    (`releaser`) commenting on an open authorisation issue — the happy path —
    so each test overrides only the dimension it exercises.
    """
    return authorization.decide(
        comment_body=comment_body,
        commenter=commenter,
        author=author,
        is_team_member=is_team_member,
        issue_is_authorisation=issue_is_authorisation,
        already_resolved=already_resolved,
    )


class TestApprove:
    def test_team_member_non_author_approves(self):
        d = decide("/approve")
        assert d.action == "approve"

    def test_author_cannot_approve_own_release(self):
        # Segregation of duties: even a team member who pushed the tag may not
        # sign off their own release.
        d = decide("/approve", commenter="releaser", author="releaser")
        assert d.action == "deny"
        assert "self" in d.reason.lower() or "author" in d.reason.lower()

    def test_non_team_member_approve_is_ignored_not_denied(self):
        # No authority is not the same as a denial — it leaves the gate open
        # for an actual approver, rather than closing the issue.
        d = decide("/approve", is_team_member=False)
        assert d.action == "ignore"


class TestDeny:
    def test_team_member_denies(self):
        d = decide("/deny")
        assert d.action == "deny"

    def test_non_team_member_deny_is_ignored(self):
        d = decide("/deny", is_team_member=False)
        assert d.action == "ignore"


class TestNonCommands:
    def test_plain_comment_is_ignored(self):
        assert decide("looks good to me").action == "ignore"

    def test_empty_comment_is_ignored(self):
        assert decide("").action == "ignore"
        assert decide("   \n  ").action == "ignore"


class TestCommandTolerance:
    def test_surrounding_whitespace_tolerated(self):
        assert decide("   /approve   ").action == "approve"

    def test_case_insensitive(self):
        assert decide("/APPROVE").action == "approve"
        assert decide("/Deny").action == "deny"

    def test_trailing_text_on_later_lines_tolerated(self):
        assert decide("/approve\n\nLGTM, ship it").action == "approve"

    def test_command_must_be_first_token(self):
        # Quoting someone else's command in prose must not fire the gate.
        assert decide("I think you meant /approve here").action == "ignore"
        assert decide("> /approve").action == "ignore"


class TestIdempotency:
    def test_resolved_issue_ignores_further_commands(self):
        assert decide("/approve", already_resolved=True).action == "ignore"
        assert decide("/deny", already_resolved=True).action == "ignore"

    def test_non_authorisation_issue_is_ignored(self):
        assert decide("/approve", issue_is_authorisation=False).action == "ignore"


def sample_record():
    """A two-component release-authorisation record."""
    return authorization.IssueRecord(
        tag="v1.4.0",
        repo="CCTC-team/trialview",
        run_id="123456789",
        run_url="https://github.com/CCTC-team/trialview/actions/runs/123456789",
        author="releaser",
        components=[
            authorization.Component(
                name="app",
                ref="ghcr.io/cctc-team/trialview",
                digest="sha256:" + "a" * 64,
            ),
            authorization.Component(
                name="api",
                ref="ghcr.io/cctc-team/trialview-api",
                digest="sha256:" + "b" * 64,
            ),
        ],
    )


class TestRenderIssue:
    def test_title_is_stable_and_greppable(self):
        title, _ = authorization.render_issue(sample_record())
        # A fixed prefix lets a caller's issue_comment workflow cheaply
        # pre-filter, and the tag pins which release this issue authorises.
        assert title.startswith(authorization.ISSUE_TITLE_PREFIX)
        assert "v1.4.0" in title

    def test_body_carries_the_human_facing_facts(self):
        _, body = authorization.render_issue(sample_record())
        assert "v1.4.0" in body
        assert "CCTC-team/trialview" in body
        assert "releaser" in body
        assert "https://github.com/CCTC-team/trialview/actions/runs/123456789" in body
        # Per-component table: each name and its pinned ref@digest.
        assert "app" in body and "ghcr.io/cctc-team/trialview@sha256:" + "a" * 64 in body
        assert "api" in body and "ghcr.io/cctc-team/trialview-api@sha256:" + "b" * 64 in body

    def test_body_explains_how_to_authorise(self):
        _, body = authorization.render_issue(sample_record())
        assert "/approve" in body
        assert "/deny" in body
        # The segregation-of-duties note must be visible to a human approver.
        assert "author" in body.lower()


class TestParseIssue:
    def test_round_trips_the_record(self):
        record = sample_record()
        _, body = authorization.render_issue(record)
        assert authorization.parse_issue(body) == record

    def test_digests_come_from_the_machine_block_not_the_table(self):
        # The parse must read the fenced machine block, so a record with the
        # same fields parses back exactly regardless of human-table formatting.
        record = sample_record()
        _, body = authorization.render_issue(record)
        parsed = authorization.parse_issue(body)
        assert [c.digest for c in parsed.components] == [
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        ]

    def test_body_without_machine_block_is_not_parseable(self):
        # A hand-crafted issue (no machine block) cannot be turned into a
        # publishable target — the comment cannot redirect the gate.
        assert authorization.parse_issue("Please release v1.4.0, thanks!") is None

    def test_machine_block_without_schema_marker_is_not_parseable(self):
        # A fenced JSON block that is not our record must not be mistaken for one.
        body = "```json\n{\"hello\": \"world\"}\n```\n"
        assert authorization.parse_issue(body) is None
