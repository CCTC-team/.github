#!/usr/bin/env bash
#
# One-time board migration: rename the lifecycle board's "PQ review" step
# and its approver/date fields to the "User acceptance" naming, matching the
# code change in this branch (PQ-before-environment fix).
#
#   Status option   "PQ review"        -> "User acceptance"
#   Field (TEXT)     "PQ Approver"      -> "Acceptance Approver"
#   Field (DATE)     "PQ Signoff Date"  -> "Acceptance Signoff Date"
#
# ─────────────────────────────────────────────────────────────────────────
#  ⚠️  TIMING IS LOAD-BEARING. Run this ONLY once the code change has merged
#      to `main`, because the scheduled enforcement workflows run from `main`.
#      The board and the code reference these names by string, so:
#        • board renamed BEFORE merge  → cards sit in a column `main` doesn't
#          know; preconditions stop firing and the transition check logs
#          spurious "illegal transition" comments (evaluate mode → no reverts,
#          but noisy).
#        • board renamed AFTER merge   → in sync. ✅  Do it at cutover.
#      Renaming in place (this script / the UI) preserves option IDs, so all
#      existing card assignments and field values are retained.
# ─────────────────────────────────────────────────────────────────────────
#
# Safe by default: prints what it WOULD do. Set DRY_RUN=0 to apply.
#   DRY_RUN=0 ./scripts/ops/rename-pq-review-to-user-acceptance.sh
#
# Requires: gh (authenticated, with project read:write scope) and jq.
#
# Idempotent: if a target already carries the new name it is skipped, so a
# re-run after a partial failure is safe.

set -euo pipefail

ORG="CCTC-team"
PROJECTS=(30 31)            # 30 = template board, 31 = test board
DRY_RUN="${DRY_RUN:-1}"

# field-name renames (text/date fields): "old=>new"
FIELD_RENAMES=(
  "PQ Approver=>Acceptance Approver"
  "PQ Signoff Date=>Acceptance Signoff Date"
)
OPTION_OLD="PQ review"
OPTION_NEW="User acceptance"
# The renamed option's own description must also drop the PQ / operational-
# environment wording (otherwise the mislabel just hides in the description).
OPTION_NEW_DESC="Feature-level user acceptance. An end-user representative (not the code author, not the test author) confirms the feature meets the URS in a development/test environment. Acceptance Approver and Acceptance Signoff Date fields must be set before advancing. This is NOT the formal Performance Qualification — the genuine PQ is the release-gate sign-off on the built release candidate."

say() { printf '%s\n' "$*" >&2; }
apply() {
  if [[ "$DRY_RUN" == "1" ]]; then say "  DRY-RUN ▷ $*"; else say "  APPLY   ▷ $*"; "$@"; fi
}

project_id() {
  gh api graphql -f query='query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){id}}}' \
    -f o="$ORG" -F n="$1" --jq '.data.organization.projectV2.id'
}

# Echo the field id for a given field name, or empty if absent.
field_id() {
  gh api graphql -f query='query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){fields(first:50){nodes{__typename ... on ProjectV2FieldCommon{id name}}}}}}' \
    -f o="$ORG" -F n="$1" \
    --jq ".data.organization.projectV2.fields.nodes[] | select(.name==\"$2\") | .id"
}

rename_field() {  # pnum "old" "new"
  local pnum="$1" old="$2" new="$3"
  if [[ -n "$(field_id "$pnum" "$new")" ]]; then say "  • field \"$new\" already present — skip"; return; fi
  local fid; fid="$(field_id "$pnum" "$old")"
  if [[ -z "$fid" ]]; then say "  • field \"$old\" not found — skip"; return; fi
  apply gh api graphql \
    -f query='mutation($id:ID!,$name:String!){updateProjectV2Field(input:{fieldId:$id,name:$name}){projectV2Field{... on ProjectV2FieldCommon{id name}}}}' \
    -f id="$fid" -f name="$new"
}

rename_status_option() {  # pnum
  local pnum="$1"
  local fid; fid="$(field_id "$pnum" "Status")"
  [[ -z "$fid" ]] && { say "  • Status field not found — skip"; return; }

  # Current options (id,name,color,description). color is an enum token.
  local opts
  opts="$(gh api graphql \
    -f query='query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){field(name:"Status"){... on ProjectV2SingleSelectField{options{id name color description}}}}}}' \
    -f o="$ORG" -F n="$pnum" --jq '.data.organization.projectV2.field.options')"

  if ! echo "$opts" | jq -e ".[]|select(.name==\"$OPTION_OLD\")" >/dev/null; then
    say "  • Status option \"$OPTION_OLD\" not present — skip"; return
  fi

  # Rebuild the FULL option set (the API replaces it), preserving every id —
  # which is what keeps existing card assignments intact — and renaming only
  # the target option. The renamed option also gets a fresh description; every
  # other option keeps its description, but with the stray "PQ signoff" phrase
  # (on "QA approved") corrected to "acceptance signoff". color is emitted as a
  # raw enum (no quotes); strings via tojson for correct escaping.
  local literal
  literal="$(echo "$opts" | jq -r --arg old "$OPTION_OLD" --arg new "$OPTION_NEW" --arg newdesc "$OPTION_NEW_DESC" '
    [ .[] |
      .name as $nm |
      (if $nm==$old then $new else $nm end) as $newname |
      (if $nm==$old then $newdesc
       else ((.description // "") | gsub("PQ signoff"; "acceptance signoff"))
       end) as $desc |
      "{id:" + (.id|tojson)
      + ", name:" + ($newname|tojson)
      + ", color:" + .color
      + ", description:" + ($desc|tojson)
      + "}"
    ] | join(", ")')"

  local mutation="mutation{updateProjectV2Field(input:{fieldId:\"$fid\", singleSelectOptions:[$literal]}){projectV2Field{... on ProjectV2SingleSelectField{id name options{name}}}}}"
  apply gh api graphql -f query="$mutation"
}

for N in "${PROJECTS[@]}"; do
  say "═══ Project $N ($(project_id "$N")) ═══"
  for pair in "${FIELD_RENAMES[@]}"; do
    rename_field "$N" "${pair%%=>*}" "${pair##*=>}"
  done
  rename_status_option "$N"
done

say ""
if [[ "$DRY_RUN" == "1" ]]; then
  say "Dry run only. Re-run with DRY_RUN=0 to apply (AFTER the code merges to main)."
else
  say "Applied. Verify the boards and consider refreshing the _project-state snapshot"
  say "branch so the first post-rename poll doesn't emit transient field-drift comments."
fi
