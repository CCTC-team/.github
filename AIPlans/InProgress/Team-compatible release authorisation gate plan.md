# Team-compatible release-authorisation gate Implementation Plan

## Context

Production release authorisation is currently gated by a GitHub **Environment**
(`production`) with **required reviewers** — see `docs/release-authorisation.md`
and the `authorize` job in `.github/workflows/release.yml`. That feature is
**unavailable for private repositories on GitHub Team** (it needs GitHub
Enterprise); the org is on Team and all regulated repos are private, so the
Environment's "Deployment protection rules" section does not even render. The
mechanism the whole authorisation design rests on therefore cannot be used.

This plan replaces the Environment gate with a **Team-compatible, event-driven
ChatOps approval**, the same way the org replaced Enterprise-only artifact
attestations with the signed release manifest:

- In `active`, the release workflow cuts a **draft** Release (full evidence +
  signed manifest already attached) and opens a **digest-bound authorisation
  issue** in the caller repo, then ends. No blocking job.
- A separate `issue_comment`-triggered workflow **publishes the draft** when a
  member of the `qa-approvers` team **who is not the release author** comments
  `/approve`; `/deny` closes it unpublished.

This preserves every guarantee the Environment gate gave — attributable,
contemporaneous, digest-bound, author≠approver — using only primitives a Read-
access user has on a private Team repo (commenting on an issue). The pull-agent
already deploys only *published* Releases, so "publish-on-approve" needs no agent
change.

---

## Key References

- **`.github/workflows/release.yml`** (this repo) — the reusable release
  workflow. The `authorize` job (lines ~515-522), the `release` job's
  authorisation-block + `gh release create` steps (lines ~558-665), and the
  `environment` input (lines ~61-64) are what this plan rewrites.
- **`scripts/release/sbom_scan.py`** + **`scripts/release/tests/test_sbom_scan.py`**
  — the pure-decision-core-behind-a-thin-shell pattern the new
  `authorization.py` mirrors (dataclass result, `summarize`/`load`-style pure
  functions, no I/O).
- **`docs/release-authorisation.md`** — the authoritative gate doc; its
  mechanism section and the six-requirement e-signature mapping must be rewritten
  for the ChatOps gate (the digest-bound/attributable/contemporaneous mapping
  still holds; the *vehicle* changes from Environment approval to issue comment).
- **`.github/workflows/gxp-traceability.yml`** (this repo) — the existing
  security pattern for an issue/comment-driven control: untrusted issue/PR bodies
  are written to a file and passed to Python **as data**, never interpolated into
  a shell or into Python source. The new approval workflow must follow it.
- **`docs/project-enforcement-app-setup.md`** / **`docs/compliance-drift-app-setup.md`**
  — how the org provisions an App installation token with org scope; the approval
  workflow needs `read:org` to verify `qa-approvers` membership server-side, which
  the default repo `GITHUB_TOKEN` cannot do.
- **`~/repos/claude-org/rules/general.md`** → "Raising GitHub Issues" — the org
  issue-template directive. See Design Decision 8 for why the machine-generated
  authorisation issue is a control artifact outside that directive.
- **`templates/compliance/release-caller.yml`** — the per-repo release caller
  stubbed into regulated repos by drift; a sibling `release-authorize` caller
  template is added here and to the onboarding scaffolding.

---

## Key Design Decisions

1. **Event-driven, not a blocking poll.** The reusable workflow runs on
   `ubuntu-latest`; GitHub kills any job at 6h and bills the wait. A job that
   blocks polling for a human approval is costly and cannot wait longer than 6h.
   Instead the build run ends after opening the issue, and a separate
   `issue_comment` run publishes on approval. Cheap, no time limit, no idle
   runner minutes. (Chosen over an in-run polling job.)

2. **Draft-until-approved; publish *is* the authorisation act.** `active` cuts a
   **draft** (not published) Release carrying every asset incl. the signed
   manifest; approval flips `draft=false`. The pull-agent already ignores drafts
   and deploys only published, non-prerelease Releases, so the human gate maps
   exactly onto the publish transition with **no agent change**. (Chosen over
   publishing-then-gating-deploy, which would expose an unauthorised published
   artifact.)

3. **Pure decision core (`authorization.py`) mirroring `sbom_scan.py`.** All
   approve/deny/ignore logic is a pure, unit-tested function over
   `(comment, commenter, author, is_team_member, issue_state)`; the workflow is a
   thin shell that gathers those inputs and acts on the verdict. Keeps the
   security-critical logic offline-testable, like the rest of `scripts/release`.

4. **Team membership is verified server-side with an org-read token — never
   trusted from the comment.** The default repo `GITHUB_TOKEN` cannot read org
   team membership, so the approval workflow is given an App-installation/PAT
   secret scoped to `read:org`. The decision core receives a *verified* boolean,
   computed by the shell from `gh api orgs/CCTC-team/teams/qa-approvers/
   memberships/<login>`. (Chosen over a checked-in approver list, which drifts
   from the team that also signs the board's `QA approved`.)

5. **Author ≠ approver, enforced from the issue-recorded author.** The release
   author (the actor who triggered the build run) is written into the
   authorisation issue at creation. Approval compares the commenter against *that*
   recorded value; an `/approve` from the author is refused with a posted reason.
   This is the segregation-of-duties control (ICH E6(R3) §3.16) that "prevent self
   review" gave on Enterprise.

6. **The release target is derived from the issue record, not the comment.** What
   gets published (repo, tag, run id, digests) is parsed from the
   workflow-authored issue body, server-side — the comment only signals
   approve/deny. A comment cannot redirect the gate to publish a different tag.

7. **Untrusted text is data, never code.** Comment and issue bodies are written
   to files and read by Python as data (mirroring `gxp-traceability.yml`); nothing
   from a comment is interpolated into a shell command or Python source.

8. **The authorisation issue is a control artifact, outside the human
   issue-template directive.** The org rule mandates templates for human-raised
   *defect/requirement* issues. This issue is machine-generated release-control
   evidence with its own fixed structure and a dedicated `release-authorisation`
   label; it is not a bug/feature/regulated-feature report, so it is not a
   free-form breach of that directive.

9. **Remove the Enterprise `environment` input and `authorize` job; add an
   `approvers_team` input.** When `approvers_team` is set and `enforcement:
   active`, the draft+issue path runs; when empty, `active` publishes directly
   (unchanged). The dead `environment` input, the `authorize` job, and the run-
   approvals-API authorisation-block step are deleted. Callers and the caller
   template are updated.

10. **Single-use / idempotent, like the `process-override:approved` pattern.**
    Once an authorisation issue is resolved (published or denied, issue closed),
    further comments are ignored. Re-opening is a fresh authorisation.

---

## Phase 1: Decision core — verdict logic

- [x] **1a. Tests — NEW:** `scripts/release/tests/test_authorization.py`
  - Cover `decide(...)` returning an `AuthDecision(action, reason)` where
    `action ∈ {"approve", "deny", "ignore"}`:
    - `/approve` by a team member who is not the author → `approve`.
    - `/approve` by the **author** (even if a team member) → `deny` with a
      self-review reason (SoD).
    - `/approve` by a **non-team-member** → `ignore` (no authority; not a deny).
    - `/deny` by a team member → `deny`.
    - `/deny` by a non-team-member → `ignore`.
    - Comment that is not a command (`looks good`, empty) → `ignore`.
    - Command tolerance: leading/trailing whitespace, surrounding text on later
      lines, case-insensitive (`/APPROVE`), but a command must be the first
      non-empty token of the comment (so quoting someone else's `/approve` in
      prose does not fire).
    - `already_resolved=True` → `ignore` regardless of command (idempotency).
    - `issue_is_authorisation=False` → `ignore`.
  - Note: pure inputs only — no `gh`, no network. Mirror `test_sbom_scan.py` shape.

- [x] **1b. Implementation — NEW:** `scripts/release/authorization.py`
  - `@dataclass AuthDecision: action: str; reason: str`.
  - `decide(*, comment_body, commenter, author, is_team_member, issue_is_authorisation, already_resolved) -> AuthDecision`.
  - Pure; module docstring states it is the testable core and the workflow does
    the I/O (membership lookup, publish, close), mirroring `sbom_scan.py`.

---

## Phase 2: Authorisation-issue render + parse

- [x] **2a. Tests — MODIFY:** `scripts/release/tests/test_authorization.py`
  - `render_issue(record) -> (title, body)`: body carries tag, repo, run id/url,
    recorded author, and a per-component `name ref@sha256:…` table, plus the
    `/approve` · `/deny` instruction and the SoD note. Title is stable/greppable.
  - `parse_issue(body) -> IssueRecord`: round-trips what `render_issue` wrote
    (tag, repo, run id, author, digests). Assert `parse_issue(render_issue(r)[1])
    == r`. A body missing the machine block → raises/returns `None` (so a hand-
    crafted issue cannot be parsed into a publishable target — Decision 6).
  - Digests are carried in a machine-readable fenced block (e.g. JSON), not only
    the human table, so `parse_issue` is exact and not regex-fragile.

- [x] **2b. Implementation — MODIFY:** `scripts/release/authorization.py`
  - `@dataclass IssueRecord` + `render_issue` / `parse_issue`. The machine block
    is the source of truth for `parse_issue`; the table is human-facing only.

---

## Phase 3: Reusable release workflow — draft + open issue

- [x] **3a. MODIFY:** `.github/workflows/release.yml`
  - Inputs: **remove** `environment`; **add** `approvers_team` (string, default
    `""`) — "org team slug whose members authorise an active release by
    commenting `/approve` on the authorisation issue".
  - **Delete** the `authorize` job and its `release`-job `needs`/`if` references
    to it; **delete** the "Fill the release authorisation block" step that reads
    the run-approvals API.
  - In the `release` job, define `gated = (enforcement == 'active' && approvers_team != '')`:
    - `gh release create`: cut a **draft** when `evaluate` **or** `gated` (so a
      gated active release is created unpublished); publish (`--latest` per the
      existing tag rules) only when `active && not gated`.
    - When `gated`: after creating the draft, **open the authorisation issue** in
      the caller repo using `authorization.render_issue` over `images.json` +
      `release-manifest.json`, with the recorded author = `${{ github.actor }}`,
      labelled `release-authorisation`, and write the run URL. Emit a step-summary
      line "Draft cut — awaiting `/approve` from @org/qa-approvers".
  - `permissions`: the `release` job additionally needs `issues: write` to open
    the issue.
  - Note: the notes' `## Release authorisation` block is rendered as **pending**
    at draft time; Phase 4 fills it on publish.

- [x] **3b. MODIFY:** `templates/compliance/release-caller.yml`
  - Replace the commented `# environment: production` line with
    `approvers_team: qa-approvers` guidance; keep `enforcement: evaluate` as the
    starting point. Update the header comment to describe the ChatOps gate.
  - **Deviation from plan:** also raised the caller's `issues:` permission from
    `read` to `write` (the reusable release job now opens the authorisation
    issue) and corrected the `actions: read` comment (it now scopes the build-
    artifact download, not the deleted run-approvals read).

- [x] **3c. MODIFY (deviation from plan):** `labels.json`
  - Added the `release-authorisation` org label. Decision 8 and Phase 3a require
    the issue to be `--label release-authorisation`, but `gh issue create` fails
    if the label does not exist in the repo, and labels are synced from this
    canonical file by `sync-labels.sh`. Registering it here is what makes the
    Phase 3a label assignment (and the Phase 4b caller's cheap label pre-filter)
    actually work. Also updated `notes.py`'s pending authorisation placeholder to
    name the `/approve` ChatOps gate instead of the removed `production`
    Environment.

---

## Phase 4: Approval workflow — publish on `/approve`

- [x] **4a. NEW:** `.github/workflows/release-authorize.yml` (reusable)
  - `on: workflow_call` with a `secrets: org_read_token` (App/PAT with
    `read:org`). Inputs carry the triggering comment + issue numbers/bodies from
    the caller's `issue_comment` context, written to files (Decision 7).
  - Steps: guard the issue carries the `release-authorisation` label and is open;
    `parse_issue` the body to the release target; resolve `is_team_member` via
    `gh api .../qa-approvers/memberships/<commenter>` using `org_read_token`;
    call `authorization.decide`; then:
    - `approve` → `gh release edit <tag> --draft=false` (+ `--latest` per tag
      rules), edit the notes to stamp the authorisation block (approver =
      commenter, UTC = comment `created_at`, digests from the record), comment the
      outcome, and **close** the issue.
    - `deny` → comment the reason and close (draft left unpublished).
    - `ignore` → no state change (optionally a one-line nudge for a non-authoriser
      `/approve`).
  - `permissions`: `contents: write` (publish/edit release), `issues: write`
    (comment/close). Idempotent: re-running on a closed/resolved issue is a no-op
    (Decision 10).

- [x] **Review fix (4a):** the approve/deny/ignore actions were first written as
  one `case` script with the notes-stamping Python heredoc **nested inside the
  `approve)` arm**. After YAML block-scalar stripping the `PY` terminator sat at
  column 4, so bash never closed the heredoc — on a real `/approve` the release
  would publish but the notes would not be stamped and the issue would not close
  (audit-trail loss). Refactored into three `if:`-gated steps so every heredoc
  sits at the base indentation and terminates cleanly; also made the notes-stamp
  fall back to *append* (not silently double) if the `## Release authorisation`
  marker is absent. Found by the correctness review sub-agent.

- [x] **4b. NEW:** `templates/compliance/release-authorize-caller.yml`
  - Per-repo caller: `on: issue_comment: [created]`, `if:` the issue is open and
    (cheaply) looks like an authorisation issue; calls
    `CCTC-team/.github/.github/workflows/release-authorize.yml@main`, passing the
    comment/issue context and `secrets: org_read_token: ${{ secrets.QA_ORG_READ_TOKEN }}`.

---

## Phase 5: Provisioning + onboarding wiring

- [x] **5a. NEW:** `docs/release-authorisation-token-setup.md`
  - How to provision the `read:org` token the approval workflow needs (extend an
    existing App installation, or a fine-grained PAT with org **Members: read**),
    stored as the org/repo Actions secret `QA_ORG_READ_TOKEN`. State the least-
    privilege scope and why the default `GITHUB_TOKEN` is insufficient.

- [x] **5b. MODIFY:** onboarding scaffolding list
  - Add the `release-authorize` caller to the regulated-repo scaffolding (the
    drift-stubbed caller set) so onboarded release-cutting repos get it, alongside
    granting `qa-approvers` Read (already documented) and the `QA_ORG_READ_TOKEN`
    secret access. (Reflected in the Documentation section below.)
  - **Where:** `scripts/compliance-drift.sh` — added
    `release-authorize-caller.yml` to the canonical-file sanity list and a stub
    block (`.github/workflows/release-authorize.yml`, stubbed-if-missing, never
    overwritten); updated the `.github/workflows/compliance-drift.yml` header
    list to match.

---

## Documentation

- [x] **MODIFY:** `docs/release-authorisation.md` — rewrite the mechanism from
  "Environment + required reviewers" to the ChatOps gate (draft → `/approve` by a
  non-author `qa-approvers` member → publish). State plainly that Environment
  required reviewers are Enterprise-only for private repos and this is the Team
  equivalent. Keep and re-anchor the six-requirement e-signature mapping (the
  digest-bound/attributable/contemporaneous evidence now comes from the issue +
  publish event; the formal e-signature of record still lives in the QMS/app).
- [x] **MODIFY:** `docs/trialview-go-live-runbook.md` §A — replace the
  Environment-creation steps with: ensure `qa-approvers` has Read (kept), add the
  `release-authorize` caller + `QA_ORG_READ_TOKEN`, set `approvers_team` in the
  caller. Drop the `gh api .../environments` calls (they don't gate on Team).
- [x] **MODIFY:** `.github/.github` `README.md` — the release rollout-log row and
  any "production Environment" wording; describe the ChatOps gate. (Added a
  dedicated `release authorisation (ChatOps)` rollout-log row.)
- [x] **MODIFY:** wiki `Release-Process.md` — the `active` description and the job
  graph (`authorize` job → ChatOps approval workflow).
- [x] **MODIFY:** wiki `Onboarding-a-Regulated-Repo.md` — under the release steps,
  add the `release-authorize` caller + `QA_ORG_READ_TOKEN` alongside the existing
  `qa-approvers` Read grant (Step 10) and signing-key access (Step 9). (Added as
  Step 10b.)
- [x] **MODIFY:** `CLAUDE.md` (release section, if it references the Environment
  gate) — point to the ChatOps mechanism. **No change needed:** CLAUDE.md does not
  reference the release/Environment gate (only a venv mention of "environment").
- [x] **MODIFY (deviation — additional stale references reconciled):** the change
  also touched files the plan did not enumerate but which described the removed
  Environment gate: `docs/release-process.md` (flow diagram + active description +
  evidence-table row), `docs/release-provenance-risk-assessment.md` (control row),
  and wiki `Release-Multi-Repo.md` + `Repository-Layout.md` (template/doc rows and
  the multi-repo authorisation wording). Per CLAUDE.md the wiki is reconciled in
  the same change.

---

## Verification

- [x] `python -m pytest scripts/release/tests/test_authorization.py` passes (20
  tests); full `scripts/release/tests` suite still green (91 tests).
- [x] Workflow YAML parses (`yaml.safe_load`) for `release.yml`,
  `release-authorize.yml`, and both caller templates.

The remaining items are a **live dry-run on TrialView** — they need a real tag
push, the `QA_ORG_READ_TOKEN` secret provisioned (Phase 5a), a second
`qa-approvers` account, and GitHub credentials this environment does not hold.
They are left unchecked for the operator to run at go-live (tracked in the
TrialView worked-example plan / go-live runbook §A):

- [ ] **Dry-run on TrialView (throwaway `v0.0.1-rcN` tag), `enforcement: active`,
  `approvers_team: qa-approvers`:** confirms a **draft** Release is cut and an
  authorisation issue is opened carrying the correct per-component digests.
- [ ] **Approve path:** a `qa-approvers` member (not the tag pusher) comments
  `/approve` → the draft is **published**, the notes carry the authorisation block
  (approver, UTC, digests), and the issue closes.
- [ ] **SoD path:** the tag pusher commenting `/approve` does **not** publish and
  gets the self-review reason.
- [ ] **Deny path:** `/deny` by a member closes the issue and leaves the release a
  draft.
- [ ] **Authority path:** `/approve` by a non-`qa-approvers` account does nothing.
- [ ] Clean up the throwaway tag, draft/published Release, and authorisation issue
  after verification.
