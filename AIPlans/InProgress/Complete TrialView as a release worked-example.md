# Complete TrialView as a release worked-example

> Top-level = not started. Picks up after `AIPlans/Complete/Replace attestation
> with signed release manifest.md`. The org release pipeline (signed-manifest
> model) is implemented and **dry-run validated**; TrialView builds, signs the
> manifest, and cuts a **draft** Release in `evaluate` mode. This plan walks the
> repo's own rollout-log gates (`README.md` §"Release pipeline rollout log" and
> §"Active-mode rollout log") to a real **published, gated, agent-deployed**
> release that backs a board card reaching `Released`.

## State at handoff (2026-06-05)

- `.github` / `server-structure` / `.github.wiki` all clean and pushed.
- Org secret `RELEASE_SIGNING_KEY` set (selected → TrialView); public key in
  `server-structure/agent/allowed_signers`; sign/verify proven end-to-end on the
  real `v0.0.1-rc7` artifact (since cleaned up — no `v0.0.1*` tags remain).
- TrialView caller is in `enforcement: evaluate`.

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

   **State (2026-06-05): in progress.** Done: **A0** — `qa-approvers` granted
   **Read** (pull=true, push=false, admin=false) on TrialView; never Write, for
   segregation of duties. **A1** — `QA_ORG_READ_TOKEN` org secret provisioned
   (fine-grained PAT under a dedicated machine account, org Members:read only),
   `visibility=selected`, scoped to TrialView; verified present. Remaining:
   **A2** — the `release-authorize.yml` caller is absent (the `compliance-drift`
   workflow is not yet present in TrialView, so nothing has stubbed it); **A3** —
   TrialView's `release.yml` caller still carries the old commented `#
   environment: production` line and has **not** been updated to
   `approvers_team:`.

3. **Pull-agent on staging (needs server access — ops).** The agent code is
   built + tested but not deployed. Per `server-structure/agent/PREREQUISITES.md`:
   docker + compose v2, `gh` + `ssh-keygen`, the GHCR-read token at
   `/srv/secrets/cctc-release-agent/staging.env`, the agent + `config.staging.yml`
   + `allowed_signers` deployed to `/srv/docker/agent`, systemd unit/timer. Do
   **one verified pull-deploy on staging** (agent verifies the signed manifest,
   pulls by digest, boots, audits).

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

- Me/agentable: #1 investigation + fixes, #4 caller flip + tag, #5 config flips,
  exact steps for #2.
- You / org admin: #2 (grant `qa-approvers` Read, provision + grant the
  `QA_ORG_READ_TOKEN` secret; the token value cannot be minted by automation).
- Ops / server access: #3 (agent install on the staging host).
