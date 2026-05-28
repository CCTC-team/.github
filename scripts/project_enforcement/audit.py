"""Nightly audit invariants + rolling drift-issue writer.

The audit is a global daily sweep over every project in
`.github/project-enforcement.yml`. It catches anything the per-event
checks miss (cards added before the system existed, polling-window
gaps, history rewrites).
"""

from __future__ import annotations

import datetime
import json
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional


CANONICAL_LIFECYCLE: tuple[str, ...] = (
    "Triage",
    "Risk linked",
    "Requirement defined",
    "In development",
    "Code review",
    "V&V tests pass",
    "PQ review",
    "QA approved",
    "Released",
    "Redundant",
    "Archived",
)


REQUIRED_FIELDS_AT_QA: tuple[str, ...] = (
    "Risk ID",
    "Requirement ID",
    "Test Type",
    "Critical-to-Quality",
    "PQ Approver",
    "PQ Signoff Date",
    "QA Approver",
    "QA Signoff Date",
)


_PQ_CHECKLIST_HEADER = "PQ review checklist:"
_QA_CHECKLIST_HEADER = "QA review checklist:"

_IN_DEVELOPMENT_STALE_DAYS = 14


@dataclass
class Finding:
    severity: str       # "hard" | "soft"
    category: str       # e.g. "required_field", "identity_conflict", "stuck", "unmonitored_clone"
    item_label: str     # human-readable card identifier (item id, project number, etc.)
    summary: str


def days_since(iso_value: Optional[str]) -> Optional[int]:
    if not iso_value:
        return None
    try:
        d = datetime.date.fromisoformat(iso_value[:10])
    except ValueError:
        return None
    return (datetime.date.today() - d).days


_PQ_OR_LATER = ("PQ review", "QA approved", "Released")
_QA_OR_LATER = ("QA approved", "Released")

# Window for "Recent bypasses honoured" in the rolling drift issue. The
# handler also applies a 30-day age-out at snapshot-write time, but
# filtering here as well guarantees the audit window holds even if the
# poller has been paused.
_BYPASS_WINDOW_DAYS = 30


def audit_project(
    snapshot: dict,
    *,
    issue_authors: Optional[dict[tuple[str, int], str]] = None,
    pr_history: Optional[dict[tuple[str, int], list[dict]]] = None,
    issue_bodies: Optional[dict[tuple[str, int], str]] = None,
) -> list[Finding]:
    """Audit one project snapshot. Returns a list of findings."""

    from project_enforcement.checkboxes import parse_checklist

    findings: list[Finding] = []
    issue_authors = issue_authors or {}
    pr_history = pr_history or {}
    issue_bodies = issue_bodies or {}

    items = (snapshot.get("items") or {})
    for item_id, meta in items.items():
        fields = meta.get("fields") or {}
        status = fields.get("Status")
        label = f"{meta.get('source_repo') or item_id}#{meta.get('number') or item_id}"
        key = (meta.get("source_repo"), meta.get("number"))

        if status in ("QA approved", "Released"):
            for required in REQUIRED_FIELDS_AT_QA:
                if not (fields.get(required) or "").strip():
                    findings.append(Finding(
                        severity="hard",
                        category="required_field",
                        item_label=label,
                        summary=f"{label} at `{status}` is missing required field `{required}`.",
                    ))

            author = issue_authors.get(key)
            pq = (fields.get("PQ Approver") or "").lstrip("@").strip()
            qa = (fields.get("QA Approver") or "").lstrip("@").strip()
            identities = {x for x in (author, pq, qa) if x}
            if author and pq and qa and len(identities) < 3:
                findings.append(Finding(
                    severity="hard",
                    category="identity_conflict",
                    item_label=label,
                    summary=(
                        f"{label} at `{status}` does not have three distinct identities across "
                        f"issue author (`{author}`), PQ Approver (`{pq}`), QA Approver (`{qa}`)."
                    ),
                ))

        if status == "Released":
            prs = pr_history.get(key, [])
            if not any(pr.get("merged") for pr in prs):
                findings.append(Finding(
                    severity="hard",
                    category="released_without_merge",
                    item_label=label,
                    summary=f"{label} is at `Released` with no linked merged PR.",
                ))

        # _QA_OR_LATER ⊂ _PQ_OR_LATER, so the outer guard is just the
        # superset; the inner branches apply the narrower QA window.
        if status in _PQ_OR_LATER:
            body = issue_bodies.get(key)
            if body is not None:
                if status in _PQ_OR_LATER:
                    parsed = parse_checklist(body, _PQ_CHECKLIST_HEADER)
                    unticked = [lbl for lbl, ticked in parsed if not ticked]
                    if parsed and unticked:
                        findings.append(Finding(
                            severity="hard",
                            category="checklist_unticked",
                            item_label=label,
                            summary=(
                                f"{label} at `{status}` has unticked PQ checklist item(s): "
                                f"{', '.join(f'`{u}`' for u in unticked)}."
                            ),
                        ))
                if status in _QA_OR_LATER:
                    parsed = parse_checklist(body, _QA_CHECKLIST_HEADER)
                    unticked = [lbl for lbl, ticked in parsed if not ticked]
                    if parsed and unticked:
                        findings.append(Finding(
                            severity="hard",
                            category="checklist_unticked",
                            item_label=label,
                            summary=(
                                f"{label} at `{status}` has unticked QA checklist item(s): "
                                f"{', '.join(f'`{u}`' for u in unticked)}."
                            ),
                        ))

        if status == "In development":
            stale = days_since(meta.get("updated_at"))
            if stale is not None and stale > _IN_DEVELOPMENT_STALE_DAYS:
                findings.append(Finding(
                    severity="soft",
                    category="stuck",
                    item_label=label,
                    summary=(
                        f"{label} has been stuck in `In development` for {stale} days "
                        f"with no assignee change."
                    ),
                ))

    return findings


def discover_unmonitored(org_projects: Iterable[dict], config: dict) -> list[Finding]:
    """Identify org projects whose Status options look like a regulated
    lifecycle but which aren't listed in `.github/project-enforcement.yml`.
    """

    canonical = set(CANONICAL_LIFECYCLE)
    monitored_numbers = {p.get("number") for p in (config.get("projects") or [])}

    findings: list[Finding] = []
    for project in org_projects:
        if project.get("closed"):
            continue
        options = set(project.get("status_options") or [])
        if not canonical.issubset(options):
            continue
        if project.get("number") in monitored_numbers:
            continue
        title = project.get("title") or "<untitled>"
        findings.append(Finding(
            severity="soft",
            category="unmonitored_clone",
            item_label=str(project.get("id") or project.get("number")),
            summary=(
                f"Project {project.get('number')} `{title}` looks like a lifecycle board but is "
                f"not in `.github/project-enforcement.yml`. URL: {project.get('url') or 'n/a'}"
            ),
        ))

    return findings


def audit_issue_title(project_label: str) -> str:
    return f"Project enforcement drift — {project_label}"


def _filter_recent_bypasses(events: list[dict]) -> list[dict]:
    """Apply the 30-day rolling window at audit-read time.

    The poller also ages out at write-time, but if the poller has been
    paused or is failing the snapshot's `bypass_events` could carry
    stale entries. Filtering here keeps the audit's "Recent" claim
    honest regardless of poller state. Malformed timestamps are kept —
    better to over-report than silently drop an audit event.
    """
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=_BYPASS_WINDOW_DAYS)
    out = []
    for ev in events:
        ts = ev.get("ts")
        if not ts:
            out.append(ev)
            continue
        try:
            if datetime.datetime.fromisoformat(ts) >= cutoff:
                out.append(ev)
        except ValueError:
            out.append(ev)
    return out


def render_audit_body(
    project_label: str,
    findings: list[Finding],
    unmonitored: list[Finding],
    bypass_events: Optional[list[dict]] = None,
) -> str:
    today = datetime.date.today().isoformat()
    bypass_events = _filter_recent_bypasses(bypass_events or [])
    lines = [
        f"_Auto-generated by the project-enforcement audit on {today}. "
        "Body replaces previous content on every run._",
        "",
    ]

    if not findings and not unmonitored and not bypass_events:
        lines.append("**No drift detected.**")
        return "\n".join(lines)

    if findings:
        lines.append(f"## Findings for `{project_label}`")
        lines.append("")
        for f in sorted(findings, key=lambda x: (x.severity != "hard", x.summary)):
            sev = "🔴" if f.severity == "hard" else "🟡"
            lines.append(f"- {sev} **[{f.category}]** {f.summary}")
        lines.append("")

    if bypass_events:
        lines.append("## Recent bypasses honoured")
        lines.append("")
        lines.append(
            "Each entry is one `process-override:approved` label that the bot honoured "
            "and cleared. The 30-day window is rolling."
        )
        lines.append("")
        for ev in sorted(bypass_events, key=lambda e: e.get("ts") or "", reverse=True):
            ts = ev.get("ts", "")[:19]
            repo = ev.get("repo") or "?"
            num = ev.get("number") or "?"
            old = ev.get("old_status") or "?"
            new = ev.get("new_status") or "?"
            lines.append(f"- `{ts}` — {repo}#{num}: `{old}` → `{new}`")
        lines.append("")

    if unmonitored:
        lines.append("## Unmonitored lifecycle boards")
        lines.append("")
        lines.append(
            "Add to `.github/project-enforcement.yml` `projects:` if a real lifecycle board, "
            "or rename its Status options if not."
        )
        lines.append("")
        for f in unmonitored:
            lines.append(f"- {f.summary}")
        lines.append("")

    return "\n".join(lines)


def update_audit_issue(gh, project_label: str, findings: list[Finding], *,
                       unmonitored: list[Finding],
                       bypass_events: Optional[list[dict]] = None):
    """Find / create / update / close the rolling drift issue for one project.

    ``gh`` is anything that exposes:
        find_any(title) -> issue|None     # any state
        find_open(title) -> issue|None    # open only
        create_issue(title, body) -> issue
        update_issue(number, body=None, state=None) -> issue
    """

    title = audit_issue_title(project_label)
    body = render_audit_body(project_label, findings, unmonitored, bypass_events)
    existing = gh.find_any(title)
    has_signal = bool(
        findings or unmonitored or _filter_recent_bypasses(bypass_events or [])
    )

    if not has_signal:
        if existing is None:
            return
        if existing.state == "open":
            gh.update_issue(existing.number, body="No drift detected on this run.", state="closed")
        return

    if existing is None:
        gh.create_issue(title, body)
        return

    if existing.state == "closed":
        gh.update_issue(existing.number, body=body, state="open")
    else:
        gh.update_issue(existing.number, body=body)
