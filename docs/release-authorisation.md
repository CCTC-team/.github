# Release authorisation: the production gate and the e-signature of record

This note explains how production releases are authorised, and — honestly — how
far the gate gets us toward the org's electronic-signature requirement and where
the formal signature of record actually lives. It is inspector-facing: it
documents a residual gap rather than hiding one.

## The gate: a ChatOps `/approve` on a digest-bound authorisation issue

Publication of a production release is gated by a **ChatOps approval**. When a
release is cut in `active` mode with an `approvers_team` set, the release
workflow does **not** publish: it cuts a **draft** Release (carrying the full
evidence set and the signed manifest) and opens a machine-generated
**authorisation issue** in the repo, bound to the exact image digest(s) being
released. A member of the QA-approver team who is **not** the release author then
**publishes** that draft by commenting `/approve` on the issue; `/deny` closes it
unpublished. The pull-agent deploys only *published* Releases, so the publish
transition **is** the authorisation act.

> **Why not a GitHub `production` Environment with required reviewers?** That is
> the obvious mechanism, but Environment *deployment protection rules* (required
> reviewers) are a **GitHub Enterprise** feature for **private** repositories.
> This org is on GitHub **Team** and every regulated repo is private, so the
> Environment's protection rules do not even render. The ChatOps gate is the
> Team-compatible equivalent — it reproduces every guarantee the Environment
> approval gave (attributable, contemporaneous, digest-bound, author≠approver)
> using only primitives a Read-access user has on a private Team repo:
> commenting on an issue. This mirrors how the org replaced Enterprise-only
> artifact attestations with the signed release manifest.

### The QA-approver team and its access (least privilege)

The approvers are a single, standing **org team, `qa-approvers`** — not a
per-repo ad-hoc list. That team is granted **Read** access (and *only* Read) on
**every repo in regulatory scope** (any repo whose `regulatory_tier` is not
`none`). Granting it is part of [onboarding a regulated
repo](https://github.com/CCTC-team/.github/wiki/Onboarding-a-Regulated-Repo), so
the team is already in place by the time a repo cuts its first release.

**Read, never Write — this is deliberate, not an oversight.** A release approver
must **not** be able to change the artifact they authorise. Write access would
let the approver push code, merge PRs, or alter the workflow — collapsing the
independence the QA gate exists to provide (segregation of duties, ICH E6(R3)
§3.16). Read lets them see the code and the digest-bound evidence and comment
`/approve` or `/deny`; commenting on an issue needs only Read. So the QA-approver
team's access ceiling across the regulated estate is Read.

### How membership is verified (and why it can't be spoofed)

The `/approve` comment carries no authority by itself. The approval workflow
verifies, **server-side**, that the commenter is a current `qa-approvers` member
by calling the org team-membership API with a dedicated **org-read token**
(`QA_ORG_READ_TOKEN`; the default `GITHUB_TOKEN` cannot read org teams — see
[release-authorisation-token-setup.md](release-authorisation-token-setup.md)).
Only an *active* membership counts. A comment from a non-member is ignored, not
honoured.

### Configure the gate, once per release-cutting repo

1. **Grant the org `qa-approvers` team Read** on the repo (onboarding Step 10).
2. **Grant the repo access to the `QA_ORG_READ_TOKEN`** org secret
   ([token setup](release-authorisation-token-setup.md)).
3. Ensure the repo has the **authorisation caller**
   `.github/workflows/release-authorize.yml` (stubbed automatically by the
   compliance-drift workflow from
   `templates/compliance/release-authorize-caller.yml`).
4. In the repo's release caller (`.github/workflows/release.yml`), set
   `approvers_team: qa-approvers` (and `enforcement: active`) so a release is
   cut as a draft and held for `/approve`.

When `approvers_team` is set on an `active` release, the build run ends after
opening the authorisation issue (no runner blocks waiting on a human). The
separate `issue_comment`-triggered run publishes the draft on `/approve`,
recording **who** approved, **when** (UTC, from the comment timestamp), bound to
the exact **image digest(s)** in the issue record. That approval is logged,
timestamped, and attributable.

### Author ≠ approver (segregation of duties)

The release author (the actor who triggered the build run) is recorded in the
authorisation issue at creation. The approval compares the `/approve` commenter
against *that* recorded author; an `/approve` from the author is refused with a
posted reason and does **not** publish. This is the segregation-of-duties control
(ICH E6(R3) §3.16) that "prevent self-review" gave on Enterprise — enforced here
from the issue record rather than an Environment setting.

### Ordering: this is the `QA approved → Released` gate

The production approval aligns with the board's **`QA approved → Released`**
transition — the last step before `Released`. It therefore fires only after
**both**:

- `User acceptance` — feature-level acceptance against the URS in a dev/test
  environment, and
- `QA approved` — independent QA of the development evidence,

preserving the PQ-before-release ordering. The formal Performance Qualification
is performed on the built release candidate at this gate.

## What the approval *is* — and what it is *not*

The `/approve` publication is **the gate and the technical evidence**. Mapped to
ALCOA+, it is:

- **Attributable** — tied to the approving member's GitHub identity, verified as
  a `qa-approvers` member server-side.
- **Contemporaneous** — timestamped server-side in UTC at the moment the comment
  was posted, and recorded against the publish event.
- **Version-bound** — bound to the immutable `sha256` image digest carried in the
  authorisation issue. The digest *is* the record-version hash that ICH E6(R3)
  e-signatures require: any change to the released artifact is a different digest.

But it is **not, by itself, the org electronic signature of record.** The org
spec (claude-org `rules/guides/regulated-gcp-systems.md` → *Electronic
Signatures*) lists six requirements. An issue-comment approval does **not** force
**re-authentication at the point of signing** — an active GitHub session
suffices — so requirement 1 is unmet. An `/approve` is therefore necessary but
not sufficient.

### Mapping the six e-signature requirements

| # | Requirement | ChatOps `/approve` gate | Where the gap is closed |
|---|---|---|---|
| 1 | **Re-authentication at signing** | ❌ Not forced — an active session comments | Application signature flow or CTU QMS/eTMF re-auth |
| 2 | **Two-component (identity + authentication)** | ⚠️ Identity yes (membership-verified); fresh credential no | QMS/app supplies the authentication component |
| 3 | **Bound to record-version hash** | ✅ Bound to the image `sha256` digest in the issue record | — (the gate satisfies) |
| 4 | **Meaning / intent** | ⚠️ Implicit "approved for release" in `/approve`; not an explicit chosen meaning | QMS/app captures explicit meaning |
| 5 | **Manifestation** (name, role, meaning, UTC, version) | ⚠️ Partial — name + UTC + digest in the issue + Release notes | QMS/app manifests role + meaning |
| 6 | **Audit trail** | ✅ Authorisation issue thread + Release authorisation block + agent deploy log | — (the gate satisfies, reinforced by the agent log) |

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

When the draft is published on `/approve`, the approval workflow fills the notes'
`## Release authorisation` block with the approver identity, the UTC timestamp of
the approving comment, and the released image digest(s) (one per component image)
— the technical-evidence half of the picture. The block also points to where the
formal e-signature of record is held, so an inspector can follow it from the
Release to the signed QMS/app record. The authorisation issue thread (the
`/approve` comment and the published-outcome comment) is retained as the
contemporaneous audit trail.

## Residual gap, stated plainly

> A ChatOps `/approve` from a membership-verified, non-author `qa-approvers`
> member enforces the release gate and provides attributable, contemporaneous,
> digest-bound evidence. It is **not** a Part-11 / ICH E6(R3) electronic
> signature on its own, because it does not force re-authentication at the moment
> of signing. The signature of record is captured in the application or the
> QMS/eTMF, referencing the release digest. This gap is documented and accepted,
> not hidden.
