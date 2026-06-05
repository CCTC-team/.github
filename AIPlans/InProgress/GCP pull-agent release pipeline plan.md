# GCP/MHRA Pull-Agent Release Pipeline Implementation Plan

> **Superseded in part:** the GitHub **attestation** trust model below (`attest-
> build-provenance`, `gh attestation verify --signer-workflow`) was removed —
> private-repo attestations need GitHub Enterprise Cloud, which the org lacks — and
> replaced by an SSH-signed release manifest the agent verifies against
> `allowed_signers`. See `Replace attestation with signed release manifest.md` and
> `docs/release-provenance-risk-assessment.md`. The pull-agent model is otherwise
> unchanged.

## Context

CCTC-team regulated repos have the *development* half of a GxP-defensible SDLC
(org rulesets, signed commits, `.compliance.yml` + schema, the `gxp-traceability`
PR gate, the `regulated_feature.yml` template, the "Regulated Feature Lifecycle"
board, the `project-enforcement` / `project-card-promote` / `project-audit`
workflows, getval validation docs). The *release* half is missing, and what exists
today is the anti-pattern this plan replaces:

- Both `~/repos/TrialView/build/build.fs` and `~/repos/CCTC_Components/build/build.fs`
  build **Release on a developer's laptop** and **SSH/SCP straight into the
  production server**, then run `docker compose build && up -d` there
  (`Lib` `Common.BuildHelpers.Deployment.deployVersionedBuild`). CI
  (`ci.yml`) only validates a Debug build of a PR — the thing CI green-lights is
  **not** the thing that reaches production.
- There is no GitHub Release, no SBOM, no build provenance, no signed artifact,
  no electronic release authorisation, no inspector-facing "show me what you
  released and the evidence it was validated" page.

A prior plan (`AIPlans/Release process plan.md`) attempted this and was deleted on
2026-06-01 because it was **founded on stale documentation** — it predated the
`system_category`→`regulatory_tier` rename, the **CtQ schema additions** (`ctq_factors`/FRM129 +
`governing_documents`/QMS anchors, three-tier RBQM), and the board rename
"PQ review"→"User acceptance" (PQ-before-environment). Its release-engineering
*bones* were sound; its compliance hooks described a system that no longer exists.

This plan is a **fresh design anchored to current truth**, built around a
**pull-agent deploy model**: production never accepts an inbound SSH/push. CI builds
and signs a container **image**, pushes it to GHCR by immutable digest, and cuts a
published GitHub Release gated by a `production` Environment approval. An agent
**on the server** polls for that approved Release, verifies the image's keyless
attestation against a pinned workflow identity, pulls the image **by digest**, and
runs it. Delivered as a reusable workflow + thin caller gated by `.compliance.yml`,
exactly like `gxp-traceability`.

This plan spans four repos. Each file path below is prefixed with its repo when it
is **not** `CCTC-team/.github` (where this plan lives). Cross-repo work (the
`claude-org` guide, the `server-structure` agent, per-product-repo manifests and
signed-tag targets) is called out as separate PRs.

---

## Key References

- ⚠️ **`~/repos/CCTC_Components/build/build.fs` is ONE EXAMPLE, not the contract.**
  Its FAKE target *names* (`Pack`, `Push`, `Tag version in git` at `:979`,
  `Build validation docs` (getval) at `:986`, chain at `:1018`), tool choice, and
  paths are repo-specific. **Do not hardcode any into the reusable workflow.** Read
  it to understand the *fundamental* process; the canonical tool-agnostic target set
  is defined in Phase 0.
- `~/repos/Lib/src/Lib/Common.BuildHelpers.fs:341` (`deployVersionedBuild`) and
  `:400` (`checkSshConnection`) — the **current SSH-push mechanism the pull-agent
  retires.** It SCPs artifacts to `{remoteBaseBuildPath}/{env}/{project}/{timestamp}`
  and runs `docker compose build && up -d --no-deps` over SSH, passing the timestamp
  via an env var (e.g. `TRIALVIEW_BUILD_VERSION`). The agent inverts this.
- `~/repos/server-structure/trialview/docker-compose.{staging,prod}.yml`,
  `DEPLOYMENT_RUNBOOK.md`, `VERSIONED_BUILDS_GUIDE.md` — the deploy target. Compose
  files currently `build:` from on-server publish dirs; this plan moves them to
  `image:` pinned by digest. The runbook's SSH-push steps become the agent.
- `.github/workflows/gxp-traceability.yml` — **the canonical reusable,
  `.compliance.yml`-gated, evaluate/active workflow** (ubuntu-latest, Python venv
  with `pyyaml`/`pathspec`, untrusted issue/PR data never interpolated into shell).
  The release workflow mirrors its gate logic and security posture exactly.
- `compliance.schema.json` — `regulatory_tier`
  ∈ {gcp-critical, gcp-supporting, data-protection, none}; `gamp_category` ∈ {3,4,5};
  `ctq_factors[]` (`frm129_ref`, `tier` ∈ {critical, important}); `governing_documents[]`
  (`ref`, `role`), both **unconditionally** required for `gcp-critical`. The schema is a
  single initial version (`schema_version: 1`) that already includes these; the
  traceability matrix and gating read from them.
- `scripts/project_enforcement/checks/preconditions/released.py` +
  `scripts/project_enforcement/evidence.py` (`release_for_sha`, `linked_prs`,
  `default_branch`) — the board state machine. The full forward-only chain
  (`state_machine.py`) is:
  `Triage → Risk linked → Requirement defined → In development → Code review →
  V&V tests pass → User acceptance → QA approved → Released`.
  **The `Released` gate is currently satisfied by any release *or bare tag*
  referencing the merge SHA** — Phase 6 hardens it. Note the production
  release/environment gate aligns with the **`QA approved → Released`** transition
  (the last step before `Released`), so it fires after **both** `User acceptance` and
  `QA approved` — the design must respect that ordering. There is a dedicated
  `QA approved` status with its own `QA Approver` (segregation of duties enforced in
  `qa_approved.py`); do not collapse it into `User acceptance`.
- `~/repos/claude-org/rules/guides/regulated-gcp-systems.md` (Electronic Signatures
  section) — the org e-signature spec: **re-authentication at point of signing**,
  **binding a SHA-256 hash of the exact record version**, captured signer
  identity+role, explicit meaning, tamper-evident. Decision 6 reconciles a GitHub
  Environment approval against this.
- `~/repos/claude-org/rules/essentials/regulated-gcp-checklist.md` — ALCOA+ and
  ICH E6(R3) §4.3.5 (release) / §4.2 obligations the artifacts must satisfy;
  "dependency vulnerability scanning in CI"; change control before release.
- `AIPlans/Complete/Project board enforcement plan.md` and
  `AIPlans/Complete/RBQM traceability and risk-proportionality plan.md` — the
  phasing/style and the handler/evidence/checks structure Phase 6 extends.

---

## Key Design Decisions

1. **Pull, never push: production accepts no inbound connection.** The deploy is
   inverted relative to today's `deployVersionedBuild`. An agent **on the server**
   polls GitHub for a new published, approved Release for its app, verifies, pulls
   the image **by digest**, and runs `docker compose up -d --no-deps` locally. No
   laptop or runner ever SSHes into production. *Why:* it eliminates the exact
   audit-trail-destroying, QA-bypassing inbound-SSH path the GCP posture forbids;
   the server only makes **outbound** calls to GitHub/GHCR.

2. **CI builds and signs the container image; the server never builds.** The
   hardened runner builds the OCI image, attests provenance + SBOM **over that
   image**, signs it, and pushes to **GHCR by immutable digest**. The agent pulls
   *that digest*. *Why:* SLSA provenance is only trustworthy when minted by a
   hardened runner with OIDC identity over the artifact that actually runs.
   Building on the server (today's `docker compose build`) means provenance covers
   a bundle, not the running image, and re-introduces the WASM-bloat/non-determinism
   noted in TrialView plan 0012. The compose files move from `build:` to
   `image: ...@sha256:<digest>`.
   **Update (component-aware):** "the container image" is now **a set of component
   images** — a repo (e.g. TrialView: Blazor host + F# API) declares N images in the
   manifest's `images` map; the workflow builds/attests each and the Release lists all,
   deployed atomically. The single-image wording above was generalised by
   `AIPlans/InProgress/Component-aware multi-image release plan.md`; Phase 3's "image"
   steps are now per-component (matrix attest).

3. **Keyless attestation, verified on the server against a pinned identity.**
   `actions/attest-build-provenance` + `actions/attest-sbom` mint keyless,
   OIDC-bound, transparency-logged attestations. The agent verifies with
   `gh attestation verify <image>@<digest> --repo CCTC-team/<repo>
   --signer-workflow CCTC-team/.github/.github/workflows/release.yml` before pulling.
   *Why:* no signing-key custody burden; the bound workflow identity means an image
   built by anything other than the approved release workflow fails verification.
   The prod/staging servers have outbound GitHub access (confirmed), so offline
   keyed cosign is unnecessary. SHA-256 digests are the inherent content binding.

4. **Three orthogonal layers: Project board = lifecycle, Milestone = release scope,
   Release = publication.** A regulated issue carries a board *status* and a
   *milestone* (`vX.Y.Z`); one milestone = one release = one defined requirement
   set. *Why:* "release 1.4.0 validated REQ-024/031/040 covering CtQ FRM129-…" is
   defensible; per-commit micro-tags are not.

5. **Traceability is CtQ-anchored, per the compliance schema.** The release notes' traceability
   matrix threads **CtQ factor (FRM129 ref + tier) → Risk ID → Requirement ID →
   `.feature` evidence → acceptance approver → QA approver**, and lists the
   `governing_documents` (QMS SOP/GD/FRM refs) that govern the release. *Why:* the
   stale plan's matrix stopped at Risk/Requirement; the schema made CtQ→FRM129→QMS
   the spine, and an inspector traces from the CtQ factor down. Read these from the
   repo's `.compliance.yml`, never assume.

6. **The `production` GitHub Environment approval is the *gate* and the technical
   evidence; the regulatory e-signature of record is captured per the org spec —
   the approval alone is necessary but not sufficient.** A `production` Environment
   with required reviewers (the QA-approver group — the role that signs the board's
   `QA approved` status) produces a logged, timestamped,
   attributable approval **bound to the exact image digest** (the digest *is* the
   record-version hash binding ICH E6(R3) requires). *But* a GitHub Environment
   approval does **not** force re-authentication at the moment of signing — an
   active session suffices — so it does **not** by itself meet the org's
   electronic-signature spec. Therefore: the Environment approval enforces the gate
   and supplies attributable/contemporaneous/version-bound evidence; the **formal
   e-signature of record** (re-auth + meaning + hash binding) is captured either in
   the application's own signature flow or in the CTU QMS/eTMF, referencing the
   release digest. *Why:* honest mapping of a platform primitive to the regulation
   rather than pretending a reviewer click is a Part-11 signature; documented
   residual gap, not a hidden one. (This is the core correction over the deleted
   plan, which treated the Environment approval *as* the e-signature.)
   This gate aligns with the board's `QA approved → Released` transition — i.e. it
   fires after **both** `User acceptance` and `QA approved` (Decision 4 of the board
   model), preserving the PQ-before-environment ordering.

7. **The release contract is a defined set of *logical*, tool-agnostic build targets
   owned by `claude-org`.** Every regulated repo's build MUST be able to do them;
   *how* (FAKE/MSBuild/Cake/npm/Make) is free. Canonical set in Phase 0a. *Why:* the
   example must not be hardcoded; a contract lets every repo comply, lets the
   workflow be written once, and gives inspectors a uniform "every regulated system
   is built and released the same way" story.

8. **The build↔workflow binding is a per-repo manifest (`.github/release-targets.yml`),
   not convention.** Each repo declares how to invoke each contractual target and
   where its outputs land (image ref, validation-report path, SBOM path), plus the
   version-pin env var its build honours. The reusable workflow reads the manifest;
   it contains **zero** hardcoded paths/commands. *Why:* a repo changing build tool
   edits only its manifest; the manifest is machine-checkable against the contract.

9. **The agent's deploy decision is pure and unit-tested; its side effects are thin.**
   The "should I deploy, and is this image trustworthy?" logic (compare running
   digest vs latest approved Release digest; require verification success) is a pure
   function with tests. Pulling, compose-up, boot-verify, and audit-logging are thin
   shells around it. *Why:* the regulated decision boundary must be testable without
   a live server.

10. **The agent keeps an append-only on-server audit log (ALCOA on the deploy
    boundary).** Every poll-and-deploy records who/what/when/digest/verification
    result/boot result to an append-only log, and retains the previous digest for
    rollback. *Why:* the deploy event is itself GxP evidence; today it lives only in
    a developer's terminal scrollback.

11. **Delivery is reusable-workflow + thin-caller + compliance-drift, gated by
    `regulatory_tier`.** Identical to `gxp-traceability` / `project-card-promote`:
    opt-in, uniform, non-regulated repos untouched, evaluate→active rollout logged
    in the README.

12. **Long-term retention is documented, not assumed.** GitHub Releases + GHCR are
    the working store, not a 25-year archive. The release artifacts are the inputs
    to the CTU QMS/eTMF export; this plan documents that hand-off as an operational
    follow-up (Decision 10 of records management), it does not implement an external
    archive sink.

---

## Phase 0: Canonical build-target contract (claude-org guidance + binding schema + checker)

The foundation. Until the contract exists, the workflow has nothing tool-agnostic to
bind to. Produces the *specification* (claude-org), the *binding schema* (.github),
and a *checker* — no release behaviour yet.

- [x] **0a. NEW (separate PR to the org repo):** `~/repos/claude-org/rules/guides/build-and-release.md`
  - The canonical, tool-agnostic build-target contract. For each logical target: its
    responsibility, required output, and scope (**all** repos vs **regulated-only**).
    Lead with a table:

    | Target | Responsibility | Required output | Scope |
    |---|---|---|---|
    | `clean` | Remove prior outputs; re-run-safe | — | all |
    | `restore` | Restore pinned deps from lockfile | — | all |
    | `build` | Compile in Release config | compiled assemblies | all |
    | `test` | Run automated tests; fail on failure | test results | all |
    | `docs` | Generate API/user docs | docs site | all |
    | `version` | Compute/stamp version; pin-able via env | version string | all |
    | `package` | Produce the distributable — **container image** (hosted apps) or nupkg/zip | image ref **or** package path | all |
    | `publish:registry` | Push the package/image to its registry (GHCR/NuGet) | pushed ref incl. **digest** | all |
    | `deploy:staging` | Make staging run the new version | — | all |
    | `verify:staging` | Automated smoke/health checks on staging | pass/fail | all |
    | `functional-tests` | E2E/functional suite (staging or sidecar) | results | all |
    | `tag` | Create a **signed** annotated version tag on the release commit | `v{ver}` tag | all |
    | `deploy:production` | Make production run the new version | — | all |
    | `verify:production` | Automated smoke/health checks on production | pass/fail | all |
    | `validation-docs` | Generate validation summary report (CtQ→URS→V&V→PQ→QA) | declared report path | **regulated** |
    | `sbom` | Generate CycloneDX/SPDX SBOM | declared SBOM path | **regulated** |

  - State explicitly the build *tool* is free; the contract is the obligation. Map
    CCTC_Components' FAKE chain to the canonical set as **one worked example, clearly
    labelled "example, not normative"**.
  - Note which targets the **release workflow** runs in CI for provenance (`build`,
    `package`, `publish:registry`, `validation-docs`, `sbom`) vs which the **agent**
    runs on the server (`deploy:*`, `verify:*`) — this split is the heart of the
    pull model.
  - Register in the Tier-2 guides table in `~/repos/claude-org/rules/general.md`
    (the table around line 43-60) and cross-link from
    `essentials/regulated-gcp-checklist.md`.

- [x] **0b. NEW:** `release-targets.schema.json`
  - JSON Schema (sibling to `compliance.schema.json`) for the per-repo manifest: a
    `targets` map keyed by the canonical target names, each with `run` (command
    string) and optional `outputs` (array of globs); a top-level `image` block for
    hosted apps (`registry`, `repository`, the env var the build stamps the digest
    into); `version_pin_env`; informational `build_tool`. Mandatory-target presence
    is enforced by 0d (it depends on `regulatory_tier`), not the schema.

- [x] **0c. NEW:** `templates/compliance/release-targets.yml.example`
  - A worked manifest **for TrialView** (hosted Blazor+API → GHCR image), every value
    commented as repo-specific and TODO-flagged so a new owner adapts rather than
    copies. Drift stubs this into regulated repos as `.github/release-targets.yml`
    (Phase 7).

- [x] **0d. NEW (Test):** `scripts/release/tests/test_contract.py`
  - Pure-function tests for `contract.check_manifest(manifest, regulatory_tier)`:
    all-mandatory-present → ok; regulated repo missing `sbom` → flagged; regulated
    missing `validation-docs` → flagged; missing `tag` → flagged; unknown target name
    → flagged; non-regulated repo without `validation-docs` → ok. Deterministic
    ordering of returned problems.

- [x] **0e. NEW (Implementation):** `scripts/release/__init__.py`, `scripts/release/contract.py`
  - `check_manifest(manifest: dict, regulatory_tier: str) -> list[str]` returning the
    list of missing mandatory targets + any declared target not in the canonical set.
    Used by the release workflow (fail fast, Phase 3) and `compliance-check` (Phase 7).

- [x] **0f. MODIFY:** `compliance.schema.json`
  - Add an optional `release_targets_path` (default `.github/release-targets.yml`) so
    the manifest location is discoverable/overridable, consistent with how
    `validated_paths` etc. are declared. This is an additive, optional field — **no
    `schema_version` bump** (the schema is a single initial version 1; a bump is only
    for a breaking change, per the migration ritual still documented in `README.md`).

---

## Phase 1: Milestone convention + release-notes config (docs, non-enforcing)

- [x] **1a. NEW:** `docs/release-process.md`
  - The three-layer model (Decision 4) with a diagram: board status vs Milestone vs
    Release.
  - The **pull-agent** end-to-end flow: milestone `vX.Y.Z` → issues worked through
    the board to `User acceptance` → merge → build pushes signed tag → release
    workflow builds+signs the image, pushes to GHCR by digest, cuts a **draft**
    Release (evaluate) or gated **published** Release (active) → `production`
    Environment approval → agent on the server verifies + pulls the digest + runs it
    → `Released`.
  - The artifact set on every regulated Release and the ICH E6(R3)/ALCOA+ clause each
    answers (image digest + provenance attestation, SBOM + its attestation,
    validation report, CtQ traceability matrix, `SHA256SUMS`, authorisation record).
    Inspector-facing "where is X" table.
  - SemVer `vMAJOR.MINOR.PATCH`, one milestone per release, milestone closed on publish.

- [x] **1b. NEW:** `templates/compliance/release.yml`
  - Ships into regulated repos as `.github/release.yml` (auto-notes categorisation).
    Categories keyed off existing labels: `regulated`/`validation` → "Validated
    requirements", `bug` → "Fixes", `security` → "Security", catch-all → "Other".
    `exclude` bot/automation labels. Header comment: the custom milestone-scoped
    generator (Phase 2) produces the authoritative notes; this only shapes the
    auto-section.
  - **Deviation from plan:** there is no `regulated` label in `labels.json`; the
    "Validated requirements" category is keyed off the labels that actually
    exist (`validation`, `compliance`, `enhancement`). Added a `breaking-change`
    category too (the label exists). Bots excluded via `exclude.authors`
    (dependabot / github-actions) since no automation *label* exists to exclude.

- [x] **1c. MODIFY:** `templates/compliance/CONTRIBUTING-regulated.md`
  - Add a "Releases & milestones" section: assign your issue to the target milestone;
    what a Release means; a release cannot publish without a green validation report
    and a verified image attestation.

- [x] **1d. MODIFY:** `README.md`
  - New "## Release process" section summarising the three layers + the pull-agent
    model, linking `docs/release-process.md`; add placeholder rows to the rollout-log
    table for the release workflow, vuln gate, hardened Released gate, and the agent
    (filled in Phase 8). Add `release-targets.schema.json`, the new workflow, and the
    templates to the "What's in here" table.
  - **Deviation from plan:** the four release-pipeline placeholders live in a
    *dedicated* "Release pipeline rollout log" table under the new Release
    process section, not in the board's "Active-mode rollout log" table — they
    flip via the caller `enforcement:` input / agent enablement, not
    `project-enforcement.yml`, so co-locating them with board checks would be
    misleading. The hardened `Released` precondition stays in the board table
    (Phase 8b updates that row) and the new section links to it.
  - **Deviation from plan:** the `.github/workflows/release.yml` "What's in here"
    row is deferred to Phase 3 (when the file is actually created) so the README
    never documents a non-existent file. The schema, `scripts/release/`,
    `docs/release-process.md` and the templates rows were added now.

---

## Phase 2: Milestone-scoped notes + CtQ/FRM129 traceability generator (TDD)

Pure-Python, highest design value — tests first.

- [x] **2a. NEW (Tests):** `scripts/release/tests/test_notes.py`
  - Fixtures: milestone issues/PRs (closed; bodies with `Risk ID:` / `Requirement ID:`
    / `Feature link:`; labels; acceptance/QA approver fields) **plus** a fixture
    `.compliance.yml` carrying `ctq_factors` and `governing_documents`. Assert:
    categorised changelog by label; a traceability table with one row per requirement
    (**CtQ factor (FRM129 ref + tier) →** issue # → Risk ID → Requirement ID →
    `.feature` URL(s) → acceptance approver/date → QA approver/date); a
    `Governing documents` list from `governing_documents`; missing fields flagged
    `_missing_`; non-regulated issues listed but excluded from the matrix;
    deterministic ordering.
  - Reuse the body-parsing regexes proven in `gxp-traceability.yml`
    (`^[#\s>*-]*risk\s*id\s*:`) so behaviour matches the PR gate.
  - **Deviation from plan:** reused `project_enforcement.body_parser.extract_field`
    (the repo's *form-aware* extractor, documented as the corrected version of
    that inline regex) instead of copying the `gxp-traceability.yml` regex string.
    Rationale: issue-form bodies render as `### Risk ID:` headings with the value
    on the next line, which the inline `…:\s*(.+)$` regex mis-handles; reusing the
    single shared parser matches real rendering and avoids propagating the known
    bug — consistent with the "go through the single source" convention.
  - **Deviation from plan:** the matrix anchors each requirement to a CtQ factor
    via a `CtQ factor:` field parsed from the issue body, with the *tier* resolved
    from `.compliance.yml` `ctq_factors` (unknown ref → `(unknown)`, absent →
    `_missing_`). The `regulated_feature.yml` issue template does not yet carry a
    `CtQ factor:` field, so real matrices show `_missing_` in that column until the
    template gains one — tracked as a follow-up (template edits are out of this
    phase's `scripts/release` scope). Approver identity/date are carried on the
    `MilestoneItem` (sourced from the board card), not parsed from the body.

- [x] **2b. NEW (Implementation):** `scripts/release/notes.py`
  - `build_notes(repo, milestone, tag, prev_tag, compliance, evidence) -> str`.
    Queries milestone issues/PRs via `gh api`/GraphQL, parses bodies, reads
    `ctq_factors`/`governing_documents` from the parsed `.compliance.yml`, emits
    markdown: summary, auto changelog, `## Traceability matrix` (CtQ-anchored),
    `## Governing documents`, then a `## Release authorisation` placeholder the
    workflow fills from the Environment approval (approver identity + UTC + **image
    digest**).
  - Security posture of `gxp-traceability.yml`: untrusted issue/PR bodies read from
    files / passed as data, **never** interpolated into shell or Python source.

- [x] **2c. NEW (Tests):** `scripts/release/tests/test_sbom_scan.py`
  - Fixtures for clean / high / critical grype JSON; assert non-zero counts +
    markdown summary text.

- [x] **2d. NEW (Implementation):** `scripts/release/sbom_scan.py`
  - Thin pure wrapper: parse grype JSON, return count of critical/high, format a
    step-summary markdown block. Scanner invocation itself lives in the workflow.

---

## Phase 3: Reusable release workflow (build image → attest → sign → GHCR → Release)

- [x] **3a. NEW:** `.github/workflows/release.yml` (reusable, `on: workflow_call`)
  - **Deviation from plan:** added a small **tested** helper `scripts/release/manifest.py`
    (+ `test_manifest.py`, 10 tests) so the workflow reads the manifest through unit-tested
    accessors / a CLI rather than inline YAML parsing — keeps the YAML thin and the
    binding in one tested place. Also: the reusable workflow checks out `CCTC-team/.github`
    (the tooling) into `_release-tooling` so `scripts/release/*` is importable in the
    caller's run context (a `tooling_ref` input, default `main`, controls which ref).
  - **Deviation from plan:** the `publish:registry` target must export the pushed
    sha256 digest to `$GITHUB_ENV` under the manifest's `image.digest_env`; the
    workflow reads it back (env from a child process can't otherwise return). Documented
    in the workflow and the example manifest. Tag-signature verification is a
    *presence* check (annotated tag carrying a PGP/SSH signature block) — full trust
    verification needs the runner's key/allowed-signers store (operational follow-up).
  - **Deviation from plan:** the `environment` input is declared now but the job-level
    `environment:` wiring + authorisation-block fill is deferred to Phase 4c (per the
    plan's own split), avoiding an empty-string-environment footgun in Phase 3.
    Release-notes approver columns render `_missing_` until board-card enrichment lands
    (same follow-up as the CtQ template-field gap).
  - **Inputs:** `compliance_path` (default `.compliance.yml`), `tag` (the `v*` ref),
    `milestone` (default: derive from tag), `enforcement`
    (`evaluate`|`active`, default `evaluate` — controls vuln gate + draft-vs-publish),
    `environment` (optional; Phase 4). **No build-tool/path/command inputs** — all
    binding comes from the manifest (Decision 8).
  - **Permissions:** `contents: write`, `id-token: write`, `attestations: write`,
    `packages: write` (push to GHCR), `issues: read`, `pull-requests: read`.
  - `runs-on: ubuntu-latest` (org policy — the public `.github` repo cannot use
    self-hosted; see the runner-choice convention). Python via venv as in
    `gxp-traceability.yml`.
  - **Gate + contract-check first** (mirror `gxp-traceability.yml` steps 1-2): no
    `.compliance.yml` or `regulatory_tier == none` → exit success. Otherwise load
    `.github/release-targets.yml` (path from `release_targets_path`) and run
    `scripts/release/contract.py` — **fail fast** if a mandatory target for this
    `regulatory_tier` is missing/undeclared.
  - **Steps (in order); every build action is `manifest.targets.<name>.run`, never a
    hardcoded command; every output is collected from declared globs/refs:**
    1. `actions/checkout@v6` at the tag ref, `fetch-depth: 0`. **Verify the tag is
       signed** (Phase 4a) — refuse to proceed on an unsigned tag. Derive `version`
       from the tag (`v1.4.0`→`1.4.0`), export via the manifest's `version_pin_env`.
    2. Run `build` then `package` (builds the OCI image) then `publish:registry`
       (pushes to GHCR), capturing the pushed **image digest** from the manifest's
       declared image-digest output. *Building here, in the hardened runner, is what
       provenance attests (Decision 2).*
    3. Run the `sbom` target → collect the CycloneDX file from declared `outputs`.
    4. Vulnerability scan (grype over the SBOM) → `scripts/release/sbom_scan.py`;
       `active` = fail on critical/high, `evaluate` = `::warning::` + continue.
    5. `actions/attest-build-provenance` and `actions/attest-sbom` **over the image
       digest** (not a file) → keyless, OIDC-bound, transparency-logged.
    6. Run `validation-docs` target → collect the report from its declared path. Fail
       if the target fails or the report is empty — no validation evidence, no Release.
    7. SHA-256 checksums over collected file assets (validation report, SBOM) →
       `SHA256SUMS`.
    8. `scripts/release/notes.py` → milestone-scoped notes + CtQ traceability matrix,
       embedding the image digest.
    9. `gh release create` for the tag: **draft in `evaluate`, published in `active`**,
       attaching the validation report, SBOM, `SHA256SUMS`, the notes, and recording
       the **`ghcr.io/...@sha256:<digest>` image ref** prominently in the body (the
       image lives in GHCR, not as a Release asset). `latest` on publish unless the
       tag has a `-rc`/`-beta` suffix (→ prerelease).
  - Write a `$GITHUB_STEP_SUMMARY` table: image digest, every attached asset +
    checksum, attestation status (the inspector-facing manifest).

- [x] **3b. NEW:** `templates/compliance/release-caller.yml`
  - Thin caller shipped as `.github/workflows/release.yml` in the regulated repo,
    `on: push: tags: ['v*']`, declaring the permissions above and
    `uses: CCTC-team/.github/.github/workflows/release.yml@main` with
    `enforcement: evaluate`. **No repo-specific paths** — all binding is in
    `.github/release-targets.yml`. Header comment explains the evaluate→active flip.

---

## Phase 4: Signed tags + production authorisation environment (config + docs)

Configuration and process, not verifiable logic — TDD exception (noted inline).

- [x] **4a. Contract requirement — the `tag` target produces a SIGNED tag.** Part of
  the canonical contract (Phase 0a): every repo's `tag` target must `git tag -s`
  (not `-a`), so the released version carries the same cryptographic attribution the
  commit ruleset already requires. The release workflow verifies the signature
  (Phase 3a step 1).
  - *Example fix (separate PR to the product repo):* CCTC_Components'
    `Tag version in git` (`build.fs:979`) uses `git tag -a` → change to `git tag -s`
    and provision the signing key on its build runner. This repo only documents the
    requirement; each product repo brings its own `tag` target into compliance.
  - **Satisfied in-scope; product-repo fix STUBBED.** The contract requirement is in
    claude-org `build-and-release.md` (§"`tag` must be signed", and called out in the
    worked example), and `release.yml` refuses an unsigned tag. The CCTC_Components
    `build.fs` `git tag` → `git tag -s` change is a product-repo edit, out of the
    agreed scope (.github + claude-org only), so its checkbox here covers only the
    org-level requirement; the product PR is deferred to a separate session.

- [x] **4b. NEW:** `docs/release-authorisation.md`
  - How to configure the `production` GitHub **Environment** with required reviewers
    (the QA-approver group — matching the board's `QA approved` gate); the approval is
    **the gate and the technical evidence** —
    attributable, contemporaneous, **bound to the image digest** (the
    record-version-hash).
  - **The honest residual gap (Decision 6):** a GitHub Environment approval does not
    force re-authentication at the moment of signing, so it does **not** by itself
    satisfy the org electronic-signature spec
    (`guides/regulated-gcp-systems.md` → Electronic Signatures). Document that the
    **formal e-signature of record** (re-auth + meaning + hash binding + captured
    role) is captured in the application's signature flow or the CTU QMS/eTMF,
    referencing the release digest; the Environment approval enforces the technical
    gate. Map each property to the ICH E6(R3) e-signature expectations and mark which
    GitHub satisfies vs which the QMS supplies.
  - Note the ordering: this gate aligns with the `QA approved → Released` transition —
    it fires after **both** `User acceptance` and `QA approved`.

- [x] **4c. MODIFY:** `.github/workflows/release.yml`
  - When `environment` is set, the publish/`latest` job runs
    `environment: ${{ inputs.environment }}` so it blocks on required reviewers. The
    notes' `## Release authorisation` block is filled with approver identity + UTC
    timestamp (from the deployment record) + the image digest.
  - **Note:** approver identity comes from
    `repos/{repo}/actions/runs/{run_id}/approvals`; the UTC timestamp is captured at
    the (post-approval) publish job as the contemporaneous deployment-record time.

---

## Phase 5: The pull-agent (server-structure)

> **STUBBED — out of scope for this execution.** Phase 5 lives entirely in
> `~/repos/server-structure`, outside the agreed scope (`.github` + `claude-org`
> only). All Phase 5 items are intentionally left unchecked and deferred to a
> separate server-structure session. The `.github`-side hooks the agent depends
> on (the published-Release artifact set, the signer-workflow identity, the
> verification contract) are delivered by Phases 3/4/6 here.

The heart of the new model. Lives in `~/repos/server-structure`. Replaces the
inbound SSH-push (`deployVersionedBuild`) with an on-server outbound poller.

- [ ] **5a. NEW (Tests):** `~/repos/server-structure/agent/tests/test_decision.py`
  - Pure-function tests for `decide(running_digest, release, verification) -> Action`:
    - latest approved Release digest == running digest → `Action.NONE`.
    - new published, non-prerelease Release for this app, digest differs,
      verification ok → `Action.DEPLOY(digest)`.
    - new Release but `gh attestation verify` failed → `Action.REFUSE` (never deploy
      an unverified image — the security boundary).
    - Release is a draft / prerelease → `Action.NONE` (evaluate-mode draft must not
      auto-deploy production).
    - no Release for the app's tag prefix → `Action.NONE`.

- [ ] **5b. NEW (Implementation):** `~/repos/server-structure/agent/decision.py`
  - The pure decision logic above. No I/O.

- [ ] **5c. NEW:** `~/repos/server-structure/agent/agent.py`
  - Thin shell around `decide`. Per poll, for the configured app + environment:
    1. `gh api` the repo's latest published Release matching the app's tag prefix;
       extract the `ghcr.io/...@sha256:<digest>` image ref from the body/asset.
    2. **Verify before trust:** `gh attestation verify <image>@<digest>
       --repo CCTC-team/<repo>
       --signer-workflow CCTC-team/.github/.github/workflows/release.yml`.
       On failure → log `REFUSE`, alert, **do not pull**.
    3. Read current running digest (from the compose `.env` / `docker inspect`).
    4. `decide(...)`. If `DEPLOY`: `docker pull <image>@<digest>`, write the digest
       into the compose `.env` (`<APP>_IMAGE_DIGEST`), `docker compose -f
       docker-compose.<env>.yml up -d --no-deps`, then run `verify:production`
       (reuse the existing HTTP smoke/health checks — `/api/health`, framework MIME,
       index freshness) with a bounded retry.
    5. Append an audit-log entry (5e) for every outcome (NONE/DEPLOY/REFUSE/boot-fail).
  - Least-privilege GitHub token (read Releases + GHCR pull only); pinned signer
    identity in config (`agent/config.<env>.yml`). Never executes anything from the
    Release body — only the digest string is consumed, validated against a
    `^ghcr\.io/CCTC-team/[\w.-]+@sha256:[0-9a-f]{64}$` allowlist regex.

- [ ] **5d. MODIFY:** `~/repos/server-structure/trialview/docker-compose.{staging,prod}.yml`
  - Replace the `build:` stanzas with `image: ghcr.io/cctc-team/<app>@${<APP>_IMAGE_DIGEST}`
    so the server runs the **CI-built, attested** image by digest instead of building
    locally (Decision 2). The Dockerfiles move to the product repo's build. Keep the
    versioned-build directory convention only for the compose `.env` history /
    rollback pointers.

- [ ] **5e. NEW:** `~/repos/server-structure/agent/audit-log.md` (format spec) +
  the append-only log the agent writes (e.g. `/var/log/cctc-release-agent/<app>.jsonl`)
  - One immutable line per poll-with-action: UTC timestamp, app, environment, prior
    digest, new digest, verification result, boot result, the Release tag + URL, and
    the approver identity copied from the Release authorisation block. ALCOA on the
    deploy boundary (Decision 10). Document log rotation that **appends/archives,
    never rewrites**.

- [ ] **5f. NEW:** `~/repos/server-structure/agent/cctc-release-agent@.service` +
  `cctc-release-agent@.timer` (systemd template, instanced per app/env)
  - The timer sets the poll interval (e.g. every 2 min); the service runs `agent.py`
    once per fire. Documented install steps in the runbook (Documentation section).
    *Why a timer over a long-running loop:* a crash can't silently stop deploys
    forever — each fire is independent and observable in `journalctl`.

- [ ] **5g. NEW:** rollback recipe in the runbook — the agent retains the previous
  digest in the `.env` history; rollback is re-pointing `<APP>_IMAGE_DIGEST` to the
  prior digest and `docker compose up -d --no-deps`. No rebuild, no inbound SSH from
  a laptop (an operator with server access does it locally, or a prior Release is
  re-approved).

---

## Phase 6: Harden the "Released" board precondition (TDD)

- [x] **6a. NEW (Tests):** extend `scripts/project_enforcement/tests/test_evidence.py`
  - For a new `published_release_for_sha`: draft release matching the SHA → not
    satisfied; published release matching the SHA but **without** the validation asset
    → not satisfied; published release **with** the validation asset (and, behind a
    config flag, a verifiable provenance attestation) → satisfied (returns release
    meta); a **bare tag** pointing at the SHA → not satisfied (the regression the old
    `release_for_sha` allowed).
  - **Deviation from plan:** tests target the pure selector `_select_published_release`
    (draft/bare-tag/no-asset/with-asset/tag-resolves-elsewhere). The validation-asset
    and provenance-flag *policy* (satisfied vs not) is asserted at the precondition
    level in `test_preconditions.py` (6c), because the config flag lives on `ctx`, not
    in evidence — `published_release_for_sha` returns the matching published Release
    (with `has_validation_asset`) so the precondition can give a precise reason.

- [x] **6b. MODIFY:** `scripts/project_enforcement/evidence.py`
  - Add `published_release_for_sha(self, repo, sha) -> Optional[ReleaseMeta]` to the
    protocol, `GhEvidence`, and the fake. Real impl: page `/repos/{repo}/releases`,
    require `draft == false`, resolve the release tag to the SHA via the tag ref (not
    a `target_commitish` string match), and inspect `assets[].name` for the
    validation-report pattern. Keep or replace the sole `release_for_sha` caller.

- [x] **6c. MODIFY:** `scripts/project_enforcement/checks/preconditions/released.py`
  - Replace `release_for_sha` with `published_release_for_sha`. Precise reasons: "no
    published Release references merge SHA", or "Release `vX.Y.Z` references the SHA
    but has no validation report attached — the release workflow must run in active
    mode and succeed". Optional provenance-attestation requirement behind a config
    flag (default off until the workflow is active everywhere).
  - Also updated the README "What it enforces" `Released` bullet to match the
    hardened behaviour. `release_for_sha` + `StubEvidence.releases` removed entirely
    (sole caller replaced); `GhEvidence` resolves each release tag to its commit via
    the tag ref (annotated tags dereferenced), never `target_commitish`.

- [x] **6d. MODIFY:** preconditions wiring / `__init__.py` if the new evidence method
  needs registering; run `test_handler_smoke.py` to confirm no signature drift.
  - No registry change needed (the status→check map is unchanged). `test_handler_smoke.py`
    passes; full enforcement + release suites green (271).

---

## Phase 7: Ship via compliance-drift + ruleset confirmation

- [x] **7a. MODIFY:** compliance-drift stubbing (`scripts/compliance-drift.sh` +
  `.github/workflows/compliance-drift.yml`)
  - Add to the idempotent, only-when-absent stub set:
    `templates/compliance/release.yml` → `.github/release.yml`,
    `templates/compliance/release-caller.yml` → `.github/workflows/release.yml`,
    `templates/compliance/release-targets.yml.example` → `.github/release-targets.yml`
    (TODO-flagged so the owner fills in their build commands/paths).

- [x] **7b. MODIFY:** `.github/workflows/compliance-check.yml`
  - For regulated repos, load `.github/release-targets.yml` and run
    `scripts/release/contract.py` (Phase 0e): a regulated repo missing a mandatory
    target (no `tag`/`validation-docs`/`sbom`/…) is flagged. evaluate→active like the
    other checks. *Why here:* makes the contract real on every PR, not only at release.
  - **Note:** added a `contract_enforcement` input (default `evaluate`) gating just
    this step (schema validation stays a hard fail) and a `tooling_ref` input; the
    workflow checks out `CCTC-team/.github` into `_release-tooling` to import
    `release.contract`. An absent manifest is itself flagged.

- [x] **7c. MODIFY:** `rulesets/cctc-gcp-critical.json` (and confirm
  `cctc-regulated-non-critical.json`) — these are the only two ruleset files.
  - **Done:** verified `refs/heads/release/*` is present in `cctc-gcp-critical.json`
    (verify-only, no change). Added `rulesets/cctc-tag-immutability.json` — a separate
    `target: tag` ruleset over `refs/tags/v*` for all regulated tiers, zero bypass,
    `non_fast_forward` + `deletion`, `enforcement: evaluate`. Documented as "Ruleset C"
    in README + the apply command + the evaluate-mode flip caveat.
  - **Deviation from plan:** scoped the tag ruleset to **all** regulated tiers
    (`gcp-critical` + `gcp-supporting` + `data-protection`), not just gcp-critical,
    since every regulated repo now releases via the pipeline and a published tag should
    be immutable regardless of tier. Rulesets left in `evaluate` (not flipped to
    `active`) — flipping is an org-admin `gh api` action gated on a clean evaluate
    cycle; documented the dependency and prompting the user separately.
  - `refs/heads/release/*` is **already** in `cctc-gcp-critical.json`'s `include` list
    alongside `main`/`develop`, sharing the PR-review + `required_signatures` +
    `non_fast_forward`/`deletion` rules — so this is a **verify-only** step; document
    any gap rather than silently widening scope.
  - Add a **tag ruleset** — a separate `target: tag` ruleset, not an addition to the
    branch ruleset's `include` — protecting `refs/tags/v*` against deletion and
    non-fast-forward, so a published version tag becomes immutable (the
    inspection-resilience payoff: a release tag can never be moved or re-pointed,
    matching the immutable image digest).
  - **Caveat:** both org rulesets are currently in **evaluate (log-only)** mode, so
    the tag-immutability and `release/*` guarantees do not actually enforce until they
    are flipped to `active`. Either flip them here or document the dependency
    (consistent with how this plan treats the e-signature residual gap).

---

## Phase 8: Evaluate → active rollout

- [x] **8a. MODIFY:** `.github/project-enforcement.yml`
  - Keep `preconditions: Released: evaluate` until the release workflow has cut at
    least one real published Release with all artifacts green **and** the agent has
    performed one verified pull-deploy on staging. Document the dependency inline.

- [x] **8b. MODIFY:** `README.md` rollout-log table
  - Add rows: `release workflow (publish)`, `release workflow (vuln gate)`,
    `pull-agent (staging)`, `pull-agent (production)` — all `_pending_`, with the
    "flip after one clean evaluate cycle" note. **Update** the existing
    `preconditions: Released` row (already in the table, currently noted as depending
    on the PR promoter) to reflect the hardened gate — do not add a duplicate row.
  - The four placeholder rows were already added in Phase 1d (the dedicated "Release
    pipeline rollout log" table); 8b updated the board table's `preconditions: Released`
    row note to the hardened published-Release gate + the staging-deploy dependency.

- [x] **8c. MODIFY:** `docs/release-process.md`
  - Final "rollout" subsection: evaluate cuts a **draft** Release (full artifacts, no
    auto-deploy — the agent ignores drafts per Phase 5a) so the team inspects output;
    active publishes, enforces the vuln gate + the `production` Environment approval,
    and the agent deploys the verified digest.

---

## Documentation

- [x] **NEW:** `~/repos/claude-org/rules/guides/build-and-release.md` — the
  tool-agnostic build-target contract (Phase 0a); register in `general.md` Tier-2
  table; cross-link from `essentials/regulated-gcp-checklist.md`.
- [x] **NEW:** `docs/release-process.md` (Phase 1a) and `docs/release-authorisation.md`
  (Phase 4b).
- [x] **MODIFY:** `README.md` — release-process section, rollout log, "What's in here"
  table (Phases 1d, 8b).
- [x] **MODIFY:** `templates/compliance/CONTRIBUTING-regulated.md` — Releases &
  milestones section (Phase 1c).
- [ ] **STUBBED (out of scope):** `~/repos/server-structure/DEPLOYMENT_RUNBOOK.md` and
  `VERSIONED_BUILDS_GUIDE.md` — the SSH-push deploy steps are **superseded by the
  pull-agent**; document the agent install (systemd template), the GHCR-image compose
  change, the audit log location, and the rollback recipe. Flag the old inbound-SSH
  steps as retired (do not silently delete — note when/why they changed).
  *(Deferred with Phase 5 to a separate server-structure session.)*
- [ ] **STUBBED (out of scope):** `~/repos/TrialView/CLAUDE.md` and `~/repos/CCTC_Components/CLAUDE.md`
  — the local `dotnet run --project ./build.fsproj` deploy is replaced by: build
  pushes a signed tag → CI release workflow → agent deploys. Note the `tag` target
  must become `git tag -s` and the manifest (`.github/release-targets.yml`) must be
  filled in. *(Product-repo edits, deferred to a separate session.)*
- [x] **MODIFY:** `~/repos/claude-org/rules/guides/regulated-gcp-systems.md` — add a
  short cross-reference from §4.3.5 (release) and the Electronic Signatures section to
  `docs/release-authorisation.md`, recording where the release e-signature of record
  is captured (Decision 6).
- [x] **MODIFY (wiki, per CLAUDE.md):** reconciled `~/repos/.github.wiki` to the repo
  (full reconciliation, user-approved). Rewrote `Release-Process.md`,
  `Release-Build-Contract.md`, `Release-Multi-Repo.md` to the pull-agent /
  container-image-by-digest model; added the tag ruleset to
  `Branch-Protection-Rulesets.md`; added `release_targets_path` and **fixed the
  pre-existing v1/v2/v3 staleness → single version 1** in `Compliance-Schema.md`,
  `Compliance-Framework.md`, `Compliance-Check-Workflow.md`; documented the
  contract-check step + new inputs in `Compliance-Check-Workflow.md`; added the release
  stubs to `Compliance-Drift-Workflow.md`; hardened the `Released` gate in
  `Project-Board-Enforcement.md`; added all new files to `Repository-Layout.md`;
  tidied `_Sidebar.md`.

---

## Verification

**Verified offline (this session):**

- [x] The build-target contract guide exists in `claude-org`, is registered in the
  rules index, and lists every canonical target with scope; the CCTC_Components
  mapping is labelled "example, not normative". *(grep-confirmed.)*
- [x] `contract.py` accepts a complete manifest and flags a regulated manifest missing
  `validation-docs`/`sbom`/`tag` and any unknown target name (`pytest`). *(11 tests.)*
- [x] **Tool-agnostic proof:** `release.yml` contains no repo-specific path, filename,
  or build command (no `getval`, no `build/config/...`, no image-name literal) — every
  build action reads from `.github/release-targets.yml`. `grep` confirms. *(grep clean;
  3 `manifest --run` bindings via the `run_target` helper.)*
- [x] **Contract side of the "second manifest" check:** a deliberately different
  MSBuild-only (no FAKE) manifest satisfies `contract.check_manifest` for
  `gcp-critical`. *(The full workflow dry-run is the live item below.)*
- [x] `scripts/release/` and `scripts/project_enforcement/` unit tests pass, including
  contract checker, CtQ-anchored notes generator, sbom-scan, and
  `published_release_for_sha` regression. *(271 passed.)*
- [x] Hardened `released` gate: a card whose PR merged with only a **bare tag** is
  **not** advanced to Released; the same card after a published Release with the
  validation asset **is** allowed. *(TestReleased, 8 cases.)*

**Deferred — require live CI / GitHub / a runner (cannot run offline):**

- [ ] All workflow YAML lints clean (`actionlint`); `release.yml`'s `workflow_call`
  inputs resolve from `release-caller.yml`. *(actionlint install was blocked this
  session; all 9 workflow YAMLs parse via PyYAML. Run `actionlint` when available.)*
- [ ] A second, deliberately different manifest drives the same workflow to a
  successful **dry-run release** *(live; contract side proven above)*.
- [ ] End-to-end dry run on the **test** repo (Project 31): push a `v0.0.x-rc` tag →
  workflow in `evaluate` builds the image, pushes to GHCR by digest, attests
  provenance + SBOM, cuts a **draft** Release with notes + CtQ traceability matrix +
  validation report + SBOM + `SHA256SUMS`; step-summary manifest complete.
- [ ] `gh attestation verify <image>@<digest> --repo … --signer-workflow …` succeeds
  for the produced image and **fails** for an image built outside the release workflow.
- [ ] Vulnerability gate: a seeded critical advisory fails the release in `active` and
  only warns in `evaluate`. *(`sbom_scan` logic unit-tested; live gate behaviour is CI.)*
- [ ] `production` Environment approval blocks publish/`latest` until a required
  reviewer approves; approver + UTC + image digest land in the Release authorisation
  block.
- [ ] Tag ruleset confirmed: a published `v*` tag cannot be deleted or moved. *(Ruleset
  authored in `evaluate`; needs applying + flipping to `active` to actually enforce.)*
- [ ] Signed-tag check: the workflow refuses to publish an unsigned tag. *(Logic present
  in `release.yml`; provable only on a live runner.)*
- [ ] `compliance-drift` dry run stubs `.github/release.yml` + caller +
  `release-targets.yml` into a regulated repo and nothing into a
  `regulatory_tier: none` repo. *(Stub logic added + `bash -n` clean; needs `gh` auth +
  cloned repos to exercise.)*

**Stubbed — out of scope (server-structure):**

- [ ] `~/repos/server-structure/agent/` unit tests pass, including the
  `REFUSE`-on-failed-verification and `NONE`-on-draft cases. *(Phase 5, deferred.)*
- [ ] Agent dry run on **staging**: verify → pull digest → `up -d --no-deps` →
  `verify:staging` → audit-log line; tampered digest → `REFUSE`. *(Phase 5, deferred.)*

---

## Open operational follow-ups (not in scope, tracked separately)

- 25-year **enduring/available** archive: export released artifacts (validation
  report, SBOM, provenance, image digest) to the CTU QMS/eTMF long-term archive of
  record. GitHub + GHCR are the working store, not the archive (Decision 12).
- The **re-auth electronic-signature of record** (Decision 6): decide per CTU SOP
  whether it is captured in-app or in the QMS/eTMF, and wire the cross-reference from
  the Release authorisation block to that record.
- Signed-tag key custody on each product repo's build runner (Phase 4a).
- GHCR retention/immutability policy for `gcp-critical` image tags (prevent digest
  reuse / enforce retention windows).
