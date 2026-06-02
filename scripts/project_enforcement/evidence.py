"""External-evidence fetchers used by precondition checks.

Preconditions need data the project snapshot doesn't carry — the source
repo's `.compliance.yml`, the issue body, linked PRs, check-run status,
and so on. This module wraps those reads behind a Protocol so tests can
inject a recorded fixture.

The default ``GhEvidence`` shells out to `gh` (assumes GH_TOKEN is set).
Each method caches its result per (repo, key) so a single run doesn't
hit the API once per precondition.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class LinkedPR:
    repo: str
    number: int
    head_sha: str
    base_ref: str
    state: str  # OPEN | CLOSED | MERGED
    merged: bool
    merge_commit_sha: Optional[str]
    commit_authors: list[str] = field(default_factory=list)
    check_runs: dict[str, str] = field(default_factory=dict)  # name → conclusion (success|failure|...)
    failed_check_runs_history: bool = False


@dataclass
class IssueMeta:
    body: str
    author: str
    assignees: list[str] = field(default_factory=list)
    opened_at: Optional[str] = None  # ISO-8601 date when the issue was created
    labels: list[str] = field(default_factory=list)


import re


@dataclass
class ReleaseMeta:
    """A published GitHub Release whose tag resolves to a given commit."""

    tag: str
    sha: str
    url: str = ""
    has_validation_asset: bool = False
    has_provenance: bool = False


# An attached asset is the release's validation report if its filename looks
# like one. The release workflow names it from the manifest's declared output;
# this pattern is deliberately loose so "validation-report.md",
# "validation_report.pdf", "trialview-validation-report-1.4.0.md" all match.
_VALIDATION_ASSET_RE = re.compile(r"validation[\s._-]*report", re.I)


def _select_published_release(releases, tag_to_sha, sha):
    """Return the first *published* release whose tag resolves to ``sha``.

    ``releases`` is the GitHub releases payload; ``tag_to_sha`` maps each
    release tag to the commit it points at, resolved via the tag ref (an
    annotated tag dereferenced to its commit) — never a ``target_commitish``
    string match. Drafts and bare tags (tags with no Release object) never
    match. The returned meta flags whether a validation-report asset is
    attached, so the caller can apply its own policy and give a precise reason.
    """
    for rel in releases or []:
        if rel.get("draft"):
            continue
        tag = rel.get("tag_name") or ""
        if not tag or tag_to_sha.get(tag) != sha:
            continue
        assets = [(a.get("name") or "") for a in (rel.get("assets") or [])]
        has_validation = any(_VALIDATION_ASSET_RE.search(n) for n in assets)
        return ReleaseMeta(
            tag=tag,
            sha=sha,
            url=rel.get("html_url") or "",
            has_validation_asset=has_validation,
        )
    return None


# Conclusion values on a check-run that indicate a previous failure
# the QA precondition should refuse to wave through without a Deviation Ref.
_FAILED_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED", "STARTUP_FAILURE"}

# Check-run names whose history is recorded for the Deviation Ref gate.
# Matched against name segments split on whitespace, `/`, or `-` to avoid
# substring false positives like "aggregate-coverage" matching "gate" or
# "generate-sbom" matching "gate". The check-run name on GitHub is
# typically rendered as "<workflow> / <job>" where each token is itself
# `-`-separated; splitting on those characters gives the actual identifiers.
_TRACKED_CHECK_NAMES = {"gxp-traceability", "compliance", "gate"}
_NAME_SEGMENT = re.compile(r"[\s/]+")


def _check_name_is_tracked(name: str) -> bool:
    if not name:
        return False
    for segment in _NAME_SEGMENT.split(name.strip().lower()):
        if segment in _TRACKED_CHECK_NAMES:
            return True
        # Also accept compound names like "gxp-traceability-gate" by
        # splitting on `-` for an additional pass — but only against the
        # multi-word tracked names, not the bare "gate" token. A name
        # like "aggregate-coverage" must not match "gate" here.
        sub = segment.split("-")
        joined = "-".join(sub)
        if joined in _TRACKED_CHECK_NAMES and joined != "gate":
            return True
    return False


def _pr_from_graphql(pr: dict, fallback_repo: str) -> "LinkedPR":
    authors = []
    failed_history = False
    for c in (pr.get("commits") or {}).get("nodes", []) or []:
        commit = c.get("commit") or {}
        user = (commit.get("author") or {}).get("user")
        if user and user.get("login"):
            authors.append(user["login"])
        for suite in (commit.get("checkSuites") or {}).get("nodes", []) or []:
            for run in (suite.get("checkRuns") or {}).get("nodes", []) or []:
                name = run.get("name") or ""
                conclusion = (run.get("conclusion") or "").upper()
                if conclusion in _FAILED_CONCLUSIONS and _check_name_is_tracked(name):
                    failed_history = True

    return LinkedPR(
        repo=(pr.get("repository") or {}).get("nameWithOwner") or fallback_repo,
        number=pr.get("number"),
        head_sha=pr.get("headRefOid") or "",
        base_ref=pr.get("baseRefName") or "",
        state=pr.get("state") or "",
        merged=bool(pr.get("merged")),
        merge_commit_sha=(pr.get("mergeCommit") or {}).get("oid"),
        commit_authors=sorted(set(authors)),
        check_runs={"rollup": (pr.get("statusCheckRollup") or {}).get("state", "")},
        failed_check_runs_history=failed_history,
    )


class EvidenceLike(Protocol):
    def issue(self, repo: str, number: int) -> Optional[IssueMeta]: ...
    def linked_prs(self, repo: str, issue_number: int) -> list[LinkedPR]: ...
    def compliance_yml(self, repo: str) -> Optional[dict]: ...
    def default_branch(self, repo: str) -> str: ...
    def url_exists(self, url: str) -> bool: ...
    def published_release_for_sha(self, repo: str, sha: str) -> Optional[ReleaseMeta]: ...


class GhEvidence:
    def __init__(self, default_branch_fallback: str = "main"):
        self._issues: dict[tuple[str, int], Optional[IssueMeta]] = {}
        self._prs: dict[tuple[str, int], list[LinkedPR]] = {}
        self._compliance: dict[str, Optional[dict]] = {}
        self._default_branch: dict[str, str] = {}
        self._default_branch_fallback = default_branch_fallback

    def issue(self, repo, number):
        key = (repo, number)
        if key not in self._issues:
            try:
                out = subprocess.run(
                    [
                        "gh", "issue", "view", str(number), "-R", repo,
                        "--json", "body,author,assignees,createdAt,labels",
                    ],
                    check=True, capture_output=True, text=True,
                ).stdout
                data = json.loads(out)
                created = (data.get("createdAt") or "")[:10] or None
                self._issues[key] = IssueMeta(
                    body=data.get("body") or "",
                    author=(data.get("author") or {}).get("login") or "",
                    assignees=[a["login"] for a in (data.get("assignees") or [])],
                    opened_at=created,
                    labels=[l["name"] for l in (data.get("labels") or [])],
                )
            except subprocess.CalledProcessError:
                self._issues[key] = None
        return self._issues[key]

    def linked_prs(self, repo, issue_number):
        key = (repo, issue_number)
        if key in self._prs:
            return self._prs[key]
        owner, name = repo.split("/", 1)
        try:
            timeline_prs = self._fetch_timeline_prs(owner, name, issue_number)
            prs: list[LinkedPR] = []
            for pr_node in timeline_prs:
                # Paginate the commits walk so PRs with >100 commits do not
                # silently truncate the failure history. This matters for
                # long-lived regulated-feature branches.
                self._paginate_commits(owner, name, pr_node)
                prs.append(_pr_from_graphql(pr_node, repo))
            self._prs[key] = prs
        except subprocess.CalledProcessError:
            self._prs[key] = []
        return self._prs[key]

    _TIMELINE_QUERY = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        issue(number: $number) {
          timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {
            nodes {
              __typename
              ... on CrossReferencedEvent { source { __typename ...prBits } }
              ... on ConnectedEvent       { subject { __typename ...prBits } }
            }
          }
        }
      }
    }
    fragment prBits on PullRequest {
      number state merged mergeCommit { oid } headRefOid baseRefName
      repository { nameWithOwner }
      statusCheckRollup { state }
      commits(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes {
          commit {
            author { user { login } email }
            checkSuites(first: 20) {
              nodes {
                checkRuns(first: 100) {
                  nodes { name conclusion }
                }
              }
            }
          }
        }
      }
    }
    """

    _COMMITS_PAGE_QUERY = """
    query($owner: String!, $name: String!, $number: Int!, $cursor: String!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          commits(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              commit {
                author { user { login } email }
                checkSuites(first: 20) {
                  nodes {
                    checkRuns(first: 100) {
                      nodes { name conclusion }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    def _fetch_timeline_prs(self, owner, name, issue_number):
        out = subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={self._TIMELINE_QUERY}",
                "-f", f"owner={owner}", "-f", f"name={name}",
                "-F", f"number={issue_number}",
            ],
            check=True, capture_output=True, text=True,
        ).stdout
        data = json.loads(out)
        node = (((data.get("data") or {}).get("repository") or {}).get("issue") or {})
        timeline = (node.get("timelineItems") or {}).get("nodes", []) or []
        prs = []
        for ev in timeline:
            pr = ev.get("source") or ev.get("subject") or {}
            if pr.get("__typename") == "PullRequest":
                prs.append(pr)
        return prs

    def _paginate_commits(self, owner, name, pr_node):
        commits = pr_node.get("commits") or {}
        page = commits.get("pageInfo") or {}
        cursor = page.get("endCursor")
        nodes = commits.get("nodes") or []
        while page.get("hasNextPage") and cursor:
            out = subprocess.run(
                [
                    "gh", "api", "graphql",
                    "-f", f"query={self._COMMITS_PAGE_QUERY}",
                    "-f", f"owner={owner}", "-f", f"name={name}",
                    "-F", f"number={pr_node.get('number')}",
                    "-f", f"cursor={cursor}",
                ],
                check=True, capture_output=True, text=True,
            ).stdout
            data = json.loads(out)
            extra = (((data.get("data") or {}).get("repository") or {})
                     .get("pullRequest") or {}).get("commits") or {}
            nodes.extend(extra.get("nodes") or [])
            page = extra.get("pageInfo") or {}
            cursor = page.get("endCursor")
        pr_node["commits"] = {"nodes": nodes}

    def compliance_yml(self, repo):
        if repo in self._compliance:
            return self._compliance[repo]
        try:
            out = subprocess.run(
                ["gh", "api", f"/repos/{repo}/contents/.compliance.yml", "--jq", ".content"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            import base64, yaml as _yaml
            raw = base64.b64decode(out)
            self._compliance[repo] = _yaml.safe_load(raw) or {}
        except subprocess.CalledProcessError:
            self._compliance[repo] = None
        return self._compliance[repo]

    def default_branch(self, repo):
        if repo in self._default_branch:
            return self._default_branch[repo]
        try:
            out = subprocess.run(
                ["gh", "api", f"/repos/{repo}", "--jq", ".default_branch"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self._default_branch[repo] = out or self._default_branch_fallback
        except subprocess.CalledProcessError:
            self._default_branch[repo] = self._default_branch_fallback
        return self._default_branch[repo]

    def url_exists(self, url):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 400
        except Exception:
            return False

    def published_release_for_sha(self, repo, sha):
        if not sha:
            return None
        try:
            out = subprocess.run(
                ["gh", "api", f"/repos/{repo}/releases", "--paginate"],
                check=True, capture_output=True, text=True,
            ).stdout
            releases = json.loads(out)
            # Resolve each release tag to the commit it points at via the tag
            # ref (dereferencing annotated tags), not the target_commitish
            # string — a bare branch name in target_commitish must never count.
            tag_to_sha: dict[str, str] = {}
            for rel in releases:
                tag = rel.get("tag_name")
                if tag and tag not in tag_to_sha:
                    resolved = self._tag_commit_sha(repo, tag)
                    if resolved:
                        tag_to_sha[tag] = resolved
            return _select_published_release(releases, tag_to_sha, sha)
        except subprocess.CalledProcessError:
            return None

    def _tag_commit_sha(self, repo, tag):
        """The commit SHA a tag points at, dereferencing annotated tags."""
        try:
            out = subprocess.run(
                ["gh", "api", f"/repos/{repo}/git/ref/tags/{tag}"],
                check=True, capture_output=True, text=True,
            ).stdout
            obj = (json.loads(out) or {}).get("object") or {}
            if obj.get("type") == "tag":
                tag_out = subprocess.run(
                    ["gh", "api", f"/repos/{repo}/git/tags/{obj.get('sha')}"],
                    check=True, capture_output=True, text=True,
                ).stdout
                return ((json.loads(tag_out) or {}).get("object") or {}).get("sha")
            return obj.get("sha")
        except subprocess.CalledProcessError:
            return None


@dataclass
class StubEvidence:
    """Recording / scripted evidence for tests."""

    issues: dict[tuple[str, int], IssueMeta] = field(default_factory=dict)
    prs: dict[tuple[str, int], list[LinkedPR]] = field(default_factory=dict)
    compliance: dict[str, dict] = field(default_factory=dict)
    branches: dict[str, str] = field(default_factory=dict)
    urls: set[str] = field(default_factory=set)
    published_releases: dict[tuple[str, str], ReleaseMeta] = field(default_factory=dict)

    def issue(self, repo, number):
        return self.issues.get((repo, number))

    def linked_prs(self, repo, issue_number):
        return self.prs.get((repo, issue_number), [])

    def compliance_yml(self, repo):
        return self.compliance.get(repo)

    def default_branch(self, repo):
        return self.branches.get(repo, "main")

    def url_exists(self, url):
        return url in self.urls

    def published_release_for_sha(self, repo, sha):
        return self.published_releases.get((repo, sha))
