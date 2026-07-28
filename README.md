# .github

Org-level **community-health defaults** for the `CCTC-team` GitHub organisation.
A repository named exactly `.github` is the only way GitHub propagates org-wide
community-health files to every repo — public **and** private — that does not
define its own, so this repo is deliberately **public** and deliberately
minimal.

For an overview of CCTC and the software we publish, see the
[organisation profile](https://github.com/CCTC-team).

## What's in here

| Path | Purpose |
| --- | --- |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Standard bug-report form |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Standard feature-request form |
| `.github/ISSUE_TEMPLATE/config.yml` | Disables blank issues; adds security + support contact links |
| `.github/pull_request_template.md` | Default PR template with clinical/compliance checklist |
| `SECURITY.md` | Org-wide vulnerability reporting policy |
| `profile/README.md` | The organisation profile page |
| `.github/CODEOWNERS` | Reviewers for this repo (does **not** propagate to other repos) |

## How inheritance works (and doesn't)

GitHub serves org-wide community-health inheritance **only** from a repo named
exactly `.github`. Inherited by every repo with no local equivalent:

- Issue templates and the issue chooser config
- Pull request template
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `FUNDING.yml`

A **private** `.github` would not propagate to public repos, which is why this
repo stays public and holds only community-health files.

Several things are **not** inherited and are handled elsewhere — labels, branch
protection / rulesets, CODEOWNERS, repo scaffolding, and the reusable workflows.

## Where the regulated machinery lives

The regulated-lifecycle enforcement engine, the compliance/release schemas, the
org rulesets, the release tooling, the rationale docs, and `labels.json` live in
the **private** [`CCTC-team/compliance-engine`](https://github.com/CCTC-team/compliance-engine)
repository (org members only). Regulated repos opt into its reusable workflows
via `uses: CCTC-team/compliance-engine/...`. This repo intentionally carries
none of that.

That includes the **regulated feature (V&V) issue form**, which is *not* an
org-wide default and is not served from here. It is delivered into each
regulated repository's own `.github/ISSUE_TEMPLATE/`, and kept in step there,
because its body contract is co-owned with the enforcement engine's parsers — a
copy that drifts silently desyncs the gate. To read or fill that form, use the
copy in the repository the requirement belongs to; it is the only one of record.
