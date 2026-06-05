# Component-Aware (Multi-Image) Release Contract Implementation Plan

> **Superseded in part:** the build-provenance **attestation** elements described
> below were removed and replaced by an SSH-signed release manifest — see
> `Replace attestation with signed release manifest.md` and
> `docs/release-provenance-risk-assessment.md`. The multi-image contract itself
> stands; read "attest each image" as "record each digest in the signed manifest".

> **CLOSED — reconciled 2026-06-05.** The multi-image contract is implemented and
> in production use (TrialView ships two images through it today). The four
> remaining "deferred — live CI" items are resolved below: the two-image dry-run
> and the aggregate vuln-gate behaviour were exercised by the TrialView
> `v0.0.1-rc7..rc9` dry-runs; `actionlint` now runs clean on `release.yml`; and the
> `gh attestation verify` item is **moot** (attestation removed → signed manifest).
> Moved to `Complete/`.

## Context

The release pipeline delivered by `AIPlans/InProgress/GCP pull-agent release pipeline plan.md`
bakes in a **single-image-per-repo** assumption: the manifest's `image:` block, the
`image_ref()`/`digest_env()` accessors in `scripts/release/manifest.py`, and the
`release.yml` build→publish→resolve-digest→attest→SBOM→notes→summary steps all assume
exactly one OCI image. But the org's real systems are **multi-component**: TrialView is two
containers (`trialview` Blazor host + `trialview-api` Giraffe F# API), cctc-components is two
(`cctc-components` WASM app + `cctc-components-docs`), and future systems could have more
(UI + API + background worker + migration job + docs). The first regulated worked example —
TrialView — therefore **cannot be expressed** by the current contract. This was raised as the
blocking open item (Decision 1 / Phase 0a) of the server-structure agent plan
(`~/repos/server-structure/AIPlans/TrialView pull-agent release deployment plan.md`).

This plan makes the release contract component-aware: **one repo → one version → one Release →
N independently-attested component images, deployed atomically**. It is a revision to the
just-built `.github` pipeline + the claude-org build contract. It changes no running service;
it unblocks TrialView as the first-class example.

**Timing matters:** the pipeline has not yet cut a real release (both org rulesets are in
`evaluate`; no production Release exists), so changing the manifest *shape* now is cheap. The
same change after repos carry committed manifests and live Releases would be a migration. **Do
it before TrialView goes live, not after.**

---

## Honest design assessment (read first)

**Q: Is TrialView's two-container split the only way, or even the right way?**
It is the right way, and it should stay. The UI and API are genuinely separate deployables:
different languages/runtimes (C# Blazor Server vs F# Giraffe), different scaling and failure
profiles (SignalR circuit fan-out vs request/response API throughput), independent resource
limits and health, and a same-origin `/api/*` proxy split that nginx already serves. "One
process per container" is the Docker norm; merging them would couple their release cadence,
bloat the image, and lose independent health/rollback for no benefit.

**Q: Should the pipeline force components into one image to keep "one image per repo"?**
No. That inverts the dependency — bending real architecture to fit a release-tool limitation.
The correct cohesion boundary is the **Release**, not the image. This aligns exactly with the
parent plan's Decision 4 (board = lifecycle, **milestone = release scope**, Release =
publication): a Release already spans many issues/requirements; it can equally span many
images. So the model is **one repo → one version → one Release carrying N attested images**,
not one-image-per-repo.

**Q: Same repo with N images, or N repos with one image each?**
The honest dividing line: components that are **co-versioned, co-deployed, and jointly
validated** belong in one repo and one Release (you want a single traceability matrix +
validation report + authorisation proving the whole feature shipped together — partial
deploys like "new UI, old API" are an untested-combination hazard a regulated system should
not allow). Components with **genuinely independent consumers and release cadence** (e.g. a
shared library) belong in separate repos. TrialView (UI+API) and cctc-components (app+docs)
are both firmly in the first bucket — keep them single-repo, multi-image.

**Q: How much does this disturb the just-built pipeline?**
Mechanically modest, conceptually low-risk: the single-image steps become a **loop over a
declared component list**. The build *targets* stay 1:1 with the contract (one `package`, one
`publish:registry`, one `sbom`) — they simply produce/push/scan N images; the manifest's new
`images` map is the *output declaration* the workflow iterates to attest, reference, and
(server-side) pin each digest. `contract.py` needs no change (targets are per-repo, not
per-image). The heavy lift is the workflow loop and the schema/accessor/notes updates.

---

## Key References

- **`release-targets.schema.json`** — the `image:` (singular object: `registry`,
  `repository`, `digest_env`) block this plan generalises to an `images` map.
- **`scripts/release/manifest.py`** — `image_ref()` / `digest_env()` (singular) and the
  `python -m release.manifest --image-ref/--digest-env` CLI the workflow shells out to; both
  become component-list accessors.
- **`.github/workflows/release.yml`** — the single-image steps to loop: "Build, package, and
  publish the image", "Resolve the pushed image digest", "Generate the SBOM" + "Vulnerability
  scan", "Attest build provenance" / "Attest SBOM" (`subject-name`/`subject-digest`), the
  notes header `> **Released image:**`, the authorisation block's single digest, and the
  summary "Image" row.
- **`scripts/release/notes.py`** — currently receives the image only as a header string; gains
  a multi-image `## Released images` table. The CtQ traceability matrix is **unchanged**
  (it is requirement-anchored, not image-anchored).
- **`~/repos/claude-org/rules/guides/build-and-release.md`** — the `package` / `publish:registry`
  rows (lines 33–34) and the CI-vs-agent split (lines 61–69) to reword for N images.
- **`templates/compliance/release-targets.yml.example`** — TrialView's worked manifest; the
  `image:` block becomes a two-entry `images` map (`trialview`, `trialview-api`).
- **`~/repos/server-structure/AIPlans/TrialView pull-agent release deployment plan.md`** —
  Decision 1 / Phase 0a there is unblocked by this plan; its agent pins N digests atomically.

---

## Key Design Decisions

1. **One component = one image; the Release is the cohesion unit.** A repo declares a set of
   component images; one tag/milestone/Release publishes all of them at one repo version, each
   independently attested and (server-side) deployed atomically. *Why:* matches real
   deployment topology and the parent plan's three-layer model; preserves a single
   per-release validation/traceability/authorisation record. *Rejected:* one-image-per-repo
   (forces separate components together — anti-pattern, breaks independent
   lifecycle/scaling/health); per-component independent Releases (fractures the regulated
   evidence; allows untested UI/API combinations).

2. **Do not change TrialView's (or cctc-components') container split.** Two images each is
   correct. This plan changes only the *contract* that describes them. *Why:* the architecture
   is sound; the tooling was under-modeled.

3. **Migrate the schema from `image:` (object) to `images:` (map keyed by component name) —
   now, while it is free.** Each entry: `{registry, repository, digest_env, sbom?}`. A
   single-image repo (e.g. gtg-web) uses a one-entry map. *Why:* one shape that scales to N;
   no dual-form complexity. *Rejected:* keeping `image:` and adding `images:` alongside
   (two code paths, ambiguous precedence); a list instead of a map (component identity matters
   for stable digest-env mapping and agent config — a map keys it cleanly).

4. **Build *targets* stay singular; the `images` map is an output declaration.** `package`
   builds all images, `publish:registry` pushes all and exports each component's
   `<COMPONENT>_IMAGE_DIGEST` to `$GITHUB_ENV`, `sbom` emits one SBOM per image. The workflow
   reads the `images` map to know which digest-env to read, which ref to attest, and which
   SBOM glob maps to which image. *Why:* keeps the tool-agnostic contract 1:1 (no per-image
   target explosion) while making outputs machine-bindable; `contract.py` is untouched.

5. **Per-image SBOM and per-image attestation.** `attest-sbom` binds an SBOM to an image
   digest, and each image has a different dependency closure (the .NET host vs the F# API vs a
   static-nginx docs image), so the SBOM granularity is per image. The vulnerability gate
   **aggregates**: in `active`, the release fails if *any* image has a Critical/High finding.
   *Why:* an SBOM must describe what actually ships; aggregating the gate keeps "no
   vulnerable image is released" as one decision.

6. **The build/attest loop stays in one job (not a job matrix).** Iterate components in bash
   within the existing job. *Why:* attestation OIDC identity is the workflow's, identical for
   every image; one build step already produces all images; a matrix would re-run
   checkout/build per image for no provenance benefit. *(Parallel-attest via matrix is a
   possible later optimisation — noted, not done.)*

7. **The agent deploys the image set atomically.** (Server-structure plan.) The Release's
   image set is all-or-nothing: the decision compares the *set* of running digests vs the
   released set and brings them up together with `up -d --no-deps`. *Why:* avoids
   partial/untested UI–API combinations; a release is one validated unit.

---

## Phase 1: Schema + contract guide (the model)

- [x] **1a. NEW (Tests):** `scripts/release/tests/test_schema_images.py`
  - Validate `release-targets.schema.json` against fixtures: a two-entry `images` map (valid);
    a one-entry map (valid); an entry missing `digest_env` (invalid); a repo with **no**
    `images` key at all — package-distributable (valid); `images` present but empty (invalid).
  - **Deviation from plan:** the plan assumed an existing Python schema-test pattern, but there
    were **none**, and `release-targets.schema.json` is not runtime-validated anywhere (it is
    editor/doc only — the org's runtime validator is the `check-jsonschema` CLI in
    `compliance-check.yml`, run against `.compliance.yml`). The test validates fixtures
    in-process with the `jsonschema` library (Draft 2020-12), which matches the plan's intent
    and mirrors that runtime validation. `jsonschema` is a test-only dependency beyond the
    documented `pytest`+`pyyaml` — install into the test venv. Added two extra cases (unknown
    entry property rejected; legacy singular `image` key rejected) to lock the migration.

- [x] **1b. MODIFY:** `release-targets.schema.json`
  - Replace the `image:` object with `images:` — `type: object`, `minProperties: 1`,
    `additionalProperties` = an object `{registry, repository, digest_env, sbom?}` (all
    `minLength: 1`; `sbom` an optional output-glob string/array mapping that image's SBOM).
    Keep `images` itself **optional** (omitted for nupkg/zip repos). Update the `$comment`/
    `description` text away from "one image".

- [x] **1c. MODIFY:** `~/repos/claude-org/rules/guides/build-and-release.md`
  - Reword the `package` / `publish:registry` rows and the CI-vs-agent split to "**each
    component image**": `package` builds all of the repo's images; `publish:registry` pushes
    each and exports each digest; `sbom` emits one SBOM per image. Add a short
    "**Multi-component repos**" subsection stating Decision 1 (one repo → one Release → N
    images, atomic deploy) and the same-repo-vs-separate-repo dividing line (Decision 1's
    rationale). Keep the CCTC_Components worked example "example, not normative".

---

## Phase 2: Manifest accessors (TDD)

- [x] **2a. MODIFY (Tests):** `scripts/release/tests/test_manifest.py`
  - Replace/extend the single-image cases: `components(manifest) -> dict` returns the `images`
    map (empty `{}` when absent); `component_ref(manifest, name)` →
    `<registry>/<repository>`; `component_digest_env(manifest, name)`; `component_sbom_globs`.
    A CLI: `--list-components` (one name per line), `--component-ref NAME`,
    `--component-digest-env NAME`. Deterministic ordering (sorted by component name).
  - **Deviation from plan:** the list accessor is `component_names(manifest) -> list[str]`
    (sorted) rather than `components(manifest) -> dict` — the workflow only needs the ordered
    name list to iterate, and the per-name accessors cover the rest. Added a `TestCli` class
    (the CLI was previously untested) covering `--list-components`, `--component-ref`,
    `--component-digest-env`, and the unknown-component exit code, since Phase 4 depends on it.

- [x] **2b. MODIFY (Implementation):** `scripts/release/manifest.py`
  - Added `component_names`, `component_ref`, `component_digest_env`, `component_sbom_globs`
    and the CLI flags `--list-components`, `--component-ref`, `--component-digest-env`,
    `--component-sbom`. **Removed** `image_ref()`/`digest_env()`/`_image()` and the
    `--image-ref`/`--digest-env` CLI (grep confirmed the only callers are the workflow,
    rewritten in Phase 4, and this module).

---

## Phase 3: Multi-image release notes (TDD)

- [x] **3a. MODIFY (Tests):** `scripts/release/tests/test_notes.py`
  - Assert `build_notes` renders a `## Released images` table — one row per component, each with
    its pinned `…@sha256:…` ref — for a two-image fixture and a single-row table for a one-image
    fixture, sorted by component name, and omitted when no images are passed. The existing CtQ
    matrix / changelog / governing-docs tests are the regression guard (all still pass).

- [x] **3b. MODIFY (Implementation):** `scripts/release/notes.py`
  - `build_notes` gained an optional `images` arg (component name → full pinned ref) and emits
    the `## Released images` section after the summary; the authorisation placeholder reads
    "digest(s)". **Deviation from plan:** `images` maps each name to the **full pinned ref**
    (`<registry>/<repository>@sha256:…`) rather than a separate registry/repository/digest
    triple — the workflow already assembles `ref@digest` per component, so one string keeps the
    binding in one place. The single `> **Released image:**` header the workflow used to prepend
    is removed there in Phase 4.

---

## Phase 4: Workflow loop (integration-tested live — TDD exception)

> The workflow change is YAML orchestration over `gh`/`docker`/attest actions; it is
> exercised by the live dry-run in Verification, not unit tests (integration-only, like the
> rest of `release.yml`). The pure pieces it calls (manifest, notes, sbom_scan) are unit-tested
> in Phases 2–3.

- [x] **4a. MODIFY:** `.github/workflows/release.yml`
  - **Deviation from plan (revises Decision 6 — user-approved):** a `uses:` step (the
    `attest-*` actions) **cannot be looped** in a single job, so the "one job, bash loop"
    model is not achievable for attestation. The workflow is now **three jobs**: `build`
    (gate → contract → signed-tag → build/package/publish all images → SBOMs → assemble the
    image set → aggregate vuln scan → validation report → assets/SHA256SUMS → notes → upload a
    `release-bundle` artifact, and output the component→digest JSON), `attest`
    (`strategy.matrix.component` from `fromJSON(needs.build.outputs.images)` — one leg per
    image: GHCR login → `attest-build-provenance` + `attest-sbom` with `push-to-registry`),
    and `release` (`environment:`-gated publish job — fills the authorisation block
    post-approval, `gh release create` attaching all assets, per-image summary).
  - Build/package/publish run once (they produce all images); the build job then loops
    components to read each image's `digest_env`, validates `^sha256:[0-9a-f]{64}$`, resolves
    each image's SBOM (per-component `sbom` glob, else the `sbom` target's `outputs`), and emits
    the matrix-facing JSON. Vuln gate aggregates (fails `active` if **any** image is critical/high).
  - **Deviation:** the `environment:` gate moved from the (former single) job to the **`release`
    job** only — build + attest run before approval; publish blocks on the required reviewers.
    This is more correct than gating the build too.
  - **Deviation:** a regulated repo that declares **no** `images` now fails fast with a clear
    error ("package-only repo not yet supported"). This preserves today's effective behaviour
    (the old workflow already hard-failed without an image digest); package-distributable repos
    were never supported by this image-centric workflow and remain a separate follow-up.
  - Tool-agnostic proof re-checked: `grep` for repo-specific path/filename/build literals is
    clean (the one hit was an illustrative comment, genericised to `<APP>_…`). YAML parses via
    PyYAML. `actionlint` deferred (installer blocked this session, as in the parent plan).

---

## Phase 5: Worked example + drift

- [x] **5a. MODIFY:** `templates/compliance/release-targets.yml.example`
  - Replaced the single `image:` block with a two-entry `images` map for TrialView
    (`trialview` → `cctc-team/trialview`, `digest_env: TRIALVIEW_IMAGE_DIGEST`;
    `trialview-api` → `cctc-team/trialview-api`, `digest_env: TRIALVIEW_API_IMAGE_DIGEST`),
    each with its `sbom` glob; updated the `publish:registry` comment to export **both** digests
    and the `sbom` target to emit one SBOM per image (with a `artifacts/*.cdx.json` outputs
    fallback for single-image repos). Validated: conforms to the new schema and passes
    `contract.check_manifest(.., "gcp-critical")`.

- [x] **5b. VERIFY (no code change expected):** `scripts/compliance-drift.sh` /
  `compliance-drift.yml` still stub the example into regulated repos unchanged — confirmed the
  stub is a file-copy (`ensure_file_matches "$TEMPLATES_DIR/release-targets.yml.example"
  ".github/release-targets.yml"`), so the multi-image shape rides along with no code change.

---

## Phase 6: Reconcile dependent plans

- [x] **6a. MODIFY:** `~/repos/server-structure/AIPlans/TrialView pull-agent release deployment plan.md`
  - Updated Decision 1 and Phase 0a from "OPEN" to **RESOLVED** (the `images`-map contract is
    landed), and changed the Phase 6 block note from "Blocked on Decision 1" to gated only on a
    published two-image TrialView Release (0b). Two images, two digest envs, atomic deploy.

- [x] **6b. MODIFY:** `AIPlans/InProgress/GCP pull-agent release pipeline plan.md`
  - Add a note under Decision 2 / Phase 3 that the image model is component-aware (link this
    plan), so the parent record is not left implying single-image.

---

## Documentation

- [x] **MODIFY:** `README.md` — the "What's in here" `release.yml` row and the "Release process"
  prose now read "image(s), one per component", per-image attestation (matrix), and atomic
  deploy.
- [x] **MODIFY:** `docs/release-process.md` + `docs/release-authorisation.md` — **not in the
  original list but required by the CLAUDE.md doc-sync rule** (both used singular "image
  digest"). Generalised the flow diagram, the artifact table (image digest(s)/per-image
  provenance + SBOM), and the authorisation-block wording to "digest(s), one per component".
- [x] **MODIFY (wiki, per CLAUDE.md):** reconciled `~/repos/.github.wiki` —
  `Release-Build-Contract.md` (the `images` map, per-image `publish:registry`/`sbom`, and a new
  "Multi-component repos" subsection with the dividing line), `Release-Process.md` (flow + the
  artifact table → one Release → N images, atomic deploy), `Release-Multi-Repo.md` (monorepo
  row + default-case prose now "one or more component images"). `Compliance-Schema.md` needed
  no change — it documents only `release_targets_path`; the manifest `images` shape is
  documented in `Release-Build-Contract.md`.
- [x] **MODIFY:** `~/repos/claude-org/rules/guides/build-and-release.md` — done in Phase 1c
  (rows + CI split + "Multi-component repos" section). The Tier-2 index entry/summary in
  `general.md` is unchanged (title/scope unaffected), so it still reads correctly.

---

## Post-implementation review fixes

Two review agents scrutinised the change (workflow data-flow; cross-artifact
consistency). Fixes applied:

- [x] **CRITICAL — `fromJSON("")` on non-regulated repos.** When `applicable=false`
  the `images` step never ran, so `needs.build.outputs.images` was `""` and the
  `attest` matrix's `fromJSON(...)` (evaluated before the job `if:`) would error,
  failing the workflow for a repo that should pass cleanly. Fixed: the `build` job
  output now defaults to `'[]'` (`steps.images.outputs.json || '[]'`) and `attest`
  guards `if: … && needs.build.outputs.images != '[]'`.
- [x] **`attest` job missing `actions: read`** — `download-artifact@v4` needs it under
  a restrictive default-token policy. Added.
- [x] **`docker login` interpolated `${{ github.token }}` into the shell string** —
  moved to an `env:` var (`echo "$GH_TOKEN" | …`), matching the file's stated
  "never interpolate secrets/untrusted data into the shell" posture.
- [x] **`run_target` swallowed `::endgroup::` on a failed build target** (step runs
  under `set -e`) — now captures the exit code via `if ! …` and closes the group.
- [x] **Stale single-image wording** the consistency reviewer found in spots missed on
  the first pass: wiki `Release-Build-Contract.md` (canonical-target table rows + CI
  prose), `Release-Process.md` intro, `Release-Multi-Repo.md` opening premise,
  `Repository-Layout.md` `release.yml` row. All generalised to component image(s).
- [x] **Test hardening:** added a living-fixture test that the shipped
  `release-targets.yml.example` validates against the schema and declares both
  components, and CLI tests for `--component-sbom` (list-style: empty + exit 0,
  consistent with `--outputs`/`--list-components`). Suite now **64 passed**.
- Reviewer note (no change): the example's target-level `sbom` `outputs` glob is a
  single-image fallback; the comment now warns a multi-image repo must declare a
  per-image `sbom` glob (both example components do).

---

## Verification

**Offline (this repo):**

- [x] `python -m pytest scripts/release/tests` passes — schema (two-/one-/zero-image,
  invalid-entry), manifest component accessors + CLI (deterministic order), notes
  `## Released images` table (multi- and single-image), CtQ matrix regression intact.
  **60 passed**; the full enforcement suite (**232 passed**) confirms no cross-package regression.
- [x] **Tool-agnostic proof still holds:** `release.yml` has no repo-specific path/filename/
  image literal (re-grep clean; the one comment hit was genericised to `<APP>_…`).
- [x] A one-entry `images` manifest (single-image repo, e.g. gtg-web shape) and a two-entry
  one (TrialView) both pass `contract.check_manifest` for `gcp-critical` (contract unchanged).

**Deferred — live CI / GitHub (cannot run offline):**

- [x] End-to-end dry run on the test repo: a `v0.0.x-rc` tag with a **two-image** manifest
  builds both images, pushes both to GHCR by digest, records each digest in the signed
  manifest **per image**, and cuts a draft Release whose notes carry a two-row `## Released
  images` table + per-image digests in the authorisation block; the step-summary lists both
  images. *(Exercised by the TrialView `v0.0.1-rc7..rc9` dry-runs — two real images
  `trialview` + `trialview-api`.)*
- [x] ~~`gh attestation verify` succeeds for each produced image~~ **SUPERSEDED:**
  attestation was removed (needs GitHub Enterprise Cloud); trust is now the SSH-signed
  release manifest verified by the pull-agent against `allowed_signers`. No attestation step
  remains to verify.
- [x] Vulnerability gate aggregates: a seeded Critical in **one** of two images fails the
  `active` release and only warns in `evaluate`. *(Logic unit-tested in `test_sbom_scan.py`;
  live behaviour exercised — and the gate hardened to fail-closed — by the TrialView rc8/rc9
  dry-runs.)*
- [x] `actionlint` clean on the revised `release.yml`. *(2026-06-05: `actionlint` 1.7.12 →
  exit 0 on `release.yml` and `release-authorize.yml`.)*
