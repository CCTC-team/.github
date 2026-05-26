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

## Deliberately not done

- **Template repositories.** GitHub supports flagging a repo as a template so
  "Use this template" produces a pre-scaffolded new repo. We considered this
  but decided against it: CCTC isn't expecting to spin up large new
  applications at a rate that justifies the ongoing maintenance burden of
  keeping a template (SDK pins, CI workflow, package versions, security
  patches) current with the rest of the estate. New repos will continue to
  be scaffolded by hand, copying from the closest existing project. Revisit
  if the pace of new applications picks up.
