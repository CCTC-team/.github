# TrialView go-live runbook

Concrete, copy-pasteable steps to take TrialView from a draft-only (`evaluate`)
release pipeline to a published, gated, agent-deployed release. It complements
the *why* docs — [`release-authorisation.md`](release-authorisation.md) (the
production gate) and [`release-process.md`](release-process.md) (the artifact
set) — with the exact clicks and commands for **this** repo.

Two of the steps need privileges this automation does not hold and are owned by
a human:

- **§A — Production Environment + reviewers** — org/repo admin, GitHub UI or API.
- **§B — Pull-agent on staging** — ops, server shell access.

The remaining steps (vuln remediation, the caller flip + signed tag, the board
flips) are automatable and are tracked in the worked-example plan. The
dependency order is: vuln gate → **§A** + **§B** (independent) → caller flip +
`v0.0.1` tag → board `Released`.

---

## §A — Production Environment + required reviewers (org/repo admin)

Gates publication of a production Release behind a QA reviewer approval, bound to
the exact image digest, with segregation of duties (author ≠ approver). Rationale
and the e-signature residual gap: [`release-authorisation.md`](release-authorisation.md).

### A0 — Ensure the `qa-approvers` team has Read on TrialView

The standing org team **`qa-approvers`** is the QA sign-off role (it also signs
the board's `QA approved`). Membership is the human decision — and at least one
member must be someone *other* than whoever cuts the `v0.0.1` tag, or
**Prevent self-review** (A1) leaves no one able to approve.

Granting that team **Read** on each regulated repo is a standing onboarding
control, not a TrialView one-off — see [onboarding a regulated
repo](https://github.com/CCTC-team/.github/wiki/Onboarding-a-Regulated-Repo),
Step 10. For TrialView specifically:

```bash
gh api -X PUT orgs/CCTC-team/teams/qa-approvers/repos/CCTC-team/TrialView \
  -f permission=pull          # "pull" == Read
```

**Read — never Write.** GitHub only requires *read* access for a required
reviewer to approve a deployment, and a release approver must not be able to
change the artifact they authorise (write would let them push code, merge PRs, or
edit the release workflow — collapsing the QA gate's independence; segregation of
duties, ICH E6(R3) §3.16). Read is the access ceiling for this team.

### A1 — Create the `production` Environment

**UI:** TrialView → *Settings → Environments → New environment* → name it
`production`.

**Or API** — resolve the team id, then create the Environment with required
reviewers, self-review prevention, and a custom (tag) branch policy in one call:

```bash
TEAM_ID=$(gh api orgs/CCTC-team/teams/qa-approvers -q .id)

gh api -X PUT repos/CCTC-team/TrialView/environments/production --input - <<JSON
{
  "wait_timer": 0,
  "prevent_self_review": true,
  "reviewers": [{ "type": "Team", "id": $TEAM_ID }],
  "deployment_branch_policy": { "protected_branches": false, "custom_branch_policies": true }
}
JSON
```

- `prevent_self_review: true` is the **segregation-of-duties** control
  (ICH E6(R3) §3.16): the release author cannot approve their own release.
- To use named individuals instead of a team, use
  `{ "type": "User", "id": <user-id> }` (`gh api users/<login> -q .id`).

### A2 — Restrict deployments to `v*` tags

```bash
gh api -X POST repos/CCTC-team/TrialView/environments/production/deployment-branch-policies \
  -f name='v*' -f type=tag
```

Only `v*` tags can then deploy to `production`, matching the signed-tag release
trigger.

### A3 — Point the caller at the Environment

In **TrialView** `.github/workflows/release.yml`, uncomment the `environment:`
line under the reusable-workflow `with:` block:

```yaml
    with:
      tag: ${{ github.ref_name }}
      enforcement: evaluate        # flipped to active at go-live (see caller-flip step)
      environment: production      # ← uncomment: pause publish on QA approval
```

When set, an approval-gate job holds the run on the `production` reviewers
**before** publish; the publish job fills the Release notes'
`## Release authorisation` block with the approver identity, UTC timestamp, and
released digest(s).

### A4 — Verify

```bash
gh api repos/CCTC-team/TrialView/environments/production \
  -q '{name: .name, reviewers: [.protection_rules[]?.reviewers[]?.reviewer.slug]}'
gh api repos/CCTC-team/TrialView/environments/production/deployment-branch-policies \
  -q '.branch_policies[] | .name + " (" + .type + ")"'
```

Expect `production`, the QA team as reviewer, and `v* (tag)`.

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
2. Flip the caller `enforcement: evaluate → active` and cut a **signed**
   `v0.0.1` tag (`git tag -s`). With §A done, publish pauses on QA approval.
3. Drive a board card (#34) to `Released` behind the published Release, then flip
   `preconditions: Released` (and the remaining board checks) `evaluate → active`
   in `.github/project-enforcement.yml`, recording the dates in the rollout logs.
