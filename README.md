# .github

Org-level repository for the `CCTC-team` GitHub organisation. The files here
become defaults for every repo in the org that does not define its own version.

This repo is private, so the defaults only flow into other **private** repos.

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
| `templates/compliance/` | `.compliance.yml.example`, `CONTRIBUTING-regulated.md`, README-banner, caller-workflow — pushed by drift |
| `.github/workflows/compliance-check.yml` | Reusable workflow regulated repos opt into |
| `.github/workflows/compliance-drift.yml` | Nightly drift correction across regulated repos |
| `scripts/compliance-drift.sh` | Drift-detection logic invoked by the workflow |

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

One-time setup (run as an org admin):

```bash
gh api -X PATCH /orgs/CCTC-team/properties/schema \
  -f 'properties[][property_name]=system_category' \
  -f 'properties[][value_type]=single_select' \
  -f 'properties[][required]=false' \
  -f 'properties[][default_value]=none' \
  -f 'properties[][description]=Inspection bucket and validation rigour for this repo. Specific regulations live in .compliance.yml.' \
  -f 'properties[][allowed_values][]=none' \
  -f 'properties[][allowed_values][]=critical-trial' \
  -f 'properties[][allowed_values][]=trial-governance' \
  -f 'properties[][allowed_values][]=personal-data'
```

Then set the property on each regulated repo:

```bash
gh api -X PATCH /orgs/CCTC-team/properties/values \
  -f 'repository_names[]=some-regulated-repo' \
  -f 'properties[][property_name]=system_category' \
  -f 'properties[][value]=critical-trial'
```

### Per-repo opt-in (or just set the property and let drift do it)

Regulated repos need five things. The drift workflow will create any that
are missing the next time it runs, but you can also commit them by hand:

1. `.github/compliance.schema.json` — copy of the canonical schema.
2. `.compliance.yml` — repo-specific metadata, validated against the schema.
3. `README.md` carrying `<!-- compliance:banner -->` (links to rules #4).
4. `CONTRIBUTING-regulated.md` — engineer-facing behavioural rules
   (what changes about your day-to-day work in a regulated repo).
5. `.github/workflows/compliance.yml` — three-line caller that points at
   `compliance-check.yml` in this repo.

Starter copies of all five live in `templates/compliance/` and at
`compliance.schema.json`.

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

### Required App permissions (TODO before first run)

The drift workflow expects org secrets `ORG_COMPLIANCE_DRIFT_APP_ID` /
`ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY` for a GitHub App with:

- Contents: **read & write** (commit drift fixes)
- Pull requests: **read & write** (open the PR)
- Metadata: read
- Custom properties: read

The existing `CCTC Label Sync` App has only `Issues: write` and is **not
sufficient**. Either provision a separate App or expand the existing one
— a separate App is cleaner because the scopes differ materially and you
may want to revoke one without the other.

## Things still to do

- [x] Replace the support email placeholder in `.github/ISSUE_TEMPLATE/config.yml`
- [x] Replace the security email placeholder in `SECURITY.md`
- [x] Replace `@CCTC-team/maintainers` in `.github/CODEOWNERS` with the real team
- [x] Create the `CCTC Label Sync` GitHub App (org-owned, Issues: read & write,
      installed on all repositories) and add the org secrets
      `ORG_LABEL_SYNC_APP_ID` and `ORG_LABEL_SYNC_APP_PRIVATE_KEY`
- [x] Audit existing repos for legacy `ISSUE_TEMPLATE.md` files that will
      override these defaults
- [ ] Define org-level Rulesets for branch protection and required checks
- [ ] Create the `system_category` org custom property (see Compliance
      metadata section)
- [ ] Provision the `CCTC Compliance Drift` GitHub App and add the secrets
      `ORG_COMPLIANCE_DRIFT_APP_ID` / `ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY`
- [ ] Tag the existing regulated repos by setting `system_category` on
      each one (drift workflow will then scaffold them on next run)

## Deliberately not done

- **Template repositories.** GitHub supports flagging a repo as a template so
  "Use this template" produces a pre-scaffolded new repo. We considered this
  but decided against it: CCTC isn't expecting to spin up large new
  applications at a rate that justifies the ongoing maintenance burden of
  keeping a template (SDK pins, CI workflow, package versions, security
  patches) current with the rest of the estate. New repos will continue to
  be scaffolded by hand, copying from the closest existing project. Revisit
  if the pace of new applications picks up.
