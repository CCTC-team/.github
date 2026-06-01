#!/usr/bin/env bash
# sync-property-topics.sh — mirror the org-level `regulatory_tier` custom
# property onto each repo as a topic pill, so the value is visible on the
# repo home page (GitHub does not render custom properties there).
#
# Behaviour per repo:
#   - If regulatory_tier is unset or "none": ensure no managed topic is present.
#   - Otherwise: ensure the matching topic is present, and any other managed
#     topic (left over from a previous value) is removed.
#
# "Managed topics" = the schema's allowed_values minus "none". Discovered at
# runtime so the script stays correct if the schema changes.
#
# Usage:
#   ./scripts/sync-property-topics.sh                 # all repos in $ORG
#   ./scripts/sync-property-topics.sh repo1 repo2     # only the named repos
#
# Requirements: gh (authenticated with org custom-properties read + repo
# administration write), jq.

set -euo pipefail

ORG="${ORG:-CCTC-team}"
PROPERTY="${PROPERTY:-regulatory_tier}"

command -v gh >/dev/null || { echo "error: gh CLI not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "error: jq not found" >&2; exit 1; }

# Discover managed topic set from the property schema.
schema=$(gh api "/orgs/$ORG/properties/schema/$PROPERTY")
mapfile -t managed < <(echo "$schema" | jq -r '.allowed_values[] | select(. != "none")')
if [[ ${#managed[@]} -eq 0 ]]; then
  echo "error: property $PROPERTY has no managed values" >&2
  exit 1
fi
# GitHub topic names must match this pattern (lowercase alphanumeric + hyphens,
# 50 chars max, no leading hyphen). Validate now so a schema change that
# introduces an invalid value fails loudly instead of silently 422-ing on PUT.
topic_re='^[a-z0-9][a-z0-9-]{0,49}$'
for t in "${managed[@]}"; do
  if ! [[ "$t" =~ $topic_re ]]; then
    echo "error: property value '$t' is not a valid GitHub topic name (must match $topic_re)." >&2
    echo "       Sanitise the schema's allowed_values before running sync." >&2
    exit 1
  fi
done

echo "Managed topics: ${managed[*]}"

# Pull property values for every repo in one paginated call.
values=$(gh api -X GET "/orgs/$ORG/properties/values" --paginate)

if [[ $# -gt 0 ]]; then
  filter_repos="$*"
else
  filter_repos=""
fi

# Iterate every repo's property record.
echo "$values" | jq -c '.[]' | while read -r row; do
  repo=$(echo "$row" | jq -r '.repository_name')
  if [[ -n "$filter_repos" ]] && ! [[ " $filter_repos " == *" $repo "* ]]; then
    continue
  fi

  value=$(echo "$row" | jq -r --arg p "$PROPERTY" '.properties[] | select(.property_name == $p) | .value // ""')

  # Desired topic: empty if unset/none, else the value itself.
  desired=""
  if [[ -n "$value" && "$value" != "none" ]]; then
    desired="$value"
  fi

  current=$(gh api "/repos/$ORG/$repo/topics" --jq '.names')

  # Compute new topic list: drop all managed topics, then add the desired one.
  new=$(echo "$current" | jq --argjson m "$(printf '%s\n' "${managed[@]}" | jq -R . | jq -s .)" \
                              --arg d "$desired" \
                              '(map(select(. as $t | $m | index($t) | not))) as $kept
                               | if $d == "" then $kept else ($kept + [$d]) | unique end')

  if [[ "$(echo "$current" | jq -c 'sort')" == "$(echo "$new" | jq -c 'sort')" ]]; then
    echo "[$repo] unchanged ($(echo "$current" | jq -c .))"
    continue
  fi

  echo "[$repo] $(echo "$current" | jq -c .) -> $(echo "$new" | jq -c .)"
  # Capture the API response so non-2xx status surfaces in the log instead of
  # being silently discarded.
  if ! response=$(echo "$new" | jq '{names: .}' | gh api -X PUT "/repos/$ORG/$repo/topics" --input - 2>&1); then
    echo "::error::[$repo] PUT /topics failed: $response" >&2
    exit 1
  fi
done

echo "Done."
