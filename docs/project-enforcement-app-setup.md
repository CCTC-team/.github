# Provisioning auth for `project-enforcement.yml`

`.github/workflows/project-enforcement.yml` polls every project listed in
`.github/project-enforcement.yml`, diffs the result against a snapshot
branch, and (in later phases) reverts illegal field writes and posts
issue comments. Two sibling workflows share the same token:
`.github/workflows/project-audit.yml` (nightly sweep) and
`.github/workflows/project-card-promote.yml` (PR-driven forward
promotion, *callable from regulated repos via the caller template*).

All three workflows expect the same pair of org secrets:

| Secret | Used by |
| --- | --- |
| `ORG_PROJECT_ENFORCEMENT_APP_CLIENT_ID`  | `project-enforcement.yml`, `project-audit.yml`, the `project-card-promote-caller.yml` template (passed in via `secrets:`) |
| `ORG_PROJECT_ENFORCEMENT_APP_PRIVATE_KEY` | (same as above) |

The token must carry:

| Capability | Why |
| --- | --- |
| `read:project` / `write:project` | Read ProjectV2 fields/items + revert illegal status moves + run the PR-driven promoter |
| `read:org` (Organization → Members → Read) | Resolve approver-field usernames and discover unmonitored project clones |
| Organization → Custom properties → Read | Phase 2/6 reads `system_category` to decide which board to enforce on |
| Repository → Contents → Read & Write | Read `.compliance.yml` and PR state on regulated repos; commit the `_project-state` snapshot branch |
| Repository → Issues → Write | Post comments, apply `process-violation`, clear `process-override:approved` |
| Repository → Pull requests → Read | Resolve `closingIssuesReferences` and check-run status |
| Repository → Metadata → Read | Mandatory baseline |

The Compliance Drift App has the Contents/PRs/Metadata/Custom-properties
scopes already but **not** Projects/Members/Issues. Two paths are viable
— **ask the user which they prefer before provisioning**; both meet the
same regulatory posture, the choice is operational.

## Option A — expand the existing `CCTC Compliance Drift` App

Add the missing scopes to the existing App. Pro: one App to rotate,
one set of org secrets to manage. Con: a single token compromise
affects both drift and project enforcement, and the audit log no longer
distinguishes which workflow made which change.

1. GitHub → CCTC-team → Settings → Developer settings → GitHub Apps →
   **CCTC Compliance Drift** → **Edit**.
2. **Permissions** — add to what's already there:
   - Organization → **Projects** → Read & Write
   - Organization → **Members** → Read
   - Repository → **Issues** → Write _(drift does not have this today;
     project enforcement needs it to post `process-violation` comments)_
3. Save. An org admin will need to **accept the permission change** on
   the installation page before the new scopes take effect.
4. Re-use the existing `ORG_COMPLIANCE_DRIFT_APP_CLIENT_ID` /
   `ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY` secrets by renaming the
   `ORG_PROJECT_ENFORCEMENT_APP_*` references in:
   - `.github/workflows/project-enforcement.yml` (2 refs)
   - `.github/workflows/project-audit.yml` (2 refs)
   - `templates/compliance/project-card-promote-caller.yml`
     (2 refs — note this is the caller template that drift pushes into
     every regulated repo, so the rename propagates org-wide on the
     next drift run)

   Re-running compliance-drift after the rename will open scaffolding
   PRs against every regulated repo to pick up the new caller —
   merge-train that as one batch.

## Option B — provision a separate `CCTC Project Enforcement` App

A second App, scopes restricted to what these three workflows need.
Pro: revocation and audit-log attribution are clean; rotation cadence
can differ from drift's. Con: one more App to provision, install, and
rotate.

1. Create the App following the same web-UI walk-through as
   [`docs/compliance-drift-app-setup.md`](compliance-drift-app-setup.md)
   §1, with these differences:
   - **GitHub App name:** `CCTC Project Enforcement`
   - **Description:** `Polls regulated lifecycle boards; reverts illegal status moves and posts traceability comments.`
   - **Permissions** — set the full table above (Projects R/W, Members
     Read, Custom Properties Read, Contents R/W, Issues Write, PRs
     Read, Metadata Read).
   - **Webhook → Active:** uncheck (polling, not event-driven).
2. Generate a private key (same as compliance-drift §2).
3. Install on the org with **All repositories** selected (same as §3).
4. Add the two org secrets:

   ```bash
   gh secret set ORG_PROJECT_ENFORCEMENT_APP_CLIENT_ID \
     --org CCTC-team --visibility selected --repos .github \
     --body "<the-client-id>"

   gh secret set ORG_PROJECT_ENFORCEMENT_APP_PRIVATE_KEY \
     --org CCTC-team --visibility selected --repos .github \
     --body "$(cat /path/to/cctc-project-enforcement.<date>.private-key.pem)"
   ```

   The promoter caller (`project-card-promote-caller.yml`) is pushed
   into every regulated repo by drift, where it reads
   `secrets.ORG_PROJECT_ENFORCEMENT_APP_*` from the org-secret scope.
   Either set `--visibility all` on the secrets or extend
   `--repos` to include each regulated repo.
5. Delete the local `.pem`. Smoke-test via
   `gh workflow run project-enforcement.yml`; the run should finish
   green with the step summary listing observed changes (none on the
   first run) and writing an empty snapshot to `_project-state`.

## Interim — fine-grained PAT

If you'd rather defer the App decision while the rollout is in early
phases, a fine-grained PAT scoped to `read:project`, `write:project`,
`read:org` plus repo-level Contents/Issues/PRs is acceptable for
**evaluate-mode** runs only. Store it as `ORG_PROJECT_ENFORCEMENT_PAT`
and swap the `actions/create-github-app-token` step in the three
workflows for a plain `env: GH_TOKEN: ${{ secrets.ORG_PROJECT_ENFORCEMENT_PAT }}`.
A PAT is tied to a personal account — switch to an App before any
check is graduated to `active`, so the audit trail attributes reverts
to an org-owned identity rather than a developer.
