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

   **Robustness caveat (follow-up, not a blocker):** `summarize()` tallies
   `grype["matches"]`; if grype ever fails to fetch its vuln DB its output is
   empty and the gate reads `total=0` → "✅ No known vulnerabilities" →
   `has_blocking=False` — i.e. a scanner failure is indistinguishable from a
   genuine clean. For a regulated gate, harden the workflow to assert grype
   actually ran (check its exit code / DB-update status, or treat a 0-total scan
   of a multi-thousand-component image as suspect). Tracked here as a
   recommended improvement to the org release workflow.

   **State:** remediation is on `rh_dev` via PR #19 → `develop` (not yet merged),
   so dependabot will not auto-close the repo-manifest alerts until it lands. The
   `v0.0.1-rc8` dry-run tag + its draft Release remain and should be cleaned up
   (like the earlier rc tags) before cutting the real `v0.0.1`.

2. **Production Environment + required reviewers.** TrialView has **no
   Environments** configured. Create a `production` Environment with the
   QA-approver group as required reviewers, restrict deployment branches/tags to
   `v*`, and set the release author ≠ approver (segregation of duties) — per
   `docs/release-authorisation.md`. Then set `environment: production` in
   TrialView's release caller.

3. **Pull-agent on staging (needs server access — ops).** The agent code is
   built + tested but not deployed. Per `server-structure/agent/PREREQUISITES.md`:
   docker + compose v2, `gh` + `ssh-keygen`, the GHCR-read token at
   `/srv/secrets/cctc-release-agent/staging.env`, the agent + `config.staging.yml`
   + `allowed_signers` deployed to `/srv/docker/agent`, systemd unit/timer. Do
   **one verified pull-deploy on staging** (agent verifies the signed manifest,
   pulls by digest, boots, audits).

4. **Flip publish to active + cut `v0.0.1`.** After 1–3: change TrialView's caller
   `enforcement: evaluate → active`, cut a **signed** `v0.0.1` tag (`git tag -s`),
   and confirm a **published** (non-draft) Release gated on the production
   Environment approval, carrying the signed manifest + validation evidence.
   Update the release rollout log rows.

5. **Board `Released` gate.** With a published Release (#4) AND a verified staging
   deploy (#3) both done, the hardened `Released` precondition's gate is real:
   drive a board card (board #34) through the lifecycle to `Released` backed by
   the release, then flip `preconditions: Released` (and the other board checks,
   per the active-mode rollout log) `evaluate → active` in
   `.github/project-enforcement.yml`. Optionally enable
   `require_signed_manifest` so the gate also requires `release-manifest.json.sig`.

**Exact runbooks for gates 2 + 3** (the human-owned steps): written up
copy-pasteable in [`docs/trialview-go-live-runbook.md`](../../docs/trialview-go-live-runbook.md)
— §A covers the `production` Environment (incl. the open decision that **no
QA-approver team exists yet**, the `gh api` to create it + the Environment with
`prevent_self_review` + `v*` tag policy, and the caller `environment:` edit); §B
covers the staging agent install over `PREREQUISITES.md` +
`DEPLOYMENT_RUNBOOK.md` with the TrialView two-image specifics and the verified
pull-deploy check.

## Parallel / separate track — TrialView GxP gaps (NOT pipeline blockers)

Issues #10 (extractable audit trail), #11 (CSV evidence pack URS/FS/IQ/OQ/PQ),
#12 (per-change validation documentation). These don't block demonstrating the
pipeline, but TrialView cannot be a *real* regulated release / hold trial data
until they close. Issue #13 ("migrate `.compliance.yml` to schema v2") looks
**stale** — the schema was collapsed to a single v1; verify and close if so.

## Owners

- Me/agentable: #1 investigation + fixes, #4 caller flip + tag, #5 config flips,
  exact steps for #2.
- You / org admin: #2 (Environment + reviewers in the GitHub UI).
- Ops / server access: #3 (agent install on the staging host).
