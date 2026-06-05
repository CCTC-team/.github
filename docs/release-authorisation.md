# Release authorisation: the production gate and the e-signature of record

This note explains how production releases are authorised, and — honestly — how
far a GitHub Environment approval gets us toward the org's electronic-signature
requirement and where the formal signature of record actually lives. It is
inspector-facing: it documents a residual gap rather than hiding one.

## The gate: a `production` Environment with required reviewers

Publication of a production release is gated by a GitHub **Environment** named
`production`, configured with **required reviewers** drawn from the QA-approver
group — the same role that signs the board's `QA approved` status.

### The QA-approver team and its access (least privilege)

The reviewers are a single, standing **org team, `qa-approvers`** — not a
per-repo ad-hoc list. That team is granted **Read** access (and *only* Read) on
**every repo in regulatory scope** (any repo whose `regulatory_tier` is not
`none`). Granting it is part of [onboarding a regulated
repo](https://github.com/CCTC-team/.github/wiki/Onboarding-a-Regulated-Repo), so
the team is already assignable as the `production` reviewer by the time a repo
cuts its first release.

**Read, never Write — this is deliberate, not an oversight.** GitHub only
requires a required reviewer to have *read* access to approve a deployment, and a
release approver must **not** be able to change the artifact they authorise.
Write access would let the approver push code, merge PRs, or alter the workflow —
collapsing the independence the QA gate exists to provide (segregation of duties,
ICH E6(R3) §3.16). Read lets them see the code and the digest-bound evidence and
approve or reject; it grants nothing that can mutate the release. So the QA-
approver team's access ceiling across the regulated estate is Read.

### Configure the Environment, once per release-cutting repo

1. **Settings → Environments → New environment → `production`.**
2. Add **Required reviewers**: the org `qa-approvers` team (Read-only, per above).
   Turn on **Prevent self-review** so the release author cannot approve their own
   release (segregation of duties, ICH E6(R3) §3.16).
3. Optionally set a **wait timer** and restrict deployment branches/tags to
   `v*`.
4. In the repo's release caller (`.github/workflows/release.yml`), set
   `environment: production` so the release pauses at this approval before it
   publishes.

When an `environment` is set, a dedicated approval-gate job runs after the build
and **before** the publish job, holding the run on this
Environment's required reviewers; the publish job only proceeds once approved.
GitHub records **who** approved, **when** (UTC), and the run is bound to the exact
**image digest(s)** being released (one per component image). That approval is
logged, timestamped, and attributable.

### Ordering: this is the `QA approved → Released` gate

The production approval aligns with the board's **`QA approved → Released`**
transition — the last step before `Released`. It therefore fires only after
**both**:

- `User acceptance` — feature-level acceptance against the URS in a dev/test
  environment, and
- `QA approved` — independent QA of the development evidence,

preserving the PQ-before-environment ordering. The formal Performance
Qualification is performed on the built release candidate at this gate.

## What the approval *is* — and what it is *not*

The Environment approval is **the gate and the technical evidence**. Mapped to
ALCOA+, it is:

- **Attributable** — tied to the approving reviewer's GitHub identity.
- **Contemporaneous** — timestamped server-side in UTC at the moment of approval.
- **Version-bound** — bound to the immutable `sha256` image digest. The digest
  *is* the record-version hash that ICH E6(R3) e-signatures require: any change
  to the released artifact is a different digest.

But it is **not, by itself, the org electronic signature of record.** The org
spec (claude-org `rules/guides/regulated-gcp-systems.md` → *Electronic
Signatures*) lists six requirements. A GitHub Environment approval does **not**
force **re-authentication at the point of signing** — an active session
suffices — so requirement 1 is unmet. A reviewer click is therefore necessary
but not sufficient.

### Mapping the six e-signature requirements

| # | Requirement | GitHub Environment approval | Where the gap is closed |
|---|---|---|---|
| 1 | **Re-authentication at signing** | ❌ Not forced — an active session approves | Application signature flow or CTU QMS/eTMF re-auth |
| 2 | **Two-component (identity + authentication)** | ⚠️ Identity yes; fresh credential no | QMS/app supplies the authentication component |
| 3 | **Bound to record-version hash** | ✅ Bound to the image `sha256` digest | — (GitHub satisfies) |
| 4 | **Meaning / intent** | ⚠️ Implicit "approved for release"; not an explicit chosen meaning | QMS/app captures explicit meaning |
| 5 | **Manifestation** (name, role, meaning, UTC, version) | ⚠️ Partial — name + UTC + digest in the run/release | QMS/app manifests role + meaning |
| 6 | **Audit trail** | ✅ Run log + Release authorisation block + agent deploy log | — (GitHub satisfies, reinforced by the agent log) |

## The e-signature of record

Because requirement 1 (and parts of 2, 4, 5) are not met by the platform
primitive, the **formal electronic signature of record** — re-authentication +
explicit meaning + signer identity *and role* + binding to the released
digest — is captured **outside** the GitHub approval:

- in the **application's own signature flow** (the `ElectronicSignature` pattern
  in the org guide), referencing the release digest; **or**
- in the **CTU QMS / eTMF** as a release-authorisation record, referencing the
  release digest.

Which of the two is authoritative is a per-CTU SOP decision (tracked as an open
operational follow-up). Either way, the record **references the release image
digest**, so the formal signature and the technical gate point at the same
immutable artifact.

## How the workflow records it

When `environment` is set, the release workflow's publish job runs under that
Environment and fills the notes' `## Release authorisation` block with the
approver identity, the UTC approval timestamp, and the released image digest(s)
(one per component image) — the technical-evidence half of the picture. The block also points to where the
formal e-signature of record is held, so an inspector can follow it from the
Release to the signed QMS/app record.

## Residual gap, stated plainly

> A GitHub `production` Environment approval enforces the release gate and
> provides attributable, contemporaneous, digest-bound evidence. It is **not** a
> Part-11 / ICH E6(R3) electronic signature on its own, because it does not force
> re-authentication at the moment of signing. The signature of record is captured
> in the application or the QMS/eTMF, referencing the release digest. This gap is
> documented and accepted, not hidden.
