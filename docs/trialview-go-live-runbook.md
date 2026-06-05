# TrialView go-live runbook

Concrete, copy-pasteable steps to take TrialView from a draft-only (`evaluate`)
release pipeline to a published, gated, agent-deployed release. It complements
the *why* docs — [`release-authorisation.md`](release-authorisation.md) (the
production gate) and [`release-process.md`](release-process.md) (the artifact
set) — with the exact clicks and commands for **this** repo.

Two of the steps need privileges this automation does not hold and are owned by
a human:

- **§A — ChatOps release authorisation** (qa-approvers Read + org-read token +
  authorise caller) — org/repo admin, GitHub UI or API.
- **§B — Pull-agent on staging** — ops, server shell access.

The remaining steps (vuln remediation, the caller flip + signed tag, the board
flips) are automatable and are tracked in the worked-example plan. The
dependency order is: vuln gate → **§A** + **§B** (independent) → caller flip +
`v0.0.1` tag → board `Released`.

---

## §A — ChatOps release authorisation (org/repo admin)

Gates publication of a production Release behind a QA `/approve`, bound to the
exact image digest, with segregation of duties (author ≠ approver). A GitHub
`production` Environment with required reviewers is **not** usable here:
deployment protection rules are an Enterprise feature for private repos, and this
org is on Team. Rationale and the e-signature residual gap:
[`release-authorisation.md`](release-authorisation.md); token provisioning:
[`release-authorisation-token-setup.md`](release-authorisation-token-setup.md).

### A0 — Ensure the `qa-approvers` team has Read on TrialView

The standing org team **`qa-approvers`** is the QA sign-off role (it also signs
the board's `QA approved`). Membership is the human decision — and at least one
member must be someone *other* than whoever cuts the `v0.0.1` tag, or the
author≠approver rule leaves no one able to approve.

Granting that team **Read** on each regulated repo is a standing onboarding
control, not a TrialView one-off — see [onboarding a regulated
repo](https://github.com/CCTC-team/.github/wiki/Onboarding-a-Regulated-Repo),
Step 10. For TrialView specifically:

```bash
gh api -X PUT orgs/CCTC-team/teams/qa-approvers/repos/CCTC-team/TrialView \
  -f permission=pull          # "pull" == Read
```

**Read — never Write.** Commenting `/approve` on an issue needs only Read, and a
release approver must not be able to change the artifact they authorise (write
would let them push code, merge PRs, or edit the release workflow — collapsing the
QA gate's independence; segregation of duties, ICH E6(R3) §3.16). Read is the
access ceiling for this team.

### A1 — Grant TrialView access to the `QA_ORG_READ_TOKEN` secret

The approval workflow verifies `qa-approvers` membership server-side with an
org-read token (the default `GITHUB_TOKEN` cannot read org teams). Grant the repo
access to the existing org secret (provision it once per
[token setup](release-authorisation-token-setup.md)):

```bash
# Re-run with the FULL repo list — --repos replaces the access set.
gh secret set QA_ORG_READ_TOKEN --org CCTC-team --visibility selected \
  --repos CCTC-team/TrialView   # add every regulated repo that cuts releases
```

If this is missed, every `/approve` resolves to a non-member and is ignored, so a
gated release can never publish.

### A2 — Ensure the authorisation caller is present

TrialView needs `.github/workflows/release-authorize.yml` (the `issue_comment`
caller that forwards `/approve` to the org's reusable authorisation workflow). It
is stubbed automatically by the compliance-drift workflow from
`templates/compliance/release-authorize-caller.yml`; confirm it exists:

```bash
gh api repos/CCTC-team/TrialView/contents/.github/workflows/release-authorize.yml \
  -q .path   # expect: .github/workflows/release-authorize.yml
```

### A3 — Point the caller at the approvers team

In **TrialView** `.github/workflows/release.yml`, uncomment the `approvers_team:`
line under the reusable-workflow `with:` block:

```yaml
    with:
      tag: ${{ github.ref_name }}
      enforcement: evaluate        # flipped to active at go-live (see caller-flip step)
      approvers_team: qa-approvers  # ← uncomment: cut a draft + hold for /approve
```

When set on an `active` release, the build cuts a **draft** Release and opens a
digest-bound authorisation issue; the authorise caller publishes the draft on a
`/approve` from a non-author `qa-approvers` member, filling the Release notes'
`## Release authorisation` block with the approver identity, UTC timestamp, and
released digest(s).

### A4 — Verify

```bash
gh api orgs/CCTC-team/teams/qa-approvers/repos/CCTC-team/TrialView -q .permissions.pull
# expect: true   (qa-approvers has Read)
gh api repos/CCTC-team/TrialView/contents/.github/workflows/release-authorize.yml -q .path
# expect: .github/workflows/release-authorize.yml
```

Confirm too that TrialView is in the `QA_ORG_READ_TOKEN` secret's repository
access list (Org → Settings → Secrets and variables → Actions).

---

## §B — Pull-agent on staging (ops, server shell)

Deploys TrialView by pulling the CI-built images **by digest** after verifying
the release's SSH-signed manifest. Full procedure already exists — this is the
TrialView-specific checklist over it.

### B1 — Host prerequisites

Work through **every** item in
[`server-structure/agent/PREREQUISITES.md`](../../server-structure/agent/PREREQUISITES.md)
on the staging host: Docker + Compose v2, `gh` ≥ 2.x, `ssh-keygen` ≥ 8.2 (the
`-Y verify` verb), Python ≥ 3.11, the `cctc-release-agent` user in both `deploy`
and `docker` groups (`umask 002`), and a working `docker login ghcr.io` with the
least-privilege token (Contents: read + Packages: read).

### B2 — Install the agent

Follow **DEPLOYMENT_RUNBOOK.md → "TrialView Pull-Agent Release Deployment" →
"Install the agent (one-time per environment)"**
([`server-structure/docs/DEPLOYMENT_RUNBOOK.md`](../../server-structure/docs/DEPLOYMENT_RUNBOOK.md),
§ at line ~425): create the service account, drop the token at
`/srv/secrets/cctc-release-agent/staging.env` (`0640`, `root:deploy`), deploy
`agent/` + `config.staging.yml` + `allowed_signers` to `/srv/docker/agent`,
install the systemd unit + timer, then:

```bash
sudo systemctl enable --now cctc-release-agent@staging.timer
systemctl list-timers 'cctc-release-agent@*'     # confirm scheduled
```

TrialView ships **two** images; `config.staging.yml` already binds both
(`trialview` → `trialview-staging`, `trialview-api` → `trialview-api-staging`).

### B3 — One verified pull-deploy

In `evaluate` the agent ignores drafts, so a real *published* Release must exist
first (i.e. after the caller flip + `v0.0.1`). Once it does, confirm the agent
verifies, pulls by digest, boots, and audits:

```bash
# manifest verifies against the deployed allowed_signers
gh release download v0.0.1 --repo CCTC-team/TrialView \
  --pattern 'release-manifest.json' --pattern 'release-manifest.json.sig' --dir /tmp/rel
ssh-keygen -Y verify -f /srv/docker/agent/allowed_signers -I release@cctc-team \
  -n cctc-release -s /tmp/rel/release-manifest.json.sig < /tmp/rel/release-manifest.json

# after the next timer cycle, the audit log shows a successful deploy by digest
sudo tail -n 20 /var/log/cctc-release-agent/trialview-staging.jsonl
docker ps --filter name=trialview-staging       # both services up on the pinned digest
```

A tampered manifest must **fail** verification (fail-closed) — confirm by editing
a byte of the downloaded manifest and re-running the verify.

---

## After §A and §B: caller flip, signed tag, board `Released`

These are automatable (not part of this human runbook) but listed so the
sequence is visible:

1. Confirm the **grype image scan** is clean in a dry-run (it scans the image
   SBOMs, not repo manifests — the remediated functional-test/Java advisories
   are not in either image).
2. Flip the caller `enforcement: evaluate → active` (and set
   `approvers_team: qa-approvers`) and cut a **signed** `v0.0.1` tag
   (`git tag -s`). With §A done, the release is cut as a **draft** and held for a
   `/approve` on the authorisation issue before it publishes.
3. Drive a board card (#34) to `Released` behind the published Release, then flip
   `preconditions: Released` (and the remaining board checks) `evaluate → active`
   in `.github/project-enforcement.yml`, recording the dates in the rollout logs.
