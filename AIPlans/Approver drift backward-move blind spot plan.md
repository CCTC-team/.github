# Approver-Drift Backward-Move Blind Spot — Implementation Plan

## Context

`approver_identity_drift` exists to leave an audit-trail comment whenever a
`PQ Approver` / `QA Approver` value is changed on a card that has reached its
review column — so a quietly-swapped approver on a reviewed card is never
silent. It decides relevance purely from the card's **current** `Status`
(`approver_identity_drift.py:9-27`): PQ-approver edits are logged only while
the card is in `PQ review` / `QA approved` / `Released`, QA-approver edits only
in `QA approved` / `Released`.

That opens a blind spot. The lifecycle state machine legally permits backward
moves to "recover from a mistaken advance" (`state_machine.py:3-8`). So a user
can move a reviewed card **back** below its review column (legal, silent), then
edit the approver. On the next poll the approver `field_change` is dispatched,
but the check reads the now-lowered current status, decides the card is not
relevant, and returns silently. The approver swap escapes the audit trail.

This plan makes the check fire on an approver edit when the card is **at/after**
its review column **or** the approver field already held a value — closing the
move-back-then-edit (and move-back-then-clear) hole without adding noise to the
normal first-time setting of an approver before review.

No behaviour outside this single drift check changes. The fix is intentionally
minimal and self-contained.

---

## Key References

- **`scripts/project_enforcement/checks/drift/approver_identity_drift.py`** —
  the check being changed. Note the `_PQ_REVIEW_STATUSES_OR_LATER` /
  `_QA_APPROVED_STATUSES_OR_LATER` sets and the `relevant` gate (lines 9-27),
  and the docstring's deliberate "does not revert — audit trail only" stance.
- **`scripts/project_enforcement/tests/test_drift_checks.py:138-163`** — the
  three existing `TestApproverIdentityDrift` cases and the `_ctx(...)` /
  `_change(...)` helpers (lines 30-59). **`test_change_before_relevant_column_silent`
  (141-147) encodes the blind spot as intended behaviour and must be flipped.**
- **`scripts/project_enforcement/snapshot.py:23-33`** — the `CardChange`
  dataclass. The check receives only the per-field change (with `old_value` /
  `new_value`) plus `ctx.snapshot` (the *current* state, `new_snap`). The prior
  snapshot is **not** available to checks — this constrains the design (see
  Decision 2).
- **`scripts/project_enforcement/state_machine.py:3-8`** — confirms backward
  moves are legal and intended, which is why this blind spot is reachable
  through normal use rather than a policy violation.
- **`README.md:541-545`** — the "Field-drift" bullet that documents this check;
  its wording ("cards already past their review column") goes stale once the
  trigger broadens.

---

## Key Design Decisions

1. **Broaden the relevance gate to `(status at/after review column) OR
   (old_value non-empty)`.** An approver field can only hold a value because
   someone set it, and approvers are set at/after the review column (enforced by
   the `pq_review` / `qa_approved` preconditions). So a non-empty *previous*
   approver value is a reliable proxy for "this card has already been through
   its review column" — which is exactly the population we want to keep auditing
   after a backward move. Combining the two conditions:
   - `"alice" → "bob"` at `In development` (tampering after move-back) → `old_value`
     non-empty → **fires** (the bug we're fixing).
   - `"alice" → ""` (clearing) at `In development` after move-back → `old_value`
     non-empty → **fires**.
   - `"" → "alice"` at `PQ review` (normal first set) → status at column →
     **fires** (current behaviour preserved).
   - `"" → "alice"` at `Triage` / `In development` (pre-setting early, never
     reviewed) → both conditions false → **silent** (no new noise).

2. **Use the `old_value`-non-empty proxy rather than plumbing the previous
   status through to the check.** The "compare against the snapshot's previous
   status" alternative is cleaner in principle but more invasive: checks today
   receive only `ctx.snapshot` (the *new* snapshot) and a per-field `CardChange`
   — the prior snapshot is held only by the handler (`handler.py:184`). Threading
   previous status in would mean changing `CheckContext` / `CardChange` and the
   handler dispatch, touching unrelated checks. The proxy needs no plumbing,
   stays within the one file, and is sufficient because approver presence already
   implies the card reached the review column. The only imprecision — an approver
   *pre-set early* and then changed *before* the card ever reaches review would
   now emit an audit comment — is acceptable: it is an unusual action, the
   comment is non-blocking ("if legitimate, no action needed"), and an audit note
   on an early approver change is arguably correct anyway.

3. **Update the comment and module-docstring wording, not just the gate.** The
   current body asserts the change happened "on a card *past* its review column",
   which is no longer always true (the card may have been moved back). Reword to
   describe the current status and the prior approver value without claiming the
   card is currently past its column, so the audit note stays accurate in the
   move-back case.

4. **Still no revert.** The check remains audit-only, consistent with its
   docstring and `test_no_revert`. We are widening *when it comments*, not
   changing it into an enforcing gate.

---

## Phase 1: Broaden the relevance gate (TDD)

Test-first, paired sub-items — the unit is one pure-ish decision function.

- [ ] **1a. MODIFY (tests):** `scripts/project_enforcement/tests/test_drift_checks.py`
  - **Flip** `test_change_before_relevant_column_silent` (141-147): rename to
    `test_change_to_existing_approver_below_column_audit_logs` and assert the
    `"alice" → "bob"` change at `Status: "In development"` now **emits one
    comment** naming `alice` and `bob`. This is the blind-spot fix; the old
    assertion encoded the bug.
  - **Add** `test_first_set_below_column_silent`: `_change("PQ Approver", "", "alice")`
    at `Status: "In development"` (and a second case at `Status: "Triage"`) →
    **no comment** (empty `old_value`, status below column → not relevant).
  - **Add** `test_clearing_existing_approver_below_column_audit_logs`:
    `_change("QA Approver", "carol", "")` at `Status: "Requirement defined"` →
    **one comment** (non-empty `old_value` ⇒ card had been reviewed).
  - Keep `test_change_after_pq_review_audit_logs` (149-157) and `test_no_revert`
    (159-163) green unchanged — they still hold under the broadened gate.
  - Note: the QA-approver case must respect its own column set — a `QA Approver`
    first-set (`"" → "carol"`) at `PQ review` is *below* the QA column, so with
    empty `old_value` it stays silent; add that as a guard case if not already
    implied.

- [ ] **1b. MODIFY:** `scripts/project_enforcement/checks/drift/approver_identity_drift.py`
  - Change the `relevant` computation (lines 21-24) so that, after determining
    the column-based relevance, it is OR-ed with "the approver previously had a
    value":

    ```python
    old_present = bool((change.old_value or "").strip())
    if change.field_name == "PQ Approver":
        relevant = status in _PQ_REVIEW_STATUSES_OR_LATER or old_present
    else:
        relevant = status in _QA_APPROVED_STATUSES_OR_LATER or old_present
    ```

  - Reword the comment body (lines 34-41) so it does not assert the card is
    currently past its column — e.g. header
    `**Approver drift — `{change.field_name}` changed on a reviewed card**`, then
    show `Card status: `{status}`` and the previous/new approver as today. Keep
    the closing "if legitimate, no action needed; otherwise revert and follow up"
    guidance.
  - Update the module docstring (lines 1-4) to state the check fires when an
    approver changes on a card that is at/after its review column **or** already
    carried an approver value (i.e. has been reviewed), and still does not revert.

---

## Documentation

- [ ] **MODIFY:** `README.md` (Field-drift bullet, lines 541-545) — change the
  approver clause from "approver changes on cards already past their review
  column" to wording that covers the broadened trigger, e.g. "approver changes
  on cards at or past their review column, **or on any card whose approver was
  already set** (so an approver edited after the card is moved backward is still
  logged)". Keep it a single clause consistent with the surrounding list style.

---

## Verification

- [ ] **Enforcement tests pass:** `python3 -m pytest scripts/project_enforcement/tests/test_drift_checks.py`
  — the flipped + new cases and all untouched approver cases are green.
- [ ] **Full suite unaffected:** `python3 -m pytest scripts/project_enforcement/tests`
  — no collateral failures (the other three drift checks and the precondition /
  transition suites are independent of this change).
- [ ] **Manual trace of the reported scenario:** a card at `Released` with
  `PQ Approver: alice` → moved back to `In development` → `PQ Approver` edited to
  `bob`. Confirm `approver_identity_drift.check` on the `alice → bob`
  `field_change` (current status `In development`) now produces exactly one audit
  comment and **no** field write (no revert).
- [ ] **Negative path:** a brand-new card at `Triage` with `PQ Approver` set for
  the first time (`"" → "alice"`) produces **no** comment — confirms the fix did
  not turn ordinary approver assignment into noise.
- [ ] **Comment wording check:** the emitted body no longer claims the card is
  "past its review column" when the card's current status is below it.
