# GCP/MHRA Inspection-Resilient Release Process Implementation Plan

## Context

> **The target end-state this plan implements is documented in the wiki**, which is now
> the official, authoritative spec:
> [Release-Process](https://github.com/CCTC-team/.github/wiki/Release-Process) (what the
> process is + what it achieves + the diagrams) and
> [Release-Build-Contract](https://github.com/CCTC-team/.github/wiki/Release-Build-Contract)
> (the tool-agnostic build-target contract). **This plan is the *how* — the phased
> implementation that delivers that target — and should be read against the wiki.** Where
> this plan and the wiki disagree on *what* the target is, the wiki wins; raise a wiki PR.

CCTC-team regulated repos already have the *development* half of a GxP-defensible
SDLC: org rulesets (signed commits, branch protection), `.compliance.yml` + schema,
the `gxp-traceability` PR gate, the `regulated_feature.yml` issue template, the
Project 30/31 "Regulated Feature Lifecycle" board, the `project-enforcement` /
`project-card-promote` / `project-audit` workflows, and getval validation-doc
generation in the FAKE build.

What is missing is the *release* half — and, critically, the *existing* release-adjacent
steps are in the wrong order. The build (`~/repos/CCTC_Components/build/build.fs`) today
runs one linear FAKE chain that deploys to staging, runs functional tests, then **packs,
pushes the NuGet package to the registry, creates an *unsigned* annotated tag (`git tag
-a`), generates the validation report, and only then deploys to production**
(`build.fs:1044-1051`): it publishes and deploys **before** the validation report that is
supposed to authorise it exists, with **no authorisation gate** anywhere, and tags
mid-chain, unsigned. The target process (see the wiki) inverts this — validate → authorise
→ distribute, build-once, one durable inspectable Release.

So this plan is **not purely additive**: bolting provenance/SBOM/Release onto the current
chain would attest and "gate" an artifact that has already shipped — provenance theatre. It
therefore both adds a first-class release tier **and** inverts the existing order, which
requires **changes to each repo's existing build** (the FAKE chain for CCTC_Components),
collected in the "Required build changes" section.

Nothing here is built yet; this is the plan only.

---

## Key References

- ⚠️ **`~/repos/CCTC_Components/build/` is ONE EXAMPLE implementation, not the
  contract.** Its FAKE target *names* (`Pack`, `Tag version in git`, `Build validation
  docs`), its tool choice (FAKE/F#), and its paths (`build/config/cctc_components_config.json`,
  `output/cctc_components.html`) are repo-specific. Other regulated repos may use MSBuild,
  Cake, npm scripts, or Make, with different names and layouts. **Do not hardcode any of
  these into the reusable workflow.** Read it to understand the *fundamental* process; the
  canonical tool-agnostic target set this plan defines is in Phase 0.
- `~/repos/CCTC_Components/build/build.fs:1044-1051` — the example target chain
  (`…→ Pack → Push → Tag version in git → Build validation docs → Deploy to Production`).
  Read it as a **cautionary** example: it packs, pushes to the registry, tags (unsigned), and
  deploys to production **before** validation runs and with **no** authorisation gate — the
  exact inversion this plan removes. The hand-off boundary is **not** a build-pushed tag (the
  original draft's assumption); it is the **once-built artifact (by digest)** produced by the
  CI pipeline, which then owns push/deploy/tag post-gate (Decisions 1, 6, 13). What the build
  must change is collected in "Required build changes".
- `~/repos/CCTC_Components/build/config/cctc_components_config.json` +
  `build.fs:986` — example getval invocation producing the validation report. The
  *requirement* is "a `validation-docs` target exists and emits a report to a declared
  path"; getval/this config is one way to satisfy it.
- `.github/workflows/gxp-traceability.yml` — the canonical pattern for a reusable,
  `.compliance.yml`-gated, evaluate/active workflow with Python heredocs that never
  interpolate untrusted data. The release workflow mirrors its security posture.
- `.github/workflows/project-card-promote.yml` + `scripts/project_enforcement/` — the
  Project-board state machine. The "Released" gate lives at
  `scripts/project_enforcement/checks/preconditions/released.py` and
  `scripts/project_enforcement/evidence.py:308` (`release_for_sha`).
- `templates/compliance/gxp-traceability-caller.yml` + `README-banner.md` +
  `.compliance.yml.example` — the thin-caller + drift-delivery + system_category-gating
  pattern every regulated repo opts into.
- `~/repos/claude-org/rules/essentials/regulated-gcp-checklist.md` — ALCOA+ and ICH
  E6(R3) §4.2/§4.3 obligations the release artifacts must satisfy (Attributable,
  Contemporaneous, Enduring, Available; validation status maintained; change control
  before release; dependency vuln scanning in CI).
- `AIPlans/Complete/Project board enforcement plan.md` — the phasing/style this plan
  follows, and the existing handler/evidence/checks structure to extend.
- **[Release-Process](https://github.com/CCTC-team/.github/wiki/Release-Process)** and
  **[Release-Build-Contract](https://github.com/CCTC-team/.github/wiki/Release-Build-Contract)**
  (wiki) — the **authoritative target spec**: what the process is, the seven guarantees it
  achieves, the three-layer model + both diagrams, the canonical build-target contract, the
  mandatory ordering + build-once/digest rules, the environment model, and the per-release
  evidence set. The design decisions and process overview that used to live in this plan now
  live there; this plan references them rather than restating them.

---

## Key Design Decisions

> These are now recorded **authoritatively in the wiki** as the target design
> ([Release-Process](https://github.com/CCTC-team/.github/wiki/Release-Process),
> [Release-Build-Contract](https://github.com/CCTC-team/.github/wiki/Release-Build-Contract)).
> The crosswalk below is kept only so each phase below can cite a decision number; it maps each
> decision to where the target documents it, plus any **implementation-only** note not in the
> wiki. For the rationale, read the wiki.

| # | Decision (target) | Authoritative wiki section | Implementation-only note (stays here) |
|---|---|---|---|
| 1 | Build-once CI pipeline, not the local build; promote the same digest | RP *What this achieves* (G2); RBC *ownership* | Build MUST NOT push/deploy/tag — those move to the pipeline (see Required build changes). |
| 2 | Three orthogonal layers: board status / milestone / Release | RP *The three layers* | — |
| 3 | Milestone-scoped, custom-generated release notes | RP *three layers*; guarantee 5 | `.github/release.yml` ships for label categorisation of the auto-section (Phase 1b); custom generator in Phase 2. |
| 4 | Validation report generated in the workflow, pre-distribution | RP guarantee 1; evidence set | Workflow runs the `validation-docs` target over the released SHA (Phase 3a step 6). |
| 5 | Provenance/SBOM via GitHub Attestations (keyless, not cosign) | RP *evidence set* (provenance row) | `actions/attest-build-provenance` + `actions/attest-sbom` (Phase 3a step 5). |
| 6 | Environment required-reviewer gate = the e-signature, before any distribution | RP guarantee 3; pipeline gate | Job B runs under `environment: production` (Phase 3a/4). Resolves the old open question (prod deploy moves behind the gate). |
| 7 | Dependency vuln scan gates the release (critical/high) | RP pipeline; RBC *pipeline-native gates* | grype over the CycloneDX SBOM; `scripts/release/sbom_scan.py` (Phase 2c/3a). |
| 8 | Hardened "Released" precondition — published Release + validation asset | RP *How it fits* | Resolve tag ref to SHA (not `target_commitish` string match); require validation asset (Phase 5). |
| 9 | Reusable workflow + thin caller + drift, `system_category`-gated | RP *Who this applies to*; *How it fits* | Delivery wiring in Phase 6. |
| 10 | Long-term retention documented, not assumed (GitHub ≠ archive) | RP retention para; *What this is not* | Archive export tracked in Open follow-ups. |
| 11 | Contract = logical, tool-agnostic targets owned by `claude-org` | RBC *Why a contract* + target table | The normative copy is the `claude-org` guide (Phase 0a), mirroring the wiki. |
| 12 | Build↔workflow binding is a per-repo manifest | RBC *Per-repo binding* | Schema in Phase 0b; example in Phase 0c. |
| 13 | Ordering + digest-pinning are contractual | RBC *Mandatory ordering and build-once/digest* | `contract.py` flags a distribution target marked `owner: build` (Phase 0d). |
| 14 | One qualified, pipeline-controlled RC/PQ environment | RP environment bullet; RBC *The environment model* | Capability separation = RC/prod creds only on the pipeline runner (Required build changes). |

The full former text of each decision is preserved in git history (this file before this
revision) if the rationale is ever needed outside the wiki.

---

## Phase 0: Define the canonical build-target contract (claude-org guidance + manifest)

The foundation. Until the contract exists, the release workflow has nothing tool-agnostic
to bind to. This phase produces the *specification* (in `claude-org`), the *binding schema*
(in `.github`), and a *checker* — no release behaviour yet.

- [ ] **0a. NEW (separate PR to the org repo):** `~/repos/claude-org/rules/guides/build-and-release.md`
  - The canonical, tool-agnostic build-target contract. **This guide is the normative copy
    in `claude-org`; its content is specified by the wiki
    [Release-Build-Contract](https://github.com/CCTC-team/.github/wiki/Release-Build-Contract)
    — reproduce it there (the canonical target table + scopes, the cross-cutting target
    properties, the pipeline-native gates, the mandatory ordering + build-once/digest rules,
    and the three-role environment model), do not re-invent it.** Add the CCTC_Components FAKE
    chain as **one worked example** mapping its target names to the canonical set, labelled
    "example, not normative", and show its required *re-ordering* against its current chain.
  - Register it in `claude-org`'s rules index (the Tier-2 guides table in
    `rules/general.md`) and cross-link from `essentials/regulated-gcp-checklist.md` and from
    the wiki contract page.

- [ ] **0b. NEW:** `.github/release-targets.schema.json`
  - JSON Schema (sibling to `compliance.schema.json`) for the per-repo manifest: a `targets`
    map keyed by the canonical target names, each with `run` (command string) and optional
    `outputs` (array of globs); a top-level `version_pin_env` (the env var the build honours
    to pin the version, e.g. CCTC_Components' `CCTC_PIN_VERSION`); informational `build_tool`.
    Mandatory-target presence is enforced by 0d, not the schema (it depends on
    `system_category`).

- [ ] **0c. NEW:** `templates/compliance/release-targets.yml.example`
  - A worked manifest **for CCTC_Components as the example**, every value commented as
    repo-specific and TODO-flagged, so a new repo owner adapts rather than copies. Drift
    stubs this into regulated repos as `.github/release-targets.yml` (wired in Phase 6).

- [ ] **0d. NEW:** `scripts/release/contract.py` (+ tests `tests/test_contract.py`, TDD)
  - Pure function: given a parsed manifest + the repo's `system_category`, return the list of
    missing mandatory targets and any declared target not in the canonical set. Used by the
    release workflow (fail fast) and by `compliance-check` (Phase 6) so a regulated repo that
    omits `validation-docs`/`sbom`, or never declares `tag`/`lint`/`rollback`, is flagged.
    **`migrate` is conditionally mandatory** — required only for stateful repos, declared by a
    manifest flag (e.g. `stateful: true`); the exact gating predicate is a refine-later detail,
    so for now treat `migrate` as required when the flag is set and optional otherwise. Tests
    cover: all mandatory present → ok; regulated repo missing `sbom` → flagged; repo missing
    `lint`/`rollback` → flagged; stateful repo missing `migrate` → flagged; stateless repo
    without `migrate` → ok; unknown target name → flagged; non-regulated repo without
    `validation-docs` → ok.

- [ ] **0e. MODIFY:** `compliance.schema.json`
  - Add an optional `release_targets_path` (default `.github/release-targets.yml`) so the
    manifest location is discoverable and overridable, consistent with how `validated_paths`
    etc. are declared.

---

## Phase 1: Milestone convention + release-notes config (docs, non-enforcing)

- [ ] **1a. NEW:** `docs/release-process.md`
  - A **thin in-repo entry point**, not a restatement: the authoritative target (the
    three-layer model, both diagrams, the end-to-end flow, the environment model + where PQ
    happens, and the per-release evidence set) is the wiki
    [Release-Process](https://github.com/CCTC-team/.github/wiki/Release-Process) /
    [Release-Build-Contract](https://github.com/CCTC-team/.github/wiki/Release-Build-Contract).
    This doc links those and adds only **repo-specific operational** detail not in the wiki:
    how a release manager triggers the workflow in this org, the `.github/release.yml`
    categorisation, and anything CCTC-operational. Do not duplicate the diagrams/tables — link
    them (mirror the existing `docs/` convention of pointing at the wiki for narrative).

- [ ] **1b. NEW:** `templates/compliance/release.yml`
  - Ships into regulated repos as `.github/release.yml` (auto-generated notes
    categorisation). Categories keyed off existing labels: `regulated`/`validation` →
    "Validated requirements", `bug` → "Fixes", `security` → "Security", catch-all →
    "Other". `exclude` the bot/automation labels.
  - Header comment noting the custom milestone-scoped generator (Phase 2) produces the
    authoritative notes; this config only shapes the auto-section.

- [ ] **1c. MODIFY:** `templates/compliance/CONTRIBUTING-regulated.md`
  - Add a "Releases & milestones" section: assign your issue to the target milestone;
    what a Release means; that a release cannot publish without a green validation report.

- [ ] **1d. MODIFY:** `README.md`
  - New "## Release process" section summarising the three layers, linking
    `docs/release-process.md`, and adding a row set to the rollout log table for the
    release workflow + hardened Released gate (filled in Phase 8).

---

## Phase 2: Milestone-scoped release-notes + traceability generator (TDD)

Pure-Python unit, highest design value — write tests first (paired sub-items).

- [ ] **2a. NEW (Tests):** `scripts/release/tests/test_notes.py`
  - Given a fixture set of milestone issues/PRs (closed, with `Risk ID:` /
    `Requirement ID:` / `Feature link:` bodies, labels, PQ/QA approver fields), assert:
    categorised changelog grouped by label; a traceability table with one row per
    requirement (issue # → Risk ID → Requirement ID → `.feature` URL(s) → PQ approver/date
    → QA approver/date); missing-field rows flagged `_missing_`; non-regulated issues
    listed but not in the traceability matrix; deterministic ordering.
  - Reuse the body-parsing regexes proven in `gxp-traceability.yml`
    (`^[#\s>*-]*risk\s*id\s*:`) so behaviour matches the PR gate.

- [ ] **2b. NEW (Implementation):** `scripts/release/__init__.py`, `scripts/release/notes.py`
  - `build_notes(repo, milestone, tag, prev_tag, evidence) -> str`. Queries milestone
    issues/PRs via `gh api`/GraphQL, parses bodies, emits markdown: summary line, auto
    changelog (label categories), then `## Traceability matrix` table, then a
    `## Release authorisation` placeholder block filled by the workflow (approver identities
    from the environment approval).
  - Follow the security posture of `gxp-traceability.yml`: untrusted issue bodies are read
    from files / passed as data, never interpolated into shell or Python source.

- [ ] **2c. NEW:** `scripts/release/sbom_scan.py`
  - Thin wrapper: parse grype JSON, return non-zero count of critical/high, format a
    markdown summary for the step summary. Pure function over the scanner's JSON so it is
    unit-testable; the scanner invocation itself lives in the workflow.

- [ ] **2d. NEW (Tests):** `scripts/release/tests/test_sbom_scan.py`
  - Fixtures for clean / high / critical grype output; assert counts + summary text.

---

## Phase 3: Reusable release workflow

- [ ] **3a. NEW:** `.github/workflows/release.yml` (reusable, `on: workflow_call`)
  - **Trigger / hand-off boundary (changed from the original draft):** because the build no
    longer creates the release tag or self-distributes (Decision 1), the pipeline is **not**
    triggered by a build-pushed `v*` tag. The caller (3b) triggers it on `workflow_dispatch`
    (release manager picks the milestone) and/or a push to `release/*`. The pipeline **creates
    the signed tag itself, post-gate** (Job B). *Why:* build-once requires the pipeline to be
    the builder; a tag pushed by a local build that already packed/pushed/deployed is exactly
    the inverted flow being removed.
  - **Inputs:** `compliance_path` (default `.compliance.yml`), `ref` (commit/branch to
    release, default the default branch), `milestone` (required — the release scope),
    `version` (optional; else computed by the `version` target), `enforcement`
    (`evaluate`|`active`, default `evaluate` — controls vuln gate + publish-vs-draft + whether
    distribution actually runs), `environment` (default `production`, Phase 4).
    **No build-tool, path, or command inputs** — those come from the manifest (Decision 12),
    so the workflow is identical across repos regardless of build tool.
  - **Permissions:** `contents: write`, `id-token: write`, `attestations: write`,
    `packages: write` (the pipeline now pushes), `issues: read`, `pull-requests: read`.
  - **Gate + contract-check first** (mirror `gxp-traceability.yml` steps 1–2): if no
    `.compliance.yml` or `system_category == none`, exit success. Otherwise load
    `.github/release-targets.yml` (path from `release_targets_path`) and run
    `scripts/release/contract.py` — **fail fast** if a mandatory target is missing/undeclared
    **or a distribution target is marked `owner: build`** (the self-distribution check). This
    is where a repo whose build doesn't meet the contract is caught.
  - **Two jobs split by the authorisation gate.** Job A (`build-validate`) runs everything up
    to and including staging validation; Job B (`distribute`) runs under
    `environment: ${{ inputs.environment }}` so the required-reviewer approval is recorded
    **before** any distribution. Every build action is `manifest.targets.<name>.run`, never a
    hardcoded command; every artifact is collected from `manifest.targets.<name>.outputs`.
  - **Job A — build, validate, scan, stage (pre-gate):**
    1. `actions/checkout@v6` at `ref`, `fetch-depth: 0`. Compute `version` (the `version`
       target, or the input) and export it via the manifest's `version_pin_env` so every
       downstream target stamps the **one** released version.
    2. Run `build` **once**, then `lint` and `test` (both fail-closed), then `pack`/`publish`
       (which repackage the once-built output — the contract forbids a recompile). Collect the
       deployable artifact(s) from declared `outputs`; **record each artifact's SHA-256 digest**
       as the promotion identity.
       *This single build is what is deployed, pushed, and attested (Decisions 1, 13).*
    3. Run `sbom` over the built artifact (or fall back to a generic CycloneDX step) →
       collect from declared `outputs`.
    4. Vulnerability scan the SBOM (grype) → `scripts/release/sbom_scan.py`; `active` =
       **fail before any distribution** on critical/high, `evaluate` = `::warning::` +
       continue. Run `license-scan` over the same SBOM (disallowed-licence policy), same
       evaluate/active semantics.
    5. `actions/attest-build-provenance` + `actions/attest-sbom` **over the recorded digest**
       — the attestation now covers the exact artifact that will ship.
    6. Run `validation-docs` over the released commit/built artifact; collect the report.
       **Fail if the target fails or the report is empty** — no validation evidence, no
       release. (CCTC_Components satisfies this with getval; the workflow neither knows nor
       cares.) Note this runs **before** any distribution (the inversion fix).
    7. `deploy:staging` of the recorded artifact (applying `migrate` forward as part of the
       deploy) → `verify:staging` → `functional-tests`. A failure here stops the release before
       the gate. (Targets the build *provides*; the pipeline *invokes* them — they no longer
       live in a standalone build chain.)
    8. Upload artifact(s) + digest + SBOM + validation report + notes inputs to the job's
       artifact store for Job B (so Job B distributes the *same* bytes, never a rebuild).
  - **Job B — authorise, then distribute (post-gate, `environment: production`):**
    9. The job pauses on the Environment's required reviewers. Their approval is the
       electronic release authorisation (Decision 6) — captured: who, UTC timestamp,
       meaning "approved for release".
    10. `push` the recorded package to the registry; `deploy:production` of the **same
        digest** (applying `migrate` forward); `verify:production`. On `verify:production` (or
        any post-gate) failure, invoke `rollback` — redeploy the prior released digest and
        reverse migrations — before failing the run.
    11. Create the **signed** tag (`git tag -s v{version}`) on the released commit and push
        it; **verify the signature** before continuing (refuse to publish an unsigned tag).
    12. SHA-256 checksums over every asset → `SHA256SUMS`; build notes via
        `scripts/release/notes.py` (milestone-scoped + traceability matrix) with the
        `## Release authorisation` block filled from the approval record.
    13. Create the GitHub Release for the tag via `gh release create`, **draft in `evaluate`
        mode, published + `latest` in `active` mode**, attaching deployable(s), validation
        report, SBOM, `SHA256SUMS`, and notes. Mark prerelease for a `-rc`/`-beta` suffix.
  - Write a `$GITHUB_STEP_SUMMARY` table of every attached artifact + checksum + attestation
    status + the approving reviewer/timestamp (the inspector-facing manifest).

- [ ] **3b. NEW:** `templates/compliance/release-caller.yml`
  - Thin caller shipped as `.github/workflows/release.yml` in the regulated repo:
    ```yaml
    name: Release
    on:
      workflow_dispatch:
        inputs:
          milestone:
            description: 'Milestone / release scope (e.g. v1.4.0)'
            required: true
      # optional: also trigger on a protected release branch
      # push:
      #   branches: ['release/*']
    jobs:
      release:
        permissions:
          contents: write
          id-token: write
          attestations: write
          packages: write
          issues: read
          pull-requests: read
        uses: CCTC-team/.github/.github/workflows/release.yml@main
        with:
          milestone: ${{ inputs.milestone }}
          enforcement: evaluate   # flip to active after one clean cycle
          environment: production
    ```
  - The caller carries **no repo-specific paths** — all binding is in
    `.github/release-targets.yml` (Phase 0c). Header comment explains: the evaluate→active
    flip; that in `evaluate` mode Job B still runs but cuts a **draft** Release and skips the
    real registry push / prod deploy (dry-run) so the team inspects output before any version
    ships; and points at the manifest for build-tool/path configuration.

---

## Phase 4: Signed tags + production authorisation environment (docs + config)

Mostly GitHub configuration + documentation; no app code. Exception to TDD (configuration
and process, not verifiable logic).

- [ ] **4a. Contract requirement: the `tag` target produces a SIGNED tag, and the pipeline
  (not the build) creates it post-gate.** Part of the canonical contract (Phase 0a): the tag
  is `git tag -s`, not `-a`, so the released version carries the same cryptographic
  attribution the commit ruleset already requires; and it is created by the pipeline's Job B
  after the authorisation gate (Decision 13), never by the local build mid-chain. The
  pipeline verifies the signature before publishing.
  - *Required build change (see "Required build changes"):* CCTC_Components' `Tag version in
    git` (`build.fs:979`) currently uses `git tag -a` **and runs inside the FAKE chain before
    validation and prod deploy**. It must be removed from that chain; if retained at all it
    becomes a callable `tag` target the pipeline invokes (signed). The signing key is
    provisioned on the **GitHub-hosted pipeline runner**, not a developer/build box.

- [ ] **4b. NEW:** `docs/release-authorisation.md`
  - How to configure the `production` GitHub **Environment** with required reviewers (the
    PQ/QA approver group), and how that approval is the electronic release authorisation
    (Decision 6): who approved, when (UTC, contemporaneous), meaning ("approved for
    release"), enduring in the deployment log.
  - Make explicit that the Environment gates **Job B (distribute)** — the registry push,
    `deploy:production`, signed tag, and Release publish — so the approval **precedes all
    irreversible steps**. Contrast with the current FAKE chain, which deploys to production
    with no approval at all.
  - State that the approver performs their **PQ qualification review against the frozen RC
    staging deployment (Decision 14)** during the gate pause — the artifact is already live and
    is the exact build that will ship — before recording approval. Note the operational
    requirement that the RC environment stay frozen (no nightly/dev redeploys) for the duration
    of the review, and that GitHub holds the paused run on the required reviewers for up to 30
    days, bounding the review window.
  - Maps each property to ICH E6(R3) e-signature expectations from the regulated-gcp
    checklist.

- [ ] **4c. MODIFY:** `.github/workflows/release.yml`
  - Wire Job B with `environment: ${{ inputs.environment }}` (default `production`) so it
    blocks on the required reviewers before any distribution. The release notes'
    `## Release authorisation` block is filled with the approver identity + UTC timestamp
    from the deployment record. In `evaluate` mode Job B runs as a dry-run (draft Release, no
    real push/prod deploy) so the gate and output can be exercised before going live.

---

## Phase 5: Harden the "Released" board precondition (TDD)

- [ ] **5a. NEW (Tests):** extend `scripts/project_enforcement/tests/test_evidence.py`
  - For a new `published_release_for_sha`: a draft release matching the SHA → not
    satisfied; a published release matching the SHA but **without** the validation asset →
    not satisfied; a published release with the asset → satisfied (returns release meta);
    a bare tag pointing at the SHA → not satisfied (this is the regression the old method
    allowed).

- [ ] **5b. MODIFY:** `scripts/project_enforcement/evidence.py`
  - Add `published_release_for_sha(self, repo, sha) -> Optional[ReleaseMeta]` to the
    protocol (`:114`), `GhEvidence` (`:308`), and the fake (`:357`). Real impl: page
    `/repos/{repo}/releases`, require `draft == false`, resolve the release tag to the SHA
    (not just `target_commitish` string match — resolve via the tag ref), and inspect
    `assets[].name` for the validation-report pattern (e.g. `*validation*.html` / a
    configured name). Keep the old `release_for_sha` or replace its only caller.

- [ ] **5c. MODIFY:** `scripts/project_enforcement/checks/preconditions/released.py`
  - Replace the `release_for_sha` call with `published_release_for_sha`. Emit precise
    reasons: "no published Release references merge SHA", or "Release `vX.Y.Z` references
    the SHA but has no validation report attached — the release workflow must run in active
    mode and succeed." Optionally also require a provenance attestation (behind a config
    flag, default off until the workflow is active everywhere).

- [ ] **5d. MODIFY:** `scripts/project_enforcement/checks/preconditions/__init__.py` /
  handler wiring if the new evidence method needs registering. Run the existing
  `test_handler_smoke.py` to confirm no signature drift.

---

## Phase 6: Ship via compliance-drift + ruleset confirmation

- [ ] **6a. MODIFY:** the compliance-drift stubbing (`scripts/` drift code +
  `.github/workflows/compliance-drift.yml`)
  - Add to the set drift stubs into regulated repos (same mechanism as the gxp-traceability
    caller; idempotent; only when absent):
    `templates/compliance/release.yml` → `.github/release.yml`,
    `templates/compliance/release-caller.yml` → `.github/workflows/release.yml`, and
    `templates/compliance/release-targets.yml.example` → `.github/release-targets.yml`
    (TODO-flagged so the owner fills in their build-tool commands/paths).

- [ ] **6b. MODIFY:** `.github/workflows/compliance-check.yml` (contract enforcement)
  - For regulated repos, load `.github/release-targets.yml` and run
    `scripts/release/contract.py` (Phase 0d): a regulated repo missing a mandatory target
    (no `tag`, no `validation-docs`, no `sbom`, …) is flagged. evaluate→active like the
    other checks. *Why here:* this is what makes "the contract" real — a repo can't quietly
    ship without meeting the defined target set; it's caught on every PR, not only at release.

- [ ] **6c. MODIFY:** `rulesets/cctc-critical-trial.json` (confirm, amend only if needed)
  - Verify `refs/heads/release/*` (`:11`) inherits the same `pull_request` review +
    `required_signatures` + `non_fast_forward`/`deletion` rules as `main`. If the rules
    array doesn't already apply to the release branch include, document the gap; do not
    silently widen scope.
  - Add (or document adding) a **tag ruleset** protecting `refs/tags/v*` against deletion
    and non-fast-forward so a published version tag is immutable — the inspection-resilience
    payoff (a release tag can never be moved or re-pointed).

- [ ] **6d. MODIFY:** `docs/release-process.md`
  - Cross-link the ruleset guarantees (immutable tags, protected release branches) and the
    drift-delivered files so a new regulated repo's owner knows what arrives automatically
    (`release.yml`, the caller, the manifest stub) vs what they must do themselves (fill in
    `.github/release-targets.yml` for their build tool, configure the `production`
    environment).

---

## Phase 7: Evaluate → active rollout

- [ ] **7a. MODIFY:** `.github/project-enforcement.yml`
  - Leave `preconditions: Released: evaluate` until the release workflow has cut at least
    one real published Release with all artifacts green (the existing README note already
    couples Released to the release machinery). Document the dependency inline.

- [ ] **7b. MODIFY:** `README.md` rollout log table (`:582`)
  - Add rows: `release workflow (publish)`, `release workflow (vuln gate)`,
    `preconditions: Released (hardened)` — all `_pending_`, with the "flip after one clean
    evaluate cycle" note. The release caller ships with `enforcement: evaluate` (draft
    releases, warn-only vuln gate); flip to `active` per repo after a clean cycle and record
    the date here.

- [ ] **7c. MODIFY:** `docs/release-process.md`
  - Final "rollout" subsection: evaluate mode cuts a **draft** Release with all artifacts so
    the team can inspect the full output before any version is published; active mode
    publishes and enforces the vuln gate + the production-environment approval.

---

## Required build changes (per-repo; CCTC_Components FAKE as the worked example)

This plan is **not purely additive**. Each regulated repo's build must change so the release
pipeline (not the build) owns distribution and the build-once/order rules hold. The `.github`
repo only *documents and enforces* these; each product repo lands them as its own PR. Listed
against CCTC_Components' `build.fs` as the concrete example — the same shape applies to any
build tool.

- [ ] **Remove distribution from the end-to-end FAKE chain.** Drop `Pack` /
  `Push CCTC_Components package` / `Tag version in git` / `Deploy to Production` (and the prod
  Cloudflare-purge + `Verify production boot`) from the linear `==>` chain
  (`build.fs:1044-1051`). These become **pipeline-owned, post-gate** steps. The standalone
  FAKE chain may still build/test/deploy-to-a-*dev*-environment/functional-test for dev use, but
  it is **not a release path** and must not reach the RC/PQ environment, production, or the
  registry (next bullet).
- [ ] **The dev chain must not deploy to the RC/PQ environment; enforce by capability, not
  policy (Decision 14).** Any dev-convenience `deploy:staging` in the standalone chain targets a
  *dev/integration* environment, never the qualified RC environment the PQ assessor reviews. The
  enforcement is **separation by credential**: the RC (and production) deploy secrets/targets
  exist **only on the GitHub-hosted pipeline runner** (scoped to the release Environments), so a
  developer or nightly build *cannot* reach the RC environment even by mistake — there is no
  manual "remember to freeze it" step to fail. For CCTC_Components: `deployVersionedBuild`'s
  RC/production endpoints and their credentials move to the pipeline runner; the local chain
  keeps only a dev-environment target (or none).
- [ ] **Fix the order so nothing distributes before validation.** Today `Build validation
  docs` (`build.fs:986`) runs *after* `Push` and `Tag`. Under the contract, `validation-docs`
  (and `sbom`, vuln scan) run **before** any push/deploy/tag — enforced by the pipeline's
  fixed step order, but the build's targets must be individually invocable so the pipeline can
  sequence them.
- [ ] **Make targets callable + idempotent + externally version-pinnable.** Each canonical
  target must be invocable on its own (FAKE already supports `-t <target>`), re-run-safe, and
  honour an **external version pin** via env (`version_pin_env`, e.g. `CCTC_PIN_VERSION`).
  Today the version comes from a `--nextVer` arg computed mid-chain (`build.fs:938,958,979`);
  it must instead accept the pipeline-supplied version so build/pack/push/deploy all stamp the
  **one** released version.
- [ ] **Build once; pack/push/deploy consume that artifact.** `Pack` already uses
  `NoBuild = true` (`build.fs:938`) — good; keep that contract (no recompile in `pack`).
  `deployVersionedBuild` (staging *and* production) and `Push` must deploy/push the artifact
  the pipeline built and recorded by digest, not rebuild.
- [ ] **Expose a `lint` / static-analysis target.** Provide a callable, fail-closed `lint`
  (e.g. `dotnet format --verify-no-changes` + the project's analyzers/linters); today the FAKE
  chain has no standalone static-analysis gate distinct from `test`.
- [ ] **Expose `migrate` for the datastores, with declared reversibility.** CCTC_Components is
  stateful (SQL Server via EF Core, Neo4j). Provide a callable `migrate` that applies forward
  schema/data migrations as part of `deploy:*` and declares how each is reversed; mark the repo
  `stateful: true` in the manifest so `contract.py` requires `migrate`. The pipeline runs it
  inside the deploy and pairs it with `rollback`. *(Exact migration/rollback strategy per
  datastore is a refine-later detail.)*
- [ ] **Expose `rollback` (backout).** Provide a callable `rollback` that redeploys the prior
  released digest (immutable, attested) and reverses migrations; the pipeline invokes it on any
  post-gate verification failure. Today there is **no** backout path — a failed prod deploy
  leaves a partially-distributed release.
- [ ] **Sign the tag, on the pipeline runner.** `git tag -a` → `git tag -s`
  (`build.fs:979`); provision the signing key on the **GitHub-hosted pipeline runner** (the
  pipeline creates the tag post-gate), not a developer/build box.
- [ ] **Acknowledge smoke-vs-functional.** `Pause 30 seconds` + `Verify * boot`
  (`build.fs:650,683,701`) are liveness smoke checks, not release gates; the functional suite
  and the e-signature gate are the controls. No code change required — documented so the crude
  pause isn't mistaken for verification.
- [ ] **Author the manifest.** Map every FAKE target to the canonical set in
  `.github/release-targets.yml` (from the Phase 0c example), `version_pin_env: CCTC_PIN_VERSION`,
  `stateful: true`, marking `push`/`deploy:production`/`tag`/`migrate`/`rollback` as
  `owner: pipeline`.

---

## Verification

- [ ] The build-target contract guide exists in `claude-org`, is registered in the rules
  index, and lists every canonical target with scope (all vs regulated) **and the mandatory
  ordering + build-once/digest-promotion rules**. The CCTC_Components mapping is labelled
  "example, not normative" and shows the required re-ordering.
- [ ] `contract.py` correctly accepts a complete manifest and flags a regulated manifest
  missing `validation-docs`/`sbom`/`tag`/`lint`/`rollback`, a `stateful: true` manifest missing
  `migrate`, any unknown target name, a missing `version_pin_env`, and any distribution target
  (`push`/`deploy:production`/`tag`) marked `owner: build` (the self-distribution regression).
- [ ] **Backout proof:** a run seeded with a failing `verify:production` (post-gate) invokes
  `rollback` — the prior released digest is redeployed and migrations reversed — and the run
  ends failed without leaving the new version live or published.
- [ ] **Tool-agnostic proof:** the reusable `release.yml` contains no repo-specific path,
  filename, or build command (no `getval`, no `build/config/...`, no `*.nupkg` literal) —
  every build action reads from `.github/release-targets.yml`. Grep confirms this.
- [ ] A second, deliberately *different* manifest (e.g. an MSBuild/`dotnet`-only invocation
  with no FAKE) drives the same workflow to a successful dry-run release — proving the
  contract, not the example, is what the workflow binds to.
- [ ] All workflow YAML lints clean (`actionlint`); the reusable `release.yml` parses and
  its `workflow_call` inputs resolve from `release-caller.yml`.
- [ ] `scripts/release/` and `scripts/project_enforcement/` unit tests pass
  (`python -m pytest`), including the contract checker, notes-generator, sbom-scan, and
  `published_release_for_sha` regression tests.
- [ ] End-to-end dry run on the **test** project/repo (Project 31): `workflow_dispatch` with
  a test milestone → release workflow in `evaluate` builds once, runs validation+SBOM+scan
  pre-gate, and cuts a **draft** Release with notes + traceability matrix + validation report
  + SBOM + provenance attestation + `SHA256SUMS` attached, **without** a real registry push or
  prod deploy; step-summary manifest is complete.
- [ ] **Build-once / digest proof:** the artifact deployed to staging, the artifact pushed to
  the registry, the artifact deployed to production, and the artifact the attestation covers
  all carry the **same SHA-256 digest** — confirming a single build is promoted, not rebuilt
  per step.
- [ ] **Order proof:** in a run seeded with a failing validation report (or a critical vuln in
  `active`), the pipeline fails **before** any push/deploy/tag — no artifact reaches the
  registry or production.
- [ ] **RC isolation proof (Decision 14):** the standalone dev/build chain has no credentials or
  target for the RC/PQ environment — a dev-run `deploy` cannot reach it (capability separation),
  and only the pipeline (via the release Environment) can deploy the RC the assessor reviews.
- [ ] `gh attestation verify` succeeds against the produced artifact + SBOM, and the verified
  artifact digest matches the one distributed.
- [ ] Hardened `released` gate: a card whose issue's PR merged and a **bare tag** exists is
  **not** advanced to Released (regression); the same card after a published Release with
  the validation asset **is** allowed.
- [ ] Vulnerability gate: a seeded critical advisory fails the release in `active` mode and
  only warns in `evaluate`.
- [ ] Production-environment approval blocks **Job B (registry push, prod deploy, tag,
  publish)** until a required reviewer approves — i.e. the approval precedes all distribution,
  not just the `latest` flag — and the approver + UTC timestamp land in the Release's
  authorisation block.
- [ ] `compliance-drift` dry run shows `.github/release.yml` + the release caller being
  stubbed into a regulated repo and nothing into a `system_category: none` repo.
- [ ] Tag ruleset confirmed: a published `v*` tag cannot be deleted or moved.
- [ ] Signed-tag check: the release workflow verifies the `v*` tag is GPG/SSH-signed and
  refuses to publish an unsigned tag.

---

## Open operational follow-ups (not in scope, tracked separately)

- 25-year **enduring/available** archive: export released artifacts (validation report,
  SBOM, provenance) to the CTU QMS/long-term archive of record. GitHub is the working
  store, not the archive (Decision 10).
- Signed-tag key custody on the **pipeline runner** (Phase 4a) — provisioning the signing
  key for the GitHub-hosted runner that now creates the tag; raise per-repo.
- **RC/production environment provisioning (Decision 14):** stand up a qualified, production-
  equivalent RC/PQ environment and scope its deploy credentials (and production's) to the
  release Environments on the pipeline runner only — so capability separation, not policy,
  keeps dev/nightly builds out. Per-repo infra task; includes confirming the dev chain's
  staging target points elsewhere (or is removed).
- Per-repo migration effort to land the "Required build changes" (removing distribution from
  the FAKE chain, making targets pin-able/idempotent) — tracked as a build PR in each product
  repo, sequenced after the contract + workflow exist here.
- *(Resolved, no longer open)* Whether the production deploy moves behind the Environment gate
  — it does (Decision 6); the build no longer deploys to production.
