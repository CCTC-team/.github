# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The org-level `.github` repository for the `CCTC-team` GitHub organisation. Two distinct kinds of thing live here:

1. **Org defaults** — community-health files (issue/PR templates, `SECURITY.md`), the canonical `labels.json`, and `compliance.schema.json`. Files here become the default for every org repo that does not define its own, but several things are deliberately **not** inherited (labels, CODEOWNERS, branch protection/rulesets, repo scaffolding) — see the "How inheritance works" section of `README.md` before assuming a change propagates.
2. **The regulated-lifecycle enforcement engine** — a Python package (`scripts/project_enforcement/`) plus the workflows that run it, which police a GitHub Projects board representing the V&V lifecycle of regulated (clinical-trial) features. This is where almost all the code and tests live and is the focus below.

The org is a UK clinical-trials unit; much of the design is driven by GxP / ALCOA+ audit-trail requirements. The `docs/*-rationale.md` files are inspector-facing explanations of *why* a control exists — read them before changing a control's behaviour.

## Commands

Tests are Python (pytest). `conftest.py` at the repo root inserts `scripts/` onto `sys.path`, so **run pytest from the repo root**, not from `scripts/`:

```bash
# Full enforcement suite
python -m pytest scripts/project_enforcement/tests

# One file / class / test
python -m pytest scripts/project_enforcement/tests/test_drift_checks.py
python -m pytest scripts/project_enforcement/tests/test_drift_checks.py::TestApproverIdentityDrift::test_no_revert
```

Dependencies: `pytest` and `pyyaml` (the handler imports `yaml`). There is no `requirements.txt`; install them into a venv if the environment lacks them.

```bash
# Label sync (needs an authenticated `gh` + `jq`); idempotent
./scripts/sync-labels.sh            # all non-archived org repos
./scripts/sync-labels.sh my-repo    # one repo
ORG=other-org ./scripts/sync-labels.sh

# The enforcement handler (normally run by the workflow, not by hand)
python scripts/project_enforcement/handler.py \
    --config .github/project-enforcement.yml --state-dir _project-state
```

## Enforcement engine architecture

The engine is a **poll → diff → dispatch** loop, runnable offline against fixtures because all GitHub side-effects sit behind Protocols.

- **`handler.py`** — entry point. Reads `.github/project-enforcement.yml`, snapshots each configured board, diffs against the previous snapshot, and dispatches every `CardChange` to the registered checks. Each check runs in a mode from the config: `off` (skip), `evaluate` (comment/label only), or `active` (also revert the offending field write, honouring the bypass label).
- **`snapshot.py`** — `CardChange` dataclass and `compute_diff`. **Important design constraint:** a check is given only the *new* snapshot (`ctx.snapshot`) plus the per-field `CardChange` (with `old_value`/`new_value`). The **prior snapshot is not available to checks** — only the handler holds it. Designs that "compare against the previous status" must work around this (e.g. infer prior state from `old_value`) rather than plumbing the old snapshot through `CheckContext`.
- **`actions.py` / `evidence.py`** — the ports. `ActionsLike` is the *only* sanctioned set of GitHub mutations (post comment, add/remove label, revert single-select, user-exists); checks must not invent new side-effects. `EvidenceLike` wraps reads a snapshot doesn't carry (the source repo's `.compliance.yml`, issue body, linked PRs, check-runs). Default impls shell out to `gh` (assume `GH_TOKEN`); tests inject `RecordingActions` / `StubEvidence`.
- **`state_machine.py`** — the lifecycle is a **forward-only chain** (`Triage … Released`). **Backward moves are always legal** (recover from a mistaken advance); two side-exits (`Redundant`, `Archived`) are reachable from anywhere and may only re-enter at `Triage`. This "backward is legal" rule is why drift checks cannot trust the card's *current* status alone.
- **`checks/`** — two families, each one small module per concern:
  - `checks/preconditions/<status>.py` — gate entry into a lifecycle status (registered in `PRECONDITIONS`).
  - `checks/drift/*.py` — fire on a specific `field_change` and decide whether the new value is consistent with the rest of the world; **audit-only by default** (comment, do not revert). Each exposes `check(change, ctx, evidence=None)` and a `register(registry)`.
- **`ctq.py`** — single source of truth for the Critical-to-Quality vocabulary (`Critical` / `Important` / `No`, plus the legacy `Yes` alias = critical, and which Test Types satisfy a critical feature). Any check reasoning about CtQ must go through `ctq.tier(...)` rather than re-deriving the aliases.

### The config switchboard

`.github/project-enforcement.yml` lists the boards under enforcement and the per-check / per-precondition mode. It lives **only in this repo and is deliberately not pushed into regulated repos by drift**. Field IDs are resolved by *name* at runtime, so the same config works against a freshly cloned board. Graduating a check is a config edit (`off → evaluate → active`), watched for a cycle in `evaluate` first.

## Conventions

- **Audit-trail checks widen *when they comment*, not *whether they revert*.** A drift check staying audit-only (never reverting) is a deliberate stance encoded in its docstring and a `test_no_revert`-style test — preserve it unless the task explicitly changes it.
- **Keep planning/process vocabulary out of source and tests.** No phase numbers, plan section refs, or review-item IDs in code, comments, fixture names, or commit-referenced identifiers — files must stand alone. Name fixtures after the behaviour they test.
- **Lifecycle status and field names are exact strings** shared across the state machine, preconditions, board, and tests (e.g. `User acceptance`, `Acceptance Approver`). A rename is cross-cutting — grep the package, the config, and `README.md`. Note the historical `PQ review`→`User acceptance` / `PQ Approver`→`Acceptance Approver` rename when reading older docs/plans.
- **`README.md` documents these controls for humans and goes stale silently.** When you change a check's trigger or a control's behaviour, update the matching `README.md` bullet (and any relevant `docs/*-rationale.md`) in the same change.

## Keep the wiki in sync

This repo has an accompanying GitHub wiki checked out alongside it at `~/repos/.github.wiki` (pages such as `Compliance-Framework.md`, `Branch-Protection-Rulesets.md`, `GxP-Traceability-Gate.md`). **Whenever anything of substance changes in this repo** — a control's behaviour, the compliance schema, rulesets, workflows, inheritance rules, labels, or the enforcement engine — check the corresponding wiki page(s) and update them so the two stay consistent. **The repo is the authoritative source of truth**; when the wiki and the repo disagree, fix the wiki to match the repo (not the other way round). Like `README.md`, the wiki goes stale silently, so reconcile it in the same change rather than leaving it for later.

## Implementation plans

`AIPlans/` holds phased implementation plans: top-level = not started, `InProgress/`, `Complete/`. Plans are executed phase-by-phase (often TDD: write/flip the test, watch it fail, then implement) with checkboxes updated as work lands. When implementing from a plan, read it in full first — its design decisions are the spec.
