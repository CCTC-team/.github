# Commit-signing setup for CCTC developers

This guide gets you to the point where every commit you push to a
regulated CCTC repo is cryptographically signed and shows the green
**Verified** badge on GitHub. It is a precondition for both planned
category rulesets — see
[../README.md#preconditions-before-the-category-rulesets-go-live](../README.md#preconditions-before-the-category-rulesets-go-live).

The *why* lives in [`alcoa-sdlc-rationale.md`](alcoa-sdlc-rationale.md):
in short, attributability of source-code changes is part of the chain
of trust that keeps clinical-trial data integrity defensible.

## Choosing SSH or GPG

GitHub accepts both. Pick one — you do not need both.

| | SSH signing | GPG signing |
| --- | --- | --- |
| Setup steps | Reuse the SSH key you already use for `git push` | Generate a separate key, install GPG, manage keyrings |
| Day-to-day friction | None — git uses the key automatically | Passphrase prompts unless you cache via `gpg-agent` |
| Revocation | Remove from GitHub Settings → SSH and GPG keys | Same, plus you should publish a revocation cert |
| Recommended for | Most CCTC developers | Developers who already use GPG for other reasons (email, package signing) |

**Default recommendation: SSH.** The instructions below assume SSH;
the GPG path is included at the bottom.

## SSH signing — one-time setup per machine

### 1. Confirm you have an SSH key

```bash
ls -1 ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub 2>/dev/null
```

If neither exists, generate one (ed25519 preferred):

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

### 2. Add the key to GitHub *as a signing key*

A key used for `git push` authentication and a key used for signing
are listed separately in GitHub, even when it is the same key file.
You need it registered under **Signing Keys**:

1. Print the public key: `cat ~/.ssh/id_ed25519.pub`
2. Go to **GitHub → Settings → SSH and GPG keys**.
3. Click **New SSH key**, set **Key type: Signing Key**, paste, save.

(If the same key is already there as an Authentication Key, add it a
second time as a Signing Key — GitHub treats the two roles independently.)

### 3. Configure git to sign by default

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git config --global tag.gpgsign true
```

Per-repo (if you only want signing in CCTC repos) — drop `--global`
and run inside the repo.

### 4. Enable local signature verification

Signing and *verifying* are separate. The config above makes git
embed an SSH signature in every commit, but `git log --show-signature`
will still report `No signature` until you tell git which keys it
should trust. Without this step, GitHub will show **Verified** while
your local git silently fails to verify.

Create an allowed-signers file mapping your email to your signing
key (use the email from `git config user.email`):

```bash
echo "your-email@example.com $(cat ~/.ssh/id_ed25519.pub)" > ~/.ssh/allowed_signers
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

Swap `id_ed25519.pub` for whichever key is set as
`user.signingkey`. The file is one line per identity, so add a line
for each teammate's key you want to verify locally, or use a glob:

```
alice@example.com ssh-ed25519 AAAA...alice
bob@example.com   ssh-ed25519 AAAA...bob
*@example.com     ssh-ed25519 AAAA...shared-bot
```

### 5. Verify

Make a commit in any repo, then:

```bash
git log --show-signature -1
```

You should see `Good "git" signature` (locally) and a green
**Verified** badge next to the commit on GitHub.

If the GitHub badge says **Unverified**: the email on the commit
(`git config user.email`) must match a verified email on your GitHub
account. Fix with `git config --global user.email "<github-email>"`
and amend or re-commit.

## GPG signing — alternative path

Only use this if you already use GPG. Otherwise the SSH path is
shorter.

### 1. Generate a key

```bash
gpg --full-generate-key
```

Choose RSA 4096, no expiry or a long one, your GitHub-verified email.

### 2. Export and add to GitHub

```bash
gpg --list-secret-keys --keyid-format=long
# Copy the long key ID, e.g. ABCD1234EF567890

gpg --armor --export ABCD1234EF567890
```

GitHub → Settings → SSH and GPG keys → **New GPG key** → paste.

### 3. Configure git

```bash
git config --global user.signingkey ABCD1234EF567890
git config --global commit.gpgsign true
git config --global tag.gpgsign true
```

### 4. Cache the passphrase

Without caching, every commit prompts. Add to `~/.gnupg/gpg-agent.conf`:

```
default-cache-ttl 28800
max-cache-ttl 28800
```

Then `gpg-connect-agent reloadagent /bye`.

## Self-hosted runners (`[self-hosted, linux, cctc]`)

A self-hosted runner only needs a signing key if a workflow on it
performs a **Git CLI push or commit** against a regulated repo.

| Workflow pattern | Needs runner-side signing? |
| --- | --- |
| Commits via a GitHub App and the Contents API (e.g. `sync-labels.yml`, the planned `compliance-drift.yml`) | **No** — GitHub signs these commits server-side. The verified badge attributes them to the App. |
| Runs `git commit && git push` from the runner's checkout (e.g. a workflow that auto-formats and pushes back) | **Yes** — set up GPG or SSH signing on the runner under the user the runner service runs as. |
| Runs only read-only or non-pushing steps (`gh pr create` against a fork, `gh issue comment`, tests) | **No** — no commit produced. |

If you do need it on a runner: prefer GPG with a passphrase-less key
stored in the runner's home directory, file permissions `0600`, and
the public key registered against a dedicated service-account
GitHub user (not a real human's account). SSH signing also works but
requires the runner's SSH key to be enrolled twice in the
service-account user's GitHub settings (auth + signing).

## Verifying org-wide adoption

Once everyone is set up, an org admin can spot-check:

```bash
# Latest commit on main for every non-archived CCTC repo, with
# the verification status of that commit.

gh repo list CCTC-team --no-archived --json name --jq '.[].name' \
  | while read -r repo; do
      status=$(gh api "/repos/CCTC-team/$repo/commits/main" \
        --jq '.commit.verification.verified' 2>/dev/null)
      printf '%-40s %s\n' "$repo" "${status:-no main}"
    done
```

A row reading `false` means the latest commit on `main` is unsigned —
that author still needs to complete the setup above.

## Troubleshooting

- **"gpg: signing failed: Inappropriate ioctl for device"** — GPG
  can't prompt for the passphrase. Run `export GPG_TTY=$(tty)` and add
  it to your shell rc.
- **"error: gpg failed to sign the data"** with SSH signing — your git
  version is older than 2.34. Upgrade.
- **GitHub shows "Unverified"** — the commit email does not match a
  verified email on your GitHub account. See SSH step 5.
- **`Verified` shows but with a different name** — the signing key is
  registered against a different GitHub user. Re-export from the right
  account.
- **GitHub says `Verified` but local `git log --show-signature` prints
  `No signature`** (often with `error: gpg.ssh.allowedSignersFile needs
  to be configured and exist for SSH signature verification`) — the
  commit *is* signed; only your local verification config is missing.
  Confirm the signature is present with `git cat-file -p HEAD | head -12`
  (look for `gpgsig -----BEGIN SSH SIGNATURE-----`), then complete SSH
  step 4. Do **not** work around this with `--no-verify` or by
  disabling signing — the signature is valid.
