# .github

Org-level engineering configuration for the `CCTC-team` GitHub
organisation — community health templates, branch-protection policy,
compliance scaffolding, and label sync. Files here become defaults
for every repo in the org that does not define its own version.

For an overview of CCTC and the software we publish, see the
[organisation profile](https://github.com/CCTC-team).

## What's in here

| Path | Purpose |
| --- | --- |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Standard bug-report form |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Standard feature-request form |
| `.github/ISSUE_TEMPLATE/regulated_feature.yml` | Regulated feature (V&V) form — populates Risk ID + Requirement ID for the GxP traceability gate |
| `.github/ISSUE_TEMPLATE/config.yml` | Disables blank issues; adds security + support contact links |
| `.github/pull_request_template.md` | Default PR template with clinical/compliance checklist |
| `.github/CODEOWNERS` | Reviewers for this repo (does **not** propagate to other repos) |
| `SECURITY.md` | Org-wide vulnerability reporting policy |
| `labels.json` | Canonical label set applied to every repo |
| `scripts/sync-labels.sh` | Applies `labels.json` to one or all org repos via `gh` |
| `.github/workflows/sync-labels.yml` | Nightly + on-change run of the label sync |
| `compliance.schema.json` | JSON Schema for `.compliance.yml` in regulated repos |
| `release-targets.schema.json` | JSON Schema for `.github/release-targets.yml` — the per-repo build-target manifest the release workflow binds to (see [Release process](#release-process)) |
| `templates/compliance/` | `.compliance.yml.example`, `CONTRIBUTING-regulated.md`, README-banner, release-notes config (`release.yml`), build-target manifest (`release-targets.yml.example`), caller workflows (`caller-workflow.yml`, `gxp-traceability-caller.yml`, `project-card-promote-caller.yml`, `release-caller.yml`) — pushed by drift |
| `scripts/release/` | Python package: the build-target contract checker (`contract.py`) and the milestone-scoped release-notes / SBOM-scan tooling the release workflow uses |
| `docs/release-process.md` | The milestone/Release/pull-agent model and the regulated Release artifact set (inspector-facing) |
| `.github/workflows/compliance-check.yml` | Reusable workflow regulated repos opt into |
| `.github/workflows/compliance-drift.yml` | Nightly drift correction across regulated repos |
| `.github/workflows/gxp-traceability.yml` | Reusable PR gate enforcing Risk ID + Requirement ID traceability on changes to validated paths |
| `.github/workflows/release.yml` | Reusable release workflow: builds + signs the container image, pushes to GHCR by digest, attests provenance + SBOM, and cuts a Release with the validation evidence (see [Release process](#release-process)) |
| `.github/workflows/project-enforcement.yml` | 5-minute poller that diffs the regulated lifecycle board(s) and dispatches each card change to the checks under `scripts/project_enforcement/` |
| `.github/workflows/project-card-promote.yml` | Reusable PR-driven forward-only promoter (Code review / V&V tests pass). Callers live in regulated repos. |
| `.github/workflows/project-audit.yml` | Nightly sweep that maintains a rolling `Project enforcement drift` issue per board |
| `.github/project-enforcement.yml` | On/evaluate/active switchboard read by the poller + audit |
| `scripts/project_enforcement/` | Python package: snapshot/diff, state machine, per-status preconditions, drift checks, audit, PR promoter decision logic |
| `scripts/compliance-drift.sh` | Drift-detection logic invoked by the workflow |
| `rulesets/` | JSON definitions of the org-level category rulesets (applied via `gh api`) |
| `docs/alcoa-sdlc-rationale.md` | Why signed commits are required across all regulated rulesets (inspector-facing) |
| `docs/risk-proportionality-rationale.md` | Why the uniform `gcp-critical` ruleset + gate is a proportionate floor, not one-size-fits-all (inspector-facing) |
| `docs/commit-signing-setup.md` | Developer-facing setup guide (SSH/GPG, runners, verification) |
| `docs/compliance-drift-app-setup.md` | Runbook for provisioning the `CCTC Compliance Drift` GitHub App |
| `docs/project-enforcement-app-setup.md` | Runbook for provisioning the token used by `project-enforcement.yml` (two options) |

## How inheritance works (and doesn't)

Inherited by every repo with no local equivalent:

- Issue templates and the issue chooser config
- Pull request template
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `FUNDING.yml`

**Not** inherited — handled separately:

- **Labels** — see `labels.json` and the sync workflow.
- **CODEOWNERS** — must live in each repo that needs them.
- **Branch protection / required reviews / required checks** — configured
  as org-level Rulesets in GitHub Settings, not via this repo.
- **Repo scaffolding** (CI workflows, `.editorconfig`, project files) — use
  one or more "template repositories" (Settings → Template repository).

## Running the label sync manually

```bash
# Sync every non-archived repo in the org
./scripts/sync-labels.sh

# Sync a specific repo
./scripts/sync-labels.sh my-repo

# Override the org
ORG=other-org ./scripts/sync-labels.sh
```

Requires `gh` (authenticated) and `jq`. The script is idempotent.

## Compliance metadata (UK CTU regulated repos)

Repos in scope for any UK clinical-trial regulation carry a machine-readable
`.compliance.yml` at their root. The canonical schema lives here at
`compliance.schema.json`; the drift workflow pushes a copy into each
regulated repo so the validator can run without cross-repo auth.

### Source of truth: the `regulatory_tier` org custom property

Whether a repo is regulated — and what inspection bucket it sits in — is
determined by a **GitHub org-level custom property** named `regulatory_tier`,
not by a topic or a file. Topics drift, files can be deleted; a custom
property is schema-defined and only org admins can change it. Drift
detection keys off this property.

The value answers "what kind of system is this?", which in turn drives the
validation rigour expected. The specific regulatory clusters live in
`.compliance.yml` as `regulatory_pillars`. Property = bucket; YAML = detail.

`regulatory_pillars` uses six clusters rather than listing every individual
regulation — the granular citation register belongs in the QMS / SOPs, not
in source control. The pillars are:

| Pillar | Bundles | Typical UK academic posture |
| --- | --- | --- |
| `uk-statutory` | UK CT Regs 2004 (as amended by SI 2025/538), UK-GDPR, DPA 2018, NHS-DSPT, HRA Transparency, CAG-S251 (conditional) | in-scope |
| `mhra-csv-di` | ICH E6 (R3), MHRA GxP-DI, MHRA CSV-for-GCP | in-scope |
| `infra-security` | Cyber Essentials Plus, ISO 27001 | in-scope |
| `international-ehr-standards` | 21 CFR Part 11, EU Annex 11 | out-of-scope unless FDA/EMA submission |
| `eu-ct-regulation` | EU CTR 536/2014 | out-of-scope unless EU sites |
| `samd-aimd` | MHRA Software/AI as Medical Device | out-of-scope unless system makes clinical decisions |

Pillars marked `out-of-scope` should still appear in `.compliance.yml`
with a `notes` field explaining why — an inspector wants to see that you
considered each one, not that you omitted it.

| Value | Meaning | Examples |
| --- | --- | --- |
| `gcp-critical` | Captures, transforms, or validates trial data. Full CSV + ALCOA+. | EDC, IRT/randomisation, data-integrity scripts, REDCap External Modules touching data |
| `gcp-supporting` | Trial metadata, no patient data. System validation + document retention. | eTMF, CTMS, QMS, project trackers |
| `data-protection` | Personal data, no trial nexus. UK GDPR / DPA only. | HR-adjacent tooling, contact databases |
| `none` | Pure infrastructure. No `.compliance.yml` expected. | Dev tooling, infra repos |

One-time setup (run as an org admin). Pass JSON via stdin — `gh api -f`
sends every value as a string and mangles nested objects, so the API
rejects it:

```bash
gh api -X PATCH /orgs/CCTC-team/properties/schema --input - <<'JSON'
{
  "properties": [
    {
      "property_name": "regulatory_tier",
      "value_type": "single_select",
      "required": false,
      "default_value": "none",
      "description": "Inspection bucket and validation rigour for this repo. Specific regulations live in .compliance.yml.",
      "allowed_values": ["none", "gcp-critical", "gcp-supporting", "data-protection"]
    }
  ]
}
JSON
```

Verify:

```bash
gh api /orgs/CCTC-team/properties/schema \
  --jq '.[] | select(.property_name == "regulatory_tier")'
```

Then set the property on each regulated repo (same JSON-via-stdin pattern):

```bash
gh api -X PATCH /orgs/CCTC-team/properties/values --input - <<'JSON'
{
  "repository_names": ["some-regulated-repo"],
  "properties": [
    { "property_name": "regulatory_tier", "value": "gcp-critical" }
  ]
}
JSON
```

For a batch, list multiple repos in `repository_names` — every named repo
gets the same value:

```bash
gh api -X PATCH /orgs/CCTC-team/properties/values --input - <<'JSON'
{
  "repository_names": ["repo-a", "repo-b", "repo-c"],
  "properties": [
    { "property_name": "regulatory_tier", "value": "gcp-critical" }
  ]
}
JSON
```

### Per-repo opt-in (or just set the property and let drift do it)

Regulated repos need seven things. The drift workflow will create any that
are missing the next time it runs, but you can also commit them by hand:

1. `.github/compliance.schema.json` — copy of the canonical schema.
2. `.compliance.yml` — repo-specific metadata, validated against the schema.
3. `README.md` carrying `<!-- compliance:banner -->` (links to rules #4).
4. `CONTRIBUTING-regulated.md` — engineer-facing behavioural rules
   (what changes about your day-to-day work in a regulated repo).
5. `.github/workflows/compliance.yml` — three-line caller that points at
   `compliance-check.yml` in this repo.
6. `.github/workflows/gxp-traceability.yml` — caller that points at
   `gxp-traceability.yml` in this repo. Stubbed in `evaluate` mode; flip
   to `active` locally once the repo's `validated_paths` is settled.
7. `.github/workflows/project-card-promote.yml` — caller that points at
   `project-card-promote.yml` in this repo. Forward-only PR-driven
   moves through the *automatic* lifecycle states (`Code review`,
   `V&V tests pass`). Set the `LIFECYCLE_PROJECT_NUMBER` repo
   variable to the number of the lifecycle board this repo's cards
   live on (e.g. `31` for the test board). Without it, the promoter
   no-ops via its guard step — drift never sets the variable for you
   because choosing the board is a deliberate per-repo decision.

Starter copies of items #2–7 live in `templates/compliance/`; the
schema (#1) is `compliance.schema.json` itself. Drift stubs the GxP caller if absent but
never overwrites it — once stubbed, the repo owns its
`enforcement` value.

### How the validator runs

`compliance-check.yml` is a **reusable workflow**. Regulated repos opt in
with `uses: CCTC-team/.github/.github/workflows/compliance-check.yml@main`
and the validator runs on every PR. It checks:

- All required files are present (schema, `.compliance.yml`, README,
  `CONTRIBUTING-regulated.md`)
- `.compliance.yml` parses and validates against the schema
- README carries the banner marker
- `last_reviewed` is within `review_cadence_months` (and not in the future)
- `schema_version` is in the validator's supported set (controlled via
  the `supported_schema_versions` input — currently `"1"`)

### Declaring the validated path scope

`.compliance.yml` carries two optional fields for declaring path scope:

```yaml
validated_paths:
  - src/**
  - tests/**
  - user_requirement_specification/**
exempt_paths:
  - "**/README.md"
```

These declare, per repo, which paths constitute the validated state.
The **traceability gate** workflow (next section) reads these to decide
whether a given PR is in scope for Risk ID + Requirement ID enforcement.

Rationale and rules:

- **Per-repo declaration, not a central list.** Repo layouts vary
  (`src/` vs `lib/`, `tests/` vs `Feature Tests/`, etc.) — a central
  glob can't predict them all. The `.compliance.yml` is already QMS-
  controlled by the drift workflow, so it's the right home.
- **Strict-mode default.** If `validated_paths` is omitted, the gate
  treats every changed file as in-scope. The absence of a declaration
  never silently relaxes the rule.
- **`exempt_paths` is subtractive.** It only excludes files that
  *also* match `validated_paths`. Use sparingly — README and comment-
  only files in a validated directory are the common case. Document
  any addition in the repo's QMS so an inspector can see the carve-
  out is intentional.
- **Defensibility.** The rule an inspector sees is "this repo's
  `.compliance.yml` declares paths X / Y / Z as validated, and CI
  blocks untraceable changes to those paths." That's stronger than
  "Claude (or anyone) picked some sensible-looking paths."
- **Code-review the declaration itself.** A developer narrowing
  `validated_paths` to skirt the gate is the obvious attack. PRs that
  touch `.compliance.yml` should route through CODEOWNERS to a QA
  reviewer; ensure CODEOWNERS in regulated repos covers
  `/.compliance.yml`.

### CtQ-factor and QMS-document anchors

Two fields anchor the repo's controls to the trial's risk-based quality
management, **required for `gcp-critical`**:

```yaml
# Critical-to-Quality factors (CCTU/FRM129) this system safeguards.
ctq_factors:
  - frm129_ref: FRM129-XYZ-001#3
    tier: critical          # critical | important
    notes: Randomisation allocation integrity.

# QMS documents governing this system's validation and risk management.
governing_documents:
  - ref: CCTU/SOP040
    title: Risk Assessment Process for CTIMPs
    role: risk-assessment   # risk-assessment | ctq-identification | csv | monitoring | change-control | other
  - ref: CCTU/FRM129
    role: ctq-identification
```

Rationale:

- **`ctq_factors`** anchors the system to its FRM129 entry and tier so an
  inspector can trace *CtQ factor → risk → requirement → V&V* as one
  narrative. Under ICH E6(R3) Principle 6, fit-for-purpose validation of
  computerised systems handling clinical data/endpoints is itself a CtQ
  factor — so the software sits inside the RBQM narrative, not beside it.
  The `tier` (`critical` / `important`) mirrors the board's three-tier
  `Critical-to-Quality` field.
- **`governing_documents`** is the pointer layer from source control into
  the QMS — the SOPs, guidance and forms that govern validation and risk
  management, each tagged with the `role` it satisfies. The granular
  regulation register stays in the QMS; this is a pointer, not a copy.
- See [`docs/risk-proportionality-rationale.md`](docs/risk-proportionality-rationale.md)
  for how these fields express ICH E6(R3) Principle 7 proportionality.

### Traceability gate

`gxp-traceability.yml` is a **reusable workflow** regulated repos opt
into. Caller pattern lives in `templates/compliance/gxp-traceability-caller.yml`.

The gate runs on every PR and, for changes that touch in-scope paths
(per `validated_paths` minus `exempt_paths`), requires:

1. The PR closes at least one issue (`Closes #N` / `Fixes #N` in the
   PR body or sidebar).
2. At least one closed issue carries the `regulated` label.
3. Each regulated-labelled closed issue has non-empty `Risk ID:` and
   `Requirement ID:` lines in its body — populated automatically by
   the `regulated_feature.yml` issue template.

It does **not** run if:

- The repo has no `.compliance.yml` (not regulated).
- `regulatory_tier == none`.
- The PR's changed-file set, after applying `validated_paths` /
  `exempt_paths`, is empty.

#### Enforcement modes

The `enforcement` input (default `evaluate`) controls failure
behaviour, mirroring the rulesets' evaluate/active pattern:

- `evaluate` — violations emit `::warning::` annotations and a
  PR-conversation step summary. The workflow exits 0 and does **not**
  block merges. Use this for rollout while developers and the
  declared `validated_paths` settle.
- `active` — violations emit `::error::` and the workflow exits 1.
  Combine with a branch-protection required-status-check rule (per
  repo, not org-level — workflow names vary) once you're ready to
  block merges on untraceable changes.

#### Rollout sequence

1. Ensure each regulated repo has `validated_paths` declared in its
   `.compliance.yml` (or accept strict-mode default for the migration
   window).
2. Add the caller workflow (`templates/compliance/gxp-traceability-caller.yml`)
   to each regulated repo. Drift can do this once the gate is proven.
3. Watch evaluate-mode runs for a cycle (1–2 weeks of real PRs).
   Adjust `validated_paths` / `exempt_paths` as you see false
   positives.
4. Flip `enforcement: active` per repo when stable, and add the
   `gate / gate` status check to that repo's branch-protection
   required checks.

### Schema evolution

The schema is currently at its initial **version 1**, which already
carries every field (including `ctq_factors` / `governing_documents`).
`schema_version` is an integer (not pinned to a constant) so the schema
can still evolve later without instantly breaking every existing
`.compliance.yml`. The migration ritual for a future breaking change:

1. Bump `schema_version` in `compliance.schema.json` and add the new
   version to the validator's `supported_schema_versions` default
   (keeping the old one).
2. Drift workflow pushes the new schema into every regulated repo.
3. Open PRs against regulated repos to migrate each `.compliance.yml` at
   the team's pace.
4. Once every repo is migrated, drop the old version from
   `supported_schema_versions` to retire it.

### How drift correction runs

`compliance-drift.yml` runs nightly. It lists every repo where
`regulatory_tier != none`, clones each, restores any missing or
out-of-date scaffolding, and opens a PR. **The PR history is the audit
evidence** — do not squash these into oblivion.

```bash
# Manual run, dry-run mode
gh workflow run compliance-drift.yml -f dry_run=true

# Run against specific repos only
gh workflow run compliance-drift.yml -f repos="repo-a repo-b"
```

### Required App permissions

The drift workflow expects org secrets `ORG_COMPLIANCE_DRIFT_APP_CLIENT_ID` /
`ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY` for a GitHub App with:

- Contents: **read & write** (commit drift fixes)
- Pull requests: **read & write** (open the PR)
- Metadata: read
- Custom properties: read

The existing `CCTC Label Sync` App has only `Issues: write` and is **not
sufficient**. Either provision a separate App or expand the existing one
— a separate App is cleaner because the scopes differ materially and you
may want to revoke one without the other.

Step-by-step provisioning instructions (web-UI walk-through,
permissions table, smoke test, rotation) live in
[`docs/compliance-drift-app-setup.md`](docs/compliance-drift-app-setup.md).

## Branch protection strategy

Branch protection is enforced via **org-level Rulesets** rather than
per-repo branch protection. Strictness is driven by the same
`regulatory_tier` custom property that drives compliance drift, so the
regulatory bucket decides the rules — not a parallel classification.

### Baseline (in effect, all repos)

| Rule | Branches | Why |
| --- | --- | --- |
| Block force-push (`non_fast_forward`) | `main`, `develop` | Prevents history rewrites on shared branches |
| Block deletion | `main`, `develop` | Prevents accidental loss of the default/integration branch |

No bypass actors. Universal — accidents nobody should be able to commit
to muscle-memory, regulated or not.

### Category-specific

Scoped via `conditions.repository_property` on `regulatory_tier`. Two
rulesets rather than three — `gcp-supporting` and `data-protection`
share enough that splitting them adds maintenance without adding
controls, while `gcp-critical` carries hard regulatory hooks
(segregation of duties, zero bypass) the others don't.

The uniform `gcp-critical` ruleset is a deliberate **proportionate
floor**, not a one-size-fits-all blanket; finer (ICH E6(R3) Principle 7)
proportionality is delegated to FRM129 tiering and SOP040 risk
evaluation ([rationale](docs/risk-proportionality-rationale.md)).

#### Ruleset A — `cctc-gcp-critical`

Defined in [`rulesets/cctc-gcp-critical.json`](rulesets/cctc-gcp-critical.json).
Scoped to repos with `regulatory_tier == gcp-critical`. Targets
`main`, `develop`, and `release/*` (the JSON also re-asserts
`non_fast_forward` and `deletion` so `release/*` branches inherit the
same safety floor as `main`/`develop`).

| Rule | Setting | Driver |
| --- | --- | --- |
| Require PR | 1+ approving review | ICH E6(R3) Principle 10 (Roles and Responsibilities) + §3.10 (Quality Management); MHRA GxP-DI segregation of duties |
| Approver ≠ last pusher | `require_last_push_approval: true` | Segregation of duties |
| Dismiss stale reviews on push | enabled | Approval reflects the final code, not an earlier version |
| Code owner review | enabled (no-op if CODEOWNERS is empty) | Routes review to the responsible party as CODEOWNERS is populated |
| Signed commits | required | Part 11 §11.10(d)(e), ALCOA+ attributability |
| Linear history | required | Clean audit trail; merge commits obscure who approved what |
| Required status checks | per-repo, not org-wide | Workflow names vary; added repo by repo as CI lands |

**Zero bypass actors.** Baseline rules (force-push, deletion blocked)
carry over.

#### Ruleset B — `cctc-regulated-non-critical`

Defined in [`rulesets/cctc-regulated-non-critical.json`](rulesets/cctc-regulated-non-critical.json).
Scoped to repos with `regulatory_tier in [gcp-supporting, data-protection]`.
Targets `main`, `develop` (the baseline ruleset already covers
`non_fast_forward` and `deletion` on the same branches, so this
ruleset doesn't re-assert them).

| Rule | Setting | Driver |
| --- | --- | --- |
| Require PR | 1+ approving review | System validation (`gcp-supporting`); UK-GDPR Art 5(1)(f) integrity (`data-protection`) |
| Dismiss stale reviews on push | enabled | Cheap uplift over a bare PR-required rule, no regulatory downside |
| Signed commits | required | UK-GDPR Art 5(1)(f) integrity; ALCOA+ attributability applies across all regulated categories, not just `gcp-critical` ([rationale](docs/alcoa-sdlc-rationale.md)) |

**Bypass:** `actor_type: OrganizationAdmin` with `bypass_mode: always`.
GitHub's API rejects `actor_type: "User"` for org-level rulesets
(despite the REST docs listing it as supported), so a specific named
user cannot be the bypass actor at this scope. A one-person Team
gives a cleaner named break-glass when that's preferable to a
role-based bypass. Every bypass event is captured in the org audit
log; an incident record should accompany each one. Baseline rules
carry over.

#### Ruleset C — `cctc-tag-immutability`

Defined in [`rulesets/cctc-tag-immutability.json`](rulesets/cctc-tag-immutability.json).
A separate `target: tag` ruleset (not part of the branch rulesets above),
scoped to all regulated repos (`gcp-critical`, `gcp-supporting`,
`data-protection`) and matching `refs/tags/v*`.

| Rule | Setting | Driver |
| --- | --- | --- |
| Block tag deletion | `deletion` | A published version tag is a release record — it must not vanish |
| Block tag force-update | `non_fast_forward` | A `v*` tag can never be moved or re-pointed, matching the immutability of the released image digest |

**Zero bypass actors** — a released version tag is immutable, full stop.
This is the inspection-resilience payoff of the release pipeline: the tag,
the GitHub Release, and the GHCR image digest are all fixed and mutually
consistent.

#### `none`

Baseline only. Direct push to `main` still allowed. No regulatory
driver.

### Preconditions before the category rulesets go live

**Shared (block both rulesets):**

- **Universal commit signing for everyone pushing to regulated repos.**
  GitHub Apps committing via the Contents API are signed by the
  platform; Git CLI pushes from runners and developer machines need
  GPG/SSH setup. Developer-facing instructions live in
  [`docs/commit-signing-setup.md`](docs/commit-signing-setup.md).

**Specific to Ruleset A (`cctc-gcp-critical`):**

- **CODEOWNERS populated in each `gcp-critical` repo.** ICH E6(R3)
  Principle 10 (Roles and Responsibilities) plus §3.10 (Quality
  Management), reinforced by MHRA GxP Data Integrity Guidance on
  segregation of duties, requires PRs to route to a qualified second
  reviewer. (§3.16 *Data and Records* covers record keeping, audit
  trails, and retention — it is the right cite for the signing /
  ALCOA+ control further up the table, not for the four-eyes rule.)
  Any developer on the regulated estate who is not the PR author
  satisfies the regulation; the gap is operational, not a staffing
  shortage. With zero bypass actors on this ruleset, a PR cannot
  merge until a reviewer who is not its author approves it (the
  require-PR + `require_last_push_approval` rules). Code-owner review
  is a no-op while CODEOWNERS is empty, so each `gcp-critical` repo
  needs CODEOWNERS populated to a team or reviewer set that excludes
  the typical PR author — both to route review to the responsible
  party and to guarantee an eligible second reviewer exists. Per-
  repo task, not org-wide.

**Out of scope for either ruleset:**

- **Required status checks** are per-repo, not org-wide. Workflow
  names vary, so these are added repo by repo as CI lands.

### Applying the category rulesets

Each ruleset is applied with one `gh api` call by an org admin. The
JSON in `rulesets/` is what gets posted; set `"enforcement"` to
`"active"` or `"evaluate"` before applying, depending on whether you
want violations blocked or only logged.

For Ruleset B's `bypass_actors`, GitHub's API rejects
`actor_type: "User"` at the org level (it is only valid in
repository-scoped rulesets). The two viable options at org scope are:

- `OrganizationAdmin` — bypass granted to anyone with the org-admin
  role. `actor_id` is ignored, pass `null`. Simplest.
- `Team` — bypass granted to members of a named team. Cleaner when
  more than one person holds the admin role and you want a specific
  named break-glass:

  ```bash
  gh api /orgs/CCTC-team/teams/<team-slug> --jq .id
  ```

  Then set `{ "actor_id": <team-id>, "actor_type": "Team", "bypass_mode": "always" }`.

Apply with:

```bash
gh api -X POST /orgs/CCTC-team/rulesets \
  --input rulesets/cctc-regulated-non-critical.json

gh api -X POST /orgs/CCTC-team/rulesets \
  --input rulesets/cctc-gcp-critical.json

gh api -X POST /orgs/CCTC-team/rulesets \
  --input rulesets/cctc-tag-immutability.json
```

> **Tag immutability depends on `active` enforcement.** All three rulesets
> ship with `"enforcement": "evaluate"` (log-only). The `v*` tag-immutability
> and `release/*` guarantees do **not** actually prevent a tag being moved or
> deleted until `cctc-tag-immutability` (and the branch rulesets) are flipped
> to `"enforcement": "active"`. Flip them once you have watched a clean
> evaluate cycle — until then the immutability is documented intent, not an
> enforced control.

**Evaluate mode.** GitHub Rulesets support a log-only mode that
records violations without blocking pushes. Set `"enforcement":
"evaluate"` in the JSON to start in log-only, watch the org's
ruleset insights (Organization → Settings → Rules → Insights) until
violations stop, then flip to `"enforcement": "active"` and re-apply
with `PUT /orgs/CCTC-team/rulesets/{id}`.

List existing rulesets and find one by name:

```bash
gh api /orgs/CCTC-team/rulesets \
  --jq '.[] | select(.name == "cctc-gcp-critical")'
```

Updating a ruleset later uses `PUT /orgs/CCTC-team/rulesets/{id}`
with the same JSON payload; the `id` comes from the list above.

## Project board enforcement

Branch protection guards the **issue → PR → merge** path; the regulated
lifecycle **board** is guarded separately by
[`.github/workflows/project-enforcement.yml`](.github/workflows/project-enforcement.yml).
The workflow polls every project listed in
[`.github/project-enforcement.yml`](.github/project-enforcement.yml)
every five minutes, diffs the current state against a snapshot stored
on the `_project-state` branch, and dispatches each card change to a
suite of checks.

### What it enforces

- **State machine.** Forward moves must advance one column at a time.
  Backward moves are always legal; side exits (`Redundant`,
  `Archived`) are legal from anywhere and only restore to `Triage`.
- **Per-column preconditions.** Entering `Risk linked` requires a
  `Risk ID` mirrored to the issue body; entering `Requirement defined`
  adds Requirement ID + a chosen Critical-to-Quality tier
  (`Critical` / `Important` / `No`); `In development` requires an
  assignee, iteration, a Test Type, and — for a `Critical` factor — a
  PQ-flavoured Test Type (`Important` needs a Test Type but not PQ;
  `No` is unconstrained); `Code review` requires an open linked PR; `V&V tests pass`
  requires green gxp-traceability + compliance checks on the PR and a
  resolvable `.feature` URL on the default branch; `User acceptance` /
  `QA approved` require the issue's acceptance / QA checkboxes ticked,
  approver usernames that resolve, segregation of duties across
  author / Acceptance / QA, and (for QA) a `Deviation Ref` when any historical
  gxp-traceability run failed; `Released` requires the linked PR
  merged to the default branch and a **published** Release — carrying the
  validation report — whose tag resolves to the merge SHA (a bare tag or a
  draft release does not satisfy it; an optional config flag additionally
  requires a verifiable provenance attestation).
- **Field-drift.** Changes to `Risk ID` / `Requirement ID` that no
  longer match the issue body, signoff dates in the future or before
  the issue was opened, Acceptance-after-QA, approver changes on cards at or
  past their review column **or on any card whose approver was already set** (so
  an approver edited after the card is moved backward is still logged), and a
  Test-Type / Critical-to-Quality
  mismatch (a `Critical` factor — including the legacy `Yes` — without a
  PQ-bearing Test Type, or an `Important` factor with `Test Type=N/A`)
  all fire comments.
- **PR-driven promotion (forward-only).** A reusable workflow
  [`.github/workflows/project-card-promote.yml`](.github/workflows/project-card-promote.yml)
  moves cards from earlier states forward through `Code review` (on PR
  opened) and `V&V tests pass` (on green check_suite). Human-attested
  states (`User acceptance`, `QA approved`, `Released`) are never reached
  by automation.
- **Nightly audit.** [`.github/workflows/project-audit.yml`](.github/workflows/project-audit.yml)
  runs at 02:00 UTC, maintains one rolling
  `Project enforcement drift — <board>` issue per project in
  `CCTC-team/.github`, and discovers any org project whose Status
  options look like a lifecycle board but isn't listed in
  `project-enforcement.yml`.

### Evaluate → active rollout

Every check carries its own mode in `project-enforcement.yml`:

- `off` — handler doesn't run the check.
- `evaluate` — handler runs the check and emits comment + label; never
  reverts.
- `active` — handler runs the check, comments, labels, **and**
  reverts the offending field write. Bypass via
  `process-override:approved` on the linked issue, single-use,
  cleared after honouring.

Checks graduate independently — `transition` flips to `active` after
one clean evaluate week, then the lower-risk preconditions
(`Risk linked`, `Requirement defined`, `In development`,
`Code review`), then the four human-attestation gates last.

### Active-mode rollout log

Each check's flip from `evaluate` to `active` is a deliberate
operational decision after one clean evaluate week. Record the date
inline so the audit trail is here, not in chat:

| Check | Flipped active | Notes |
| --- | --- | --- |
| `transition` | _pending_ | Awaiting first clean evaluate week |
| `preconditions: Risk linked` | _pending_ | |
| `preconditions: Requirement defined` | _pending_ | |
| `preconditions: In development` | _pending_ | |
| `preconditions: Code review` | _pending_ | |
| `preconditions: V&V tests pass` | _pending_ | |
| `preconditions: User acceptance` | _pending_ | |
| `preconditions: QA approved` | _pending_ | |
| `preconditions: Released` | _pending_ | Hardened gate: needs a published Release carrying the validation report (see [Release pipeline rollout log](#release-pipeline-rollout-log)). Stays in evaluate until the release workflow has cut one green published Release **and** the agent has done one verified staging pull-deploy |
| `drift_id_mirror` | _pending_ | |
| `drift_date_sanity` | _pending_ | |
| `drift_approver_identity` | _pending_ | |
| `drift_type_quality` | _pending_ | |

To flip a row, edit `.github/project-enforcement.yml` and replace this
table cell with the date (`2026-MM-DD`) and the audit issue number
that proves the evaluate week was clean.

### Board `Critical-to-Quality` field migration

The `Critical-to-Quality` single-select on each lifecycle board must
gain the options **Critical / Important / No** to match the three-tier
enforcement. This is org-admin board configuration applied via the board
UI / API, not via this repo, so it is recorded here rather than enforced
by code:

- Add `Critical`, `Important`, `No` as options on the board's
  `Critical-to-Quality` field.
- Retain the legacy **Yes** option (hidden if the UI allows) until every
  existing card is migrated off it. The enforcement code aliases `Yes`
  → `Critical`, so old and new cards both validate during the
  transition; remove `Yes` once no card uses it.

### App + secrets

The poller, promoter, and audit each need a token with `read:project`
+ `write:project` + `read:org`. Provisioning instructions and two
options (expand the Compliance Drift App or stand up a separate
`CCTC Project Enforcement` App) live in
[`docs/project-enforcement-app-setup.md`](docs/project-enforcement-app-setup.md).

## Release process

Where the project board governs a *feature's* V&V lifecycle, the release
pipeline governs how a *validated build* reaches production — and the evidence
it leaves behind. Three orthogonal layers:

- **Project board status** — where a feature is in its lifecycle (`Triage …
  Released`).
- **Milestone (`vX.Y.Z`)** — which requirements a release covers; one milestone
  = one release.
- **Release** — what was published, on a signed `vX.Y.Z` tag, with its evidence.

The deploy model is **pull, never push**: production accepts no inbound
connection. CI builds and signs a container **image**, pushes it to GHCR by
immutable digest, and cuts a Release gated by a `production` Environment
approval. An agent **on the server** verifies the image's keyless attestation
against the release workflow's identity, pulls it **by digest**, and runs it.
The build↔workflow binding is a per-repo manifest (`.github/release-targets.yml`,
schema [`release-targets.schema.json`](release-targets.schema.json)) against the
tool-agnostic build-target contract in claude-org
`rules/guides/build-and-release.md`.

The full model — the artifact set on every regulated Release and the ICH E6(R3)
/ ALCOA+ clause each answers — is in
[`docs/release-process.md`](docs/release-process.md); the production
authorisation gate and the electronic-signature residual gap are in
[`docs/release-authorisation.md`](docs/release-authorisation.md).

### Release pipeline rollout log

The release controls roll out evaluate → active like the board checks, but flip
by a different mechanism: the caller workflow's `enforcement:` input
(`evaluate` cuts a **draft** Release and the agent ignores drafts; `active`
publishes a gated Release, enforces the vulnerability gate and the `production`
approval, and the agent deploys the verified digest), and — for the agent —
enabling the on-server timer. Record each flip here.

| Control | Active | Notes |
| --- | --- | --- |
| release workflow (publish) | _pending_ | Flip the caller `enforcement: evaluate → active` after one clean draft-Release cycle |
| release workflow (vuln gate) | _pending_ | Fails on critical/high in `active`; warns in `evaluate` |
| pull-agent (staging) | _pending_ | Enable after one verified pull-deploy on staging |
| pull-agent (production) | _pending_ | Enable after staging is proven |

The hardened `Released` board precondition (a card may reach `Released` only
behind a *published* Release carrying its validation evidence) is tracked in the
[board rollout log](#active-mode-rollout-log).

## Deliberately not done

- **Template repositories.** GitHub supports flagging a repo as a template so
  "Use this template" produces a pre-scaffolded new repo. We considered this
  but decided against it: CCTC isn't expecting to spin up large new
  applications at a rate that justifies the ongoing maintenance burden of
  keeping a template (SDK pins, CI workflow, package versions, security
  patches) current with the rest of the estate. New repos will continue to
  be scaffolded by hand, copying from the closest existing project. Revisit
  if the pace of new applications picks up.
