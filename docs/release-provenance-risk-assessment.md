# Release provenance: risk assessment for deploying without GitHub attestations

> **Status: documentation of a design decision.** This note records *why* the
> release pipeline proves provenance with a signed manifest rather than GitHub
> attestations. It does not need approval in its own right — the decision is
> reviewed and signed off as part of the **wider validation/approval of the
> release process**, of which this note is one input.

This note records the regulatory rationale for **not** treating GitHub artifact
attestations (SLSA build provenance) as a required control in the regulated
release/deploy pipeline, and for relying instead on **content-addressed digest
verification plus an SSH-signed release manifest** within an access-controlled
chain. It is inspector-facing: it documents a deliberate, risk-assessed design
choice rather than a silent gap. It
is the companion to [release-process.md](release-process.md),
[release-authorisation.md](release-authorisation.md),
[alcoa-sdlc-rationale.md](alcoa-sdlc-rationale.md) and
[risk-proportionality-rationale.md](risk-proportionality-rationale.md).

## The control under assessment

A GitHub artifact attestation is a cryptographically signed statement that *an
artifact with digest X was built by workflow Y, from commit Z, in repo W, at time
T*. The signature makes that provenance claim unforgeable. The threat it closes
is narrow and specific: **substitution or tampering of the built artifact between
build and deploy, or deployment of an artifact that never came from the
pipeline.** It does **not** validate the software, prove tests ran, or evidence
change control — it only pins an artifact to its origin.

The pipeline was originally designed so the on-server pull-agent runs
`gh attestation verify --signer-workflow …/release.yml` and **refuses to deploy**
any image whose attestation does not pass.

## The constraint

Persisting attestations for a **private** repository requires **GitHub Enterprise
Cloud**; the Free/Pro/**Team** plans cover public repositories only (see the
GHEC prerequisite note in [release-process.md](release-process.md)). The
CCTC-team organisation is on the
**Team** plan, so a private regulated repo such as TrialView (`gcp-critical`,
GAMP 5, 25-year retention) **cannot persist attestations today.** The release
build *generates* the provenance correctly; only persistence is blocked.

## The question

Is verifiable build provenance a **required** control for this system, such that
deployment must block without it — or is it supply-chain hardening that GxP does
not mandate, whose residual risk is adequately controlled by other means?

## The assessment

**Provenance attestation is a software-supply-chain control, not a GxP control.**
Verifiable SLSA-style provenance originates in supply-chain security practice
(US EO 14028, SolarWinds-driven). The regulations that bind this system —
**ICH E6(R3)** (computerised systems: validation, audit trail, access control,
controlled release), **EU Annex 11**, and the **MHRA 'GXP' Data Integrity
Guidance** (ALCOA+) — require *validated systems, documented change control,
traceability, access control, and an attributable audit trail*. None of them
requires cryptographic build provenance, and the overwhelming majority of
validated GxP systems have no equivalent. An inspector asks for the deployment
SOP, change records, reviewed/approved and **signed** commits, CI logs tying a
release to a commit, and restricted deployment permissions — not an in-toto
attestation.

**The residual risk is small and already inside an access-controlled boundary.**
The tampering window the attestation closes is narrow, and every link in the
chain that would have to be defeated is already a controlled GxP control:

| Compensating control | What it gives | Where |
| --- | --- | --- |
| **Content-addressed digest.** The agent only accepts `…@sha256:<64-hex>` refs and deploys exactly that digest; `docker pull` by digest verifies the bytes against the hash — the registry **cannot** serve different content for a digest. | Tamper-evidence on the artifact itself (ALCOA+ *Original*: the bytes deployed are the bytes named). | `server-structure/agent` `decision.py` |
| **SSH-signed release manifest.** CI signs the `tag → per-component digest` manifest with the org release-signing key; the agent verifies it against `allowed_signers` (the same SSH trust root the rulesets require) before trusting any digest. Forging it needs the private key, not just Release-write access. | An unforgeable **origin signature** over the deployed digests, with no GHEC/cloud licence (ALCOA+ *Attributable*). | release workflow → agent; [release-signing-setup.md](release-signing-setup.md) |
| **The digest is named by the authenticated, access-controlled GitHub Release** the pipeline cut. Substituting it requires compromising org Release-write permissions — the same boundary that protects the rulesets and audit log. | A second, independent trust root, scoped by org access control. | release workflow → Release notes |
| **Signed tag + signed commits, approver ≠ last pusher, zero bypass.** The release is cut from a signed tag over signed commits under the `gcp-critical` ruleset. | Cryptographic integrity of the **source** end of the chain (ALCOA+ *Attributable*). | branch/tag rulesets; [alcoa-sdlc-rationale.md](alcoa-sdlc-rationale.md) |
| **Deploy record logs digest + build run ID + commit SHA.** | The artifact → build run → reviewed, signed commit link an inspector actually wants (ALCOA+ *Complete*, *Contemporaneous*). | agent audit log (25-year retention) |
| **Restricted deployment + production Environment approval.** | Only an authorised actor causes a deploy; the QA approver is recorded. | [release-authorisation.md](release-authorisation.md) |

The artifact is therefore pinned to a reviewed, signed source commit and to an
immutable, content-verified digest **carried in an SSH-signed manifest**, recorded
in a 25-year audit trail — a complete ALCOA+ chain whose only difference from
GitHub attestation is the signing infrastructure (an org SSH key the agent
verifies, rather than GitHub's GHEC-gated Sigstore instance).

**Conclusion: residual risk is acceptable.** Verifiable build provenance is
hardening, not a regulatory requirement for this system. Deploying on the basis
of content-addressed digest verification within the access-controlled chain above
is a proportionate control consistent with ICH E6(R3) Principle 7.

## The decision

GitHub artifact attestations are **removed** from the pipeline — not parked
behind a switch — because the org will not hold the GitHub Enterprise Cloud
licence they require, so a "flip on later" capability would be dead weight on a
regulated workflow. Two zero-licence controls replace them:

1. **Content-addressed digest verification (the deploy gate).** The pull-agent
   only accepts `…@sha256:<64-hex>` refs and deploys exactly those; pulling by
   digest verifies the bytes against the hash. It refuses any malformed ref or a
   digest shared across components, and writes the digest + build run ID + commit
   SHA to the deployment audit record.
2. **An SSH-signed release manifest (the origin signature).** CI signs the
   `tag → per-component digest` manifest with a dedicated **org** signing key
   (`ssh-keygen -Y sign -n cctc-release`, secret `RELEASE_SIGNING_KEY`); the agent
   verifies it against a shipped `allowed_signers` before trusting any digest —
   the same SSH-signing trust root the branch rulesets already require for
   commits. This recovers an unforgeable origin signature with **no GHEC or cloud
   dependency**. Setup: [release-signing-setup.md](release-signing-setup.md).

The signed manifest is the **authoritative** source of what the agent deploys;
the release body's image table is human-readable only. The design documents are
amended in lockstep so no document claims an attestation is verified — see
*Amends*.

## Amends

This decision is implemented in, and its documents amended across:
`.github/workflows/release.yml` (attest job removed; manifest signed),
`templates/compliance/release-caller.yml` + each regulated caller (attestation
permissions dropped; signing key passed), the agent
(`server-structure/agent` — `agent.py`/`release.py`/`decision.py`/`config*.yml`/
`allowed_signers`/`PREREQUISITES.md`), `docs/release-process.md` +
`docs/release-signing-setup.md`, wiki `Release-Process` / `Release-Multi-Repo` /
`Release-Build-Contract`, and `README.md`.

## Decision record

| Field | Value |
| --- | --- |
| Decision | Remove GitHub attestation; deploy on content-addressed digest verification + an SSH-signed release manifest (org key, zero licence) |
| Rationale | This note (residual risk acceptable; provenance is supply-chain hardening, not a GxP requirement) |
| Recorded by | Richard Hardy |
| Date recorded | 2026-06-05 |
| Sign-off | Carried by the wider release-process validation/approval — not a standalone gate |
| Review trigger | A sponsor / Cyber-Essentials supply-chain requirement for in-toto attestation, or a release-signing key rotation/compromise |
