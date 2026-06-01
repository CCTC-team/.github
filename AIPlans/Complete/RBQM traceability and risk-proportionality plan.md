# RBQM Traceability and Risk-Proportionality Implementation Plan

## Context

The CCTU slide deck *Quality, Risk and Risk Proportionality* (v1.0,
27 May 2026) sets out what the amended UK CTR (SI 2025/538) and
ICH E6(R3) make **legally mandatory from 28 April 2026**: Quality by
Design, risk proportionality (Principle 7), Critical-to-Quality (CtQ)
factor identification, the six-step RBQM lifecycle, and the MHRA
expectation that an inspector can *trace each CtQ factor → its risks →
its controls → evidence of lifecycle oversight* as a coherent
narrative. The deck explicitly names *"fit-for-purpose validation of
computerised systems used for clinical data or endpoints"* as a CtQ
factor — so the software this repo governs sits **inside** that
narrative, not beside it.

A review of `CCTC-team/.github` against the deck found the SDLC
mechanics (Risk ID → Requirement ID → V&V, ALCOA+, GAMP, retention)
already strong, but five medium-or-above gaps in how the software
controls *connect to* the RBQM narrative. This plan integrates those
five gaps. Scope was fixed by the author's decisions:

- **(A) CtQ-factor anchor — repo-level only.** Add a `ctq_factors`
  block to `.compliance.yml` linking the system to its FRM129 entry.
  No per-feature card/issue field for CtQ in this plan.
- **(B) QMS document anchor.** Add a `governing_documents` block to
  `.compliance.yml` citing the SOPs/forms (SOP040, GD073, FRM129, …)
  that govern the system's validation and risk management.
- **(C) RBQM re-assessment triggers.** Extend the
  regulatory-tier questionnaire's trigger list with the trial-level
  RBQM triggers (substantial modification, safety review, serious
  breach/non-compliance, audit/inspection findings).
- **(D) Risk-proportionality rationale.** A new inspector-facing doc
  framing the uniform `gcp-critical` controls as the proportionate
  *validation floor*, with finer proportionality delegated to
  FRM129/SOP040 — pre-empting the "one-size-fits-all" objection the
  deck calls out as unacceptable.
- **(E) Three-tier Critical-to-Quality.** Replace the binary CtQ flag
  with FRM129's **Critical / Important / No**. *Critical* keeps
  today's PQ-Test-Type rule; *Important* requires a Test Type but not
  necessarily PQ; *No* carries no Test-Type constraint.

**Prerequisite/ordering note:** A and B are a breaking validation
change (new required fields for `gcp-critical`), so they ride a
`schema_version` bump to **3** and follow the existing schema-migration
ritual in `README.md` ("Schema evolution"). They do not become
required for `gcp-critical` repos still on `schema_version: 2`.

---

## Key References

- **`README.md`** — the single source of truth for this repo's
  process narrative. Sections that must stay in sync: *Compliance
  metadata*, *Schema evolution* (the migration ritual A/B must
  follow), *Project board enforcement → What it enforces*, and
  *Branch protection strategy*.
- **`compliance.schema.json`** — the schema to extend. Note the
  existing `allOf` conditional pattern keyed on `regulatory_tier`
  (lines 130-149); A/B add a conditional also keyed on
  `schema_version` so v2 files don't break.
- **`docs/alcoa-sdlc-rationale.md`** — the model for the gap-D doc:
  an inspector-facing "why this control exists" note cross-referenced
  from the README. Match its tone and structure (objection → answer →
  regulatory hooks).
- **`scripts/project_enforcement/checks/preconditions/in_development.py`
  and `…/requirement_defined.py`, `…/checks/drift/type_quality_consistency.py`**
  — the three checks that currently special-case
  `Critical-to-Quality == "yes"`. Gap E touches all three.
- **`scripts/project_enforcement/tests/test_preconditions.py` and
  `test_drift_checks.py`** — existing CtQ test cases (search
  `Critical-to-Quality`) that gap E must extend, not break. They
  currently assert `"Yes"` behaves as critical — keep that as a
  legacy alias.
- **`.github/workflows/compliance-check.yml`** — the validator;
  `supported_schema_versions` default is `"1,2"` (line 37). A/B bump
  it to `"1,2,3"`.
- **CCTU QMS references from the deck** — CCTU/SOP040 (Risk
  Assessment), CCTU/GD073 (CtQ guidance), CCTU/FRM129 (CtQ form),
  CCTU/SOP011 + CCTU/TPL030 (monitoring). These are the values
  `governing_documents` and `ctq_factors` will cite.

---

## Key Design Decisions

1. **Repo-level CtQ anchor, not per-feature (gap A).** The system is
   itself one CtQ factor (per the deck's "validation of computerised
   systems" example), so a `.compliance.yml` block is the natural and
   sufficient home. A per-card "CtQ Factor" field was considered and
   rejected for this iteration: it would touch the org-wide
   `regulated_feature.yml`, add a board single-select, and need a new
   precondition — disproportionate when the system→FRM129 link already
   closes the inspector's trace. Revisit if a single repo is found to
   serve multiple distinct CtQ factors that need per-feature
   attribution.

2. **New required fields are gated on `schema_version ≥ 3`, not just
   `regulatory_tier` (gaps A, B).** If the conditional keyed only on
   `regulatory_tier == gcp-critical`, every existing v2 file would
   fail validation the moment the drift workflow pushes the new schema.
   Adding `schema_version: { minimum: 3 }` to the `if` clause means v2
   `gcp-critical` files stay valid until deliberately migrated —
   exactly the "migrate at the team's pace" behaviour the README's
   migration ritual promises.

3. **`governing_documents` is a structured list with a `role` enum,
   not free text (gap B).** A `role` (`risk-assessment`,
   `ctq-identification`, `csv`, `monitoring`, `change-control`,
   `other`) lets an inspector — or a future audit check — see *which*
   QMS control each citation satisfies, rather than reading prose. It
   deliberately does **not** reproduce the granular regulation
   register (that stays in the QMS, per the README's standing
   decision); it is a pointer layer only.

4. **Three CtQ tiers with a legacy `"yes" → critical` alias (gap E).**
   FRM129 classifies Critical / Important / neither. The board field
   becomes `Critical | Important | No`. Existing cards carry `Yes`;
   rather than a flag-day board migration, the enforcement code
   normalises `yes`/`critical` → `critical`, so old and new cards both
   work during the transition. The normalisation lives in **one shared
   helper** (`scripts/project_enforcement/ctq.py`) imported by all
   three checks, so the tier vocabulary has a single definition.

5. **"Important" requires a Test Type but not PQ (gap E).** The deck
   states Important factors are *not* monitored by sponsor monitors but
   *are* monitored by coordination — i.e. they warrant verification but
   not the full PQ rigour reserved for Critical. So: Critical → Test
   Type ∈ {PQ, OQ+PQ, IQ+OQ+PQ}; Important → Test Type set (any,
   including N/A is *not* acceptable); No → no constraint. This makes
   the control itself risk-proportionate, which is the point of gap D.

6. **Gap D is documentation, not a new control.** The proportionality
   the deck demands is already expressed by the two-ruleset split
   (`gcp-critical` vs `regulated-non-critical`) and the tiered CtQ.
   What's missing is the *written rationale* that the uniform
   `gcp-critical` floor is a deliberate proportionate minimum, with
   per-feature proportionality delegated to FRM129/SOP040. A rationale
   doc (mirroring `alcoa-sdlc-rationale.md`) closes this without adding
   machinery.

7. **Gap C stays in the questionnaire, not in code.** Re-assessment
   triggers are a human process step; the questionnaire + assessment
   proforma already own that process. No enforcement check can detect
   "a substantial modification happened", so encoding it would be
   false assurance. Documentation is the correct and honest home.

---

## Phase 1: Schema v3 — CtQ-factor and QMS-document anchors (gaps A, B)

- [x] **1a. MODIFY:** `compliance.schema.json`
  - Update the `schema_version` property `description` to add:
    `v3 = adds ctq_factors + governing_documents, required for gcp-critical`.
  - Add two top-level properties:

    ```json
    "ctq_factors": {
      "description": "Critical-to-Quality factors (CCTU/FRM129) this system supports or safeguards. ICH E6(R3) Principle 6 treats fit-for-purpose validation of computerised systems handling clinical data/endpoints as a CtQ factor; this anchors the system to its FRM129 entry so an inspector can trace CtQ factor -> risk -> requirement -> V&V. Required for gcp-critical from schema_version 3.",
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "type": "object",
        "required": ["frm129_ref", "tier"],
        "additionalProperties": false,
        "properties": {
          "frm129_ref": { "type": "string", "minLength": 1, "description": "CtQ factor identifier on CCTU/FRM129 (trial-specific form ID + row, e.g. FRM129-XYZ-001#3)." },
          "tier": { "enum": ["critical", "important"], "description": "FRM129 classification. critical = compromise breaks participant safety / result reliability; important = significant but not critical. 'neither' factors are not listed." },
          "notes": { "type": "string", "minLength": 1 }
        }
      }
    },
    "governing_documents": {
      "description": "QMS documents (SOPs, guidance, forms, templates) governing this system's validation and risk management — the pointer layer between repo controls and the CTU QMS. The granular regulation register stays in the QMS. Required for gcp-critical from schema_version 3.",
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "type": "object",
        "required": ["ref", "role"],
        "additionalProperties": false,
        "properties": {
          "ref": { "type": "string", "minLength": 1, "description": "QMS document number, e.g. CCTU/SOP040, CCTU/GD073, CCTU/FRM129." },
          "title": { "type": "string", "minLength": 1 },
          "role": { "enum": ["risk-assessment", "ctq-identification", "csv", "monitoring", "change-control", "other"] }
        }
      }
    }
    ```

  - Add a third `allOf` conditional (alongside the existing two):

    ```json
    {
      "if": {
        "properties": {
          "regulatory_tier": { "const": "gcp-critical" },
          "schema_version": { "minimum": 3 }
        },
        "required": ["schema_version", "regulatory_tier"]
      },
      "then": {
        "required": ["ctq_factors", "governing_documents"]
      }
    }
    ```

  - Note: do **not** raise the top-level `required` array — these
    fields are conditionally required only for v3 `gcp-critical`.

- [x] **1b. MODIFY:** `.github/workflows/compliance-check.yml`
  - Change the `supported_schema_versions` default from `"1,2"` to
    `"1,2,3"` (line 37). This is step 1 of the README migration ritual
    ("add the new version to the validator's supported set, keeping the
    old one") — it must merge **before** any repo bumps to v3.

- [x] **1c. MODIFY:** `templates/compliance/.compliance.yml.example`
  - Bump `schema_version: 2` → `schema_version: 3`.
  - Add a `ctq_factors` block after `regulatory_pillars`, with a
    TODO-style entry and explanatory comment, e.g.:

    ```yaml
    # Critical-to-Quality factors (CCTU/FRM129) this system supports.
    # The software's fit-for-purpose validation is itself a CtQ factor
    # under ICH E6(R3) Principle 6. Cite the FRM129 entry so an inspector
    # can trace CtQ factor -> risk register -> requirement -> V&V evidence.
    ctq_factors:
      - frm129_ref: TODO-FRM129-<trial>#<row>
        tier: critical          # critical | important
        notes: TODO — which trial CtQ factor this system safeguards.
    ```

  - Add a `governing_documents` block, e.g.:

    ```yaml
    # QMS documents that govern this system's validation and risk
    # management — the pointer from source control into the QMS.
    governing_documents:
      - ref: CCTU/SOP040
        title: Risk Assessment Process for CTIMPs
        role: risk-assessment
      - ref: CCTU/FRM129
        title: Critical to Quality Factors Form
        role: ctq-identification
      - ref: TODO-CCTU/SOP-CSV
        role: csv
    ```

---

## Phase 2: Three-tier Critical-to-Quality enforcement (gap E)

TDD throughout — write the failing test, then the code. Start with the
shared helper so the three checks can build on it.

- [x] **2a. NEW (test):** `scripts/project_enforcement/tests/test_ctq.py`
  - Assert a `tier()` helper normalises: `"Yes"`/`"yes"`/`"Critical"` →
    `"critical"`; `"Important"` → `"important"`; `"No"`/`"None"`/`""` →
    `"no"` (treat empty as unset — see note); unknown → lower-cased
    passthrough.
  - Note: decide and document whether empty maps to `"no"` or a
    distinct `"unset"` sentinel — `requirement_defined` needs to tell
    "unset" apart from a deliberate "No". Recommend an `unset` return
    for empty so 2e can flag it.

- [x] **2b. NEW:** `scripts/project_enforcement/ctq.py`
  - Implement `tier(value_or_fields) -> str` per 2a. Single source of
    truth for the CtQ vocabulary and the legacy `yes → critical` alias.
  - Expose the PQ-required set: `CRITICAL_TEST_TYPES = {"PQ", "OQ+PQ", "IQ+OQ+PQ"}`
    (moved from `in_development.py`).

- [x] **2c. MODIFY (test):** `scripts/project_enforcement/tests/test_preconditions.py`
  - Extend the `in_development` cases: `Critical` + non-PQ Test Type →
    reason; `Important` + any set Test Type (e.g. `OQ`) → no reason;
    `Important` + unset Test Type → reason (the existing "Test Type
    unset" rule); `No` + non-PQ → no reason. Keep a legacy `"Yes"` case
    asserting it still behaves as `Critical`.

- [x] **2d. MODIFY:** `scripts/project_enforcement/checks/preconditions/in_development.py`
  - Replace the `_CTQ_TEST_TYPES` literal and `ctq == "yes"` branch
    with `from project_enforcement import ctq`; compute
    `tier = ctq.tier(fields)`; apply the PQ constraint only when
    `tier == "critical"`. Leave the generic "Test Type unset" check as
    the mechanism that catches an `Important` factor with no Test Type.

- [x] **2e. MODIFY (test + code):**
  `scripts/project_enforcement/checks/preconditions/requirement_defined.py`
  (and its cases in `test_preconditions.py`)
  - Tests first: `Critical-to-Quality` unset → reason (unchanged);
    add a case that a recognised tier (`Critical`/`Important`/`No`)
    passes. Optionally flag an *unrecognised* value.
  - Code: keep the "field set" requirement but phrase via
    `ctq.tier(...)` returning `"unset"`; update the reason text to
    name the three valid tiers.

- [x] **2f. MODIFY (test):** `scripts/project_enforcement/tests/test_drift_checks.py`
  - Extend `type_quality_consistency` cases: `Critical` + `N/A` →
    comment requiring PQ; `Important` + `N/A` → comment requiring a
    (non-PQ-OK) Test Type; `Important` + `OQ` → **no** comment;
    `Critical` + `PQ` → no comment (existing). Keep a legacy `"Yes"`
    case.

- [x] **2g. MODIFY:** `scripts/project_enforcement/checks/drift/type_quality_consistency.py`
  - Use `ctq.tier(fields)`. For `critical`: existing N/A→comment text
    (must include PQ). Add an `important` branch: if Test Type ∈
    {N/A, None, ""}, comment that an Important CtQ factor still
    requires a Test Type (PQ not required). No comment for `no`.

- [x] **2h. MODIFY:** `.github/ISSUE_TEMPLATE/regulated_feature.yml`
  - In the intro markdown (the list of card fields) and any CtQ
    mention, update **Critical-to-Quality** guidance to describe the
    three tiers and what each implies for Test Type. This file is
    org-wide and inherited by every repo — keep the edit to wording,
    not structure, and do not rename the load-bearing `User spec:` /
    `Feature link:` labels.

- [x] **2i. Operational (NOT a repo file — record in README rollout
      note, see Documentation):** the project board's
      `Critical-to-Quality` single-select must gain options
      **Critical / Important / No**. Retain **Yes** as a hidden/legacy
      option until existing cards are migrated; the enforcement alias
      in 2b makes both valid meanwhile. Board field options are
      org-admin configuration, applied via the board UI / API, not via
      this repo.

---

## Phase 3: RBQM re-assessment triggers (gap C)

- [x] **3a. MODIFY:** `docs/regulatory-tier-questionnaire.md`
  - Under *Re-assessment triggers* (≈ line 332), add the trial-level
    RBQM triggers from the deck (slides 11–12, 139), distinct from the
    existing software-classification triggers:
    - A **substantial modification** to the trial protocol that
      changes the system's CtQ/risk posture (even if `regulatory_tier`
      is unchanged).
    - A **safety review** outcome (IDMC/TSC) or new safety signal
      affecting data this system handles.
    - A **serious breach or serious GCP non-compliance** involving the
      system.
    - **Audit or inspection findings** touching the system or its
      validation.
    - A change to the trial's **monitoring plan / KRIs / QTLs** that
      relies on this system's outputs.
  - Add one line making explicit that these may require updating
    `ctq_factors` / `governing_documents` (Phase 1) even when the
    category is unchanged.

- [x] **3b. MODIFY:** `templates/compliance/regulatory-tier-assessment.md`
  - Add `ctq_factors` and `governing_documents` rows to *Section D —
    Inspector-readiness fields* (or a short new sub-section), so the
    proforma captures the FRM129 link and QMS citations with rationale.
  - In the *Re-assessment history* preamble, note that an RBQM trigger
    (3a) is a valid reason to append a history row, not only a category
    change.

---

## Phase 4: Risk-proportionality rationale (gap D)

- [x] **4a. NEW:** `docs/risk-proportionality-rationale.md`
  - Model on `docs/alcoa-sdlc-rationale.md`: inspector-facing,
    objection → answer → regulatory hooks. Cover:
    - The deck's Principle 7 mandate and its "one-size-fits-all is not
      acceptable" statement.
    - Why the uniform `cctc-gcp-critical` ruleset + gxp gate is a
      deliberate **proportionate floor** (the irreducible minimum for
      any system that can corrupt trial data), not an undifferentiated
      blanket.
    - Where finer proportionality actually lives: FRM129 tiering
      (Critical vs Important, now mirrored by the three-tier CtQ
      field), SOP040 risk evaluation (likelihood/consequence/
      detectability), and the `regulated-non-critical` ruleset for
      lower-risk buckets.
    - The traceability chain that demonstrates proportionate control
      selection: `ctq_factors` → risk register → Requirement ID →
      Test Type tier → V&V evidence.

- [x] **4b. MODIFY:** `README.md`
  - In *Branch protection strategy* (and/or *Category-specific*), add a
    one-line cross-reference to `docs/risk-proportionality-rationale.md`
    exactly as the signing rule references `docs/alcoa-sdlc-rationale.md`.

---

## Documentation

- [x] **MODIFY:** `README.md`
  - *Compliance metadata* section: document the new `ctq_factors` and
    `governing_documents` fields and that they are required for
    `gcp-critical` from `schema_version: 3`.
  - *Schema evolution* section: record the v2→v3 migration as a worked
    example of the existing ritual (validator first, then drift push,
    then per-repo migration PRs).
  - *Project board enforcement → What it enforces*: update the
    `Critical-to-Quality` description from binary to the three tiers
    and their Test-Type implications.
  - *Branch protection strategy*: the gap-D cross-reference (4b).
  - Add the board-field option change (2i) as a rollout note so the
    operational step is recorded, not lost in chat.
- [x] **MODIFY:** `templates/compliance/.compliance.yml.example` —
  covered structurally by 1c; ensure the inline comments read as
  guidance, not just placeholders.
- [x] **MODIFY:** `templates/compliance/regulatory-tier-assessment.md` —
  covered by 3b.
- [x] **MODIFY:** `docs/regulatory-tier-questionnaire.md` — covered by
  3a.
- [x] **CHECK:** `templates/compliance/CONTRIBUTING-regulated.md` — if
  it describes the CtQ field or the day-to-day meaning of
  Critical-to-Quality, update it for the three tiers; otherwise leave.
  **Checked: no CtQ / Test Type mention, so left unchanged.**

---

## Verification

- [x] **Schema validates the example.** Locally reproduce the CI
  validator:
  `pipx run check-jsonschema --schemafile compliance.schema.json templates/compliance/.compliance.yml.example`
  (or the venv install the workflow uses). The v3 example with both
  new blocks must pass; deleting `ctq_factors` from it must fail.
- [x] **Back-compat: a v2 gcp-critical file still validates** against
  the new schema *without* `ctq_factors`/`governing_documents`
  (confirms Design Decision 2). Construct a throwaway v2 fixture to
  check.
- [x] **Enforcement tests pass:**
  `python3 -m pytest scripts/project_enforcement/tests` — all existing
  plus the new/extended CtQ cases (2a, 2c, 2e, 2f) green.
- [x] **Legacy alias works:** a card with `Critical-to-Quality: "Yes"`
  and `Test Type: "OQ"` still produces the PQ-required reason
  (`in_development`) and the inconsistency comment
  (`type_quality_consistency`).
- [x] **Three-tier behaviour, manual trace:** `Important` + `OQ` →
  clean; `Important` + `N/A` → comment; `No` + `OQ` → clean;
  `Critical` + `IQ+OQ+PQ` → clean.
- [x] **Validator gate honoured:** `compliance-check.yml`
  `supported_schema_versions` includes `3`; a repo bumping to v3
  before this merges would (correctly) fail the "schema_version
  supported" step — confirm the default change landed.
- [x] **Docs render and links resolve:** the new
  `docs/risk-proportionality-rationale.md` is reachable from the
  README anchor, mirroring the ALCOA doc's linkage.
- [x] **No load-bearing labels renamed** in `regulated_feature.yml`
  (`User spec:`, `Feature link:`, `Risk ID:`, `Requirement ID:`
  intact).
