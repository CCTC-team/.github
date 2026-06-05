# Contributing to a regulated repo

This repository is regulated under UK clinical-trial law (see
[`.compliance.yml`](./.compliance.yml) for the exact frameworks that apply).
That changes what you can do in PRs and merges. The rules below are
**enforced** — some by CI, some by reviewers, some by org rulesets.

If you think a rule is wrong for your change, flag it in the PR description.
Don't quietly route around it.

## The merge rules

1. **No direct pushes to `main`.** Every change goes via PR with at least
   one review from someone other than the author. Force-pushes to `main`
   are blocked by org ruleset.
   - **Signed commits are required.** First-time setup at
     [CCTC-team/.github → `docs/commit-signing-setup.md`](https://github.com/CCTC-team/.github/blob/main/docs/commit-signing-setup.md).
     Unsigned commits will be rejected by the org ruleset.
2. **PR description must state regulatory impact.** Even "no impact" is
   fine — the inspector wants to see you considered it. Use the PR
   template's "Clinical / compliance checklist".
3. **Schema or audit-trail changes need a V&V issue.** Open one with
   [`regulated_feature.yml`](https://github.com/CCTC-team/.github/blob/main/.github/ISSUE_TEMPLATE/regulated_feature.yml)
   and link it from the PR. This applies to: database migrations, changes
   to logged fields, changes to electronic signature flow, changes that
   alter what users see or can do.
4. **Reason-for-change in commit messages.** Not just *what* — *why*. An
   MHRA inspector reading your `git log` should be able to tell why a
   change was made without asking you.

## Data handling rules

5. **No PID / CPI in the repo, ever.** Not in code, tests, fixtures,
   logs, screenshots, error messages, or PR comments. If you need
   realistic test data, generate or pseudonymise it. If you find PID in
   the repo, treat it as an incident — see [SECURITY.md](https://github.com/CCTC-team/.github/blob/main/SECURITY.md).
6. **Audit-trail behaviour is preserved unless a V&V issue says
   otherwise.** Migrations that drop, truncate, or rename audit-trail
   columns will be rejected on review. Tests that disable audit logging
   to make assertions easier will be rejected on review.
7. **No shared credentials.** Service accounts must be individually
   named and attributable. Anything that lets two humans share an
   identity for a GCP-relevant action breaks ALCOA+.

## Change-control rules

8. **`.compliance.yml` is owned by the QA lead.** Changes to it need
   QA-lead approval and cannot be self-approved. The `last_reviewed`
   date and `audit_trail_kind` / `account_model` / `pid_boundary` fields
   are inspector-facing — treat them as you'd treat a signed document.
9. **Validation evidence (`csv_evidence`) must be kept current.** If you
   change behaviour that the URS/FS/IQ/OQ/PQ pack describes, the pack
   gets updated in the same PR or a linked follow-up tracked before
   release.
10. **Dependency bumps need review like any other change.** No
    auto-merging dependabot PRs in this repo — every dependency change
    is a potential validation impact. Cyber Essentials Plus expects
    triaged security advisories within 14 days.

## Working with AI assistance (Claude, Copilot, etc.)

AI assistance is allowed in this repo, with two hard rules:

11. **Never paste PID or CPI into a prompt.** The same rule as #5
    applies to prompts, even transient ones. If you wouldn't send it in
    a Slack DM, don't send it to a model.
12. **Review AI-generated code like any other code.** The author of a
    PR is responsible for everything it contains. "Claude wrote it"
    isn't a defence at audit.

## Lifecycle board

Regulated work moves card-by-card through a forward-only project board.
Each regulated repo is mapped to a specific lifecycle board via its
`LIFECYCLE_PROJECT_NUMBER` repo variable; the boards under enforcement
are listed in
[`CCTC-team/.github/.github/project-enforcement.yml`](https://github.com/CCTC-team/.github/blob/main/.github/project-enforcement.yml)
under `projects:`. Ask the QA lead which board this repo lives on if
you're not sure.

The board is **enforced** by automation — moves that skip steps are
commented on, labelled `process-violation`, and (as checks graduate)
reverted.

- **Status order is enforced.** Forward moves advance one column at a
  time. Backward moves and side exits (`Redundant`, `Archived`) are
  always allowed. From `Redundant` or `Archived`, the only legal
  restoration target is `Triage` — a card cannot launder its history by
  being archived and dropped back into a later column.
- **Approver fields must be GitHub usernames.** `Acceptance Approver` and
  `QA Approver` are free-text on the card; type the username without
  the `@`. The automation validates the login via the GitHub API and
  refuses the move if it doesn't resolve.
- **Segregation of duties is required.** The PR author, Acceptance Approver,
  and QA Approver must be three distinct people. The audit flags any
  card that ends in `QA approved` with fewer than three identities.
- **Acceptance / QA checkboxes on the issue body are load-bearing.** Tick them
  before moving the card to `User acceptance` / `QA approved` — the
  automation reads them from the issue body, not from your memory.
  `User acceptance` is the feature-level acceptance sign-off (the feature
  meets the URS in a dev/test environment); it is **not** the formal
  Performance Qualification, which is performed on the built release
  candidate at the release-pipeline authorisation gate.
- **`Risk ID` / `Requirement ID` on the card mirror the issue body.**
  The issue body is canonical; edit the issue, not the card, if they
  diverge. Drift fires a comment within 5 minutes.
- **Bypasses are single-use and admin-gated.** If you genuinely need
  to skip a step, ask an org admin to apply
  `process-override:approved` on the linked issue. The label is
  honoured for one transition and cleared by the bot afterwards.
  Every bypass is recorded in the nightly audit issue.
- **Rolling audit issue.** A daily sweep maintains
  `Project enforcement drift — <board name>` in
  `CCTC-team/.github`. Findings appear there overnight; the issue is
  auto-closed when the board is clean.

## Releases & milestones

Regulated changes are released in **milestones**, not per-commit. The
mechanics:

- **Assign your issue to the target milestone (`vX.Y.Z`).** One milestone
  groups the requirement set for exactly one release. The release notes
  trace every requirement in the milestone from its CtQ factor down — an
  issue with no milestone is invisible to that matrix.
- **A Release is a published, evidenced artifact — not a tag.** Cutting a
  release builds a container image in CI, pushes it to GHCR by immutable
  digest, attaches the validation report, SBOM, checksums, the signed release
  manifest and the CtQ traceability matrix, and records who authorised it.
  The server then *pulls* that verified image; nothing pushes into production.
- **A release cannot publish without a green validation report and a signed
  release manifest.** The release workflow fails if the `validation-docs`
  target produces no report or the manifest cannot be signed, and the
  on-server agent **refuses to deploy** any digest not covered by a manifest
  whose SSH signature verifies against its `allowed_signers`. "It built" is
  not "it released".
- **The version tag must be signed**, the same as your commits. The build's
  `tag` target creates a signed tag; the release workflow refuses an
  unsigned one, and a tag ruleset stops a published `v*` tag being moved or
  deleted.
- **Production publish is gated by a `production` Environment approval** from
  the QA-approver group, bound to the exact image digest. This aligns with
  the board's `QA approved → Released` step — it happens after both
  `User acceptance` and `QA approved`. Note the GitHub approval is the
  technical gate; the formal re-authenticated electronic signature of record
  is captured per the CTU SOP (in-app or in the QMS/eTMF), referencing the
  release digest.

The full model — the three layers, the artifact set and the clause each
answers — is in
[`CCTC-team/.github → docs/release-process.md`](https://github.com/CCTC-team/.github/blob/main/docs/release-process.md).

## How CI enforces what it can

- `.compliance.yml` must parse and validate against the schema.
- README must carry the `<!-- compliance:banner -->` marker.
- `last_reviewed` must be within `review_cadence_months`.
- `schema_version` must be in the validator's supported set.

Everything else above is enforced by reviewers and rulesets, not CI.
Be a good reviewer.

---

This file is canonical at
[`CCTC-team/.github/templates/compliance/CONTRIBUTING-regulated.md`](https://github.com/CCTC-team/.github/blob/main/templates/compliance/CONTRIBUTING-regulated.md)
and pushed into each regulated repo by the compliance-drift workflow. To
change the rules for the whole org, edit it there.
