# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this repo is

The **public** org-level `.github` repository for the `CCTC-team` GitHub
organisation. It holds **only community-health defaults** — issue/PR templates,
`SECURITY.md`, and the organisation profile README. A repo named exactly
`.github` is the single mechanism GitHub uses to propagate org-wide
community-health files to every repo (public and private) that lacks its own, so
this repo must stay public and must stay minimal.

**The regulated machinery is not here.** The enforcement engine, compliance/
release schemas, org rulesets, release tooling, rationale docs, and
`labels.json` were split out into the **private**
[`CCTC-team/compliance-engine`](https://github.com/CCTC-team/compliance-engine)
repository. Do not re-add engine code, workflows, or schemas to this repo —
they would become world-readable, which is exactly what the split avoided.

## What stays here (and why)

- `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md` — inherited by
  org repos with no local equivalent.
- `SECURITY.md` — org-wide vulnerability-reporting policy (inherited).
- `profile/README.md` — the organisation profile page.
- `.github/CODEOWNERS` — reviewers for **this** repo only (CODEOWNERS does not
  propagate).

## The inheritance constraint

See `README.md` → "How inheritance works (and doesn't)". The short version:
inheritance is served only from a repo named exactly `.github`, and a private
`.github` does not propagate to public repos — hence this repo is public and
holds nothing sensitive.

## Public wiki

This repo's wiki carries the community-health framing only (`Home`,
`Community-Health-Files`). The engine's documentation lives in the private
`compliance-engine` wiki. Keep this wiki minimal and consistent with this repo.
