# Release signing: the manifest-signing key and `allowed_signers`

The regulated release pipeline signs each release's **manifest**
(`release-manifest.json` — the authoritative `tag → per-component digest` map)
with a dedicated organisation SSH key, and the on-server pull-agent verifies that
signature against an `allowed_signers` file before it will deploy any digest.
This replaces GitHub artifact attestations, which need GitHub Enterprise Cloud
(see [release-provenance-risk-assessment.md](release-provenance-risk-assessment.md)).
This note is the one-time operational setup.

This is the **artifact-end** signature; it complements the human-signed release
**tag** (the source end). The signing key is an *identity of CI*, never a
personal key.

## 1. Generate the key (once)

A dedicated ed25519 key, **no passphrase** (CI cannot enter one):

```bash
ssh-keygen -t ed25519 -C "release@cctc-team" -f cctc-release-signing -N ""
# produces: cctc-release-signing (private)  cctc-release-signing.pub (public)
```

Keep the private key only in the org secret below; do not commit it anywhere.

## 2. Set the organisation secret

Add the **private** key as an organisation-level Actions secret named
`RELEASE_SIGNING_KEY`, scoped to the regulated repositories:

- **Org → Settings → Secrets and variables → Actions → New organization secret**
- Name: `RELEASE_SIGNING_KEY`
- Value: the full contents of `cctc-release-signing` (the private file, including
  the `-----BEGIN/END OPENSSH PRIVATE KEY-----` lines)
- Repository access: the regulated repos (e.g. TrialView)

Each regulated repo's release caller passes it through as
`secrets.release_signing_key` (already wired in
`templates/compliance/release-caller.yml`).

## 3. Publish the public key to the agent's `allowed_signers`

The pull-agent ships an `allowed_signers` file (in `server-structure/agent`). Add
one line mapping the signer identity to the **public** key, pinned to the
`cctc-release` namespace the workflow signs under:

```
release@cctc-team namespaces="cctc-release" ssh-ed25519 AAAA…<the .pub contents>… release@cctc-team
```

The agent verifies with:

```bash
ssh-keygen -Y verify -f allowed_signers -I release@cctc-team \
  -n cctc-release -s release-manifest.json.sig < release-manifest.json
```

## Rotation

Rotating the key is a **governed change** (it is a release control): generate a
new key, replace `RELEASE_SIGNING_KEY`, and update the `allowed_signers` line in
the same change. To accept both old and new during a cut-over, list **both**
public keys in `allowed_signers` for `release@cctc-team`, then remove the old one
once no in-flight release relies on it.

## What this does and does not give you

- **Does:** an unforgeable statement that *this release's digests came from the
  CI signing identity*, verifiable offline by the agent, with no GitHub
  Enterprise Cloud licence.
- **Does not:** validate the software or prove tests ran — that is the validation
  report and the board's V&V/QA gates. Provenance only pins origin; the residual
  risk is assessed in
  [release-provenance-risk-assessment.md](release-provenance-risk-assessment.md).
