# GCP/MHRA Inspection-Resilient Release Process Implementation Plan

## Context

CCTC-team regulated repos already have the *development* half of a GxP-defensible
SDLC: org rulesets (signed commits, branch protection), `.compliance.yml` + schema,
the `gxp-traceability` PR gate, the `regulated_feature.yml` issue template, the
Project 30/31 "Regulated Feature Lifecycle" board, the `project-enforcement` /
`project-card-promote` / `project-audit` workflows, and getval validation-doc
generation in the FAKE build.

What is missing is the *release* half. The build (`~/repos/CCTC_Components/build/build.fs`)
publishes a NuGet package, pushes an **annotated git tag** `v{ver}` on the merge SHA,
generates a validation report via getval, and deploys — but it never cuts a **GitHub
Release**. A git tag is a bare pointer; a Release is the durable, immutable, inspectable
record that *this exact version was validated and released*, with evidence attached. An
MHRA inspector's "show me what you released and the evidence it was validated" should be
answered by one Release page, not by SSH into a server.

This plan adds a first-class release tier that adopts the full best-practice set:
GitHub Release creation keyed off the version tag, milestone-scoped release notes +
traceability matrix, validation summary report attachment, SBOM, SLSA build-provenance
attestation, checksums/signatures, dependency vulnerability gating, an
electronic-signature-grade production authorisation gate, a hardened "Released" board
precondition, `release/*` + tag ruleset confirmation, and the established
evaluate→active rollout — all delivered as a reusable workflow + thin caller, gated by
`.compliance.yml`, exactly like the existing compliance machinery.

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
- `~/repos/CCTC_Components/build/build.fs:1018` — the example target chain
  (`…→ Pack → Push → Tag version in git → Build validation docs → Deploy to Production`),
  showing one concrete realisation of the canonical targets. The hand-off boundary for the
  release workflow is the **signed version tag** the build pushes — that boundary is
  contractual; how the build reaches it is not.
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

---

## Key Design Decisions

1. **Release is a tag-triggered reusable workflow in CI, not a build-script target.**
   Each repo's build keeps creating and pushing the signed `v{ver}` tag; the **tag push is
   the hand-off boundary**. A reusable `release.yml` runs `on: push: tags: ['v*']` on a
   hardened GitHub-hosted runner. *Why:* SLSA build provenance is only trustworthy when the
   attestation is minted by a hardened runner with OIDC identity — a statement generated on
   a developer laptop proves nothing. Folding releases into whatever local build tool a repo
   uses would forfeit the provenance guarantee. Keeping each repo's deploy pipeline untouched
   also limits blast radius. The workflow invokes the build's *contractual* targets
   (Decision 11) by reading a per-repo manifest, never by hardcoded command or path.

2. **Three orthogonal layers: Project board = lifecycle, Milestone = release scope,
   Release = publication.** A regulated issue carries a board *status* (Risk linked →
   … → Released) **and** a *milestone* (e.g. `v1.4.0`) — these are independent. One
   milestone = one release version = one defined requirement set. *Why:* "release 1.4.0
   validated REQ-024, REQ-031, REQ-040" is defensible; a stream of per-commit micro-tags
   is not. Milestone-batched releases are the GxP-friendly model.

3. **Release notes are milestone-scoped and custom-generated, not GitHub's default.**
   GitHub's `generate_release_notes` builds notes from PRs since the last tag; we instead
   query the **milestone's** closed issues/PRs and emit a categorised changelog *plus* a
   traceability appendix (issue → Risk ID → Requirement ID → `.feature` evidence → PQ/QA
   approver + signoff date). `.github/release.yml` still ships for label categorisation
   of the auto-section. *Why:* GxP needs requirement-set scoping and an inspector-facing
   traceability matrix, not a flat PR list.

4. **The validation summary report is regenerated *in the release workflow* by invoking
   the repo's `validation-docs` target, as the authoritative attached copy.** Rather than
   trusting whatever file a local build left behind, the release job runs the contractual
   `validation-docs` target (CCTC_Components happens to satisfy it with getval; another repo
   may use a different generator) against the tagged commit, then attaches the report from
   the path the manifest declares. *Why:* single source of truth, attributable to the exact
   released SHA — ALCOA+ Attributable + Original — and tool-agnostic.

5. **Provenance and SBOM use GitHub Attestations (sigstore-backed), not self-managed
   cosign keys.** `actions/attest-build-provenance` + `actions/attest-sbom` mint keyless,
   OIDC-bound, transparency-logged attestations verifiable with `gh attestation verify`.
   *Why:* no signing-key custody burden, and the attestations are independently verifiable
   by an inspector or downstream consumer. SHA-256 checksums are still attached for
   air-gapped verification.

6. **Production release/deploy sits behind a GitHub Environment with required reviewers —
   this *is* the electronic release authorisation.** A `production` Environment with
   required reviewers (the PQ/QA approver group) produces a logged, timestamped,
   attributable approval before the release is marked `latest` / the prod deploy proceeds.
   *Why:* reuses a platform primitive to satisfy ICH E6(R3) e-signature intent
   (Attributable + Contemporaneous + meaning="approved for release") instead of building a
   bespoke flow. The approval event is enduring in the deployment log.

7. **Dependency vulnerability scan gates the release.** The release job scans the generated
   SBOM (grype against the CycloneDX output) and fails on critical/high before a Release is
   published. *Why:* the GCP checklist requires "dependency vulnerability scanning in CI";
   a release is the right hard gate. Respects evaluate→active: warn-only until flipped.

8. **The "Released" board precondition is hardened to require a *published* Release.**
   Today `released.py` is satisfied by any release whose `target_commitish` matches the
   SHA *or even a bare tag pointing at it* (`evidence.py:308`). It will instead require a
   **published (non-draft)** Release referencing the merge SHA **with the validation-report
   asset attached**. *Why:* closes the gap where a tag alone — the thing the build already
   makes — falsely satisfies the strongest gate on the board.

9. **Delivery is reusable-workflow + thin-caller + compliance-drift, gated by
   `system_category`.** Identical to `gxp-traceability` and `project-card-promote`, so
   adoption across regulated repos is uniform and opt-in, and non-regulated repos are
   untouched. Rollout follows the same per-check evaluate→active log in the README.

10. **Long-term retention is documented, not assumed.** GitHub release assets are durable
    but not a 25-year archive of record. The release workflow's artifacts are *also* the
    inputs to the CTU QMS/archive export; this plan documents that hand-off as an
    operational follow-up rather than implementing an external archive sink. *Why:* the
    enduring/available obligation (ICH E6(R3) §4.2.7) is a records-management process the
    CTU owns; we make the artifacts exportable and say so explicitly rather than implying
    GitHub is the archive.

11. **The release contract is a defined set of *logical* build targets, tool-agnostic and
    owned by `claude-org`.** CCTC_Components' FAKE targets are one *implementation*; the
    contract names what every regulated repo's build MUST be able to do, not how. The
    canonical set (Phase 0) is `clean, restore, build, test, docs, version, publish, pack,
    push, deploy:staging, verify:staging, functional-tests, tag, deploy:production,
    verify:production` for **all** software repos, plus `validation-docs` and `sbom` as
    **additionally mandatory for regulated** (`system_category != none`) repos. Each target
    has a defined responsibility and declared outputs. *Why:* the user's point exactly — the
    example must not be hardcoded. A contract lets MSBuild/Cake/npm/Make repos all comply,
    lets the release workflow be written once, and gives inspectors a uniform "every
    regulated system is built and released the same way" story. The spec lives in
    `claude-org` (guidance, the source of truth) and is enforceable from `.github`.

12. **The build↔workflow binding is a per-repo manifest, not convention.** Each repo
    declares, in `.github/release-targets.yml`, how to invoke each contractual target (the
    command) and where its outputs land (artifact globs, validation-report path, SBOM path),
    plus the version-pin env var the build honours. The reusable workflow derives the version
    from the tag ref, reads the manifest, runs the declared target commands in CI, and
    collects the declared outputs. *Why:* zero hardcoded paths/commands in the shared
    workflow (Decision 1); a repo changing its build tool only edits its manifest; the
    manifest is itself machine-checkable against the contract (Phase 0d).

---

## Phase 0: Define the canonical build-target contract (claude-org guidance + manifest)

The foundation. Until the contract exists, the release workflow has nothing tool-agnostic
to bind to. This phase produces the *specification* (in `claude-org`), the *binding schema*
(in `.github`), and a *checker* — no release behaviour yet.

- [ ] **0a. NEW (separate PR to the org repo):** `~/repos/claude-org/rules/guides/build-and-release.md`
  - The canonical, tool-agnostic build-target contract. For each logical target: its
    responsibility, its required outputs, and whether it is mandatory for **all** repos or
    **regulated-only**. Lead with a table:

    | Target | Responsibility | Required output | Scope |
    |---|---|---|---|
    | `clean` | Remove prior build outputs; re-run-safe | — | all |
    | `restore` | Restore pinned deps from lockfile | — | all |
    | `build` | Compile in Release config | compiled assemblies | all |
    | `test` | Run automated tests; fail build on failure | test results | all |
    | `docs` | Generate API/user documentation | docs site | all |
    | `version` | Compute/stamp next version; pin-able via env | version string | all |
    | `publish` | Produce deployable artifact(s) | declared artifact path(s) | all |
    | `pack` | Package distributable (nupkg/container/zip) | declared package path(s) | all |
    | `push` | Publish package to the registry | — | all |
    | `deploy:staging` | Deploy to pre-production | — | all |
    | `verify:staging` | Automated smoke/health checks on staging | pass/fail | all |
    | `functional-tests` | E2E/functional suite (staging or deterministic sidecar) | results | all |
    | `tag` | Create a **signed**, annotated version tag on the release commit | `v{ver}` tag | all |
    | `deploy:production` | Deploy to production | — | all |
    | `verify:production` | Automated smoke/health checks on production | pass/fail | all |
    | `validation-docs` | Generate validation summary report (URS→V&V→PQ→QA traceability) | declared report path | **regulated** |
    | `sbom` | Generate CycloneDX/SPDX SBOM | declared SBOM path | **regulated** |

  - State explicitly: the build *tool* is free (FAKE, MSBuild, Cake, npm, Make, …); the
    contract is the obligation, not the implementation. Show CCTC_Components' FAKE chain as
    **one worked example** mapping its target names to the canonical set — clearly labelled
    "example, not normative".
  - Note which targets the release *workflow* re-invokes in CI for provenance (`build`,
    `pack`, `publish`, `validation-docs`, `sbom`) vs which the build runs in its own pipeline
    (`deploy:*`, `verify:*`).
  - Register it in `claude-org`'s rules index (the Tier-2 guides table in
    `rules/general.md`) and cross-link from `essentials/regulated-gcp-checklist.md`.

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
    omits `validation-docs`/`sbom`, or never declares `tag`, is flagged. Tests cover: all
    mandatory present → ok; regulated repo missing `sbom` → flagged; unknown target name →
    flagged; non-regulated repo without `validation-docs` → ok.

- [ ] **0e. MODIFY:** `compliance.schema.json`
  - Add an optional `release_targets_path` (default `.github/release-targets.yml`) so the
    manifest location is discoverable and overridable, consistent with how `validated_paths`
    etc. are declared.

---

## Phase 1: Milestone convention + release-notes config (docs, non-enforcing)

- [ ] **1a. NEW:** `docs/release-process.md`
  - The three-layer model (Decision 2) with a diagram: Project board status vs Milestone
    vs Release.
  - The end-to-end flow: create milestone `vX.Y.Z` → assign regulated issues at triage →
    work through board columns → all milestone issues `QA approved` + merged → build pushes
    signed tag → release workflow cuts the published Release → production environment
    approval → `latest`.
  - The artifact set attached to every regulated Release and the ICH E6(R3)/ALCOA+ clause
    each one answers (validation report, traceability matrix, SBOM, provenance, checksums,
    authorisation record). Inspector-facing "where is X" table.
  - The milestone naming/versioning convention (SemVer `vMAJOR.MINOR.PATCH`, one milestone
    per release, milestone closed on publish).

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
  - **Inputs:** `compliance_path` (default `.compliance.yml`), `tag` (the `v*` ref),
    `milestone` (default: derive from tag), `enforcement` (`evaluate`|`active`, default
    `evaluate` — controls vuln gate + publish-vs-draft), `environment` (optional, Phase 4).
    **No build-tool, path, or command inputs** — those come from the manifest (Decision 12),
    so the workflow is identical across repos regardless of build tool.
  - **Permissions:** `contents: write`, `id-token: write`, `attestations: write`,
    `packages: read`, `issues: read`, `pull-requests: read`.
  - **Gate + contract-check first** (mirror `gxp-traceability.yml` steps 1–2): if no
    `.compliance.yml` or `system_category == none`, exit success. Otherwise load
    `.github/release-targets.yml` (path from `release_targets_path`) and run
    `scripts/release/contract.py` — **fail fast** if a mandatory target for this
    `system_category` is missing or undeclared. This is where a repo whose build doesn't meet
    the contract is caught.
  - **Steps (in order) — every build action is `manifest.targets.<name>.run`, never a
    hardcoded command; every artifact is collected from `manifest.targets.<name>.outputs`:**
    1. `actions/checkout@v6` at the tag ref, `fetch-depth: 0`. Derive `version` from the tag
       (`v1.4.0` → `1.4.0`) and export it via the manifest's `version_pin_env` so the build
       targets stamp the exact released version.
    2. Run the `build` then `pack`/`publish` targets via their manifest `run` commands;
       collect the deployable artifact(s) from their declared `outputs` globs. *Note:*
       building here (in the hardened runner) is what the provenance attests (Decision 1).
    3. Run the `sbom` target (or, if a repo legitimately can't, fall back to a generic
       CycloneDX step) → collect from declared `outputs`.
    4. Vulnerability scan the SBOM (grype) → `scripts/release/sbom_scan.py`; `active` =
       fail on critical/high, `evaluate` = `::warning::` + continue.
    5. `actions/attest-build-provenance` over the collected artifacts; `actions/attest-sbom`
       over the SBOM.
    6. Run the `validation-docs` target via its manifest `run` command; collect the report
       from its declared `outputs` path. Fail the release if the target fails or the report
       is empty — a release with no validation evidence must not publish. (For CCTC_Components
       this happens to invoke getval; the workflow neither knows nor cares.)
    7. SHA-256 checksums over every collected asset → `SHA256SUMS`.
    8. Build notes via `scripts/release/notes.py` (milestone-scoped + traceability matrix).
    9. Create the GitHub Release for the tag via `gh release create`, **draft in `evaluate`
       mode, published in `active` mode**, attaching all collected artifacts: deployable(s),
       validation report, SBOM, `SHA256SUMS`, and the generated notes. Mark prerelease for
       a `-rc`/`-beta` tag suffix, else `latest` on publish.
  - Write a `$GITHUB_STEP_SUMMARY` table of every attached artifact + checksum + attestation
    status (the inspector-facing manifest).

- [ ] **3b. NEW:** `templates/compliance/release-caller.yml`
  - Thin caller shipped as `.github/workflows/release.yml` in the regulated repo:
    ```yaml
    name: Release
    on:
      push:
        tags: ['v*']
    jobs:
      release:
        permissions:
          contents: write
          id-token: write
          attestations: write
          packages: read
          issues: read
          pull-requests: read
        uses: CCTC-team/.github/.github/workflows/release.yml@main
        with:
          enforcement: evaluate   # flip to active after one clean cycle
    ```
  - The caller carries **no repo-specific paths** — all binding is in
    `.github/release-targets.yml` (Phase 0c). Header comment explains the evaluate→active
    flip and points at the manifest for build-tool/path configuration.

---

## Phase 4: Signed tags + production authorisation environment (docs + config)

Mostly GitHub configuration + documentation; no app code. Exception to TDD (configuration
and process, not verifiable logic).

- [ ] **4a. Contract requirement: the `tag` target produces a SIGNED tag.** This is part of
  the canonical contract (Phase 0a) — every repo's `tag` target must `git tag -s`, not
  `-a`, so the released version carries the same cryptographic attribution the commit
  ruleset already requires. The release workflow verifies the tag's signature before
  publishing.
  - *Example fix (separate PR to the product repo):* CCTC_Components' `Tag version in git`
    (`build.fs:979`) currently uses `git tag -a` — change to `git tag -s` and provision the
    signing key on its build runner. This plan's repo (.github) only documents the
    requirement; each repo brings its own `tag` target into compliance.

- [ ] **4b. NEW:** `docs/release-authorisation.md`
  - How to configure a `production` GitHub **Environment** with required reviewers (the
    PQ/QA approver group), and how that approval is the electronic release authorisation
    (Decision 6): who approved, when (UTC, contemporaneous), meaning ("approved for
    release"), enduring in the deployment log.
  - The release workflow's publish/`latest` step (or the prod-deploy job) references this
    environment so the approval is mandatory and logged.
  - Maps each property to ICH E6(R3) e-signature expectations from the regulated-gcp
    checklist.

- [ ] **4c. MODIFY:** `.github/workflows/release.yml`
  - Add an optional `environment` input; when set, the publish/`latest` job runs
    `environment: ${{ inputs.environment }}` so it blocks on the required reviewers. The
    release notes' `## Release authorisation` block is filled with the approver identity +
    UTC timestamp from the deployment record.

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

## Verification

- [ ] The build-target contract guide exists in `claude-org`, is registered in the rules
  index, and lists every canonical target with scope (all vs regulated). The CCTC_Components
  mapping in it is labelled "example, not normative".
- [ ] `contract.py` correctly accepts a complete manifest and flags a regulated manifest
  missing `validation-docs`/`sbom`/`tag` and any unknown target name.
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
- [ ] End-to-end dry run on the **test** project/repo (Project 31): push a `v0.0.x-rc` tag
  → release workflow in `evaluate` cuts a **draft** Release with notes + traceability matrix
  + validation report + SBOM + provenance attestation + `SHA256SUMS` attached; step summary
  manifest is complete.
- [ ] `gh attestation verify` succeeds against the produced artifact + SBOM.
- [ ] Hardened `released` gate: a card whose issue's PR merged and a **bare tag** exists is
  **not** advanced to Released (regression); the same card after a published Release with
  the validation asset **is** allowed.
- [ ] Vulnerability gate: a seeded critical advisory fails the release in `active` mode and
  only warns in `evaluate`.
- [ ] Production-environment approval blocks publish/`latest` until a required reviewer
  approves, and the approver + UTC timestamp land in the Release's authorisation block.
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
- Signed-tag key custody on the build runner (Phase 4a) — raise as a CCTC_Components PR.
- Decide per-repo whether the production deploy itself (currently in FAKE `Deploy to
  Production`) should move behind the same GitHub Environment gate, or remain build-driven
  with the environment gating only the Release publish.
