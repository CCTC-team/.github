# Release authorisation: the org-read token (`QA_ORG_READ_TOKEN`)

The Team-compatible release gate publishes a draft release when a member of the
`qa-approvers` team who is **not** the release author comments `/approve` on the
authorisation issue (see [release-authorisation.md](release-authorisation.md)).
The approval workflow (`.github/workflows/release-authorize.yml`) must verify
that membership **server-side** — it is the whole authority check, and it cannot
be trusted from the comment.

This note is the one-time operational setup for the token that lets it.

## Why the default `GITHUB_TOKEN` is not enough

The per-repo `GITHUB_TOKEN` is scoped to the repository the workflow runs in. It
**cannot read organisation team membership** (`GET /orgs/{org}/teams/
{team}/memberships/{user}` returns 404/403 for it). So the gate would have no way
to tell a `qa-approvers` member from any other commenter — anyone could
`/approve`. A token with **organisation Members: read** (`read:org`) is required,
and that is a *separate, least-privilege* credential, stored as the Actions
secret `QA_ORG_READ_TOKEN`.

`read:org` (Members: read) is **read-only** and grants nothing that can mutate a
release, the repo, or the team. The publish/close actions themselves run under
the workflow's own `GITHUB_TOKEN` (`contents: write`, `issues: write`); this
token is used *only* for the membership lookup.

## Option A — extend an existing org App installation (preferred)

The org already runs Apps for project-enforcement and compliance-drift (see
[project-enforcement-app-setup.md](project-enforcement-app-setup.md) and
[compliance-drift-app-setup.md](compliance-drift-app-setup.md)). The cleanest
provisioning is to mint a short-lived installation token from an org App that has
**Organization permissions → Members: Read-only**, the same way those workflows
do, and expose it to the approval workflow as `QA_ORG_READ_TOKEN`.

1. On the App (an existing one, or a dedicated "QA release authorisation" App):
   **Settings → Permissions → Organization → Members: Read-only.** Accept the
   permission update on the org installation.
2. Install (or confirm) the App on the regulated repositories that cut releases.
3. Provide the App's Client ID and private key as org secrets, and generate the
   token in the caller with `actions/create-github-app-token` — *or*, more simply,
   set `QA_ORG_READ_TOKEN` directly (Option B) if you are not already minting App
   tokens per run.

An App token is short-lived (expires after the run) — the least-privilege,
auto-rotating choice.

## Option B — a fine-grained PAT with org Members: read

If you are not provisioning an App for this, a **fine-grained personal access
token** works:

1. **Token owner:** the CCTC-team organisation (a fine-grained PAT scoped to the
   org, ideally owned by a service/bot account, not a person who also writes
   code — keep the read identity independent).
2. **Resource owner:** `CCTC-team`.
3. **Organization permissions → Members: Read-only.** No repository write
   permissions are needed.
4. Set an expiry and a calendar reminder to rotate (a PAT does not auto-rotate
   like an App token).

## Set the secret

Store the token as the Actions secret **`QA_ORG_READ_TOKEN`**, scoped to the
regulated release-cutting repos:

- **Org → Settings → Secrets and variables → Actions → New organization secret**
- Name: `QA_ORG_READ_TOKEN`
- Value: the App installation token (Option A) or the fine-grained PAT (Option B)
- Repository access: the regulated repos (e.g. TrialView)

Each repo's authorisation caller passes it through as
`secrets.org_read_token` — already wired in
`templates/compliance/release-authorize-caller.yml`, which the compliance-drift
workflow stubs into every regulated repo.

## Onboarding a new regulated repo

Like the signing key, the token is **shared org-wide**; onboarding a new repo
needs no new token — only that the repo is **granted access to the existing
secret**. The secret's *Selected repositories* list is a **standing, recurring
control**: it is the authoritative set of regulated release-cutting repos and
must be extended **every time a new repo enters the regulatory tier** — it does
not inherit or self-update.

1. **Org → Settings → Secrets and variables → Actions → `QA_ORG_READ_TOKEN` →
   Repository access → add the new repo.** The UI picker **appends** — tick the
   new repo and save. (If you grant via the CLI instead, `gh secret set …
   --repos` **replaces** the whole access set, so pass the *full* list of every
   release-cutting repo, not just the new one.)
2. The repo's authorisation caller already passes the secret through (it ships
   from `templates/compliance/release-authorize-caller.yml` via compliance-drift).

If this step is missed, the approval workflow cannot verify membership: every
`/approve` resolves to a non-member and is ignored, so a gated release can never
be published until the secret is granted. This is called out in the
regulated-repo onboarding checklist (wiki `Onboarding-a-Regulated-Repo`).

## What this does and does not give you

- **Does:** let the gate prove, server-side, that an approver is a current member
  of `qa-approvers` — the authority half of the author≠approver control.
- **Does not:** authorise anything by itself. The token only *reads* membership;
  publication still requires a `/approve` from a non-author member, and the
  publish action runs under the workflow's own write token, not this one.
