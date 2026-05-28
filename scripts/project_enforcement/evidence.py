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


# Conclusion values on a check-run that indicate a previous failure
# the QA precondition should refuse to wave through without a Deviation Ref.
_FAILED_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED", "STARTUP_FAILURE"}

# Check-run names whose history is recorded for the Deviation Ref gate.
_TRACKED_CHECK_NAMES = ("gxp-traceability", "compliance", "gate")


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
                name = (run.get("name") or "").lower()
                conclusion = (run.get("conclusion") or "").upper()
                if conclusion in _FAILED_CONCLUSIONS and any(
                    tracked in name for tracked in _TRACKED_CHECK_NAMES
                ):
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
    def release_for_sha(self, repo: str, sha: str) -> bool: ...


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
        # The commits/checkSuites/checkRuns walk is heavy but only fires
        # when a card enters a status that needs it (QA approved /
        # Released); cached per (repo, issue) for the rest of the run.
        query = """
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
          commits(last: 100) {
            nodes {
              commit {
                author { user { login } email }
                checkSuites(first: 20) {
                  nodes {
                    checkRuns(first: 50) {
                      nodes { name conclusion }
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            out = subprocess.run(
                [
                    "gh", "api", "graphql",
                    "-f", f"query={query}",
                    "-f", f"owner={owner}", "-f", f"name={name}",
                    "-F", f"number={issue_number}",
                ],
                check=True, capture_output=True, text=True,
            ).stdout
            data = json.loads(out)
            nodes = (((data.get("data") or {}).get("repository") or {}).get("issue") or {})
            timeline = (nodes.get("timelineItems") or {}).get("nodes", []) or []
            prs: list[LinkedPR] = []
            for ev in timeline:
                pr = ev.get("source") or ev.get("subject") or {}
                if pr.get("__typename") != "PullRequest":
                    continue
                prs.append(_pr_from_graphql(pr, repo))
            self._prs[key] = prs
        except subprocess.CalledProcessError:
            self._prs[key] = []
        return self._prs[key]

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

    def release_for_sha(self, repo, sha):
        if not sha:
            return False
        try:
            out = subprocess.run(
                ["gh", "api", f"/repos/{repo}/releases", "--paginate"],
                check=True, capture_output=True, text=True,
            ).stdout
            data = json.loads(out)
            for release in data:
                if (release.get("target_commitish") or "") == sha:
                    return True
            # Fall back to checking tags pointing at the SHA.
            out_tags = subprocess.run(
                ["gh", "api", f"/repos/{repo}/git/matching-refs/tags/", "--paginate"],
                check=True, capture_output=True, text=True,
            ).stdout
            tags = json.loads(out_tags)
            return any((t.get("object") or {}).get("sha") == sha for t in tags)
        except subprocess.CalledProcessError:
            return False


@dataclass
class StubEvidence:
    """Recording / scripted evidence for tests."""

    issues: dict[tuple[str, int], IssueMeta] = field(default_factory=dict)
    prs: dict[tuple[str, int], list[LinkedPR]] = field(default_factory=dict)
    compliance: dict[str, dict] = field(default_factory=dict)
    branches: dict[str, str] = field(default_factory=dict)
    urls: set[str] = field(default_factory=set)
    releases: set[tuple[str, str]] = field(default_factory=set)

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

    def release_for_sha(self, repo, sha):
        return (repo, sha) in self.releases
