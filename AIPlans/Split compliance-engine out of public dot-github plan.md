# Split `compliance-engine` Out of the Public `.github` Repo — Implementation Plan

## Context

`CCTC-team/.github` is **public** for one legitimate reason: a repo named exactly
`.github` is the only way GitHub propagates org-wide community-health defaults
(issue/PR templates, `SECURITY.md`, the org profile README) to every repo —
public *and* private — in the organisation. A private `.github` does **not**
propagate to public repos, so the public `.github` must stay.

But the repo has accreted the entire regulated-lifecycle enforcement engine,
the GCP/compliance schemas, rationale docs, rulesets, release tooling, plans,
and label manifest — all now world-readable. None of that needs to be public,
and exposing the org's regulatory *processes* is undesirable.

This plan splits the repo in two:

- **`CCTC-team/.github`** stays public, slimmed to the genuine community-health
  core.
- **`CCTC-team/compliance-engine`** (new, **private**) takes everything else,
  **with full git history preserved** (the engine's evolution is itself
  ALCOA+/audit-relevant).

Exactly **one** downstream consumer exists today — `CCTC-team/TrialView`, set up
to exercise the real GxP process — which makes this the correct moment to cut
over. The success anchor is: **when the plan completes, TrialView's full
pipeline (compliance check, GxP traceability gate, project-board enforcement,
release authorise + release dry-run) returns to exactly the same green state it
is in now**, but driven from `compliance-engine` instead of `.github`.

### Decisions taken before planning (do not re-litigate)

- **Engine history:** *preserve full history* — stand up `compliance-engine` by
  mirroring the current repo, then deleting the community-health-only files
  there.
- **Public `.github` history:** *leave as-is, remove going forward* — delete the
  engine files in a normal commit; do **not** rewrite public history (already
  public/indexed; rewrite is disruptive and only symbolic).
- **Doc scope:** *include consumers* — also repoint TrialView's prose/docs and
  audit `claude-org/rules` so nothing points at a stale engine location.

---

## Key References

- **`README.md` → "How inheritance works"** (this repo) — the authoritative
  statement of what GitHub does and does **not** inherit from a `.github` repo.
  Confirms templates/`SECURITY.md`/profile inherit; labels, CODEOWNERS,
  rulesets, scaffolding do not. The split must not break the inheriting set.
- **`CLAUDE.md` → "Keep the wiki in sync"** — the repo is the source of truth;
  the wiki at `~/repos/.github.wiki` must be reconciled in the *same* change.
  After the split the bulk of it belongs to `compliance-engine`'s wiki.
- **`~/repos/.github.wiki/Home.md` and `_Sidebar.md`** — the wiki's own
  description of the seven/eight subsystems and its navigation tree; the
  template for what to move vs. keep.
- **`~/repos/TrialView/.github/workflows/*.yml`** — the five caller workflows
  (`compliance.yml`, `gxp-traceability.yml`, `project-card-promote.yml`,
  `release.yml`, `release-authorize.yml`) that pin
  `uses: CCTC-team/.github/...@main`; the blast radius of the rename.
- **`.github/workflows/{compliance-check,release,release-authorize,project-card-promote}.yml`**
  — **four** workflows contain `actions/checkout` of `repository: CCTC-team/.github`
  **with no `token:`** (`compliance-check.yml:56-59`, `release.yml:116` & `:541`,
  `release-authorize.yml:78`, `project-card-promote.yml:100`). These work *only
  because the repo is public*; once private they need an App token with
  `contents:read`. This is the single most likely silent breakage — see Design
  Decision 4. `compliance-check.yml` is the highest-traffic of the four (fires on
  every regulated PR) and currently declares **no `secrets:` block at all**, so
  its `workflow_call` interface must gain App-credential secrets.
- **`~/repos/claude-org/rules/general.md` → "Raising GitHub Issues"** — points
  at `CCTC-team/.github/.github/ISSUE_TEMPLATE`. Templates **stay** public, so
  this reference stays valid; the plan only *verifies* it, changing nothing
  there unless an engine reference is also present.

---

## Key Design Decisions

1. **Name `compliance-engine`, private.** Chosen by the user. The public repo
   keeps the mandated name `.github`. No `.github-private` is used: that special
   repo only serves the org *profile README* to members and carries **no**
   community-health defaults, so it cannot host the templates and is irrelevant
   here.

2. **Preserve history by mirror-then-strip, not clean import.** Create
   `compliance-engine` from a full mirror of the current repo so every engine
   commit (and its ALCOA+-relevant audit trail) survives, then `git rm` the
   community-health-only files in `compliance-engine`. The public `.github`
   keeps its history untouched and simply deletes the engine files going
   forward. Net effect: both repos share history up to the split point — the
   safest possible basis for "same state".

3. **Cut over with a safe overlap window; never a flag-day.** Order of
   operations keeps TrialView green throughout:
   stand up `compliance-engine` fully (history + token fix + platform config)
   **while `.github` still also carries the callable workflows** →
   repoint TrialView and verify green against `compliance-engine` →
   only *then* strip `.github`. The **callable** workflows may safely exist in
   both repos during the window (they run only when called). The
   **self-running/scheduled** workflows (drift, project-enforcement poller,
   project-audit, sync-labels, sync-property-topics) must run from **one** repo
   only — so they are **disabled in `.github` the moment `compliance-engine` is
   live** (Phase 2), to avoid double enforcement / double label-sync /
   conflicting board writes.

4. **The engine self-checkout needs an App token once private — in FOUR
   workflows.** Today `compliance-check.yml`, `release.yml`,
   `release-authorize.yml`, and `project-card-promote.yml` `checkout
   repository: CCTC-team/.github` using the default token — fine for a public
   repo, broken for a private one (the caller's `GITHUB_TOKEN` is scoped to
   TrialView, not `compliance-engine`). Fix: in each, mint a GitHub App token
   (`actions/create-github-app-token`) from App credentials the caller passes,
   **before** the checkout, and pass `token:` to it. Per-workflow nuance:
   - `compliance-check.yml` — **no `secrets:` block today**; add
     `app_client_id`/`app_private_key`, add a token-mint step before the
     `:56` checkout. (Highest traffic — every regulated PR.)
   - `release-authorize.yml` — declares **only** `org_read_token`; must gain
     `app_client_id`/`app_private_key` too.
   - `release.yml` — two checkouts (`:116`, `:541`), both need `token:`.
   - `project-card-promote.yml` — already mints an app token, but the step
     (~`:119-122`) is **after** the `:100` checkout, so it must be **reordered**
     ahead of it.
   The App (label-sync App `3868995`, or a dedicated tooling App) must be
   installed on `compliance-engine` with `contents:read`.

5. **Distribute `release-targets.schema.json` co-located, like
   `compliance.schema.json`.** TrialView's `.github/release-targets.yml` pins
   `$schema:` to a **raw public URL** on `.github`, which 404s once private
   (raw URLs on private repos require a token the editor won't send). Rather
   than embed a tokened URL, extend the **compliance-drift** workflow to also
   push `release-targets.schema.json` into each regulated repo (it already
   pushes `compliance.schema.json`), and point the manifest's `$schema:` at the
   co-located relative copy. This keeps the IDE hint working and is consistent
   with how the compliance schema is already distributed. (If the user prefers
   to keep it simple, the fallback is to drop the `$schema:` line; noted in the
   phase.)

6. **References to *community-health* files stay pointing at `.github`;
   references to *engine* files repoint to `compliance-engine`.** This
   distinction governs every link edit. Links to `ISSUE_TEMPLATE/*`,
   `pull_request_template.md`, `SECURITY.md`, and the profile README keep
   `CCTC-team/.github`. Links to `scripts/`, `docs/`, `templates/`, the schemas,
   `labels.json`, rulesets, and the reusable workflows move to
   `CCTC-team/compliance-engine`.

7. **Each repo gets its own `README.md`, `CLAUDE.md`, `CODEOWNERS`, and wiki.**
   The current (engine-centric) `README.md`/`CLAUDE.md` become
   `compliance-engine`'s. The public `.github` gets freshly-written minimal
   versions describing only the community-health purpose and pointing members
   at the private engine repo. The wiki splits the same way (Phase 7).

---

## Inventory: stays vs. moves

**Stays in public `.github`** (the inheriting community-health core + its
governance):
`.github/ISSUE_TEMPLATE/{bug_report,config,feature_request,regulated_feature}.yml`,
`.github/pull_request_template.md`, `SECURITY.md`, `profile/README.md`,
`.github/CODEOWNERS` (slimmed), `README.md` (new minimal), `CLAUDE.md` (new
minimal), `.gitignore` (minimal).

**Moves to private `compliance-engine`** (full history):
`scripts/**`, `docs/**`, `AIPlans/**`, `rulesets/**`, `templates/**`,
`compliance.schema.json`, `release-targets.schema.json`, `labels.json`,
`conftest.py`, `.github/project-enforcement.yml`, **all** of
`.github/workflows/*.yml` (10 files), and the current engine-centric
`README.md` + `CLAUDE.md`. Plus the bulk of the wiki (Phase 7).

---

## Phase 0: Pre-flight

- [ ] **0a.** Confirm `gh auth status` has an account with **org-admin** on
  `CCTC-team` (needed to create a private repo, set Actions access, install
  Apps, and manage rulesets/secrets). If not, flag the UI-only steps for the
  user.
- [ ] **0b.** Snapshot the current green baseline so "same state" is verifiable
  later: record the latest successful run IDs/conclusions of TrialView's
  `compliance`, `gxp-traceability`, `project-card-promote`, `release-authorize`,
  and `release` workflows (`gh run list --repo CCTC-team/TrialView`), and the
  current state of the in-progress release dry-run
  (`TrialView/AIPlans/InProgress/release-pipeline-dry-run-resume.md`).
- [ ] **0c.** Record the org rulesets in scope (evaluate mode, ids `16889857`
  Ruleset B / `16892559` Ruleset A) and how they key off the `regulatory_tier`
  custom property, so Phase 2 can confirm `compliance-engine` lands in the
  correct (infrastructure / not-regulated-app) ruleset bucket.
- [ ] **0d.** Take a clean full mirror of the current repo for Phase 1:
  `git clone --mirror git@github.com:CCTC-team/.github.git /tmp/ce-mirror.git`.

---

## Phase 1: Stand up `compliance-engine` (private, full history)

- [ ] **1a. NEW (repo):** Create the empty private repo —
  `gh repo create CCTC-team/compliance-engine --private --description "Regulated-lifecycle enforcement engine, compliance schemas, release tooling, and labels for CCTC-team (split out of the public .github repo)."`
- [ ] **1b.** Push the **full history** from the Phase 0d mirror:
  `git -C /tmp/ce-mirror.git push --mirror git@github.com:CCTC-team/compliance-engine.git`.
  `compliance-engine` is now byte-for-byte the current `.github`, history and
  all.
- [ ] **1c. MODIFY (in a fresh working clone of `compliance-engine`):** `git rm`
  the community-health-only files that belong to the *public* side:
  `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `SECURITY.md`,
  `profile/README.md`. (They remain in `compliance-engine`'s *history*, which is
  fine — private repo.)
- [ ] **1d. MODIFY:** `compliance-engine/README.md` and `CLAUDE.md` — keep the
  current engine-centric content but fix repo-identity wording ("the org-level
  `.github` repository" → "the org's private `compliance-engine` repository";
  describe the community-health split-out). Remove the community-health
  sections that no longer live here (point them at public `.github`).
- [ ] **1e. NEW/MODIFY:** `compliance-engine/.github/CODEOWNERS` — replace the
  community-health-oriented CODEOWNERS with one covering the engine paths
  (`/scripts/`, `/.github/workflows/`, `/labels.json`, `/compliance.schema.json`,
  `/release-targets.schema.json`, `/rulesets/`, `/templates/`, `/docs/`).
- [ ] **1f. MODIFY (self-references — grep `compliance-engine` for
  `CCTC-team/.github` and fix every hit that points at an *engine* artefact;
  leave hits that point at community-health files):**
  - `compliance.schema.json` `$id` + description → `.../compliance-engine/...`
  - `release-targets.schema.json` `$id` → `.../compliance-engine/...`
  - `.github/workflows/release.yml` — `repository: CCTC-team/.github`
    (two checkouts) → `CCTC-team/compliance-engine`; `tooling_ref` /
    `compliance_path` input descriptions.
  - `.github/workflows/release-authorize.yml` — `repository:` checkout +
    `tooling_ref` description.
  - `.github/workflows/project-card-promote.yml` — `repository:` checkout.
  - `.github/workflows/{compliance-check,compliance-drift,gxp-traceability}.yml`
    — header comments AND the `tooling_ref` input description
    (`compliance-check.yml:42-44` reads "Ref of CCTC-team/.github to load the
    contract checker…") that name `CCTC-team/.github` as the tooling source.
    Note: `compliance-check.yml` also needs the token/interface change in
    Phase 3 — this 1f item is only its text references.
  - `templates/compliance/.compliance.yml.example` line ~4 "Canonical schema:"
    comment (leave the relative `$schema=./.github/compliance.schema.json`).
  - `docs/*.md` — any `CCTC-team/.github/...` that names an engine file.
- [ ] **1g.** Commit on `main` of `compliance-engine`. Run the suite locally to
  prove the move is intact: `python -m pytest scripts/project_enforcement/tests`
  (from the `compliance-engine` clone root — `conftest.py` came across).

---

## Phase 2: Platform configuration for `compliance-engine`

> Several of these are `gh api` / admin or GitHub-UI actions, not file edits —
> they are called out so the implementer wires the platform, not just the code.

- [ ] **2a.** **Enable private reusable-workflow sharing**: `compliance-engine`
  → Settings → Actions → *Access* → "Accessible from repositories in the
  `CCTC-team` organisation" (or `gh api` equivalent
  `actions/permissions/access`). Without this, TrialView cannot resolve
  `uses: CCTC-team/compliance-engine/...`.
- [ ] **2b.** **Install the GitHub App** (label-sync App `3868995`, or a
  dedicated tooling App) on `compliance-engine` with at least `contents:read`
  (for the engine self-checkout) and the scopes the scheduled workflows need
  (org projects read/write for the board poller, `members:read` if any run
  needs org-team reads). See `cctc-label-sync-app` notes.
- [ ] **2c.** **Replicate repo secrets** that the *self-running* workflows in
  `compliance-engine` consume (the callable ones receive secrets from the
  TrialView caller, so those are not duplicated here): `app_client_id`,
  `app_private_key`, and any others used by `sync-labels.yml`,
  `project-enforcement.yml`, `project-audit.yml`, `compliance-drift.yml`,
  `sync-property-topics.yml`. Confirm with `gh secret list`.
- [ ] **2d.** **Branch protection / ruleset coverage** for `compliance-engine`:
  ensure it is covered by the appropriate org ruleset bucket (signed commits if
  required for infrastructure repos) and is **not** accidentally subject to the
  regulated-app rulesets that would block routine maintenance. Verify against
  the `regulatory_tier` keying recorded in 0c.
- [ ] **2e.** **Disable the scheduled/self-running workflows in `.github`** so
  they run from `compliance-engine` only (Design Decision 3). Use **`gh workflow
  disable`** (not just editing the `schedule:` block) for `compliance-drift`,
  `project-enforcement`, `project-audit`, `sync-labels`, and
  `sync-property-topics` **in `CCTC-team/.github`**. `gh workflow disable` halts
  *all* triggers — important because `sync-labels.yml` and
  `sync-property-topics.yml` also fire on `push: branches: [main]`
  (`sync-labels.yml:5-10`, `sync-property-topics.yml:5-9`), so the Phase 5a
  deletion commit would otherwise re-fire them one last time. Leave the
  *callable* workflows live in `.github` for the overlap window. Confirm the
  same five are **enabled** in `compliance-engine`.
- [ ] **2f.** **Seed `compliance-engine`'s project-enforcement state** before
  enabling its poller/audit. The enforcement engine persists its prior snapshot
  between runs (state dir / branch); a cold start makes the first run diff
  against an empty snapshot and emit spurious drift findings or reset the
  rolling audit issue — audit noise that itself harms the ALCOA+ record. First
  determine where `.github` persists this (the `_project-state` branch /
  workflow artifact used by `handler.py --state-dir _project-state`), then carry
  it across to `compliance-engine` (e.g. push the `_project-state` branch). Only
  enable the scheduled workflows in `compliance-engine` after seeding.
- [ ] **2g.** Smoke-test one self-running workflow end-to-end from
  `compliance-engine`: trigger `sync-labels` (idempotent) and confirm it
  authenticates via the App and makes no unintended label changes.

---

## Phase 3: Token fix for the engine self-checkout (in `compliance-engine`)

> Reference: Design Decision 4 — **four** workflows, not three. This must land
> before TrialView is repointed, or the first private-repo run fails at
> checkout. For each, the `workflow_call` interface must declare the App-credential
> secrets it doesn't already have, so the TrialView caller can pass them (Phase 4).

- [ ] **3a. MODIFY:** `compliance-engine/.github/workflows/compliance-check.yml`
  — **add a `secrets:` block** (`app_client_id`, `app_private_key`) to the
  `workflow_call` interface (it has none today); add an
  `actions/create-github-app-token@v3` step before the "Checkout contract
  checker tooling" step (`:56`); add `token: ${{ steps.app-token.outputs.token }}`
  to that checkout. Highest priority — this fires on every regulated PR.
- [ ] **3b. MODIFY:** `compliance-engine/.github/workflows/project-card-promote.yml`
  — move the existing `actions/create-github-app-token@v3` step (~`:119-122`)
  **above** the `repository: CCTC-team/compliance-engine` checkout (`:100`), and
  add `token: ${{ steps.app-token.outputs.token }}` to that checkout.
- [ ] **3c. MODIFY:** `compliance-engine/.github/workflows/release.yml` — add an
  app-token mint step (from caller-passed App secrets) before the two engine
  checkouts (~`:116`, `:541`) and set `token:` on both. Add `app_client_id`/
  `app_private_key` to its `workflow_call` secrets.
- [ ] **3d. MODIFY:** `compliance-engine/.github/workflows/release-authorize.yml`
  — its `workflow_call` interface currently declares **only** `org_read_token`
  (`:56`); add `app_client_id`/`app_private_key`, add an app-token mint step,
  and set `token:` on the engine checkout (`:78`).
- [ ] **3e.** Commit. (Cannot be fully exercised until TrialView is repointed —
  verified in Phase 8. Expected failure mode if any of 3a-3d is skipped: the
  corresponding TrialView run fails at the engine `checkout` with a 404/403.)

---

## Phase 4: Repoint TrialView (keep CI green against `compliance-engine`)

- [ ] **4a. MODIFY:** the five TrialView callers — change each `uses:` from
  `CCTC-team/.github/.github/workflows/<x>.yml@main` to
  `CCTC-team/compliance-engine/.github/workflows/<x>.yml@main`:
  - `.github/workflows/compliance.yml` (→ `compliance-check.yml`)
  - `.github/workflows/gxp-traceability.yml`
  - `.github/workflows/project-card-promote.yml`
  - `.github/workflows/release.yml`
  - `.github/workflows/release-authorize.yml`

  (TrialView's sixth workflow, `ci.yml`, is **not** a caller of the engine — it
  needs no change here.)
- [ ] **4b. MODIFY:** ensure each caller passes the App credentials the engine
  self-checkout now needs (Phase 3). Add `app_client_id`/`app_private_key` as
  `secrets:` to TrialView's callers of **`compliance.yml`** (→ compliance-check —
  no secrets passed today), **`release.yml`**, and **`release-authorize.yml`**
  (passes only `org_read_token` today); `project-card-promote.yml` already passes
  them. Confirm `tooling_ref` inputs still resolve against `compliance-engine`
  refs (default `main`).
- [ ] **4c. MODIFY:** `TrialView/.github/release-targets.yml` `$schema:` (line 1)
  — repoint per Design Decision 5. Preferred: relative co-located path once
  drift distributes the schema (4d); interim/fallback: drop the line. Update the
  `CCTC-team/.github` comments (lines 4, 6, 9) to `compliance-engine`.
- [ ] **4d. MODIFY:** `compliance-engine/.github/workflows/compliance-drift.yml`
  (engine side) — extend the schema-distribution step to also push
  `release-targets.schema.json` co-located into each regulated repo, alongside
  `compliance.schema.json`, so 4c's relative `$schema:` resolves. Update the
  README/wiki note that lists what drift distributes.
- [ ] **4e. MODIFY (TrialView doc/comment references):**
  - `.compliance.yml` line 4 "Canonical schema:" comment → `compliance-engine`.
  - `.github/compliance.schema.json` `$id`/description — will be refreshed by
    drift from the canonical copy; if not waiting for a drift run, update
    directly to `compliance-engine`.
  - `CONTRIBUTING-regulated.md` line 81 (templates link) → `compliance-engine`;
    **leave** lines 20 (`ISSUE_TEMPLATE`) and 33 (`SECURITY.md`) pointing at
    `.github` (community health stays).
  - `README.md` line 9 — keep the `.github` pointer for templates/policy; add a
    `compliance-engine` pointer for schema/engine.
  - `build/release.sh` line 6 comment → `compliance-engine`.
- [ ] **4f.** Open a throwaway PR (or `workflow_dispatch`) in TrialView to fire
  `compliance` and `gxp-traceability` against `compliance-engine@main`; confirm
  green. Do **not** proceed to Phase 5 until these pass.

---

## Phase 5: Strip the public `.github` repo

> Only after Phase 4 is green. Normal-commit deletion (no history rewrite).

- [ ] **5a. MODIFY (delete):** in `CCTC-team/.github`, `git rm` everything that
  moved: `scripts/`, `docs/`, `AIPlans/`, `rulesets/`, `templates/`,
  `compliance.schema.json`, `release-targets.schema.json`, `labels.json`,
  `conftest.py`, `.github/project-enforcement.yml`, and **all**
  `.github/workflows/*.yml` (the callable ones too — TrialView no longer
  references them; the scheduled ones were disabled in 2e).
- [ ] **5b. NEW:** `.github/README.md` — fresh minimal README describing only the
  community-health purpose (templates, PR template, `SECURITY.md`, profile),
  the "how inheritance works" note (kept), and a line for org members pointing
  at the private `CCTC-team/compliance-engine` for the regulated/compliance
  machinery.
- [ ] **5c. NEW:** `.github/CLAUDE.md` — minimal guidance for the public repo
  (what it is, what stays, the inheritance constraint, "engine lives in
  compliance-engine"). Strip all engine/enforcement guidance.
- [ ] **5d. MODIFY:** `.github/.github/CODEOWNERS` — slim to the surviving paths
  (`/.github/ISSUE_TEMPLATE/`, `/.github/pull_request_template.md`,
  `/SECURITY.md`, `/profile/`). Remove `/labels.json`, `/scripts/`,
  `/.github/workflows/` lines.
- [ ] **5e.** Verify the public repo still renders the org profile and that
  `.github/ISSUE_TEMPLATE/*` + `pull_request_template.md` are intact (Phase 8
  confirms inheritance end-to-end).

---

## Phase 6: Consumer prose & org-rules audit

- [ ] **6a.** Grep `~/repos/TrialView` for any remaining `CCTC-team/.github`
  that names an **engine** artefact (CLAUDE.md, READMEs, AIPlans, docs) and
  repoint to `compliance-engine`; leave community-health references. (The
  in-progress `AIPlans/InProgress/release-pipeline-dry-run-resume.md` PR-table
  references are historical — annotate rather than rewrite.)
- [ ] **6b.** Update `~/repos/claude-org` engine references. This is **not** a
  "no change" audit — `rules/guides/regulated-gcp-systems.md` and
  `rules/guides/build-and-release.md` carry many hard links into engine
  artefacts that are moving, which would 404 for agents once `compliance-engine`
  is private:
  - **Repoint to `compliance-engine`** (engine artefacts):
    `regulated-gcp-systems.md` lines 19, 35 (`compliance.schema.json`), 29 / 309
    (`docs/alcoa-sdlc-rationale.md`), 45 / 311 / 125 / 156 / 184
    (`templates/compliance/CONTRIBUTING-regulated.md`), 45 (`compliance-drift.yml`),
    119 / 310 (`docs/commit-signing-setup.md`), 121-122 / 315
    (`rulesets/*.json`), 268 (`docs/release-authorisation.md`,
    `docs/release-process.md`), 308 (`compliance.schema.json`); and
    `build-and-release.md` line 19 (`release-targets.schema.json`).
  - **Leave pointing at `.github`** (community-health, stay public):
    `general.md` issue-template directive; `regulated-gcp-systems.md` lines 124 /
    314 (`pull_request_template.md`), 184 / 313 (`regulated_feature.yml`), 276 /
    312 (`SECURITY.md`).
  - Note: these links target a now-**private** repo; agents reach them via
    authenticated `gh` rather than anonymous web. Keep that in mind if any are
    rendered for non-members.

---

## Phase 7: Wiki migration (`~/repos/.github.wiki` → `compliance-engine` wiki)

> Reference: `_Sidebar.md` and `Home.md`. Almost everything is engine content
> and moves; only the community-health page (and the public-facing framing)
> stays with `.github`.

- [ ] **7a. NEW (wiki repo):** Initialise the `compliance-engine` wiki (create
  the first page in the UI to enable it, or push to
  `git@github.com:CCTC-team/compliance-engine.wiki.git`). Seed it by pushing a
  clone of the current `.github.wiki` so page **history** is preserved.
- [ ] **7b. MODIFY (in the `compliance-engine` wiki):** rewrite the framing
  pages for the new home:
  - `Home.md` — describe `compliance-engine` (private engine repo); drop the
    "repository is public" paragraph; keep the subsystem table minus
    community-health.
  - `_Sidebar.md` — keep the Compliance/Project-Board/Release/Rulesets/Apps/
    Operations tree; **remove** `Community-Health-Files` (it belongs to the
    public wiki).
  - `Repository-Layout.md` — rewrite to describe the `compliance-engine` layout
    (scripts/, docs/, templates/, schemas, workflows) rather than the old
    combined repo.
  - Fix every in-page cross-link: `github.com/CCTC-team/.github/...` that points
    at an **engine** file → `compliance-engine`; links to templates/`SECURITY.md`
    stay `.github`. Internal `[[Wiki-Page]]` links stay as-is (same wiki) except
    the dropped `Community-Health-Files`.
  - Delete `Community-Health-Files.md` from the `compliance-engine` wiki.
- [ ] **7c. MODIFY (in the public `.github` wiki) — slim it down:** keep a
  rewritten `Home.md` (community-health purpose + inheritance note + "engine
  docs live in the private compliance-engine wiki") plus `Community-Health-Files.md`;
  rewrite `_Sidebar.md` to just those; remove the engine pages (their history
  survives in the `compliance-engine` wiki).
- [ ] **7d.** Update `compliance-engine/CLAUDE.md`'s "Keep the wiki in sync"
  section to point at the `compliance-engine` wiki path; update `.github`'s new
  minimal `CLAUDE.md` to reference only the slimmed public wiki.

---

## Documentation

The doc updates are woven into the phases above rather than deferred, because
this *is* a documentation-bearing change. Summary of what must not be left to
drift:

- [ ] **MODIFY:** `compliance-engine/README.md` + `CLAUDE.md` — engine content,
      repo-identity reworded (1d, 7d).
- [ ] **NEW:** `.github/README.md` + `CLAUDE.md` — minimal community-health
      versions (5b, 5c).
- [ ] **MODIFY:** both wikis split and reconciled (Phase 7).
- [ ] **MODIFY:** TrialView prose/docs repointed (4e, 6a).
- [ ] **AUDIT:** `claude-org/rules/general.md` (6b) — change only if it names an
      engine file; template references stay.
- [ ] **MODIFY:** README/wiki note on what compliance-drift distributes, now
      including `release-targets.schema.json` (4d).

---

## Verification — "back to the same state"

The pipeline must end green and equivalent to the Phase 0b baseline, driven from
`compliance-engine`.

### Engine integrity
- [ ] `python -m pytest scripts/project_enforcement/tests` passes in
      `compliance-engine` (full suite, from repo root).
- [ ] `git log` in `compliance-engine` shows the full pre-split history (not a
      single import commit) — confirms history preservation.

### Reusable-workflow resolution & token fix (the private-repo risk)
- [ ] TrialView `compliance` (→ `compliance-check.yml`) and `gxp-traceability`
      runs succeed against `compliance-engine@main` (Phase 4f). The `compliance`
      run specifically proves the **compliance-check** engine-checkout token fix
      (Phase 3a) — the highest-traffic of the four and the easiest to forget.
- [ ] TrialView `project-card-promote`, `release-authorize`, and `release`
      runs succeed — specifically the steps that `checkout` the engine repo,
      proving the App-token fix (Phase 3b-3d) works for a **private** source. A
      failure in any of the four manifests as a checkout 404/403 error.
- [ ] `release-authorize` still correctly verifies approver-team membership via
      `org_read_token` (unchanged behaviour).

### Release dry-run equivalence
- [ ] Resume the in-progress TrialView release dry-run
      (`AIPlans/InProgress/release-pipeline-dry-run-resume.md`) and confirm it
      reaches the **same** state/outcome it was tracking before the split —
      this is the user's explicit "same state" anchor.

### Scheduled workflows: exactly one owner
- [ ] `compliance-drift`, `project-enforcement`, `project-audit`,
      `sync-labels`, `sync-property-topics` run **only** from
      `compliance-engine` (disabled in `.github`). Confirm via
      `gh run list` on both repos — no duplicate/competing runs.
- [ ] The Phase 5a deletion commit does **not** trigger a final
      `sync-labels`/`sync-property-topics` run in `.github` (proves the
      `push:` triggers were fully disabled in 2e, not just the schedule).
- [ ] `compliance-engine`'s first project-enforcement/audit run produces **no
      spurious drift findings** — confirms the `_project-state` seed (2f)
      carried the prior snapshot across.
- [ ] A drift run pushes both `compliance.schema.json` **and**
      `release-targets.schema.json` co-located into TrialView; TrialView's
      `release-targets.yml` `$schema:` resolves (no IDE 404).
- [ ] The project-board poller still promotes/holds cards correctly with no
      double-writes.

### Community-health inheritance intact (public side untouched in function)
- [ ] Public `.github` still serves issue templates: in a repo with no local
      templates, `gh api repos/CCTC-team/.github/contents/.github/ISSUE_TEMPLATE/bug_report.yml`
      resolves and the org template picker still offers the four templates.
- [ ] Org profile README still renders on the org home page.
- [ ] `SECURITY.md` advisory path still resolves.

### Reference hygiene (no stale pointers)
- [ ] Org-wide grep: **no** remaining `CCTC-team/.github/.github/workflows/...`
      references anywhere (TrialView, claude-org). All callable-workflow
      references now point at `compliance-engine`.
- [ ] `claude-org` grep: the engine links in `regulated-gcp-systems.md` /
      `build-and-release.md` (6b) now point at `compliance-engine`; the
      community-health links (`general.md` templates, `SECURITY.md`,
      `regulated_feature.yml`, `pull_request_template.md`) still point at
      `.github` and still resolve.
- [ ] **No** raw-URL `$schema`/link pointing at a now-private `compliance-engine`
      file (would 404 for un-tokened fetchers) — all such are co-located
      relative or member-web links.
- [ ] Links that *should* stay on `.github` (templates, `SECURITY.md`, profile)
      still do and still resolve.

### Platform/permissions
- [ ] `compliance-engine` → Actions → Access permits org repos (2a).
- [ ] The App is installed on `compliance-engine` with the needed scopes (2b);
      `gh secret list` shows the required secrets (2c).
- [ ] `compliance-engine` sits in the correct ruleset bucket (2d) — routine
      maintenance is not blocked, required protections are present.

### Wiki
- [ ] Both wikis render; sidebars valid; no broken `[[links]]`.
- [ ] Engine pages exist in the `compliance-engine` wiki **with history**;
      public wiki carries only `Home` + `Community-Health-Files`.
- [ ] No wiki page still claims the engine lives in a public repo.
