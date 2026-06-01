# ALCOA+ applied to the SDLC: why regulated repos require signed commits

This note exists to record the regulatory rationale for the
`required_signatures` rule in both category rulesets defined in
[../README.md#category-specific](../README.md#category-specific).
It is intended as inspector-facing evidence that the control was
chosen deliberately, not by reflex.

## The objection

ALCOA+ was originally written for **clinical trial data** — case
report forms, lab results, patient diaries, audit-trail entries in
the EDC. A developer writing code for an EDC is not signing a patient
record. So why does enforcement of `required_signatures` belong in
the branch-protection ruleset for `gcp-critical` *and*
`gcp-supporting` / `data-protection` repos, rather than only at the
data layer?

## The answer: ALCOA+ extends up the chain of trust

In modern computerised clinical trials, regulators (FDA, EMA, MHRA)
treat the software managing trial data as a critical component of the
trial's compliance footprint. Frameworks that explicitly bridge SDLC
practice to data integrity:

- **GAMP 5** (Good Automated Manufacturing Practice) — classifies
  EDCs and similar systems as computerised systems whose source code
  directly impacts patient safety and data integrity.
- **ICH E6(R3)** — extends GCP expectations to the lifecycle of
  computerised systems, not only the data they hold.
- **MHRA GxP Data Integrity Guidance (2018)** — applies ALCOA+
  principles to "the lifecycle of GxP records", which includes the
  systems that generate and modify those records.

A bug or unauthorised change in EDC code could silently corrupt
clinical data (e.g. flipping a `>` to a `<` in a validation script,
or dropping an audit-trail column in a migration). The code itself is
therefore part of the chain that must be attributable, traceable, and
unforgeable.

## How ALCOA+ maps from trial data to repository hygiene

| ALCOA+ principle | Applied to trial data (traditional) | Applied to EDC / regulated-system code (modern) | Control in our rulesets |
| --- | --- | --- | --- |
| **Attributable** | Who recorded the patient's adverse event? | Who wrote this data-integrity script or changed this schema? | `required_signatures` — commit signing cryptographically binds the change to an identity |
| **Legible** | Can a regulator read the CRF or database entry? | Is the source code readable, are peer-review logs and PR approvals preserved? | PR-required rule + audit log retention |
| **Contemporaneous** | Was the blood pressure logged at the time taken? | Was the code reviewed and approved before merge? | `pull_request` rule with `dismiss_stale_reviews_on_push` |
| **Original** | First entry, or transcription? | Is this the original, untampered source code? Did the build pull from `main`? | `non_fast_forward`, `required_linear_history` (gcp-critical), branch-deletion block |
| **Accurate** | Is the dosage recorded correctly? | Does the code do what it is supposed to? | Required status checks (per-repo, as CI lands) |

## The chain of trust

The integrity of the patient record depends on a chain of evidence:

1. **Patient data** must have an immutable audit trail — the EDC's
   own audit log.
2. **To trust that log**, the *features* of the EDC must themselves
   be validated — URS / FS / IQ / OQ / PQ documentation.
3. **To trust those features**, the *source code* implementing them
   must have an immutable, attributable history — GitHub rulesets,
   signed commits, PR approvals.

A developer signing a commit is not signing a patient record. They
are cryptographically certifying the integrity of the machine that
holds the patient record. This is why `required_signatures` is
enforced for `gcp-critical` repos — but it is also why the same
rule applies to `gcp-supporting` and `data-protection` repos: the
attributability principle does not weaken because the data nexus is
softer. UK-GDPR Art 5(1)(f) (integrity and confidentiality) makes
the same demand for personal data, and gcp-supporting systems
(eTMF, CTMS, QMS) are themselves validated computerised systems
under ICH E6(R3).

## What this justifies in the rulesets

- `required_signatures` in **both** `cctc-gcp-critical` and
  `cctc-regulated-non-critical` — attributability applies to every
  regulated category, not only the GCP-strictest.
- `require_last_push_approval` and zero bypass actors in
  `cctc-gcp-critical` only — these implement segregation of duties
  as required by ICH E6(R3) Principle 10 (Roles and Responsibilities)
  and §3.10 (Quality Management), reinforced by MHRA GxP Data
  Integrity Guidance. (ICH E6(R3) §3.16 *Data and Records* covers
  record keeping and audit trails — relevant to the attributability /
  signing rule above, not to segregation of duties.) The non-critical
  regulations have no direct four-eyes equivalent.
- The decision *not* to require signed commits for repos with
  `regulatory_tier == none` — these systems sit outside the chain of
  trust and the control would be unjustified friction.
