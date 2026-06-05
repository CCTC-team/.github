# Replace GitHub attestation with an SSH-signed release manifest

## Context

Persisting GitHub artifact attestations for a **private** repo requires GitHub
Enterprise Cloud; the CCTC-team org is on Team and will not be upgrading. The
regulated release pipeline currently makes attestation a hard deploy gate (the
pull-agent runs `gh attestation verify` and refuses an unverified image), so on
the Team plan no `gcp-critical` repo can ever publish an attested production
release. Per the provenance risk assessment
(`docs/release-provenance-risk-assessment.md`), attestation is supply-chain
hardening, not a GxP requirement.

**Decision:** remove attestation entirely and replace it with two zero-licence
controls — (a) content-addressed digest verification (already implemented in the
agent) and (b) an **SSH-signed release manifest**: CI signs a `tag→digest`
manifest with a dedicated org signing key, and the agent verifies it against an
`allowed_signers` file (the same SSH-signing trust root the rulesets already
mandate for commits). This recovers an unforgeable origin signature with no GHEC
or cloud dependency.

**Key custody:** a dedicated `cctc-release-signing` ed25519 key. Private key →
**org-level** Actions secret `RELEASE_SIGNING_KEY`. Public key → committed
`allowed_signers` shipped with the agent. The user generates the key and sets the
secret; this plan scaffolds everything that uses it.

Signing namespace: `cctc-release`. Signer principal: `release@cctc-team` (the
identity recorded in `allowed_signers`).

## Phase 1 — Producer (CCTC-team/.github)  ✅ (.github 0eafefc · TrialView 290f64c5)

`release.yml` (reusable):
- Delete the `attest` matrix job and the evaluate-tolerance / "Flag unattested
  image" step added earlier; drop the workflow `env: FORCE_JAVASCRIPT_…` note's
  attest rationale if it no longer applies (download/upload-artifact still use it).
- In the **build** job's asset-collection, emit a canonical
  `release-manifest.json` `{schema, tag, repo, commit, run_id, components:[{name,
  ref, digest}]}` into the bundle/assets and include it in `SHA256SUMS` (data
  only — no key in the build job).
- In the **release** job (runs no repo build commands → safe to hold the key),
  add a "Sign the release manifest" step: write `secrets.RELEASE_SIGNING_KEY` to
  a `0600` temp file, `ssh-keygen -Y sign -n cctc-release -f <key> <manifest>` →
  `release-manifest.json.sig`, drop both into `assets/`. Fail in `active`; warn
  in `evaluate` if the secret is absent.
- `release` job `needs: [build, authorize]` (attest removed). Drop `id-token:
  write` / `attestations: write` everywhere they were only for attestation.
- Declare `secrets.release_signing_key` in `workflow_call.secrets`.

`templates/compliance/release-caller.yml` + TrialView caller: drop `id-token:
write` / `attestations: write`; pass `secrets: inherit` (or explicit
`release_signing_key`).

New `docs/release-signing-setup.md`: how to generate the key, set the org secret,
and add the public key to `allowed_signers` (mirrors the `*-app-setup.md` docs).

Verify: `actionlint` clean.

## Phase 2 — Consumer (server-structure/agent), TDD  ✅ (server-structure ee308db; 34 tests pass; sign/verify proven locally)

- `config.py`: replace `signer_workflow` with `allowed_signers` (path),
  `signer_principal`, `signature_namespace`. Update `config.*.yml` + ship
  `allowed_signers` (placeholder public key until the user provides the real one).
- `release.py`: the **signed manifest** is the authoritative digest source — add
  manifest-JSON parsing; keep the body table only as human-readable.
- `agent.py`: replace `verify_image` (`gh attestation verify`) with
  `verify_manifest` — download `release-manifest.json` + `.sig` from the release
  assets, `ssh-keygen -Y verify -f allowed_signers -I <principal> -n
  cctc-release -s <sig>`, and confirm each deploy digest equals the signed
  manifest's digest for that component.
- `decision.py`: keep the refuse-on-unverified rule; update the `verification`
  docstring (now "covered by the signed manifest", not "attestation").
- Tests first: update `tests/test_decision.py`; add manifest parse + verify
  tests; update `tests/test_config.py` for the new fields.
- `PREREQUISITES.md`: replace the `gh attestation verify` prerequisite with
  `ssh-keygen -Y verify` + the `allowed_signers` file.

Verify: `python -m pytest` (agent suite) green.

## Phase 3 — Docs, wiki, risk assessment, memory  ✅ (.github aae6675 · wiki 263d348)

- Finalise `docs/release-provenance-risk-assessment.md`: attestation **removed**
  (not parked); SSH-signed manifest is the implemented alternative; drop the
  "flip to require on GHEC" framing; update the review trigger.
- Amend `docs/release-process.md`, wiki `Release-Process.md` /
  `Release-Multi-Repo.md` / `Release-Build-Contract.md`, `README.md`: the agent
  verifies the **signed manifest + digest**, not an attestation. Fix the mermaid
  `C5 attest` node. Replace the GHEC-prerequisite notes (blocker → declined).
- Update the `attestations-need-enterprise-cloud` memory to record the decision.

## Phase 4 — Operational setup + end-to-end validation  ✅

Org secret `RELEASE_SIGNING_KEY` set (selected → TrialView). `v0.0.1-rc7` dry-run
ran green: the CI release job signed `release-manifest.json`; the draft carried it
+ `.sig`; downloading the real asset and running the agent's exact
`ssh-keygen -Y verify` against the committed `allowed_signers` returned
`Good "cctc-release" signature for release@cctc-team`. rc7 tag + draft cleaned up.
(Remaining real-world step beyond this plan: the broader pull-agent staging/prod
enablement; and QA sign-off on `docs/release-provenance-risk-assessment.md`.)

- **User:** generate `cctc-release-signing` ed25519 key; set org secret
  `RELEASE_SIGNING_KEY`; commit the real public key into the agent's
  `allowed_signers`.
- Cut `v0.0.1-rc7` → confirm the build signs the manifest, the release carries
  `release-manifest.json` + `.sig`, and `ssh-keygen -Y verify` + the agent's
  `decide()` accept it (agent `--dry-run`).
- Clean up the rc7 tag/draft afterwards.
