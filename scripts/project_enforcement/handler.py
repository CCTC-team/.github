"""Project enforcement handler.

Polls every project listed in ``.github/project-enforcement.yml``, diffs
its current state against the prior snapshot, and dispatches each
detected change to the registered check functions.

No checks are wired in by default — other modules append to
``CHECKS`` to opt in. The dispatch loop honours the per-check mode
(``off | evaluate | active``) from the config.

CLI:
    python scripts/project_enforcement/handler.py \\
        --config .github/project-enforcement.yml \\
        --state-dir _project-state
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

import yaml

from project_enforcement import snapshot
from project_enforcement.actions import ActionsLike, GhActions
from project_enforcement.evidence import EvidenceLike, GhEvidence
from project_enforcement.fields import FieldRef, resolve_fields
from project_enforcement.checks import transition as _transition_check
from project_enforcement.checks.drift import (
    approver_identity_drift as _drift_approver,
    date_sanity as _drift_date,
    id_mirror as _drift_id,
    type_quality_consistency as _drift_tq,
)
from project_enforcement.checks.preconditions import PRECONDITIONS


CheckMode = str  # "off" | "evaluate" | "active"


@dataclasses.dataclass
class CheckContext:
    project_cfg: dict
    fields: dict[str, FieldRef]
    config: dict
    mode: CheckMode
    snapshot: dict  # the current-state snapshot (new), so checks can look up item meta
    actions: ActionsLike
    evidence: Optional[EvidenceLike] = None
    # Per-run audit log. Checks append a record when they honour a bypass
    # label; the handler folds the list into the new snapshot before
    # writing it out, so the nightly audit can render recent overrides
    # in the rolling drift issue.
    bypass_events: list = dataclasses.field(default_factory=list)


CheckFn = Callable[[snapshot.CardChange, CheckContext], None]


# Module-level registry. Other modules call ``register(name, fn)`` at
# import time. Tests pass their own dict in via the ``checks=`` kwarg.
CHECKS: dict[str, CheckFn] = {}


def register(name: str, fn: CheckFn) -> None:
    CHECKS[name] = fn


_transition_check.register(CHECKS)
_drift_id.register(CHECKS)
_drift_date.register(CHECKS)
_drift_approver.register(CHECKS)
_drift_tq.register(CHECKS)


def to_snapshot(project_json: dict) -> dict:
    """Strip a fetched project_json down to the form stored in the snapshot branch."""
    items = {}
    for item_id, meta in (project_json.get("items") or {}).items():
        items[item_id] = {
            "content_id": meta.get("content_id"),
            "content_type": meta.get("content_type"),
            "source_repo": meta.get("source_repo"),
            "number": meta.get("number"),
            "title": meta.get("title"),
            "updated_at": meta.get("updated_at"),
            "fields": meta.get("fields") or {},
        }
    return {
        "project_id": project_json.get("project_id"),
        "owner": project_json.get("owner"),
        "number": project_json.get("number"),
        "title": project_json.get("title"),
        "items": items,
    }


def state_path(state_dir: str, project_cfg: dict) -> str:
    owner = project_cfg["owner"]
    number = project_cfg["number"]
    return os.path.join(state_dir, f"{owner}-{number}.json")


def _log_event(**kwargs) -> None:
    kwargs.setdefault("ts", datetime.datetime.now(datetime.UTC).isoformat())
    print(json.dumps(kwargs, sort_keys=True), flush=True)


def _append_summary(summary_path: Optional[str], lines: Iterable[str]) -> None:
    if not summary_path:
        return
    with open(summary_path, "a") as f:
        for line in lines:
            f.write(line + "\n")


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def all_checks_off(config: dict) -> bool:
    def _is_off(value):
        return value in (None, "", "off", False)

    for value in (config.get("checks") or {}).values():
        if not _is_off(value):
            return False
    for value in (config.get("preconditions") or {}).values():
        if not _is_off(value):
            return False
    return True


def run(
    config: dict,
    *,
    state_dir: str,
    fetch_project: Callable[..., dict] = snapshot.fetch_project,
    load_snapshot: Callable[[str], dict] = snapshot.load_snapshot,
    write_snapshot: Callable[[str, dict], None] = snapshot.write_snapshot,
    checks: Optional[dict[str, CheckFn]] = None,
    actions: Optional[ActionsLike] = None,
    evidence: Optional[EvidenceLike] = None,
    summary_path: Optional[str] = None,
) -> int:
    """Run one polling cycle. Returns 0 on success, non-zero on failure.

    All side effects (network, disk, summary) are injected so the unit
    smoke test can run without touching GitHub or the filesystem outside
    a temp dir.
    """

    registry = checks if checks is not None else CHECKS
    actions = actions if actions is not None else GhActions()
    evidence = evidence if evidence is not None else GhEvidence(
        default_branch_fallback=(config.get("default_branch_fallback") or "main")
    )

    summary_lines: list[str] = ["## Project enforcement"]
    summary_lines.append(f"Run at: {datetime.datetime.now(datetime.UTC).isoformat()}")
    summary_lines.append("")

    projects = config.get("projects") or []
    if not projects:
        summary_lines.append("_No projects configured — nothing to do._")
        _append_summary(summary_path, summary_lines)
        return 0

    for project_cfg in projects:
        owner = project_cfg["owner"]
        number = project_cfg["number"]
        name = project_cfg.get("name") or f"{owner}/{number}"

        _log_event(event="fetch_start", project=name, owner=owner, number=number)
        project_json = fetch_project(owner, number)
        new_snap = to_snapshot(project_json)
        old_snap = load_snapshot(state_path(state_dir, project_cfg))
        diff = snapshot.compute_diff(old_snap, new_snap)

        # Carry the bypass-event log forward across snapshots; it's the
        # audit-trail record of every override the bot honoured. Checks
        # append into the same list via ctx.bypass_events.
        bypass_events = list((old_snap or {}).get("bypass_events") or [])

        try:
            fields = resolve_fields(project_json)
        except KeyError as exc:
            _log_event(event="field_resolution_error", project=name, error=str(exc))
            summary_lines.append(f"### {name}\n\n- field resolution failed: `{exc}`")
            continue

        summary_lines.append(f"### {name}")
        summary_lines.append("")
        if not diff:
            summary_lines.append("_No changes since last run._")
        else:
            summary_lines.append(f"Observed **{len(diff)}** change(s):")
            for change in diff:
                summary_lines.append(
                    f"- `{change.kind}` `{change.item_id}` "
                    f"{change.field_name or ''} "
                    f"{change.old_value!r} → {change.new_value!r}".rstrip()
                )

        fired = 0
        for change in diff:
            for check_name, fn in registry.items():
                mode = (config.get("checks") or {}).get(check_name, "off")
                if mode in (None, "", "off", False):
                    continue
                ctx = CheckContext(
                    project_cfg=project_cfg,
                    fields=fields,
                    config=config,
                    mode=mode,
                    snapshot=new_snap,
                    actions=actions,
                    evidence=evidence,
                    bypass_events=bypass_events,
                )
                _log_event(
                    event="check_dispatch",
                    project=name,
                    check=check_name,
                    mode=mode,
                    item=change.item_id,
                    kind=change.kind,
                    field=change.field_name,
                )
                fn(change, ctx)
                fired += 1

            # Per-status precondition dispatch (separate from named checks
            # because each status carries its own mode in config.preconditions).
            if change.kind == "field_change" and change.field_name == "Status" and change.new_value in PRECONDITIONS:
                status = change.new_value
                pre_mode = (config.get("preconditions") or {}).get(status, "off")
                if pre_mode not in (None, "", "off", False):
                    pctx = CheckContext(
                        project_cfg=project_cfg,
                        fields=fields,
                        config=config,
                        mode=pre_mode,
                        snapshot=new_snap,
                        actions=actions,
                        evidence=evidence,
                        bypass_events=bypass_events,
                    )
                    item = (new_snap.get("items") or {}).get(change.item_id) or {}
                    reasons = PRECONDITIONS[status](item, pctx, evidence)
                    _log_event(
                        event="precondition_dispatch",
                        project=name,
                        status=status,
                        mode=pre_mode,
                        item=change.item_id,
                        failures=len(reasons),
                    )
                    if reasons and item.get("source_repo") and item.get("number"):
                        body_lines = [
                            f"**Precondition violation entering `{status}`** (mode: `{pre_mode}`)",
                            "",
                        ]
                        body_lines.extend(f"- {r}" for r in reasons)
                        actions.post_comment(item["source_repo"], item["number"], "\n".join(body_lines))
                        actions.apply_label(item["source_repo"], item["number"], "process-violation")
                        fired += 1

                        if pre_mode == "active":
                            from project_enforcement.enforcement import (
                                clear_bypass, has_bypass, revert_status,
                            )
                            if has_bypass(pctx, item["source_repo"], item["number"]):
                                clear_bypass(
                                    pctx, item["source_repo"], item["number"],
                                    item_id=change.item_id,
                                    old_status=change.old_value,
                                    new_status=change.new_value,
                                )
                            else:
                                revert_status(pctx, change.item_id, change.old_value)

        summary_lines.append(f"\nChecks fired: **{fired}**\n")

        # Age out bypass events older than 30 days before persisting; the
        # audit only needs a recent window for the rolling-issue panel.
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
        def _recent(ev):
            ts = ev.get("ts")
            if not ts:
                return True
            try:
                return datetime.datetime.fromisoformat(ts) >= cutoff
            except ValueError:
                return True
        new_snap["bypass_events"] = [ev for ev in bypass_events if _recent(ev)]

        write_snapshot(state_path(state_dir, project_cfg), new_snap)
        _log_event(event="snapshot_written", project=name)

    _append_summary(summary_path, summary_lines)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=".github/project-enforcement.yml")
    parser.add_argument("--state-dir", default="_project-state")
    args = parser.parse_args(argv)

    config = load_config(args.config)

    if all_checks_off(config):
        _log_event(event="all_checks_off", config=args.config)
        _append_summary(
            os.environ.get("GITHUB_STEP_SUMMARY"),
            [
                "## Project enforcement",
                "",
                "_All checks are `off` — handler skipped._",
            ],
        )
        return 0

    return run(
        config,
        state_dir=args.state_dir,
        summary_path=os.environ.get("GITHUB_STEP_SUMMARY"),
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
