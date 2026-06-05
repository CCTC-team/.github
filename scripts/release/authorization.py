"""The release-authorisation decision core.

The production release gate is a ChatOps approval: a member of the QA-approver
team comments `/approve` (or `/deny`) on a machine-generated authorisation issue
attached to a draft Release, and that publishes (or closes) it. This module is
the pure, unit-tested heart of that gate — like :mod:`release.sbom_scan`, it does
no I/O. :func:`decide` takes the comment, who wrote it, who authored the release,
a *verified* team-membership boolean, and the issue's state, and returns an
:class:`AuthDecision`. The workflow shell does the I/O the decision rests on:
looking up team membership with an org-read token, publishing the draft, editing
the notes, and closing the issue.

The membership boolean is computed server-side by the workflow and is never
trusted from the comment; segregation of duties (author may not approve their own
release) is enforced here against the author recorded in the issue at creation.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

#: The commands an authoriser can issue, mapped to the action they request.
_COMMANDS = {"/approve": "approve", "/deny": "deny"}

#: Fixed prefix of every authorisation issue title; a caller's issue_comment
#: workflow can pre-filter on it, and the parse never relies on the title.
ISSUE_TITLE_PREFIX = "Release authorisation: "

#: Schema marker carried in the machine-readable block. ``parse_issue`` only
#: trusts a block that declares it, so a hand-crafted issue (or some other
#: fenced JSON) cannot be turned into a publishable release target.
_RECORD_SCHEMA = "cctc-release-authorisation/v1"

#: A fenced ```json block — the machine-readable record is carried in one.
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class AuthDecision:
    """What the gate should do with a comment.

    ``action`` is one of ``"approve"`` (publish the draft), ``"deny"`` (close the
    issue, leave it a draft), or ``"ignore"`` (no state change). ``reason`` is a
    human-facing explanation, posted back on the issue for the deny/approve cases.
    """

    action: str
    reason: str


def _command(comment_body: str) -> str | None:
    """The authorisation command a comment carries, or ``None``.

    A command must be the **first non-empty token** of the comment (case- and
    surrounding-whitespace-insensitive). Trailing prose on later lines is fine;
    quoting someone else's ``/approve`` inside a sentence — or a Markdown quote
    (``> /approve``) — is deliberately *not* a command.
    """
    stripped = (comment_body or "").strip()
    if not stripped:
        return None
    first_token = stripped.split()[0].lower()
    return _COMMANDS.get(first_token)


def decide(
    *,
    comment_body: str,
    commenter: str,
    author: str,
    is_team_member: bool,
    issue_is_authorisation: bool,
    already_resolved: bool,
) -> AuthDecision:
    """Decide how the gate should respond to one comment.

    ``is_team_member`` must be the workflow's *verified* answer (from an org-read
    token), never a value derived from the comment. ``author`` is the release
    author recorded in the issue at creation, against which self-review is checked.
    """
    if not issue_is_authorisation:
        return AuthDecision("ignore", "Not a release-authorisation issue.")
    if already_resolved:
        return AuthDecision(
            "ignore", "This authorisation is already resolved; comment ignored."
        )

    command = _command(comment_body)
    if command is None:
        return AuthDecision("ignore", "No authorisation command in the comment.")

    if not is_team_member:
        # No authority to authorise — leave the gate open for an actual approver
        # rather than closing it. This is intentionally not a denial.
        return AuthDecision(
            "ignore",
            f"@{commenter} is not a member of the authorising team; comment ignored.",
        )

    if command == "approve":
        if commenter == author:
            return AuthDecision(
                "deny",
                f"@{commenter} authored this release and may not approve it "
                "(segregation of duties). A different team member must `/approve`.",
            )
        return AuthDecision("approve", f"Approved by @{commenter}.")

    return AuthDecision("deny", f"Denied by @{commenter}.")


@dataclass
class Component:
    """One image published by a release: its component name and pinned ref."""

    name: str
    ref: str
    digest: str


@dataclass
class IssueRecord:
    """The publishable release target recorded in an authorisation issue.

    This — not the approving comment — is what the gate publishes (Decision 6):
    the workflow parses it back from the issue body it authored, so a comment
    cannot redirect the gate to a different tag or digest.
    """

    tag: str
    repo: str
    run_id: str
    run_url: str
    author: str
    components: list[Component] = field(default_factory=list)


def render_issue(record: IssueRecord) -> tuple[str, str]:
    """Render an :class:`IssueRecord` to an ``(title, body)`` pair.

    The body carries a human-facing summary (a per-component ``ref@digest``
    table, the author, the build run, and how to authorise) **and** a fenced
    machine-readable JSON block that is the source of truth for
    :func:`parse_issue`. The table is for people; the block is for the gate.
    """
    title = f"{ISSUE_TITLE_PREFIX}{record.tag} ({record.repo})"

    rows = "\n".join(
        f"| `{c.name}` | `{c.ref}@{c.digest}` |" for c in record.components
    )
    block = json.dumps(
        {"schema": _RECORD_SCHEMA, **asdict(record)}, indent=2, sort_keys=True
    )
    body = (
        f"# Release authorisation required\n\n"
        f"Repository **{record.repo}** is requesting authorisation to publish "
        f"release **{record.tag}**.\n\n"
        f"- **Release author:** @{record.author}\n"
        f"- **Build run:** {record.run_url}\n\n"
        f"## Components to be published\n\n"
        f"| Component | Image |\n|---|---|\n{rows}\n\n"
        f"## How to authorise\n\n"
        f"A member of the authorising team who is **not** the release author "
        f"(@{record.author}) authorises this release by commenting `/approve`. "
        f"Commenting `/deny` closes it unpublished. Segregation of duties: the "
        f"release author may not approve their own release.\n\n"
        f"<!-- machine-readable authorisation record — do not edit -->\n"
        f"```json\n{block}\n```\n"
    )
    return title, body


def parse_issue(body: str) -> IssueRecord | None:
    """Recover the :class:`IssueRecord` from an issue body, or ``None``.

    Reads the fenced machine block (never the human table) and only accepts one
    that declares the authorisation schema. A body with no such block — a
    hand-crafted issue — returns ``None`` so it can never be published.
    """
    for match in _JSON_BLOCK.finditer(body or ""):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("schema") != _RECORD_SCHEMA:
            continue
        try:
            components = [
                Component(name=c["name"], ref=c["ref"], digest=c["digest"])
                for c in data.get("components", [])
            ]
            return IssueRecord(
                tag=data["tag"],
                repo=data["repo"],
                run_id=data["run_id"],
                run_url=data["run_url"],
                author=data["author"],
                components=components,
            )
        except (KeyError, TypeError):
            return None
    return None
