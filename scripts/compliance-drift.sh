#!/usr/bin/env bash
# Audit every regulated org repo for compliance-scaffold drift and open a PR
# against any that have drifted. See .github/workflows/compliance-drift.yml.

set -euo pipefail

ORG="${ORG:-CCTC-team}"
DRY_RUN="${DRY_RUN:-false}"
REPOS="${REPOS:-}"

SCHEMA_FILE="compliance.schema.json"
TEMPLATES_DIR="templates/compliance"
BANNER_MARKER="compliance:banner"

# Sanity-check the canonical files exist in this checkout before touching
# anything else — a corrupt source would propagate to every regulated repo.
for f in "$SCHEMA_FILE" \
         "$TEMPLATES_DIR/.compliance.yml.example" \
         "$TEMPLATES_DIR/caller-workflow.yml" \
         "$TEMPLATES_DIR/gxp-traceability-caller.yml" \
         "$TEMPLATES_DIR/project-card-promote-caller.yml" \
         "$TEMPLATES_DIR/release.yml" \
         "$TEMPLATES_DIR/release-caller.yml" \
         "$TEMPLATES_DIR/release-authorize-caller.yml" \
         "$TEMPLATES_DIR/release-targets.yml.example" \
         "$TEMPLATES_DIR/README-banner.md" \
         "$TEMPLATES_DIR/CONTRIBUTING-regulated.md"; do
  [ -f "$f" ] || { echo "::error::Canonical file missing in .github checkout: $f"; exit 1; }
done

SOURCE_DIR="$PWD"

# Allow git push using the App token via gh's credential helper.
gh auth setup-git

regulated_repos() {
  if [ -n "$REPOS" ]; then
    printf '%s\n' $REPOS
    return
  fi

  # GitHub returns repo-by-repo with all set properties. We keep repos
  # where `regulatory_tier` is set to anything other than `none`. The
  # `any(.properties[]?; ...)` form yields a single boolean per repo,
  # avoiding fragile per-property emission.
  gh api --paginate "/orgs/$ORG/properties/values" \
    | jq -r '
        .[]
        | select(
            any(.properties[]?;
                .property_name == "regulatory_tier"
                and .value != null
                and .value != "none")
          )
        | .repository_name
      '
}

ensure_file_matches() {
  # $1 = canonical source path (in this checkout)
  # $2 = destination path (relative to the cloned target repo)
  local src="$1" dst="$2"
  if [ ! -f "$dst" ] || ! cmp -s "$SOURCE_DIR/$src" "$dst"; then
    mkdir -p "$(dirname "$dst")"
    cp "$SOURCE_DIR/$src" "$dst"
    return 0  # changed
  fi
  return 1    # unchanged
}

check_and_fix() {
  local repo="$1"
  local workdir
  workdir="$(mktemp -d)"

  echo "::group::$repo"

  if ! gh repo clone "$ORG/$repo" "$workdir" -- --depth=1 --quiet 2>/dev/null; then
    echo "::warning::Cannot clone $repo (App not installed, or repo archived). Skipping."
    rm -rf "$workdir"
    echo "::endgroup::"
    return
  fi

  pushd "$workdir" >/dev/null
  local changed=0 reasons=()

  # 1. Schema in sync with canonical
  if ensure_file_matches "$SCHEMA_FILE" ".github/$SCHEMA_FILE"; then
    changed=1; reasons+=("schema drift")
  fi

  # 2. Caller workflow present
  if [ ! -f .github/workflows/compliance.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/caller-workflow.yml" ".github/workflows/compliance.yml" || true
    changed=1; reasons+=("caller workflow missing")
  fi

  # 3. .compliance.yml present (DON'T overwrite if it exists — humans curate this).
  # Template `last_reviewed` to today so the stub isn't already stale.
  if [ ! -f .compliance.yml ]; then
    sed "s/^last_reviewed:.*/last_reviewed: \"$(date -u +%Y-%m-%d)\"/" \
      "$SOURCE_DIR/$TEMPLATES_DIR/.compliance.yml.example" > .compliance.yml
    changed=1; reasons+=("compliance metadata missing (stubbed)")
  fi

  # 4. README banner
  if [ -f README.md ] && ! grep -qF "$BANNER_MARKER" README.md; then
    {
      cat "$SOURCE_DIR/$TEMPLATES_DIR/README-banner.md"
      echo
      cat README.md
    } > README.md.new
    mv README.md.new README.md
    changed=1; reasons+=("README banner missing")
  fi

  # 5. CONTRIBUTING-regulated.md (kept in sync with canonical)
  if ensure_file_matches "$TEMPLATES_DIR/CONTRIBUTING-regulated.md" "CONTRIBUTING-regulated.md"; then
    changed=1; reasons+=("CONTRIBUTING-regulated.md drift")
  fi

  # 6. GxP traceability caller workflow (stubbed if missing, NOT
  # overwritten — repos may have tuned enforcement to active locally
  # and we mustn't reset that on a nightly run).
  if [ ! -f .github/workflows/gxp-traceability.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/gxp-traceability-caller.yml" ".github/workflows/gxp-traceability.yml" || true
    changed=1; reasons+=("gxp-traceability caller workflow missing (stubbed)")
  fi

  # 7. Project-card promote caller workflow (stubbed if missing, NOT
  # overwritten — repos may swap the source ref or customise inputs).
  # Without the LIFECYCLE_PROJECT_NUMBER repo variable the workflow
  # no-ops on its guard step; the caller is safe to ship before the
  # variable is configured.
  if [ ! -f .github/workflows/project-card-promote.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/project-card-promote-caller.yml" ".github/workflows/project-card-promote.yml" || true
    changed=1; reasons+=("project-card-promote caller workflow missing (stubbed)")
  fi

  # NB: The drift workflow does not check LIFECYCLE_PROJECT_NUMBER on
  # each regulated repo. Doing so would require the App to hold
  # `Variables: read`, which is broader than this App's existing scopes
  # and is not worth adding for a soft warning. The promoter caller
  # workflow's own guard step prints a step-summary line on every PR
  # run when the variable is unset, so the signal lands in the right
  # place (the PR, not the drift PR) anyway.

  # 8. Release-notes auto-categorisation config (stubbed if missing, NOT
  # overwritten — repos may tune their changelog categories locally).
  if [ ! -f .github/release.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/release.yml" ".github/release.yml" || true
    changed=1; reasons+=("release-notes config missing (stubbed)")
  fi

  # 9. Release caller workflow (stubbed if missing, NOT overwritten — repos
  # may have flipped enforcement to active or set approvers_team locally).
  if [ ! -f .github/workflows/release.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/release-caller.yml" ".github/workflows/release.yml" || true
    changed=1; reasons+=("release caller workflow missing (stubbed)")
  fi

  # 9b. Release-authorisation caller workflow (stubbed if missing, NOT
  # overwritten). Publishes a gated draft release on a /approve from a non-author
  # qa-approvers member; needs the QA_ORG_READ_TOKEN secret to verify team
  # membership. Safe to ship before a repo gates releases — it only fires on
  # comments on a release-authorisation-labelled issue, which exist only once a
  # gated active release is cut.
  if [ ! -f .github/workflows/release-authorize.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/release-authorize-caller.yml" ".github/workflows/release-authorize.yml" || true
    changed=1; reasons+=("release-authorisation caller workflow missing (stubbed)")
  fi

  # 10. Build-target manifest (stubbed from the worked example if missing, NOT
  # overwritten — it is TODO-flagged for the repo owner to fill in their own
  # build commands and image refs; the release workflow no-ops usefully until
  # then, and the contract check flags any missing mandatory target).
  if [ ! -f .github/release-targets.yml ]; then
    ensure_file_matches "$TEMPLATES_DIR/release-targets.yml.example" ".github/release-targets.yml" || true
    changed=1; reasons+=("release-targets manifest missing (stubbed, TODO)")
  fi

  if [ "$changed" -eq 0 ]; then
    echo "  ✓ no drift"
    popd >/dev/null
    rm -rf "$workdir"
    echo "::endgroup::"
    return
  fi

  echo "  drift:"
  for r in "${reasons[@]}"; do echo "    - $r"; done

  if [ "$DRY_RUN" = "true" ]; then
    echo "  (dry-run — would open PR)"
    popd >/dev/null
    rm -rf "$workdir"
    echo "::endgroup::"
    return
  fi

  # Stable branch name. Force-push every run so the PR always reflects
  # the latest drift state — never accumulates a backlog of stale PRs.
  local branch="compliance-drift/auto"
  git config user.name  "cctc-compliance-bot"
  git config user.email "compliance-bot@users.noreply.github.com"

  git checkout -b "$branch"
  git add -A
  git commit -m "Restore compliance scaffolding" \
             -m "$(printf 'Automated drift correction from CCTC-team/.github (run %s).\n\nFixes:\n%s\n' \
                    "$(date -u +%Y-%m-%d)" \
                    "$(printf -- '- %s\n' "${reasons[@]}")")"

  git push -f origin "$branch"

  if gh pr list --head "$branch" --state open --json number -q '.[0].number' | grep -q .; then
    echo "  open PR exists on $branch — refreshed via force-push"
  else
    gh pr create \
      --title "Restore compliance scaffolding (automated)" \
      --body "$(printf 'Automated drift correction from \`CCTC-team/.github\`.\n\nFixes:\n%s\n\nReview the \`.compliance.yml\` carefully if it was newly stubbed — the stub contains TODOs.\n\nThis PR is updated in place on every drift run; do not rebase it.' \
                "$(printf -- '- %s\n' "${reasons[@]}")")" \
      --label compliance
  fi

  popd >/dev/null
  rm -rf "$workdir"
  echo "::endgroup::"
}

mapfile -t repos < <(regulated_repos)
echo "Found ${#repos[@]} regulated repo(s) under $ORG"

for repo in "${repos[@]}"; do
  [ -z "$repo" ] && continue
  check_and_fix "$repo"
done
