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
   [`validation.yml`](https://github.com/CCTC-team/.github/blob/main/.github/ISSUE_TEMPLATE/validation.yml)
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
