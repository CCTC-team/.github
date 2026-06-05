# Complete TrialView as a release worked-example

> **In progress.** Picks up after `AIPlans/Complete/Replace attestation with
> signed release manifest.md`. The org release pipeline (signed-manifest model)
> is implemented and **dry-run validated**; TrialView builds, signs the manifest,
> and cuts a **draft** Release in `evaluate` mode. This plan walks the repo's own
> rollout-log gates (`README.md` §"Release pipeline rollout log" and §"Active-mode
> rollout log") to a real **published, gated, agent-deployed** release that backs
> a board card reaching `Released`.

## COLD-START — resume here (verified 2026-06-05 EOD)

**Read this first, then jump to "## Remaining work" at the bottom.** Three repos
are involved, all cloned under `~/repos/`: `.github` (this repo; work on `main`),
`TrialView` (the regulated app; default branch `develop`, signed commits),
`server-structure` (the deploy/agent repo). `.github` + `.github.wiki` are clean
and pushed.

Gate status as verified today:

- **Gate 1 (vuln) — ✅ COMPLETE.** PR #19 merged to TrialView `develop`
  (`1bcf690`); **0 critical / 0 high** open alerts (1 low + 2 medium remain,
  time-boxed in `functional_scripts/SECURITY-triage.md`).
- **Gate 2 (§A ChatOps authorisation) — ✅ COMPLETE.** `qa-approvers` has Read on
  TrialView; `QA_ORG_READ_TOKEN` org secret provisioned (machine-account
  fine-grained PAT, Members:read, scoped to TrialView); `release-authorize.yml`
  caller + `approvers_team: qa-approvers` landed on TrialView `develop`
  (`f756c9c`). Caller still `enforcement: evaluate`.
- **Gate 3 (§B staging agent) — ❌ BLOCKED (see finding below).** Not just an ops
  install: the staging compose still `build:`s from source, so the agent's digest
  pin is ignored. Must be cut over to `image: …@${DIGEST}` first, and that wants a
  published `v0.0.1` to pin against — so §B's verified deploy now sits **after**
  gate 4, not parallel to §A.
- **Gate 4 (active flip + `v0.0.1`) — ❌ NOT STARTED.** No `v0.0.1*` tag/Release;
  caller is `evaluate`. This is the next agentable unblock (needs your go-ahead —
  it publishes a real production Release).
- **Gate 5 (board `Released`) — ❌ NOT STARTED.** Gated on #4 + #3.

Standing facts: org secret `RELEASE_SIGNING_KEY` set (selected → TrialView),
public key in `server-structure/agent/allowed_signers`, sign/verify proven
end-to-end on the (since-cleaned-up) `v0.0.1-rc7..rc9` dry-runs. `gh` is
authenticated as `rmh54` with an `admin:org` token.

### 🔑 KEY FINDING TODAY — staging compose is not digest-pinned (blocks §B)

The agent binding in `server-structure/agent/config.staging.yml` is **correct**
(both images `trialview` + `trialview-api`; component keys, GHCR repos,
`digest_env` vars, and `compose_service` names all match
`TrialView/.github/release-targets.yml`). **But** the compose file it points at
(`server-structure/trialview/docker-compose.staging.yml`) uses `build:` (rebuild
from `/srv/builds/staging/TrialView`) for both services — there is **no `image:
…@${TRIALVIEW_IMAGE_DIGEST}`**. The agent writes the digest into `.env`
(`agent/agent.py:193`) then `docker compose up -d --no-deps`
(`agent/agent.py:213`), but nothing consumes the var → the digest pin is silently
ignored and the server rebuilds from local source, defeating verified-pull-by-
digest. Fix = the compose cutover already specced as **Phase 6** of
`server-structure/AIPlans/InProgress/TrialView pull-agent release deployment
plan.md` (all Phase 6 items unchecked); Phase 6a pre-flight needs a real
published two-image Release to pin. Hence the re-ordering noted above.

## Gates remaining (dependency order)

1. **Vuln gate (HARD BLOCKER for any active release).** TrialView has **1
   critical + 16 high** open dependabot alerts; the active-mode grype scan fails
   on critical/high. Remediate the image dependencies (bump/replace) or produce a
   documented, time-boxed triage for any that cannot be fixed. Re-run a dry-run
   and confirm grype is clean (or only warns) before flipping active.

   **Status (2026-06-05): dependabot critical/high remediated on `rh_dev`
   (TrialView commit `6e2e487`).** Key finding: every critical/high alert lived
   in `functional_scripts/` npm **test tooling** (handlebars, minimatch, lodash,
   glob, braces, cross-spawn, picomatch, tmp, flatted) and one Java **test**
   dep (`assertj-core`) — none is in either deployed image. Confirmed by
   grepping the rc7 image SBOMs (`trialview.cdx.json` / `trialview-api.cdx.json`,
   ~4100 components each): **zero** occurrences of any alerted package. Both
   images are `dotnet publish` output only. Remediation: bumped
   `@typescript-eslint/{eslint-plugin,parser}` 7.2.0→7.18.0 + lockfile resolution
   (clears all npm critical/high without breaking changes); `assertj-core`
   3.22.0→3.27.7. 8 **moderate** remain (uuid via Cucumber/allure report tooling,
   need a breaking major upgrade) — time-boxed in
   `functional_scripts/SECURITY-triage.md` (review by 2026-09-05). Test harness
   re-verified (cucumber `--dry-run`: 36 scenarios / 149 steps load).
   **Grype image scan — confirmed clean by dry-run.** Pushed signed tag
   `v0.0.1-rc8` (TrialView run 27020450194, evaluate mode → draft Release). The
   active-mode vuln gate (`scripts/release/sbom_scan.py`, blocks on any
   critical/high in an image SBOM) reported **no blocking findings**: the
   evaluate-mode "Critical/High present — would fail in active mode" warning did
   **not** fire in execution (the build job log carries the string only once, as
   the echoed step script, not as an emitted annotation). So the grype gate would
   pass in `active` on the current images. Same result on rc7 (image is unchanged
   by the test-dep fixes).

   **Robustness gap — fixed.** Previously `summarize()` tallied `grype["matches"]`
   only; a grype DB-fetch failure yielded empty output read as `total=0` → "✅ No
   known vulnerabilities" → false clean. Hardened: `sbom_scan.load()` is now
   fail-closed (rejects a non-zero grype exit, empty/garbage output, or a document
   with no vulnerability-DB descriptor with `ScanError`), and the release
   workflow's vuln-scan step fails the build **in either mode** when the scan does
   not complete. Covered by `TestLoad` in `test_sbom_scan.py`; README +
   `docs/release-process.md` + wiki `Release-Process.md` updated.

   **Hardened gate validated in CI.** A further dry-run on the hardened gate
   (`v0.0.1-rc9`, TrialView run 27021688515) **passed** — and because a scan that
   fails to complete now exits the build in **either** mode, a green build proves
   grype genuinely ran (DB loaded) and found no critical/high. This upgrades the
   earlier rc7/rc8 result from "inferred clean" to **positively proven clean**.

   **State (updated 2026-06-05): GATE 1 COMPLETE.** PR #19 (`rh_dev` →
   `develop`) **merged** (`1bcf690`); dependabot auto-closed the critical/high
   advisories — TrialView now shows **0 critical / 0 high** open alerts (1 low +
   2 medium remain, within the time-boxed triage in
   `functional_scripts/SECURITY-triage.md`). All `v0.0.1-rc*` dry-run tags and
   their draft Releases have been cleaned up — the repo carries no `v0.0.1*` tag
   or Release, leaving the name clear for the real `v0.0.1`.

2. **ChatOps release authorisation (`qa-approvers` `/approve`).**
   *Supersedes the original "production Environment + required reviewers" step:
   GitHub Environment deployment-protection rules are Enterprise-only for private
   repos and the org is on Team, so that gate could never render. It was replaced
   by an event-driven ChatOps `/approve` gate, now implemented — see
   `AIPlans/Complete/Team-compatible release authorisation gate plan.md`.* In
   `active` the release cuts a **draft** and opens a digest-bound authorisation
   issue; a `qa-approvers` member who is **not** the release author publishes it
   by commenting `/approve` (author ≠ approver = segregation of duties, ICH
   E6(R3) §3.16). Setup per `docs/trialview-go-live-runbook.md` §A: grant
   `qa-approvers` **Read** on TrialView; provision the org secret
   `QA_ORG_READ_TOKEN` (`read:org`) and grant TrialView access; ensure the
   `release-authorize.yml` caller is present (stubbed by compliance-drift); set
   `approvers_team: qa-approvers` in TrialView's release caller.

   **State (2026-06-05): §A COMPLETE.** **A0** — `qa-approvers` granted **Read**
   (pull=true, push=false, admin=false) on TrialView; never Write, for
   segregation of duties. **A1** — `QA_ORG_READ_TOKEN` org secret provisioned
   (fine-grained PAT under a dedicated machine account, org Members:read only),
   `visibility=selected`, scoped to TrialView; verified present. **A2** —
   `.github/workflows/release-authorize.yml` caller added to TrialView (verbatim
   from the org template). **A3** — TrialView's `release.yml` caller set to
   `approvers_team: qa-approvers`, `issues:` raised to `write`, and the stale
   removed-Environment-gate comments refreshed. A2+A3 committed signed directly to
   TrialView `develop` (commit `f756c9c`); caller stays `enforcement: evaluate`
   (approvers_team has no effect until the gate-4 active flip). Verified present on
   `origin/develop`.

3. **Pull-agent on staging (needs server access — ops) — ⚠ also needs a code
   change first.** The agent code is built + tested but not deployed. Per
   `server-structure/agent/PREREQUISITES.md`: docker + compose v2, `gh` +
   `ssh-keygen`, the GHCR-read token at `/srv/secrets/cctc-release-agent/
   staging.env`, the agent + `config.staging.yml` + `allowed_signers` deployed to
   `/srv/docker/agent`, systemd unit/timer. Do **one verified pull-deploy on
   staging** (agent verifies the signed manifest, pulls by digest, boots, audits).

   **⚠ BLOCKER (found 2026-06-05):** the staging compose still `build:`s from
   source, so the agent's digest pin is ignored (see "KEY FINDING" at the top).
   The compose cutover (`server-structure` plan **Phase 6b/6c**) must land first,
   and its pre-flight (6a) needs a published `v0.0.1` to pin — so the **verified
   pull-deploy can only happen after gate 4**. The agent *install* (B1/B2) can be
   done anytime; only the verified deploy (B3) is gated.

4. **Flip publish to active + cut `v0.0.1`.** After 1–3: change TrialView's caller
   `enforcement: evaluate → active`, cut a **signed** `v0.0.1` tag (`git tag -s`),
   and confirm the release is cut as a **draft** that publishes only after a
   non-author `qa-approvers` member comments `/approve` on the authorisation
   issue (gate 2), the published Release carrying the signed manifest + validation
   evidence and the stamped `## Release authorisation` block. Update the release
   rollout log rows.

5. **Board `Released` gate.** With a published Release (#4) AND a verified staging
   deploy (#3) both done, the hardened `Released` precondition's gate is real:
   drive a board card (board #34) through the lifecycle to `Released` backed by
   the release, then flip `preconditions: Released` (and the other board checks,
   per the active-mode rollout log) `evaluate → active` in
   `.github/project-enforcement.yml`. Optionally enable
   `require_signed_manifest` so the gate also requires `release-manifest.json.sig`.

**Exact runbooks for gates 2 + 3** (the human-owned steps): written up
copy-pasteable in [`docs/trialview-go-live-runbook.md`](../../docs/trialview-go-live-runbook.md)
— §A covers the ChatOps authorisation gate (the standing `qa-approvers` team, now
created, granted **Read** on the repo — never Write, for segregation of duties;
the `QA_ORG_READ_TOKEN` org-read secret; the `release-authorize` caller; the
caller `approvers_team:` edit); §B covers the staging agent install over `PREREQUISITES.md`
+ `DEPLOYMENT_RUNBOOK.md` with the TrialView two-image specifics and the verified
pull-deploy check. The QA-approver-team **Read** grant is a standing onboarding
control for every regulated repo — captured in `docs/release-authorisation.md`
and the wiki onboarding page (Step 10), not just this runbook.

## Parallel / separate track — TrialView GxP gaps (NOT pipeline blockers)

Issues #10 (extractable audit trail), #11 (CSV evidence pack URS/FS/IQ/OQ/PQ),
#12 (per-change validation documentation). These don't block demonstrating the
pipeline, but TrialView cannot be a *real* regulated release / hold trial data
until they close. Issue #13 ("migrate `.compliance.yml` to schema v2") looks
**stale** — the schema was collapsed to a single v1; verify and close if so.

## Owners

- Me/agentable: #1 (done), #2 A0/A2/A3 (done), #4 caller flip + tag, the Phase 6
  compose cutover in `server-structure`, #5 config flips.
- You / org admin: #2 A1 (done — secret provisioned); the `/approve` itself at
  go-live must come from a `qa-approvers` member who is **not** whoever cuts the
  `v0.0.1` tag (author ≠ approver).
- Ops / server access: #3 agent install + the verified pull-deploy on staging.

## Remaining work — implementation plan (resume here)

Ordered by true dependency (the original "§A ∥ §B before v0.0.1" ordering is
**corrected**: §B's verified deploy now follows gate 4 because of the compose
cutover finding). Gates 1 + 2 are done. Tackle the phases below in order.

### Phase A — Gate 4: active flip + first published `v0.0.1` (agentable; needs go-ahead)

> Outward-facing: this publishes a **real production Release**. Confirm before the
> tag push and again before the `/approve`. Needs a second `qa-approvers` member
> who is not the tag-pusher.

- [ ] **A1. Pre-flight dry-run (optional but recommended).** Push a throwaway
  `v0.0.1-rcN` tag with `enforcement: active` + `approvers_team: qa-approvers`
  already set; confirm the build cuts a **draft** Release and opens a digest-bound
  authorisation issue carrying both component digests. Then exercise the ChatOps
  paths (approve by non-author → publishes + stamps notes + closes issue; SoD:
  author `/approve` refused; `/deny`; non-member `/approve` ignored). Clean up the
  rcN tag/release/issue. (These are the unchecked verification items at the bottom
  of `AIPlans/Complete/Team-compatible release authorisation gate plan.md`.)
- [ ] **A2. Flip caller to active.** In TrialView `.github/workflows/release.yml`
  set `enforcement: evaluate → active` (commit signed to `develop`).
  `approvers_team: qa-approvers` is already set.
- [ ] **A3. Cut the signed tag.** `git tag -s v0.0.1 -m '…'` on the release commit
  and push. Build cuts a **draft** Release (full evidence + signed manifest) and
  opens the authorisation issue.
- [ ] **A4. Authorise.** A `qa-approvers` member who is **not** the tag-pusher
  comments `/approve` on the issue → draft publishes, notes carry the `## Release
  authorisation` block (approver, UTC, digests), issue closes.
- [ ] **A5. Record.** Update the `README.md` release rollout-log + active-mode
  rows; capture the published digests for Phase B.

### Phase B — Gate 3 / §B: compose cutover + staging deploy

- [ ] **B1. Compose cutover (agentable — `server-structure`).** Execute Phase
  6b/6c of `server-structure/AIPlans/InProgress/TrialView pull-agent release
  deployment plan.md`: replace the `build:` stanza of `trialview-staging` and
  `trialview-api-staging` (and the prod services) with `image:
  ghcr.io/cctc-team/trialview@${TRIALVIEW_IMAGE_DIGEST}` /
  `…/trialview-api@${TRIALVIEW_API_IMAGE_DIGEST}`, preserving secrets, the external
  `server-network`, `depends_on`, healthchecks. Pre-flight (6a) confirms the
  `v0.0.1` digests from Phase A exist. Staging first, then prod after a clean
  staging cycle.
- [ ] **B2. Agent install on staging (ops — server shell).** Work
  `server-structure/agent/PREREQUISITES.md` then DEPLOYMENT_RUNBOOK.md "Install
  the agent"; enable the systemd timer. Runbook §B in
  `docs/trialview-go-live-runbook.md`.
- [ ] **B3. One verified pull-deploy (ops).** Agent verifies the signed manifest
  against `allowed_signers`, pulls **both** images by digest, boots, audits;
  confirm a tampered manifest fails closed. Both `trialview-staging` +
  `trialview-api-staging` up on the pinned digests.

### Phase C — Gate 5: board `Released` + activate board checks (agentable; needs go-ahead)

- [ ] **C1.** Drive a board card (board #34) through the lifecycle to `Released`
  backed by the published `v0.0.1` Release.
- [ ] **C2.** Flip `preconditions: Released` (and the remaining board checks per
  the active-mode rollout log) `evaluate → active` in
  `.github/project-enforcement.yml`; optionally enable `require_signed_manifest`.
  Record dates in the rollout logs.

### Documentation / sync (do alongside the phase that changes behaviour)

- [ ] Update `README.md` rollout-log rows (Phase A5, C2) and reconcile the wiki
  (`Release-Process.md`, `Onboarding-a-Regulated-Repo.md`) per CLAUDE.md "keep the
  wiki in sync".
- [ ] When `server-structure` Phase 6 lands, tick its checkboxes there too (that
  plan is the source of truth for the compose cutover).

### First move on cold-start

Decide whether to do **Phase A1 (dry-run)** first or go straight to the real
`v0.0.1`. Everything in Phase A is outward-facing — confirm before the tag push
and before the `/approve`.
