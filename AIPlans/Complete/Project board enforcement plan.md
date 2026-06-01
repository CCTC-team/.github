# Project board enforcement plan

## Context

The CCTC regulated-feature lifecycle board (project 31 in the `CCTC-team`
org) is currently a visualisation only — none of its 27 fields are
validated and a card can be dragged from `Triage` straight to
`QA approved` without going through code review, V&V, PQ, or QA. The
existing gates (`gxp-traceability.yml`, `compliance-check.yml`, org
rulesets, issue-template required fields, label sync) protect the
**issue → PR → merge** path; they do not protect the **board** that the
QA / PQ reviewers actually look at when attesting to a feature.

This plan adds project-level enforcement layered on top of those gates:
a state-machine for legal status transitions, per-column precondition
checks (including segregation-of-duties for PQ/QA approvers), checkbox
enforcement on the regulated-feature issue body, card↔issue field-drift
detection, opt-in auto-population from PR events, and a nightly audit
sweep. Rollout follows the same evaluate→active pattern the rulesets
and the GxP gate already use, so violations are observed in
production before they start blocking.

Cards on the board originate from many repos, so every per-card check
must resolve regulatory context (`.compliance.yml`, default branch,
linked-PR state) against the **card's source repo**, not against
`.github`.

---

## Key References

- `.github/workflows/gxp-traceability.yml` — the canonical pattern this
  plan extends: evaluate/active enforcement modes, Python-in-venv,
  quoted heredocs for untrusted data, GraphQL via `gh api`, step
  summary. Reuse this shape; do not invent a new one.
- `.github/ISSUE_TEMPLATE/regulated_feature.yml` — defines the exact
  labels (`PQ review checklist:`, `QA review checklist:`) and the
  `Risk ID:` / `Requirement ID:` lines the handler must parse out of
  issue bodies. The PQ/QA checklist `options:` text is what `- [x] …`
  must match.
- `README.md` §"Compliance metadata" + §"Branch protection strategy" —
  authoritative description of `regulatory_tier`, `validated_paths`,
  enforcement modes, and the rationale the audit issue should cite.
- `.github/workflows/compliance-drift.yml` + `scripts/compliance-drift.sh`
  — the established org-wide nightly sweep pattern; copy its
  repo-iteration style for the nightly audit.
- `templates/compliance/` — drift pushes these into every regulated
  repo; the regulated-developer documentation added in Phase 7 lives
  here so it propagates without per-repo PRs.
- GitHub docs:
  - REST: `POST /repos/{owner}/{repo}/dispatches` (repository_dispatch
    trigger) — needed if Phase 0 ever upgrades from polling to
    webhook-driven.
  - GraphQL `ProjectV2`, `ProjectV2Item`, `updateProjectV2ItemFieldValue`,
    `closingIssuesReferences` — the mutation/query surface the handler
    uses.
  - `projects_v2_item.edited` webhook payload reference (for the
    eventual webhook upgrade).
- Project 31 field IDs (already captured via
  `gh project field-list 31 --owner CCTC-team --format json`) — the
  handler resolves field IDs by **name** at runtime rather than
  hard-coding these IDs, so the project can be cloned for production
  use without code changes.

---

## Key Design Decisions

1. **Polling-based plumbing in v1; webhook upgrade deferred.** GitHub
   Actions has no `on: projects_v2_item` trigger. Three options were
   considered: (A) org webhook → hosted receiver → `repository_dispatch`,
   (B) a new GitHub App with the `organization_projects` subscription
   replying directly, (C) a scheduled poller in `.github` that diffs
   project state. Picked **C** because it is pure-GitHub-native (no
   new hosted infrastructure, no new App to provision), matches the
   existing `compliance-drift` cron pattern, and the lag (5 min) is
   acceptable for evaluate-mode rollout. The handler is structured so
   the same Python module can later be driven by a `repository_dispatch`
   payload — only the entry point changes when upgrading to A.

2. **Snapshot stored on a dedicated `_project-state` branch in `.github`,
   not in Actions cache or artifacts.** Cache is best-effort and can be
   evicted; artifacts expire after 90 days. A force-pushed orphan
   branch (`_project-state`, bot-only) gives a durable diff base and an
   inspectable history of project state — useful evidence for an audit.

3. **Field resolution by name, not by hard-coded ID.** Project 31's
   field IDs are specific to that project; the production board will
   have different IDs. The handler reads the project's field list at
   the start of each run and builds a `name → id` map. Cards moved
   across cloned boards (e.g. test → production) still work.

4. **Issue body is the source of truth for `Risk ID` / `Requirement ID`;
   project fields are mirrors.** The PR gate already reads the issue
   body. If the card field drifts from the issue body, the handler
   reverts the card field and comments on the issue — never the other
   way around. This keeps the regulated-feature template's
   `required: true` fields load-bearing.

5. **Evaluate→active rollout per check, not all-or-nothing.** Each
   check carries its own `evaluate | active` setting in a
   `.github/project-enforcement.yml` config file (committed to the
   `.github` repo). A check can graduate independently as
   evaluate-mode telemetry shows it is well-calibrated. Same shape as
   `gxp-traceability.yml`'s `enforcement` input.

6. **Reverts and comments are the only side effects; no force-close,
   no auto-promote to `QA approved`.** Auto-population (Phase 5) only
   moves cards *forward* through *automatic* states (`Code review`,
   `V&V tests pass`). `PQ review`, `QA approved`, and `Released` are
   human-attested and must never be reached by automation.

7. **Segregation-of-duties check compares GitHub login identities, not
   names.** Approver fields on the card are free-text — they must be
   GitHub usernames (without the `@`) for the check to work. The
   handler validates the username exists via `gh api /users/{login}`
   before accepting the transition. Documented in the regulated
   contributor doc (Phase 7).

8. **One project handler module, one workflow.** Resist the temptation
   to give each check its own workflow file. The state-machine and
   precondition checks share the GraphQL fetch, the snapshot diff,
   and the comment/revert helpers. Splitting them would multiply API
   calls and make the snapshot diff race-prone.

9. **Bypass via a `process-override:approved` label on the linked
   issue, set by an org admin.** Mirrors the ruleset `OrganizationAdmin`
   bypass actor pattern. The override applies to one transition only —
   the handler clears the label after honouring it and records the
   override in the nightly audit issue. No standing exemptions.

10. **No new GitHub App in v1.** The workflow uses the existing
    `GITHUB_TOKEN` plus a fine-grained PAT (or the existing
    Compliance Drift App's token) for cross-repo issue/PR reads and
    project field writes. Adding a third App was considered and
    rejected for v1 — defer until the webhook upgrade (which needs
    one anyway). The token requirements are documented in Phase 0.

11. **Multiple lifecycle board copies are first-class; the project
    number is never hard-coded.** Project 30 is the template, project
    31 is the test clone, and production will likely have several
    (e.g. per-trial or per-programme boards). Two consequences flow
    from this:
    - The polling handler iterates `projects:` in
      `.github/project-enforcement.yml`. New copies are enforced by
      adding one line to that file. Snapshots and audit issues are
      per-project so copies stay isolated.
    - The PR-driven promoter (Phase 5) reads
      `vars.LIFECYCLE_PROJECT_NUMBER` from each regulated repo
      rather than hard-coding a number in the caller workflow.
      Repos that point at different boards just set different
      variable values; drift pushes the same caller everywhere.
    Auto-discovery of clones was considered and rejected — "any
    project with these Status options" is too fuzzy to be the basis
    of a regulated control. Instead the nightly audit (Phase 6f)
    *warns* about org projects that look like lifecycle boards but
    aren't in the config; enforcement still requires an explicit
    config entry.

---

## Phase 0: Plumbing — scheduled poller, snapshot, handler skeleton

Goal: a workflow that runs every 5 minutes, fetches project state,
diffs against the previous snapshot, and invokes a Python handler with
the per-card change set. No checks are wired in yet — this phase only
proves the plumbing.

- [x] **0a. NEW:** `.github/project-enforcement.yml`
  - Repo-level config consumed by the workflow.
  - Fields:
    - `projects:` — list of `{ owner, number, name }` entries the
      handler should watch (initially just project 31).
    - `checks:` — map of check name → `evaluate | active | off`.
      Initially every check defaults to `off`; phases below flip
      individual entries to `evaluate`.
    - `bypass_label:` — `process-override:approved`.
    - `default_branch_fallback:` — `main`.
  - Note: This file is the single switch the team uses to graduate
    checks. It is **not** in `templates/compliance/` — it lives in
    `.github` only.

- [x] **0b. NEW:** `scripts/project_enforcement/__init__.py`
  - Empty package marker.

- [x] **0c. NEW (test):** `scripts/project_enforcement/tests/test_snapshot_diff.py`
  - Pytest cases for `compute_diff(old, new) -> list[CardChange]`:
    - New card added (no entry in old).
    - Card removed (no entry in new).
    - Card's Status field changed: emits `field_change` with
      `field="Status"`, `old="Triage"`, `new="Risk linked"`.
    - Card's custom field changed (e.g. `Risk ID`).
    - Card unchanged: emits nothing.
    - Multiple cards changed in one run.

- [x] **0d. NEW:** `scripts/project_enforcement/snapshot.py`
  - `fetch_project(owner, number) -> dict`: GraphQL query returning
    every item with all field values, paginated. Use `gh api graphql`
    via `subprocess.run` (matches existing scripts' style).
  - `compute_diff(old, new) -> list[CardChange]`: implementation that
    satisfies 0c.
  - `CardChange` is a `@dataclass`: `item_id, content_id, content_type
    (issue | pull_request | draft), source_repo, kind (added | removed |
    field_change), field_name, old_value, new_value`.

- [x] **0e. NEW (test):** `scripts/project_enforcement/tests/test_field_resolution.py`
  - Pytest cases for `resolve_fields(project_json) -> dict[str, FieldRef]`:
    - Returns name→id mapping for every field.
    - Distinguishes single-select fields (carries `options:
      {name → id}`) from plain text/date fields.
    - Raises a clear error if a required field name is missing.

- [x] **0f. NEW:** `scripts/project_enforcement/fields.py`
  - `resolve_fields(project_json) -> dict[str, FieldRef]` that
    satisfies 0e. Used by every check so they can write back via
    name.

- [x] **0g. NEW:** `scripts/project_enforcement/handler.py`
  - Entry point. CLI: `python handler.py --config .github/project-enforcement.yml`.
  - Loads config, iterates projects, for each: fetches snapshot from
    `_project-state` branch (empty dict if absent), fetches current
    state via GraphQL, computes diff, dispatches each `CardChange` to
    a registry of check functions (empty in this phase), writes new
    snapshot back to `_project-state`.
  - Emits a per-run step summary listing every change observed and
    every check that fired (none in this phase) — same shape as
    `gxp-traceability.yml`'s summary.
  - Logs structured JSON to stdout for each event (timestamp, project,
    item, kind, fields).

- [x] **0h. NEW:** `.github/workflows/project-enforcement.yml`
  - Triggers:
    - `schedule: - cron: "*/5 * * * *"`
    - `workflow_dispatch:` (manual run for development)
  - Job:
    - `runs-on: ubuntu-latest`
    - Permissions: `contents: write` (snapshot branch),
      `issues: write` (comments, labels), `pull-requests: read`.
    - Steps: checkout `main`, checkout `_project-state` into a sub-
      directory (allow-fail if branch absent), set up Python venv
      installing `pyyaml`, `pathspec`, `pytest` (test-time only),
      run `python scripts/project_enforcement/handler.py`, commit and
      force-push `_project-state` (signed by the App, see 0j).
  - Note: concurrency `group: project-enforcement` `cancel-in-progress:
    false` — never overlap runs, never lose state.

- [x] **0i. MODIFY:** `.github/workflows/project-enforcement.yml`
  - Add a guard step that exits 0 if `project-enforcement.yml` config
    file is missing or all checks are `off`. Keeps the cron cheap
    while the rollout is in early phases.
  - **Deviation from plan:** the guard step was authored as part of 0h
    rather than as a separate follow-up edit. The end state matches
    what the plan describes; the two items were collapsed into a
    single file write.

- [x] **0j. MODIFY:** `docs/compliance-drift-app-setup.md` (or NEW
  `docs/project-enforcement-app-setup.md` if it grows beyond a section)
  - **Deviation from plan:** chose the NEW path
    (`docs/project-enforcement-app-setup.md`) because the project/org
    scopes differ materially from drift's scopes and the runbook is
    long enough to stand alone. Both provisioning options
    (Option A: expand the existing App; Option B: provision a separate
    `CCTC Project Enforcement` App) are presented side-by-side; the
    user must choose before secrets are created. README.md table
    updated to point at the new doc.
  - Document the token requirements: the workflow needs
    `read:project`, `write:project`, `read:org` (to resolve approver
    usernames), and `repo` (to read `.compliance.yml` and PR state
    from other repos). The existing Compliance Drift App has the
    repo scopes but not project scopes — either expand it or add a
    `read:project,write:project` org-secret PAT for v1.
  - Note: ask the user which path they prefer before provisioning;
    do not pick unilaterally.

- [x] **0k. NEW:** `scripts/project_enforcement/tests/test_handler_smoke.py`
  - One end-to-end test using a recorded GraphQL response fixture:
    handler receives a known diff, the (empty) check registry is
    called with the expected `CardChange` objects, snapshot writer
    is called with the expected JSON. No real network.

**Verification at end of Phase 0**: the workflow runs on the cron,
the `_project-state` branch is created and updated, the step summary
shows changes observed without taking any action.

---

## Phase 1: State-machine transition check (evaluate mode)

Goal: detect illegal status transitions; comment on the linked issue;
do not revert yet.

- [x] **1a. NEW (test):** `scripts/project_enforcement/tests/test_state_machine.py`
  - Pytest cases for `legal_transition(old: str, new: str) -> bool`:
    - Forward path legal: `Triage → Risk linked`,
      `Risk linked → Requirement defined`, …,
      `QA approved → Released`.
    - Skipping forward is illegal: `Triage → QA approved`,
      `Code review → Released`.
    - Backward moves always legal: `Released → Triage`,
      `PQ review → In development`.
    - Side exits always legal: anything → `Redundant`,
      anything → `Archived`.
    - From `Redundant` or `Archived`, restoring to `Triage` legal;
      restoring directly to anything past `Triage` illegal.

- [x] **1b. NEW:** `scripts/project_enforcement/state_machine.py`
  - Constants for the lifecycle order.
  - `legal_transition(old, new) -> bool` satisfying 1a.

- [x] **1c. NEW:** `scripts/project_enforcement/checks/transition.py`
  - Check function registered as `transition`. Triggered by a
    `field_change` with `field_name == "Status"`.
  - On illegal transition: emit a step-summary row, post an issue
    comment quoting the rule and the actor (from
    `projectV2Item.lastEditedBy` if available — fall back to
    "unknown" in polling mode), apply the
    `process-violation` label (created by sync-labels — add it in
    1e).
  - In evaluate mode: only comment and label. Do not revert.

- [x] **1d. MODIFY:** `scripts/project_enforcement/handler.py`
  - Register the `transition` check; flip the config entry for
    `transition: evaluate` in `.github/project-enforcement.yml`.

- [x] **1e. MODIFY:** `labels.json`
  - Add `process-violation` (red, "Skipped a required step in the
    regulated-feature lifecycle") and `process-override:approved`
    (yellow, "Org admin has authorised a single bypass").

- [x] **1f. NEW (test):** `scripts/project_enforcement/tests/test_check_transition.py`
  - Pytest cases covering: legal forward = no action; illegal forward
    = one comment, one label, no revert; backward = no action; the
    actor identity appears in the comment; evaluate mode never calls
    the revert helper.

**Verification at end of Phase 1**: deliberately drag the test card
on project 31 from `Triage` to `QA approved`; within 5 min the issue
gets a comment and the `process-violation` label; the card is **not**
moved back.

---

## Phase 2: Per-column precondition checks (evaluate mode)

Goal: when a card *enters* a status, assert the preconditions for that
status are satisfied; comment + label if not. Still no revert.

Each precondition function is its own module so they can graduate to
active independently.

**Deviation from plan:** items 2b–2j were implemented before the
parameterised test surface in 2a. The end state matches the plan, and
the 42 cases in `test_preconditions.py` cover the matrix the plan asks
for (passing case + failing case per individual precondition), but the
discipline was implementation-first rather than test-first. Introduced
two supporting modules the plan did not name: `evidence.py` (with
`GhEvidence` + `StubEvidence`) and `body_parser.py` (form-aware
`### Header` extractor) — the preconditions need external reads
(`.compliance.yml`, issue body, linked PRs, default branch, URL HEAD,
releases) and a body parser that handles the issue-form rendering.
`actions.py` was also introduced under Phase 1 to provide the
write-side surface (comments, labels, single-select revert,
`user_exists`).

- [x] **2a. NEW (test):** `scripts/project_enforcement/tests/test_preconditions.py`
  - One test class per status with parameterised cases. For each
    precondition documented in the design table (Risk linked,
    Requirement defined, In development, Code review, V&V tests pass,
    PQ review, QA approved, Released): a passing case and one failing
    case per individual precondition.
  - Use fixtures for: project field values, issue body, linked-PR
    GraphQL result, `.compliance.yml` content for the source repo.

- [x] **2b. NEW:** `scripts/project_enforcement/checks/preconditions/risk_linked.py`
  - Asserts `Risk ID` field non-empty **and** matches the
    `Risk ID:` line in the issue body. Returns a list of failure
    reasons (empty = pass).

- [x] **2c. NEW:** `scripts/project_enforcement/checks/preconditions/requirement_defined.py`
  - Asserts `Requirement ID` field non-empty, matches issue body,
    and `Critical-to-Quality` chosen.

- [x] **2d. NEW:** `scripts/project_enforcement/checks/preconditions/in_development.py`
  - Asserts assignee present, `Iteration` set, `Test Type` set, and
    if `Critical-to-Quality == Yes` then `Test Type ∈ {PQ, OQ+PQ,
    IQ+OQ+PQ}`.

- [x] **2e. NEW:** `scripts/project_enforcement/checks/preconditions/code_review.py`
  - Calls `closingIssuesReferences` in reverse (find PRs that close
    this issue) on the **source repo**; asserts at least one open PR
    exists.

- [x] **2f. NEW:** `scripts/project_enforcement/checks/preconditions/vv_tests_pass.py`
  - Linked PR's `gxp-traceability` and `compliance` check runs are
    green on the latest head. `Feature link:` URL resolves
    (HEAD 200) to a `.feature` path on the source repo's default
    branch.
  - Note: fetch default branch from
    `repos/{owner}/{repo}` GET; cache per source repo per run.

- [x] **2g. NEW:** `scripts/project_enforcement/checks/preconditions/pq_review.py`
  - Both `PQ review checklist` boxes ticked in issue body
    (`- [x]` against the exact option strings from
    `regulated_feature.yml`). `PQ Approver` set and is a valid
    GitHub user. `PQ Approver` ≠ issue author and ≠ any commit author
    on the linked PR.

- [x] **2h. NEW:** `scripts/project_enforcement/checks/preconditions/qa_approved.py`
  - Both `QA review checklist` boxes ticked. `QA Approver` and
    `QA Signoff Date` set; date not in future; date ≥
    `PQ Signoff Date`. `QA Approver` ∉ {issue author, PR commit
    authors, PQ Approver}. If the linked PR has any previous failing
    `gxp-traceability` run, `Deviation Ref` non-empty.

- [x] **2i. NEW:** `scripts/project_enforcement/checks/preconditions/released.py`
  - Linked PR merged into the source repo's default branch.
  - Previous status was `QA approved` (already enforced by the
    state machine, but re-asserted here for defence-in-depth).
  - A release tag or draft referencing the merge SHA exists on the
    source repo.

- [x] **2j. NEW:** `scripts/project_enforcement/checks/preconditions/__init__.py`
  - `PRECONDITIONS: dict[str, Callable] = { "Risk linked":
    risk_linked.check, "Requirement defined":
    requirement_defined.check, … }`.
  - One dispatch function the handler calls when a `Status` field
    change is observed and the new value has an entry.

- [x] **2k. MODIFY:** `scripts/project_enforcement/handler.py`
  - On any `Status` field change, after the transition check, look up
    the new status in `PRECONDITIONS`; if present, run the function
    and emit failures the same way the transition check does
    (comment + label, no revert in evaluate mode).

- [x] **2l. MODIFY:** `.github/project-enforcement.yml`
  - Add `preconditions:` map of status name → `evaluate | active | off`,
    all initially `evaluate` except `Released` (`off` until Phase 5 is in
    place, since its precondition depends on PR-driven auto-population).

**Verification at end of Phase 2**: for each status, set up a card that
violates exactly one precondition, move it into that column, observe
the expected comment.

---

## Phase 3: Issue-body checkbox enforcement

Goal: the PQ / QA checklists on the issue body must be ticked before
the card can advance past PQ / QA. Already partially covered by 2g /
2h, but the parsing logic is shared and worth a dedicated test surface.

- [x] **3a. NEW (test):** `scripts/project_enforcement/tests/test_checkbox_parser.py`
  - Pytest cases for `parse_checklist(body: str, header: str) ->
    list[(label, checked)]`:
    - Recognises the exact `PQ review checklist:` and
      `QA review checklist:` headers from `regulated_feature.yml`.
    - Picks up `- [x]` (checked) and `- [ ]` (unchecked) under the
      correct header only.
    - Stops at the next header (does not bleed into the section
      below).
    - Handles trailing whitespace and capital `X`.
    - Returns empty list if the header is missing.

- [x] **3b. NEW:** `scripts/project_enforcement/checkboxes.py`
  - `parse_checklist` implementation satisfying 3a.
  - `all_ticked(parsed) -> bool`.

- [x] **3c. MODIFY:** `scripts/project_enforcement/checks/preconditions/pq_review.py`
  - Replace ad-hoc regex with a call to `parse_checklist` +
    `all_ticked`.

- [x] **3d. MODIFY:** `scripts/project_enforcement/checks/preconditions/qa_review.py`
  - Same.
  - **Deviation from plan:** the file is named `qa_approved.py` (not
    `qa_review.py`) because the *status* it gates is "QA approved" and
    the precondition dispatcher keys on status names. The plan
    referenced the legacy column name; the refactor in 3d was applied
    to `qa_approved.py`.

**Verification at end of Phase 3**: move a card to PQ review with one
checkbox unticked — get a comment that names the unticked item.

---

## Phase 4: Field-drift checks (evaluate mode)

Goal: detect inconsistencies on `edited` events that aren't status
changes — e.g. someone changes the card's `Risk ID` field but not the
issue body, or back-dates a signoff.

- [x] **4a. NEW (test):** `scripts/project_enforcement/tests/test_drift_checks.py`
  - Cases for each drift check below: matching state passes, drifted
    state returns a failure reason.

- [x] **4b. NEW:** `scripts/project_enforcement/checks/drift/id_mirror.py`
  - On `Risk ID` or `Requirement ID` field change, compare to the
    issue body; if they don't match, post a comment naming both
    values and flag the issue body as canonical.

- [x] **4c. NEW:** `scripts/project_enforcement/checks/drift/date_sanity.py`
  - On `PQ Signoff Date` or `QA Signoff Date` change: not in future,
    not before the issue was opened, PQ ≤ QA.

- [x] **4d. NEW:** `scripts/project_enforcement/checks/drift/approver_identity_drift.py`
  - On `PQ Approver` or `QA Approver` change when the card is **past**
    that column: log an audit comment with old/new approver and the
    actor. Do not revert (the change might be a legitimate
    correction); the goal is the audit trail.

- [x] **4e. NEW:** `scripts/project_enforcement/checks/drift/type_quality_consistency.py`
  - On `Test Type` or `Critical-to-Quality` change: inconsistent
    combination (`Test Type=N/A` + `Critical-to-Quality=Yes`) → comment.

- [x] **4f. MODIFY:** `scripts/project_enforcement/handler.py`
  - Wire drift checks into the field_change dispatcher (independent
    of status transitions).

**Verification at end of Phase 4**: edit a card's `Risk ID` to something
different from the issue body — get the mirror-drift comment.

---

## Phase 5: Auto-population from PR events

Goal: PR-driven, forward-only automatic moves through the *automatic*
states (`Code review`, `V&V tests pass`). Never promote past `V&V
tests pass`.

Note: this phase introduces an event-driven workflow (in the
**source repos**, via the existing reusable-workflow pattern) — it is
not part of the polling handler.

- [x] **5a. NEW:** `.github/workflows/project-card-promote.yml`
  - Reusable workflow callable by regulated repos. Inputs:
    `project_owner` (string), `project_number` (number, **passed by
    the caller from a repo variable** — not defaulted), target
    board's regulated-status field name (default `Status`).
  - Triggered indirectly: regulated repos add a caller workflow that
    fires on `pull_request` (`opened`, `synchronize`, `closed`) and
    `check_suite.completed`.
  - **Guard step:** if `project_number` is empty or `0`, exit 0 with
    a step-summary note "no LIFECYCLE_PROJECT_NUMBER set on this
    repo — promotion skipped". This is the failure mode when a
    regulated repo opts in via drift but hasn't yet had its variable
    set; better to no-op than to fail every PR check.
  - **Allowlist check:** after resolving the project, refuse to write
    if the resolved project ID is not present in the
    `projects:` list of `.github/project-enforcement.yml`. Prevents a
    regulated repo from accidentally promoting cards on an
    unmonitored board.
  - Logic:
    - On PR opened that closes a regulated issue → move card to
      `Code review` (only if currently `In development` or earlier).
    - On `check_suite.completed` for that PR's head SHA, where
      `gxp-traceability` and `compliance` are green → move card to
      `V&V tests pass` (only if currently `Code review` or earlier).
    - On PR merged → do nothing automatic. (Confirmed by Decision 6.)
  - Uses `gh api graphql` for the `updateProjectV2ItemFieldValue`
    mutation. Lookup the card via the issue's
    `projectItems(first: 20)` connection.

- [x] **5b. NEW:** `templates/compliance/project-card-promote-caller.yml`
  - Caller that regulated repos opt into. Reads
    `vars.LIFECYCLE_PROJECT_NUMBER` instead of hard-coding a value:
    ```yaml
    name: Project card promote
    on:
      pull_request:
        types: [opened, synchronize, closed]
      check_suite:
        types: [completed]
    jobs:
      promote:
        uses: CCTC-team/.github/.github/workflows/project-card-promote.yml@main
        with:
          project_owner: CCTC-team
          project_number: ${{ vars.LIFECYCLE_PROJECT_NUMBER }}
    ```
  - Note: `vars.LIFECYCLE_PROJECT_NUMBER` is the **repository
    variable** name. Each regulated repo sets it once (Settings →
    Secrets and variables → Actions → Variables) to the project
    number that hosts its lifecycle cards. Repos with no value set
    hit the guard step in 5a and no-op.

- [x] **5c. MODIFY:** `scripts/compliance-drift.sh` and any drift code
  that lists "files to stub in regulated repos"
  - Add the new caller to the list of scaffolding files drift pushes.
    Drift never overwrites it once stubbed (matches the
    `gxp-traceability` caller behaviour).
  - Drift does **not** set the `LIFECYCLE_PROJECT_NUMBER` variable —
    that is a deliberate per-repo decision made when the repo joins
    a lifecycle board. Drift's step summary should call out any
    regulated repo that has the caller workflow but no variable
    value set, so it's visible in the drift PR rather than silent.

- [x] **5d. MODIFY:** `README.md` §"Per-repo opt-in"
  - Add the seventh required file to the bullet list. Reference
    `templates/compliance/project-card-promote-caller.yml`.
  - Add a sentence under the new bullet: "Set the
    `LIFECYCLE_PROJECT_NUMBER` repo variable to the number of the
    lifecycle board this repo's cards live on (e.g. `31` for the
    test board). Without it, the promoter no-ops."

- [x] **5e. MODIFY:** `.github/project-enforcement.yml`
  - Flip `preconditions: { Released: evaluate }` now that the PR
    pipeline is in place.

- [x] **5f. NEW (test):** `scripts/project_enforcement/tests/test_promote_guard.py`
  - Cases for the guard + allowlist logic in 5a (extract the
    decision into a small Python function the caller workflow shells
    into, so it's unit-testable):
    - Empty `project_number` → skip with reason "no variable set".
    - `project_number` not in config allowlist → skip with reason
      "project not monitored".
    - In-allowlist + valid → proceeds.

**Verification at end of Phase 5**: open a PR from a regulated repo that
closes a regulated issue on the test board — the card moves to
`Code review` within a minute; when the PR's checks turn green, it
moves to `V&V tests pass`; merging does nothing further.

---

## Phase 6: Nightly audit + rolling drift issue

Goal: a global daily sweep that catches anything the per-event checks
miss (e.g. cards added before this system existed, or where the
polling window missed an event).

- [x] **6a. NEW (test):** `scripts/project_enforcement/tests/test_audit.py`
  - Cases for each invariant: a card in `Released` with a missing
    field is reported; a card in `QA approved` with author == QA
    approver is reported; a card stuck in `In development` for
    more than N days is reported as a soft warning; healthy cards
    are not reported.

- [x] **6b. NEW:** `scripts/project_enforcement/audit.py`
  - Per-project invariants (one report per project listed in
    `.github/project-enforcement.yml`):
    - Every card in `QA approved` or `Released` has all of:
      `Risk ID`, `Requirement ID`, `Test Type`, `Critical-to-Quality`,
      `PQ Approver`, `PQ Signoff Date`, `QA Approver`,
      `QA Signoff Date`. `Deviation Ref` only if the PR had any
      failed gxp-traceability run.
    - Three distinct identities across issue author / PQ Approver /
      QA Approver.
    - No card in `Released` lacks a linked merged PR.
    - No card in `PQ review` or later with unticked PQ checklist; same
      for QA.
    - Soft: cards in `In development` with no assignee change in
      14 days.
  - **Unmonitored-clone discovery (org-wide invariant).** List every
    project in the `CCTC-team` org via GraphQL
    (`organization.projectsV2`). For each, fetch the `Status`
    field's option names. Compare to the canonical lifecycle
    (`Triage`, `Risk linked`, `Requirement defined`, `In
    development`, `Code review`, `V&V tests pass`, `PQ review`,
    `QA approved`, `Released`, `Redundant`, `Archived`). If a
    project's options are a superset of the canonical set **and**
    it is not in `projects:` in `.github/project-enforcement.yml`,
    add an "Unmonitored lifecycle board" finding naming the project,
    its owner, its number, and the URL. Soft signal only — never
    enforces, never moves cards, never creates issues on the
    unmonitored project. The goal is "you forgot to add this to
    the config" visibility.

- [x] **6c. NEW:** `.github/workflows/project-audit.yml`
  - `schedule: - cron: "0 2 * * *"` (daily, 02:00 UTC — after
    compliance-drift's nightly window).
  - Calls `python scripts/project_enforcement/audit.py`.
  - Finds the open issue titled `Project enforcement drift —
    <project name>` in `.github`; if absent, creates one. Edits its
    body with today's findings (replaces, doesn't append, so the
    issue doesn't grow unbounded).
  - If there are zero findings for the day, closes the issue with a
    comment "no drift detected".

- [x] **6d. NEW (test):** `scripts/project_enforcement/tests/test_audit_issue_writer.py`
  - Cases for: creates issue when none exists; updates body when one
    exists; closes issue when findings are empty; reopens issue when
    findings reappear after a closure.

- [x] **6e. NEW (test):** `scripts/project_enforcement/tests/test_unmonitored_discovery.py`
  - Cases for the discovery logic in 6b:
    - Project's Status options are an exact match for the
      canonical lifecycle and it's in the config → no finding.
    - Project's Status options are an exact match and it's **not**
      in the config → one finding.
    - Project's Status options are a strict superset (e.g. extra
      custom status added) and not in config → one finding.
    - Project has unrelated Status options (e.g. a generic kanban
      `Todo / Doing / Done`) → no finding.
    - Project is archived/closed → no finding regardless.

- [x] **6f. MODIFY:** the rolling audit issue body produced by 6c
  - Add a top-level section "Unmonitored lifecycle boards" listing
    each finding from 6b's discovery pass, with a one-line nudge:
    "Add to `.github/project-enforcement.yml` `projects:` if this is
    a real lifecycle board, or rename its Status options if it is
    not."

**Verification at end of Phase 6**: deliberately leave a `QA Approver`
field blank on a `QA approved` card; the next morning a `Project
enforcement drift` issue exists naming that card and the missing field.

---

## Phase 7: Documentation in templates (so it ships via drift)

Goal: every regulated repo's `CONTRIBUTING-regulated.md` learns about
the board enforcement so developers understand the rules without
reading `.github/AIPlans/`.

- [x] **7a. MODIFY:** `templates/compliance/CONTRIBUTING-regulated.md`
  - Add a "Lifecycle board" section explaining:
    - The status order is enforced; you cannot skip steps.
    - Approver fields must be GitHub usernames (no `@`).
    - PQ / QA checkboxes on the issue body are load-bearing — tick
      them before moving the card.
    - If you genuinely need to bypass a step, ask an org admin to set
      `process-override:approved` on the issue for one transition.
    - Link to the rolling audit issue in `.github`.

- [x] **7b. MODIFY:** `README.md`
  - Add a "Project board enforcement" section after "Branch protection
    strategy", summarising what the new workflow does, the
    evaluate→active rollout, and where the config switch lives
    (`.github/project-enforcement.yml`).

- [x] **7c. MODIFY:** `.github/ISSUE_TEMPLATE/regulated_feature.yml`
  - Update the top-of-form markdown to note that the PQ / QA
    checkboxes are enforced by the board automation, not just
    process guidance.

**Verification at end of Phase 7**: the next compliance-drift run
pushes the updated `CONTRIBUTING-regulated.md` into every regulated
repo; spot-check one.

---

## Phase 8: Flip from evaluate to active

Goal: graduate checks one at a time as evaluate-mode telemetry shows
each is well-calibrated.

- [x] **8a. MODIFY:** `scripts/project_enforcement/handler.py`
  - When a check is in `active` mode and a violation is detected on a
    `Status` field change: in addition to commenting + labelling,
    revert the field via `updateProjectV2ItemFieldValue` to the old
    value. Suppress the revert if the issue carries the
    `bypass_label`; clear that label after honouring it.

- [x] **8b. NEW (test):** `scripts/project_enforcement/tests/test_active_mode.py`
  - Cases for: evaluate mode never reverts; active mode reverts on
    violation; active mode does not revert when bypass label
    present; bypass label is cleared after honouring; revert failure
    (e.g. card already moved again) is logged and surfaced in the
    next audit.

- [x] **8c. MODIFY:** `.github/project-enforcement.yml`
  - Flip `transition: active` after one full week of clean evaluate
    runs.
  - Then graduate per-column preconditions one at a time, lowest-risk
    first (`Risk linked`, `Requirement defined`, `In development`,
    `Code review`) before the four human-attestation gates
    (`V&V tests pass`, `PQ review`, `QA approved`, `Released`).
  - **Deviation from plan:** the config is left in `evaluate` across
    the board. Flipping to `active` is an operational decision that
    must be made *after* the production evaluate-mode telemetry
    confirms each check is well-calibrated — doing the flip in this
    PR would enforce reverts before any real telemetry exists. The
    revert + bypass code (8a) is in place; the rollout log in
    `README.md` (8d) tracks each per-check flip with date + audit
    issue number when it actually happens.

- [x] **8d. MODIFY:** `README.md`
  - Document the active rollout dates per check (mirrors how the
    ruleset enforcement-flip dates are tracked).

**Verification at end of Phase 8**: deliberately violate an active
check; the card snaps back within 5 min, an issue comment names the
rule, the audit issue picks it up overnight.

---

## Verification (overall)

- [x] `python -m pytest scripts/project_enforcement/` — all unit tests
      green. **177 passing locally.**
- [ ] Workflow YAMLs lint clean (`actionlint`) and the reusable
      `project-card-promote.yml` is callable from a sibling repo.
      _Not run locally — actionlint isn't installed in this
      environment. The four new YAMLs (`project-enforcement.yml`,
      `project-card-promote.yml`, `project-audit.yml`, and the caller
      template) all parse cleanly via `yaml.safe_load`. Run actionlint
      in CI or locally before merging._
- [ ] `compliance-drift` dry-run shows the new caller workflow being
      offered to regulated repos. _Pending — requires the
      `ORG_COMPLIANCE_DRIFT_APP_*` secrets plus org access. The
      change is in `scripts/compliance-drift.sh` (sanity-check list +
      step 7 fix block + `LIFECYCLE_PROJECT_NUMBER` notice)._
- [ ] Manual smoke for each phase as captured in its own Verification
      block above. _Pending — needs the project-enforcement token
      provisioned (see Phase 0/0j) and a real card to drag on test
      project 31._
- [ ] Production sign-off: the test project (31) sees a violation,
      audit, and bypass cycle end-to-end without manual intervention,
      then the same exercise is repeated on a freshly-cloned
      production project to prove the field-resolution-by-name
      decision (#3) holds. _Pending — operational, must come after
      the token is provisioned and the workflow has had at least one
      clean cron cycle._

## Open operational follow-ups

1. **Choose Option A vs Option B in
   `docs/project-enforcement-app-setup.md`** and provision the
   resulting App / PAT. Until secrets are set, the cron exits early on
   its guard step.
2. **Set `LIFECYCLE_PROJECT_NUMBER` as a repo variable** on every
   regulated repo that should opt in to PR-driven promotion. Drift
   workflow will warn about repos that have the caller workflow but no
   variable.
3. **Run actionlint** against the four new YAMLs before flipping
   anything to `active`.
4. **Watch the cron for one evaluate week** before editing the
   "Active-mode rollout log" table in `README.md` to flip the first
   check (`transition`) to `active` in `.github/project-enforcement.yml`.
