<!--
  Proforma for the regulatory-tier assessment described in
  CCTC-team/.github → docs/regulatory-tier-questionnaire.md.

  Purpose. An inspector wants to see the reasoning behind this repo's
  regulatory_tier, GAMP category, and pillar status — not only the
  values. The values live in .compliance.yml; the reasoning lives here.

  How to use.
   1. Copy this file into the regulated repo as
      docs/compliance/regulatory-tier-assessment.md (or wherever the
      repo's `csv_evidence` path points).
   2. Replace every TODO. Leave empty rationale fields empty only when
      the answer is "not applicable" — and say so explicitly.
   3. Commit. The git history of this file *is* the audit evidence of
      every reassessment.
   4. Re-run when any trigger in the questionnaire's "Re-assessment
      triggers" section fires, and append a row to the history table
      at the bottom. Do not overwrite previous decisions silently.

  Delete this comment block before committing the filled-in copy.
-->

# Regulatory tier assessment — `<repo-name>`

## Decision summary

| Field | Value | One-line reason |
| --- | --- | --- |
| `regulatory_tier` | TODO (`gcp-critical` / `gcp-supporting` / `data-protection` / `none`) | TODO |
| `gamp_category` | TODO (`3` / `4` / `5`) | TODO |
| In-scope pillars | TODO (comma-separated) | TODO |
| Re-assessment due by | TODO (date = assessment date + `review_cadence_months`) | — |

**Questionnaire version used:** `CCTC-team/.github` →
`docs/regulatory-tier-questionnaire.md` @ `<commit-sha-or-date>`

**Assessment date:** TODO
**Assessor:** TODO (name, role)
**QA reviewer:** TODO (name, role, sign-off date)
**Sponsor contact informed:** TODO (name, date)

---

## Section A — `regulatory_tier` determination

Answer each question in order. Record **Yes** or **No**, the
**evidence** you relied on (file paths, screenshots, design notes,
protocol references), and the **rationale** — i.e. *why* the
evidence supports the answer. Stop at the first **Yes**; mark
subsequent questions **N/A — earlier question triggered**.

### A1 — Does the system capture, transform, validate, or algorithmically guide clinical-trial data?

- **Answer:** TODO (Yes / No)
- **Evidence:** TODO (e.g. "src/edc/forms/*.ts implements CRF capture
  for protocol XYZ-001"; "scripts/reconcile_samples.sql joins EDC
  exports against LIMS")
- **Rationale:** TODO (which of the four sub-tests in A1 applies, and
  why this is not merely operational/metadata)

### A2 — Does the system hold trial metadata, documents, or governance artefacts without identifiable participant clinical data?

- **Answer:** TODO (Yes / No / N/A — A1 triggered)
- **Evidence:** TODO
- **Rationale:** TODO (confirm the absence of participant clinical
  data; if PI/staff personal data is present, note that this is
  governed by the `uk-statutory` pillar and does not flip the
  category to `data-protection`)

### A3 — Does the system process personal data with no trial nexus?

- **Answer:** TODO (Yes / No / N/A — A1 or A2 triggered)
- **Evidence:** TODO
- **Rationale:** TODO (confirm no trial nexus; if there is *any*
  link to a trial, return to A1/A2 rather than landing here)

### A4 — Pure dev tooling / infrastructure / docs?

- **Answer:** TODO (Yes / No)
- **Evidence:** TODO
- **Rationale:** TODO ("I'm not sure" is never `none` — escalate to
  QA before defaulting)

### Conclusion

The first **Yes** above triggered → `regulatory_tier` = **TODO**.

---

## Section B — `gamp_category` determination

GAMP 5 (ISPE, 2nd edition). The schema accepts `3`, `4`, or `5` —
infrastructure (Cat 1) is `regulatory_tier: none`; Cat 2 was retired
in GAMP 5 2nd ed.

- **Selected category:** TODO (`3` / `4` / `5`)
- **Custom code present?** TODO (Yes / No — if Yes, the answer is 5
  regardless of any off-the-shelf component)
- **Configuration scope (Cat 4 only):** TODO (workflows, edit checks,
  forms, approval chains — describe what was configured vs shipped
  as-is)
- **Vendor product (Cat 3/4 only):** TODO (name, version, support
  contract status)
- **Evidence:** TODO (link to source tree, configuration exports, or
  vendor SoW)
- **Rationale:** TODO

### Shared-library carve-out

Only relevant if this repo is a library consumed by other regulated
systems. Skip otherwise.

- **Consumers:** TODO (list the repos that import this one)
- **Strictest consumer category:** TODO
- **Inherits to:** TODO (this library's `regulatory_tier` = strictest
  consumer's)

---

## Section C — `regulatory_pillars`

Every pillar must be considered — including the ones ruled out. An
inspector wants to see deliberate exclusion, not silent omission.

| Pillar | Status | Rationale / out-of-scope reason |
| --- | --- | --- |
| `uk-statutory` | TODO (`in-scope` / `partial` / `out-of-scope`) | TODO (note HTA, CAG-S251, NHS-DSPT applicability here if relevant) |
| `mhra-csv-di` | TODO | TODO (any partial scope — e.g. governance-only — explained here) |
| `infra-security` | TODO | TODO (Cyber Essentials Plus / ISO 27001 status of the hosting; funder contractual requirements) |
| `international-ehr-standards` | TODO | TODO (FDA/EMA submission planned? If no, say so) |
| `eu-ct-regulation` | TODO | TODO (any active EU sites? CTIS routing?) |
| `samd-aimd` | TODO | TODO (does the system make or guide a clinical decision? a pure capture/governance system is no) |

---

## Section D — Inspector-readiness fields

**Mandatory if `regulatory_tier` = `gcp-critical`. Recommended
otherwise.** Mark each field N/A with a one-line reason if the
regulatory tier does not require it.

| Field | Value | Rationale / evidence |
| --- | --- | --- |
| `audit_trail_kind` | TODO (`extractable` / `read-only` / `append-only` / `none`) | TODO (where is the trail, how is it extracted, what guarantees immutability) |
| `account_model` | TODO (`named` / `named-with-roles` / `shared` / `mixed`) | TODO (any shared accounts? if mixed, which paths break attributability and why is that defensible) |
| `pid_boundary` | TODO (`separated` / `commingled` / `none`) | TODO (be honest about indirect re-identification risk — courier manifests, freezer locations, etc.) |
| `retention_years` | TODO (integer; 25 for UK CT records) | TODO (cite the regulation driving the retention) |
| `csv_evidence` | TODO (URL or repo path) | TODO (URS, FS, IQ, OQ, PQ, risk assessment — what's there and what's still missing) |
| `ctq_factors` | TODO (FRM129 ref(s) + tier per factor) | TODO (which trial Critical-to-Quality factor(s) this system safeguards, and why the tier — `critical` vs `important` — is correct; this is the anchor that lets an inspector trace CtQ factor → risk → requirement → V&V) |
| `governing_documents` | TODO (QMS doc refs + role per doc) | TODO (the SOPs / guidance / forms that govern this system's validation and risk management — e.g. CCTU/SOP040 risk-assessment, CCTU/FRM129 ctq-identification, the CSV SOP; the pointer from source control into the QMS) |

---

## Cross-checks before sign-off

Tick each before the QA reviewer signs.

- [ ] The `regulatory_tier` value above matches the org custom
      property set via `gh api -X PATCH /orgs/CCTC-team/properties/values`.
- [ ] The `regulatory_tier`, `gamp_category`, `regulatory_pillars`,
      and inspector-readiness values match what's in `.compliance.yml`.
- [ ] If `regulatory_tier` = `gcp-critical`, the schema's
      conditional `allOf` requirements are satisfied (GAMP ∈ {4, 5},
      all five inspector-readiness fields present; plus
      `ctq_factors` and `governing_documents`).
- [ ] If GAMP = 5 or `regulatory_tier` = `gcp-critical`, the
      `csv_evidence` link resolves and the pack covers URS / FS /
      IQ / OQ / PQ + risk assessment.
- [ ] Any `out-of-scope` pillar carries a `notes` field in
      `.compliance.yml` explaining why.
- [ ] The repo's `validated_paths` (in `.compliance.yml`) reflects
      the scope determined here.
- [ ] CODEOWNERS in this repo covers `/.compliance.yml` and this
      assessment file, so narrowing them routes to QA review.

---

## Sign-off

| Role | Name | Date | Signature / commit SHA |
| --- | --- | --- | --- |
| Assessor (drafter) | TODO | TODO | TODO |
| QA reviewer | TODO | TODO | TODO |
| Sponsor contact (informed) | TODO | TODO | — |

Signed commits on this file in the repo's git history are the
attributable signature. Do not amend a signed commit to "fix a
typo" in a past decision — open a new commit with the correction
and an entry in the history table below.

---

## Re-assessment history

Append a row each time the questionnaire is re-run. Do not delete
previous rows. A trial-level RBQM trigger — a substantial modification,
safety review, serious breach, audit/inspection finding, or monitoring
plan / KRI / QTL change (see the questionnaire's "Re-assessment
triggers") — is a valid reason to append a row, not only a change to the
regulatory category. Such a trigger may revise `ctq_factors` or
`governing_documents` even when `regulatory_tier` is unchanged.

| Date | Trigger | What changed vs previous | Assessor | QA reviewer |
| --- | --- | --- | --- | --- |
| TODO (initial) | Initial assessment | n/a | TODO | TODO |
