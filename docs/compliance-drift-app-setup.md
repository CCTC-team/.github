# Provisioning the `CCTC Compliance Drift` GitHub App

This runbook is the provisioning record for the GitHub App backing
the nightly compliance-drift workflow (`.github/workflows/compliance-drift.yml`).
The workflow needs an installation token for a GitHub App that can
commit drift fixes and open PRs across every regulated repo in the
org; this guide creates that App, installs it, and wires up the two
org secrets the workflow reads.

The parallel here is the existing `CCTC Label Sync` App
(`ORG_LABEL_SYNC_APP_CLIENT_ID` / `ORG_LABEL_SYNC_APP_PRIVATE_KEY`) —
the steps below are terse where they duplicate that setup.

## Why a separate App rather than expanding `CCTC Label Sync`

Label Sync has `Issues: write` only. Compliance Drift needs Contents
and Pull Requests at read & write, plus Custom Properties at read.
Two Apps means you can revoke one without affecting the other, and
the audit log clearly attributes which App made which change. Keep
them separate.

## Permissions to grant

Set exactly these on the new App — narrower than the defaults, no
broader:

| Permission | Access | Why |
| --- | --- | --- |
| **Repository → Contents** | Read & Write | Commit drift-fix patches to regulated repos |
| **Repository → Pull requests** | Read & Write | Open the PR carrying the fix |
| **Repository → Metadata** | Read | Mandatory baseline for any App |
| **Organization → Custom properties** | Read | List repos where `regulatory_tier != none` |

No webhook events are needed — the workflow polls via the GitHub API
on a cron, it does not respond to GitHub-pushed events.

## Step-by-step

### 1. Create the App

1. **GitHub → CCTC-team org → Settings → Developer settings → GitHub
   Apps → New GitHub App.**
2. Fill in:
   - **GitHub App name:** `CCTC Compliance Drift`
   - **Description:** `Nightly compliance scaffolding drift correction across regulated CCTC repos.`
   - **Homepage URL:** `https://github.com/CCTC-team/.github`
   - **Identifying and authorizing users / User authorization callback URL:** leave blank.
   - **Webhook → Active:** **uncheck** (no events needed).
3. **Permissions** — set the four rows from the table above.
   Everything else stays **No access**.
4. **Subscribe to events:** none (webhook is off anyway).
5. **Where can this GitHub App be installed?** Select **Only on this
   account** (locks installation to CCTC-team).
6. Click **Create GitHub App**.

You now have the App. Note the **Client ID** (a string starting
`Iv23li…`, shown near the top of the settings page next to the
App ID) — you'll need it for the secret in step 4. The numeric App
ID is not required by the workflow; we use Client ID because the
action's `app-id` input is deprecated in v3.

### 2. Generate a private key

1. Still on the App's settings page, scroll to **Private keys**.
2. Click **Generate a private key**. A `.pem` file downloads — treat
   it as a credential. Save it somewhere temporary you'll delete once
   the org secret is in place.

### 3. Install the App on the org

1. On the App's settings page, **Install App** in the left sidebar.
2. Click **Install** next to CCTC-team.
3. Choose **All repositories** (so any future regulated repo is
   covered automatically; the workflow's `regulatory_tier` filter
   handles which ones get acted on).
4. Confirm.

### 4. Add the two org secrets

```bash
# Client ID — pass the Iv23li… string you noted in step 1
gh secret set ORG_COMPLIANCE_DRIFT_APP_CLIENT_ID \
  --org CCTC-team --visibility selected --repos .github \
  --body "<the-client-id>"

# Private key — feed the .pem file directly so newlines are preserved
gh secret set ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY \
  --org CCTC-team --visibility selected --repos .github \
  --body "$(cat /path/to/cctc-compliance-drift.<date>.private-key.pem)"
```

Verify both landed:

```bash
gh secret list --org CCTC-team | grep COMPLIANCE_DRIFT
```

Then **delete the local `.pem` file** — the secret is the canonical
copy now, and the file is a stale credential you don't want sitting
in Downloads.

### 5. Smoke test

A dry-run kicks the workflow but skips the drift-fix PRs, so it
exercises App auth + the `regulatory_tier` lookup without changing
any repo:

```bash
gh workflow run compliance-drift.yml -f dry_run=true

# Wait a few seconds, then check the latest run
gh run list --workflow=compliance-drift.yml -L 1
gh run view --log --job="$(gh run list --workflow=compliance-drift.yml -L 1 --json databaseId --jq '.[0].databaseId')" 2>&1 | head -80
```

Look for two things in the log:

1. **The "Generate app token" step succeeds.** A failure here
   indicates the Client ID secret is wrong, the private key secret
   is wrong/malformed, or the App isn't installed on the org.
2. **The repo enumeration step lists the regulated repos** (matching
   what `gh api /orgs/CCTC-team/properties/values --jq '.[] | select(.properties[0].value != "none")'`
   returns).

Once both pass, the nightly schedule (`37 4 * * *`) takes over.

## Rotation

Private keys do not expire on the GitHub side, but rotate them on a
cadence anyway (12 months is typical, faster if a key has ever been
on a machine that left your control). To rotate:

1. Generate a new private key in App settings (you can keep multiple
   simultaneously — generate the new one before deleting the old).
2. Update `ORG_COMPLIANCE_DRIFT_APP_PRIVATE_KEY` with the new key's
   `.pem` contents.
3. Trigger a dry-run and confirm it still succeeds.
4. Delete the old key from App settings.

## If something goes wrong

- **`Bad credentials`** in the workflow log → Client ID and private
  key don't match. Re-check the Client ID against the settings page;
  re-feed the `.pem` into the secret.
- **`Resource not accessible by integration`** on a Contents or PR
  call → permissions missing. Re-check the four permission rows
  above; install-time changes need a re-acceptance from an org admin
  (GitHub will prompt).
- **No regulated repos found** in the workflow run → the
  `regulatory_tier` custom property isn't set on any repo, or the
  Custom Properties read permission is missing.
