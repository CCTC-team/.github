# System category questionnaire

A short structured assessment to decide the `system_category` org custom
property (and the rest of `.compliance.yml`) for a CCTC repo. Run this
once when a repo is created, and re-run it at every `review_cadence_months`
checkpoint or when the system's purpose materially changes.

There is no MHRA-published equivalent: ICH E6 (R3), the MHRA GxP Data
Integrity guidance, and the MHRA Inspectorate's CSV-for-GCP posts all
require the sponsor to operate a risk-based, proportionate process, but
none of them prescribe a form. This questionnaire is that form for
CCTC — derived from those sources plus GAMP 5 (ISPE) for the software
classification.

**Output.** A completed copy of the proforma template at
[`templates/compliance/system-category-assessment.md`](../templates/compliance/system-category-assessment.md),
committed to the regulated repo (typically at
`docs/compliance/system-category-assessment.md`) so its git history
is the audit trail of every reassessment. The four lettered sections
below each pin down one field of `.compliance.yml`; the proforma
captures the answer *and* the rationale. An inspector wants to see
the decision and the reasoning, not just the final value.

**Who completes it.** Drafted by the technical lead, reviewed and
signed off by the QA lead listed in `contacts.qa_lead`. Disagreements
escalate to the sponsor contact.

---

## Section A — `system_category` (the bucket)

Answer the questions in order. Stop at the first **Yes**: the
question that triggers is the category.

### A1 — `critical-trial`?

Does the system do **any** of the following for an active or planned
clinical trial?

- Capture trial data directly from participants or sites (EDC, ePRO,
  eConsent, eDiary, randomisation/IRT).
- Transform trial data in a way that feeds the CSR, statistical
  output, or regulatory submission (data-cleaning scripts, derivation
  pipelines, SDTM/ADaM mappers, statistical programs).
- Validate trial data (range checks, edit checks, query generation,
  data-integrity scripts, audit-trail tooling that gates a lock).
- Run an algorithm whose output guides clinical decision-making for a
  participant (dose adjustment, eligibility, safety triggers) — note
  this likely also pulls in the `samd-aimd` pillar.

→ **Yes to any → `critical-trial`**. Stop. Go to Section B.

### A2 — `trial-governance`?

Does the system hold trial **metadata, documents, or governance
artefacts** without holding identifiable participant clinical data?

- eTMF / regulatory document store.
- CTMS, monitoring trackers, site-management tooling.
- QMS, SOP repository, training records tied to trials.
- IMP accountability, drug-supply tooling, label generation.
- Project trackers whose contents are reviewable by an MHRA inspector
  as evidence of trial conduct — i.e. *this repo's own artefacts*
  are the governance evidence, not documentation describing a
  different repo's system. A docs-only repo describing a regulated
  system from outside it is `none` (see row 17 below).

→ **Yes → `trial-governance`**. Stop. Go to Section B.

### A3 — `personal-data`?

Does the system process personal data of any kind (UK-GDPR /
DPA 2018) **without** a trial nexus?

- HR-adjacent tooling, recruitment pipelines for staff.
- Mailing lists, contact databases, stakeholder registers.
- Non-trial research participant contact details (e.g. PPI panels).

→ **Yes → `personal-data`**. Stop. Go to Section B.

### A4 — `none`

If A1–A3 are all **No**, and the system is pure dev tooling /
infrastructure / docs with no PID and no trial nexus, the value is
`none`. No `.compliance.yml` is required.

If you cannot answer with confidence — escalate to QA before
defaulting to `none`. "I'm not sure" is never `none`.

---

## Section B — `gamp_category` (software classification)

GAMP 5 second edition, ISPE. Only categories 3/4/5 are accepted by
`compliance.schema.json` (category 1 infrastructure is `system_category:
none`; category 2 was retired in GAMP 5 2nd edition).

Pick the **highest** category that applies — if any custom code exists
in the repo, the answer is 5 regardless of what the rest is.

| If the repo is… | GAMP category |
| --- | --- |
| Off-the-shelf product used as shipped, no configuration beyond basic settings | **3** |
| Off-the-shelf product with material configuration (workflows, edit checks, forms, approval chains) — e.g. REDCap projects, RAVE studies, Veeva Vault configurations | **4** |
| Any custom-written code: in-house apps, scripts, External Modules, data-cleaning programs, derivation pipelines, bespoke web apps | **5** |

A repo that is "REDCap configuration **plus** a custom External
Module" is **5** — the EM dominates.

**If Section A landed on `critical-trial`, GAMP 3 is not permitted.**
The schema's conditional in `compliance.schema.json` restricts
`critical-trial` repos to GAMP 4 or 5. If a system is genuinely
off-the-shelf with no configuration *and* it captures or validates
trial data, the configuration was either underestimated (it should
be 4) or there is custom glue code somewhere (it should be 5) —
re-examine before recording 3.

**Trivial custom utilities.** A one-line deploy shim, an autoformat
hook, or a CI helper does not on its own push an otherwise-Cat-4
repo to 5. GAMP 5 2nd ed. permits a documented risk-based
downward classification for trivial custom components that do not
touch trial data. Default to 5; argue down to 4 only with the
rationale recorded in this proforma.

---

## Section C — `regulatory_pillars` (which clusters apply)

Mark each pillar `in-scope`, `out-of-scope`, or `partial`. The
out-of-scope ones still go in `.compliance.yml` with a `notes` field
— inspectors want evidence you considered them.

| Pillar | Mark in-scope if… | Default for UK academic trial |
| --- | --- | --- |
| `uk-statutory` | The work touches UK clinical-trial regulation, UK-GDPR/DPA, NHS-DSPT, HRA transparency, or CAG-S251 | **in-scope** (mandatory) |
| `mhra-csv-di` | The system is GAMP 4 or 5 and sits in the GCP audit trail | **in-scope** for `critical-trial` and most `trial-governance` |
| `infra-security` | The repo defines hosting, runtime, or has a Cyber Essentials Plus / ISO 27001 obligation under a funder contract | **in-scope** if NIHR/UKRI-funded |
| `international-ehr-standards` | Trial has an FDA IND, FDA NDA submission exposure, or EMA filing | out-of-scope unless explicitly noted |
| `eu-ct-regulation` | Trial has any active EU site. CTIS has been mandatory for new EU applications since 31 January 2023; legacy CTD-authorised trials had to complete transition by 31 January 2025. | out-of-scope unless EU sites are recruiting |
| `samd-aimd` | The system makes or guides a clinical decision (dose, eligibility, safety alert) | out-of-scope unless A1 question 4 was Yes |

---

## Section D — Inspector-readiness fields (`critical-trial` only)

Required when Section A landed on `critical-trial`. For other
categories these are recommended but not schema-enforced.

| Field | Question | Allowed values |
| --- | --- | --- |
| `audit_trail_kind` | Can a regulator extract a complete, immutable audit trail of who changed what data and when? | `extractable`, `read-only`, `append-only`, `none` |
| `account_model` | Is every action attributable to a named individual? Shared/service accounts break ALCOA+ attributability for any GCP-relevant action. | `named`, `named-with-roles`, `shared`, `mixed` |
| `pid_boundary` | Does the system hold direct patient-identifiable data, only pseudonymised data, or no PID? | `separated`, `commingled`, `none` |
| `retention_years` | Minimum retention. UK CT Regs (as amended by SI 2025/538, in force 28 April 2026) require **25 years** for trial records on applications submitted on or after that date; pre-amendment trials remain on the 5-year rule under the 2004 Regs. Cite which regime applies. | integer ≥ 1 |
| `csv_evidence` | Where is the URS / FS / IQ / OQ / PQ + risk assessment pack? | URL or repo path |
| `requirements.audit_trail` | Is the audit trail a hard requirement, recommended, or n/a? Critical-trial systems have no defensible "n/a" answer. | `required`, `recommended`, `not-applicable` |
| `requirements.electronic_signatures` | Are e-signatures required (e.g. data lock, IMP accountability, sponsor sign-off)? | `required`, `recommended`, `not-applicable` |
| `requirements.validation_documentation` | URS / FS / IQ / OQ / PQ pack — required for critical-trial. | `required`, `recommended`, `not-applicable` |
| `requirements.change_control` | Formal change control (CAB / change request workflow) or lightweight (PR review only)? | `formal`, `lightweight`, `not-applicable` |
| `requirements.access_review_frequency` | How often is user access reviewed? | `monthly`, `quarterly`, `biannual`, `annual` |

The `requirements.*` block is mandatory in `.compliance.yml` for
`critical-trial` repos (the schema's `allOf` requires at least
`audit_trail`, `validation_documentation`, `change_control` to be
present) — omitting it will fail the validator.

If any of these answers is "I don't know" or "we haven't built it
yet" — the system is **not yet `critical-trial`-ready**, even if A1
says it should be. Record the gap, raise it as a regulated issue with
a Risk ID, and treat the gap as blocking trial go-live.

---

## Worked examples

| # | Repo | A | B | C in-scope pillars | `system_category` |
| --- | --- | --- | --- | --- | --- |
| 1 | In-house EDC for a CTIMP | A1 Yes (capture) | 5 | uk-statutory, mhra-csv-di, infra-security | `critical-trial` |
| 2 | REDCap External Module that auto-randomises | A1 Yes (algorithm) | 5 | uk-statutory, mhra-csv-di, samd-aimd if it gates eligibility | `critical-trial` |
| 3 | SQL scripts that verify data integrity across a REDCap in-place upgrade (schema diff + row/checksum reconciliation pre- vs post-upgrade) | A1 Yes (validate) | 5 | uk-statutory, mhra-csv-di, infra-security (partial) | `critical-trial` |
| 4 | SAS / R statistical pipeline producing CSR tables, listings, figures from locked EDC export | A1 Yes (transform) | 5 | uk-statutory, mhra-csv-di | `critical-trial` |
| 5 | SDTM/ADaM mapping repo (CDISC derivations) | A1 Yes (transform) | 5 | uk-statutory, mhra-csv-di, international-ehr-standards if FDA filing | `critical-trial` |
| 6 | Safety-signal detection script that auto-flags SAEs from EDC | A1 Yes (algorithm guides clinical decision) | 5 | uk-statutory, mhra-csv-di, samd-aimd | `critical-trial` |
| 7 | Read-only monitoring dashboard reading from an EDC, no write path, no derived data feeding the CSR | A1 Yes (transform — see borderline note) | 5 | uk-statutory, mhra-csv-di | `critical-trial` |
| 8 | Reusable randomisation library imported by multiple trial systems | A1 Yes (transform; library *is* the algorithm) | 5 | uk-statutory, mhra-csv-di | `critical-trial` |
| 9 | eTMF document store (off-the-shelf SaaS, configured) | A1 No, A2 Yes | 4 | uk-statutory, mhra-csv-di (partial — governance scope only), infra-security | `trial-governance` |
| 10 | CTMS site/monitoring tracker holding visit dates, no clinical data | A1 No, A2 Yes | 4 | uk-statutory, mhra-csv-di (partial) | `trial-governance` |
| 11 | QMS / SOP repository (web app holding controlled documents and training records) | A1 No, A2 Yes | 4 or 5 | uk-statutory, mhra-csv-di (partial) | `trial-governance` |
| 12 | PPI / participant-recruitment portal that captures contact details but no trial enrolment data | A1/A2 No, A3 Yes | 4 or 5 | uk-statutory | `personal-data` |
| 13 | HR onboarding tracker for CTU staff | A1/A2 No, A3 Yes | 4 | uk-statutory | `personal-data` |
| 14 | Public-facing study website (study description only, no forms, no PID) | A1–A3 all No | 3 or 4 | none | `none` |
| 15 | Terraform repo provisioning self-hosted runners | A1–A3 all No | n/a | infra-security only (org-level, not repo-level scope) | `none` |
| 16 | CI/CD workflow templates for a regulated app, stored in a separate repo | A1–A3 all No (template only; the regulated app's own CI is in-scope) | n/a | none | `none` |
| 17 | Documentation-only repo describing a `critical-trial` system | A1–A3 all No (docs are validated artefacts of the *other* repo, not this one) | n/a | none | `none` |
| 18 | Bespoke sample chain-of-custody tool reconciling two sources (e.g. EDC "sample taken" vs LIMS "sample received") to flag outstanding samples | A1 Yes (validate — cross-source reconciliation of trial data) | 5 | uk-statutory (incl. Human Tissue Act note), mhra-csv-di, infra-security | `critical-trial` |
| 19 | Bespoke site-status dashboard: ingests trial metadata from ClinicalTrials.gov, lets authenticated sponsor staff and site PIs record whether each site is open for recruitment | A1 No (no participant data, no clinical decision), A2 Yes (site activation metadata) | 5 | uk-statutory, mhra-csv-di (partial — governance scope), infra-security; add `international-ehr-standards` if any of the listed trials carry FDA/EMA exposure | `trial-governance` |

---

### Borderline cases — why these answers

Several of the rows above are not obvious. Recording the reasoning is
the point of the questionnaire; inspectors care more about a defensible
"why" than a confident-sounding label.

**#3 — SQL data-integrity scripts around a REDCap upgrade.** This is
the canonical case where teams under-classify. The scripts themselves
don't capture data — they read it. But Section A1 calls out
"data-integrity scripts" and "validate trial data" explicitly, and a
REDCap in-place upgrade is one of the exact moments where the audit
trail and row-level consistency of *live trial data* are at risk. The
output of these scripts is the evidence the sponsor relies on to say
the upgrade was safe; if the scripts are wrong, a silent data
corruption can be signed off as clean. They are also bespoke SQL
(GAMP 5), and they directly inform a GCP decision (whether to release
the upgrade to production). Treat them as `critical-trial`, version
them under the same ruleset as the EDC, and tie each script to a
Risk ID + Requirement ID via the traceability gate. The schema diff
script in particular ("what tables and columns are added") is also
upgrade-validation evidence — keep its output as part of the CSV
pack for that REDCap version bump.

**#7 — Read-only EDC dashboard.** "Read-only" feels safer than the
underlying EDC and tempts a `trial-governance` answer. Resist it.
Anything that *displays* trial data to a decision-maker is part of
the data lifecycle the MHRA inspects: an incorrect aggregation, a
silently-dropped row, or a stale cache can mislead a DMC or trial
manager just as effectively as a write-path bug. If the dashboard's
output is ever used to make a clinical, safety, or trial-conduct
decision, it is `critical-trial`. If it is genuinely operational
(server uptime, login counts), it is not — but document the carve-out.

**#8 — Shared randomisation library.** A library has no users of its
own, only consumers. Classify it by the *strictest* category any
consumer requires. A randomisation library used by even one CTIMP is
`critical-trial`, and downgrading it because "the library doesn't
know what it's used for" is not defensible.

**#11 — QMS holding SOPs and training records.** GAMP category
depends on what's in the repo: an off-the-shelf QMS configuration is
4; a hand-built Django app implementing the same workflows is 5. The
*system_category* is `trial-governance` either way — training records
are governance evidence, not trial data — but the validation rigour
under `mhra-csv-di` scales with the GAMP category.

**#14 vs #12 — public study website vs PPI portal.** The dividing
line is whether the system *collects* personal data. A study
description page with no forms is `none`. The moment it accepts
"contact me" submissions, an email address lands in a database and
the repo crosses into `personal-data`.

**#18 — Sample chain-of-custody reconciliation.** The instinct is to
call this `trial-governance` because it feels logistical — boxes,
freezers, couriers — and not "clinical data". That instinct is
wrong. A missing sample is a missing data point: a missed PK
timepoint, a lost biomarker reading, an SAE workup that never
reached the lab. The reconciliation output drives queries to sites,
protocol-deviation reports, and ultimately whether a participant's
contribution to the endpoint is complete. That puts the tool
squarely inside A1's "validate trial data" test and makes it
`critical-trial`. Two consequences worth noting:

- **`pid_boundary` is rarely `none`.** Even if sample IDs are
  pseudonymised, courier manifests, freezer locations, or shipping
  addresses can re-identify when joined with the EDC. Default to
  `separated` and only claim `none` if you have actively excluded
  those fields from the repo's scope.
- **Human Tissue Act (HTA) sits inside `uk-statutory`.** The pillar
  list doesn't enumerate HTA, but custody, traceability, and
  consent-scope checks on human tissue are statutory in the UK.
  Record the HTA-licensed establishment and consent-scope assumptions
  in the `notes` field of the `uk-statutory` pillar so an inspector
  sees you considered them.
- **Reconciliation logic is the high-risk surface.** An off-by-one
  in a SQL `LEFT JOIN`, a silent timezone mismatch on a "sample
  collected" timestamp, or a case-sensitive ID compare can hide
  missing samples behind a clean-looking report. Each reconciliation
  rule should map to a Requirement ID and be exercised by a test
  case with a known-discrepant fixture, gated by the traceability
  workflow.

**#19 — Site-status dashboard with CT.gov ingest.** Three sub-calls
each pull in a different direction; the net answer is
`trial-governance`, and the reasoning matters.

- **Not `critical-trial`, despite the "two sources" shape.** It looks
  superficially like #18 — sponsor view vs PI view, flag the gaps —
  but the data being reconciled is *site activation metadata*, not
  participant clinical data. A wrong "open" flag can cause a
  protocol deviation (an enrolment recorded against a not-yet-open
  site), which is a CTMS-class concern, not a data-integrity-of-the-
  endpoint concern. Same family as #10. Promote to `critical-trial`
  only if the dashboard's output is wired into an automated
  enrolment gate; manual gating by a trial manager keeps it
  governance.
- **Not `personal-data`, despite authenticating named PIs.** PI
  identities, NHS affiliations, and emails are personal data and
  trigger `uk-statutory` (UK-GDPR), but the trial nexus dominates.
  `personal-data` is reserved for systems with *no* trial nexus
  (Section A3); a system that exists to manage trial sites is
  governance even if it stores PI accounts to do so.
- **ClinicalTrials.gov is an inbound trusted source, not an
  authoritative one.** CT.gov data is public, so confidentiality
  isn't the concern — integrity of the ingest path is. A tampered
  feed could mark a site "active" that the sponsor never opened, or
  silently drop a site that was withdrawn. Treat the ingest as a
  validated interface: fix the API version, log every fetch with a
  hash of the response, alert on schema drift, and don't let the
  ingest overwrite a sponsor- or PI-recorded status without an
  explicit reconciliation step. If CT.gov and the sponsor record
  disagree, surface the discrepancy — don't auto-resolve.
- **`audit_trail_kind` still matters even though we're governance.**
  An inspector will ask "when did this PI confirm the site was
  open?" The trail must be extractable and attributable to the
  named PI account — shared sponsor logins defeat the point.

**#15 / #16 / #17 — infrastructure, CI templates, docs-only.** All
three feel like they "support" regulated work, and there is a
temptation to pull them in for completeness. Don't. Section A's
"trial nexus" test is about whether *this repo's artefacts* are
themselves validated. A Terraform repo provisioning runners affects
many regulated systems but is not itself the system under
validation; its controls belong under `infra-security` at the
organisation level. The same logic applies to CI templates and
docs-only repos. If you find yourself wanting to apply
`critical-trial` controls to one of these, the right move is usually
to tighten the *consuming* regulated repo's own gates, not to
relabel the infrastructure.

---

## Re-assessment triggers

Re-run the questionnaire when **any** of the following happens, not
only at the calendar review:

- Scope change: trial adds EU sites, FDA exposure, or a SaMD-class
  feature.
- A system that was off-the-shelf gains custom code (Cat 4 → 5).
- Pseudonymised system starts holding direct PID (`pid_boundary`
  flips `separated` → `commingled`).
- A `personal-data` system starts ingesting trial data, or vice versa.
- Funder contract changes the security obligations (`infra-security`
  becomes mandatory).

Each re-run updates `last_reviewed` and, if the answers changed, the
relevant `.compliance.yml` fields and the org custom property.
