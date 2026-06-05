# Release process: milestones, releases, and the pull-agent

This note describes how a regulated CCTC system goes from merged code to a
running production deployment, and what evidence each release leaves behind. It
is inspector-facing: it explains *where* the release evidence ICH E6(R3) and
ALCOA+ expect actually lives.

The model has one governing principle: **production accepts no inbound
connection.** Nothing — no laptop, no CI runner — pushes to or SSHes into a
production server. Instead, CI builds and signs an artifact, and an agent *on
the server* pulls it. The server only ever makes **outbound** calls to GitHub
and the container registry.

## Three orthogonal layers

A regulated change is tracked by three independent things. Keeping them separate
is what makes a release statement defensible.

| Layer | Question it answers | Where it lives |
| --- | --- | --- |
| **Project board status** | Where is this *feature* in its V&V lifecycle? | The "Regulated Feature Lifecycle" board (`Triage … Released`) |
| **Milestone** (`vX.Y.Z`) | Which requirements does this *release* cover? | A GitHub Milestone; one milestone = one release |
| **Release** | What was *published*, and with what evidence? | A GitHub Release on a signed `vX.Y.Z` tag |

A regulated issue therefore carries both a board *status* and a *milestone*. One
milestone groups the requirement set for exactly one release. That is what lets
a release note say *"release 1.4.0 validated REQ-024/031/040 covering CtQ
factor FRM129-…"* — a per-commit micro-tag could never make that claim.

## End-to-end flow (pull-agent model)

```
  milestone vX.Y.Z opened
        │
        ▼
  issues worked through the board ─► … ─► User acceptance ─► QA approved
        │                                  (feature sign-off)   (independent QA)
        ▼
  PR merged to main
        │
        ▼
  build pushes a SIGNED tag  vX.Y.Z
        │
        ▼
  ┌─────────────────────── CI: reusable release workflow ───────────────────────┐
  │  build ─► package (OCI image(s), one per component) ─► publish:registry      │
  │  sbom (one per image) ─► vuln scan ─► sign the release manifest (tag→digests) │
  │  validation-docs ─► SHA256SUMS ─► milestone-scoped notes + CtQ matrix        │
  │  gh release create:  evaluate → DRAFT  |  active+approvers_team → DRAFT+issue │
  │                      active (no team)  → PUBLISHED                            │
  └──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ChatOps authorisation  (qa-approvers /approve on the digest-bound issue;
        │                  author ≠ approver; publishes the draft Release)
        ▼
  ┌─────────────────────── on-server pull-agent ────────────────────────────────┐
  │  poll for the approved, published Release for this app                        │
  │  ssh-keygen -Y verify the signed release-manifest ─► trust its digests        │
  │  pull image BY DIGEST ─► docker compose up -d --no-deps ─► verify:production   │
  │  append an audit-log line (prior digest, new digest, verification, boot)      │
  └──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  board card advanced to  Released  (gated on the published Release + its evidence)
```

The split between **CI targets** (`build`, `package`, `publish:registry`,
`validation-docs`, `sbom`) and **agent targets** (`deploy:*`, `verify:*`) is the
heart of the model: the trustworthy image is built once in a hardened runner
with an OIDC identity, and the server only verifies and runs it. See the build
target contract in claude-org `rules/guides/build-and-release.md`.

The release-authorisation gate aligns with the board's **`QA approved → Released`**
transition — it fires only after *both* `User acceptance` (feature-level sign-off
in a dev/test environment) and `QA approved` (independent QA). The formal
Performance Qualification is performed on the built release candidate at this
gate, not earlier on the board.

## What every regulated Release carries

Each published Release for a regulated repo bundles the evidence below. A repo
ships **one or more component images** (e.g. a Blazor host *and* an F# API); each
image is listed by digest in the signed manifest and SBOM'd independently, and the
agent deploys the set atomically. The images live in GHCR (referenced by digest),
not as Release assets.

| Artifact | What it is | Clause it answers |
| --- | --- | --- |
| **Image digest(s)** (`ghcr.io/…@sha256:…`, one per component) | The exact, immutable artifact(s) that run | ICH E6(R3) §4.3.4 (validated state is the thing deployed); ALCOA+ *Original* |
| **Signed release manifest** (one per release) | The `tag → per-component digest` map, SSH-signed by the org release-signing key; the agent verifies it against `allowed_signers` before deploying (see [release-signing-setup.md](release-signing-setup.md)) | ICH E6(R3) §4.3.5 (controlled release); ALCOA+ *Attributable* |
| **SBOM** (per image) | CycloneDX bill of materials, one per image, attached to the Release and checksummed | Cyber Essentials / supply-chain; dependency vulnerability posture |
| **Validation report** | CtQ → URS → V&V → acceptance → QA summary for the milestone | ICH E6(R3) §4.3.4 (validation evidence) |
| **CtQ traceability matrix** | CtQ factor (FRM129) → Risk → Requirement → `.feature` → acceptance/QA approver | ICH E6(R3) Principle 6 (CtQ); ALCOA+ *Complete* |
| **`SHA256SUMS`** | Checksums over the attached file assets | ALCOA+ *Accurate*, tamper evidence |
| **Release authorisation record** | Approver identity + UTC + image digest(s), from the `/approve` on the authorisation issue | ICH E6(R3) §4.3.5; ALCOA+ *Contemporaneous*, *Attributable* |

Inspector "where is X" shortcut: the images are in **GHCR** (by digest); the
signed release manifest, validation report, SBOM, checksums, notes and
authorisation block are on the **GitHub Release**; the formal re-authenticated
e-signature of record is in the application's signature flow or the CTU QMS/eTMF
(see [release-authorisation.md](release-authorisation.md)).

> **Why no GitHub attestation.** GitHub artifact attestations are deliberately
> **not** used: persisting them for a private repo requires GitHub Enterprise
> Cloud, which this org does not hold. Origin is instead proven by the **SSH-signed
> release manifest** (org signing key, verified by the agent against
> `allowed_signers`) plus content-addressed digests — equivalent origin + integrity
> with no licence. The full risk assessment is in
> [release-provenance-risk-assessment.md](release-provenance-risk-assessment.md);
> key setup in [release-signing-setup.md](release-signing-setup.md).

## Conventions

- **Versioning is SemVer** — `vMAJOR.MINOR.PATCH`. A `-rc`/`-beta` suffix marks a
  prerelease (the agent never auto-deploys a prerelease or a draft to production).
- **One milestone per release.** Assign every issue in the release to its
  milestone; close the milestone when the Release publishes.
- **Tags are signed and immutable.** The `tag` build target produces a signed
  annotated tag; a tag ruleset prevents a published `v*` tag from being moved or
  deleted, matching the immutability of the image digest.

## Rollout: evaluate → active

The release pipeline graduates from `evaluate` to `active` like the other
regulated controls, watched for a cycle before each step is turned on. The two
modes differ in what they produce and enforce:

**`evaluate`** (the starting point):

- The release workflow runs end to end and cuts a **draft** Release with the
  full artifact set — image digest, signed release manifest, SBOM(s), validation
  report, CtQ traceability matrix, `SHA256SUMS`. The team inspects this output
  for real, but nothing is published.
- The vulnerability scan **warns** on critical/high findings but does not fail.
  It does, however, **fail the build in either mode if the scan itself does not
  complete** (e.g. grype's vulnerability DB fails to download) — an image that was
  never scanned is never certified clean.
- The pull-agent **ignores drafts**, so nothing auto-deploys to production. The
  draft is for human inspection only.

**`active`** (after a clean evaluate cycle):

- The workflow cuts a **published** Release. If `approvers_team` is set, it
  instead cuts a **draft** and opens a digest-bound authorisation issue;
  publication waits for a `/approve` from a non-author member of that team
  (the Team-compatible gate — see [release-authorisation.md](release-authorisation.md)).
- The vulnerability scan **fails** the release on any critical/high finding, and
  (as in `evaluate`) also fails closed if the scan does not complete.
- The pull-agent sees the published, approved Release, verifies its **signed
  release manifest** against `allowed_signers`, pulls the image **by digest**, and
  deploys it — recording the deploy in its append-only audit log.

The hardened `Released` board precondition (a card may reach `Released` only
behind a *published* Release carrying the validation report) stays in `evaluate`
until the workflow has cut one green published Release **and** the agent has done
one verified staging pull-deploy — otherwise it would block legitimate cards
behind a gate whose upstream cannot yet be produced.

The current per-control status is the rollout table in the repository
[`README.md`](../README.md#release-pipeline-rollout-log).
