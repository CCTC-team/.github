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
| `.github/ISSUE_TEMPLATE/validation.yml` | GCP validation & verification form |
| `.github/ISSUE_TEMPLATE/config.yml` | Disables blank issues; adds security + support contact links |
| `.github/pull_request_template.md` | Default PR template with clinical/compliance checklist |
| `.github/CODEOWNERS` | Reviewers for this repo (does **not** propagate to other repos) |
| `SECURITY.md` | Org-wide vulnerability reporting policy |
| `labels.json` | Canonical label set applied to every repo |
| `scripts/sync-labels.sh` | Applies `labels.json` to one or all org repos via `gh` |
| `.github/workflows/sync-labels.yml` | Nightly + on-change run of the label sync |
| `compliance.schema.json` | JSON Schema for `.compliance.yml` in regulated repos |
| `templates/compliance/` | `.compliance.yml.example`, `CONTRIBUTING-regulated.md`, README-banner, caller workflows (`caller-workflow.yml`, `gxp-traceability-caller.yml`) — pushed by drift |
| `.github/workflows/compliance-check.yml` | Reusable workflow regulated repos opt into |
| `.github/workflows/compliance-drift.yml` | Nightly drift correction across regulated repos |
| `.github/workflows/gxp-traceability.yml` | Reusable PR gate enforcing Risk ID + Requirement ID traceability on changes to validated paths |
| `scripts/compliance-drift.sh` | Drift-detection logic invoked by the workflow |
| `rulesets/` | JSON definitions of the planned org-level category rulesets (applied via `gh api`) |
| `docs/alcoa-sdlc-rationale.md` | Why signed commits are required across all regulated rulesets (inspector-facing) |
| `docs/commit-signing-setup.md` | Developer-facing setup guide (SSH/GPG, runners, verification) |
| `docs/compliance-drift-app-setup.md` | Runbook for provisioning the `CCTC Compliance Drift` GitHub App |

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

### Source of truth: the `system_category` org custom property

Whether a repo is regulated — and what inspection bucket it sits in — is
determined by a **GitHub org-level custom property** named `system_category`,
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
| `critical-trial` | Captures, transforms, or validates trial data. Full CSV + ALCOA+. | EDC, IRT/randomisation, data-integrity scripts, REDCap External Modules touching data |
| `trial-governance` | Trial metadata, no patient data. System validation + document retention. | eTMF, CTMS, QMS, project trackers |
| `personal-data` | Personal data, no trial nexus. UK GDPR / DPA only. | HR-adjacent tooling, contact databases |
| `none` | Pure infrastructure. No `.compliance.yml` expected. | Dev tooling, infra repos |

One-time setup (run as an org admin). Pass JSON via stdin — `gh api -f`
sends every value as a string and mangles nested objects, so the API
rejects it:

```bash
gh api -X PATCH /orgs/CCTC-team/properties/schema --input - <<'JSON'
{
  "properties": [
    {
      "property_name": "system_category",
      "value_type": "single_select",
      "required": false,
      "default_value": "none",
      "description": "Inspection bucket and validation rigour for this repo. Specific regulations live in .compliance.yml.",
      "allowed_values": ["none", "critical-trial", "trial-governance", "personal-data"]
    }
  ]
}
JSON
```

Verify:

```bash
gh api /orgs/CCTC-team/properties/schema \
  --jq '.[] | select(.property_name == "system_category")'
```

Then set the property on each regulated repo (same JSON-via-stdin pattern):

```bash
gh api -X PATCH /orgs/CCTC-team/properties/values --input - <<'JSON'
{
  "repository_names": ["some-regulated-repo"],
  "properties": [
    { "property_name": "system_category", "value": "critical-trial" }
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
    { "property_name": "system_category", "value": "critical-trial" }
  ]
}
JSON
```

### Per-repo opt-in (or just set the property and let drift do it)

Regulated repos need six things. The drift workflow will create any that
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

Starter copies of all six live in `templates/compliance/` and at
`compliance.schema.json`. Drift stubs the GxP caller if absent but
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

Schema v2 adds two optional fields to `.compliance.yml`:

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
- **Strict-mode default.** If `validated_paths` is omitted (e.g. an
  older schema_version=1 file not yet migrated), the gate treats every
  changed file as in-scope. The absence of a declaration never
  silently relaxes the rule.
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
   the `feature.yml` / `validation.yml` issue templates.

It does **not** run if:

- The repo has no `.compliance.yml` (not regulated).
- `system_category == none`.
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

`schema_version` is an integer (not pinned to a constant) so the schema
can evolve without instantly breaking every existing `.compliance.yml`.
The migration ritual for a breaking change:

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
`system_category != none`, clones each, restores any missing or
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
`system_category` custom property that drives compliance drift, so the
regulatory bucket decides the rules — not a parallel classification.

### Baseline (in effect, all repos)

| Rule | Branches | Why |
| --- | --- | --- |
| Block force-push (`non_fast_forward`) | `main`, `develop` | Prevents history rewrites on shared branches |
| Block deletion | `main`, `develop` | Prevents accidental loss of the default/integration branch |

No bypass actors. Universal — accidents nobody should be able to commit
to muscle-memory, regulated or not.

### Category-specific

Scoped via `conditions.repository_property` on `system_category`. Two
rulesets rather than three — `trial-governance` and `personal-data`
share enough that splitting them adds maintenance without adding
controls, while `critical-trial` carries hard regulatory hooks
(segregation of duties, zero bypass) the others don't.

#### Ruleset A — `cctc-critical-trial`

Defined in [`rulesets/cctc-critical-trial.json`](rulesets/cctc-critical-trial.json).
Scoped to repos with `system_category == critical-trial`. Targets
`main`, `develop`, and `release/*` (the JSON also re-asserts
`non_fast_forward` and `deletion` so `release/*` branches inherit the
same safety floor as `main`/`develop`).

| Rule | Setting | Driver |
| --- | --- | --- |
| Require PR | 1+ approving review | ICH E6(R3) §3.16 |
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
Scoped to repos with `system_category in [trial-governance, personal-data]`.
Targets `main`, `develop` (the baseline ruleset already covers
`non_fast_forward` and `deletion` on the same branches, so this
ruleset doesn't re-assert them).

| Rule | Setting | Driver |
| --- | --- | --- |
| Require PR | 1+ approving review | System validation (`trial-governance`); UK-GDPR Art 5(1)(f) integrity (`personal-data`) |
| Dismiss stale reviews on push | enabled | Cheap uplift over a bare PR-required rule, no regulatory downside |
| Signed commits | required | UK-GDPR Art 5(1)(f) integrity; ALCOA+ attributability applies across all regulated categories, not just `critical-trial` ([rationale](docs/alcoa-sdlc-rationale.md)) |

**Bypass:** `actor_type: OrganizationAdmin` with `bypass_mode: always`.
GitHub's API rejects `actor_type: "User"` for org-level rulesets
(despite the REST docs listing it as supported), so a specific named
user cannot be the bypass actor at this scope. A one-person Team
gives a cleaner named break-glass when that's preferable to a
role-based bypass. Every bypass event is captured in the org audit
log; an incident record should accompany each one. Baseline rules
carry over.

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

**Specific to Ruleset A (`cctc-critical-trial`):**

- **CODEOWNERS populated in each `critical-trial` repo.** ICH E6(R3)
  §3.16 four-eyes review requires PRs to route to a qualified second
  reviewer. Any developer on the regulated estate who is not the PR
  author satisfies the regulation; the gap is operational, not a
  staffing shortage. With zero bypass actors on this ruleset and
  code-owner review enabled, an empty CODEOWNERS file means no PR can
  merge — so each `critical-trial` repo needs CODEOWNERS populated to
  a team or reviewer set that excludes the typical PR author. Per-
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
  --input rulesets/cctc-critical-trial.json
```

**Evaluate mode.** GitHub Rulesets support a log-only mode that
records violations without blocking pushes. Set `"enforcement":
"evaluate"` in the JSON to start in log-only, watch the org's
ruleset insights (Organization → Settings → Rules → Insights) until
violations stop, then flip to `"enforcement": "active"` and re-apply
with `PUT /orgs/CCTC-team/rulesets/{id}`.

List existing rulesets and find one by name:

```bash
gh api /orgs/CCTC-team/rulesets \
  --jq '.[] | select(.name == "cctc-critical-trial")'
```

Updating a ruleset later uses `PUT /orgs/CCTC-team/rulesets/{id}`
with the same JSON payload; the `id` comes from the list above.

## Deliberately not done

- **Template repositories.** GitHub supports flagging a repo as a template so
  "Use this template" produces a pre-scaffolded new repo. We considered this
  but decided against it: CCTC isn't expecting to spin up large new
  applications at a rate that justifies the ongoing maintenance burden of
  keeping a template (SDK pins, CI workflow, package versions, security
  patches) current with the rest of the estate. New repos will continue to
  be scaffolded by hand, copying from the closest existing project. Revisit
  if the pace of new applications picks up.
