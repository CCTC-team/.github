#!/usr/bin/env bash
# sync-labels.sh — apply the standard label set to every repo in the org.
#
# Usage:
#   ./scripts/sync-labels.sh                 # syncs every repo in $ORG
#   ./scripts/sync-labels.sh repo1 repo2     # syncs only the named repos
#
# Requirements: gh (authenticated), jq.
# The script is idempotent: --force updates existing labels rather than failing.

set -euo pipefail

ORG="${ORG:-CCTC-team}"
LABELS_FILE="${LABELS_FILE:-$(dirname "$0")/../labels.json}"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not found" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq not found" >&2
  exit 1
fi
if [[ ! -f "$LABELS_FILE" ]]; then
  echo "error: labels file not found at $LABELS_FILE" >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  repos=("$@")
else
  mapfile -t repos < <(gh repo list "$ORG" --limit 1000 --no-archived --json name --jq '.[].name')
fi

for repo in "${repos[@]}"; do
  echo "==> $ORG/$repo"
  jq -c '.[]' "$LABELS_FILE" | while read -r label; do
    name=$(jq -r '.name'        <<<"$label")
    color=$(jq -r '.color'       <<<"$label")
    desc=$(jq -r '.description' <<<"$label")

    gh label create "$name" \
      --repo "$ORG/$repo" \
      --color "$color" \
      --description "$desc" \
      --force >/dev/null
  done
done

echo "Done."
