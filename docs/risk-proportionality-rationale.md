# Risk proportionality: why a uniform `gcp-critical` floor is the proportionate control, not a blanket

This note records the regulatory rationale for applying **one** ruleset
(`cctc-gcp-critical`) plus the **GxP traceability gate** uniformly to
every `gcp-critical` repo, rather than tuning the branch-protection and
gate controls per feature. It is the companion to
[alcoa-sdlc-rationale.md](alcoa-sdlc-rationale.md) and is referenced
from the branch-protection strategy in
[../README.md#branch-protection-strategy](../README.md#branch-protection-strategy).
It is intended as inspector-facing evidence that the uniformity is a
*deliberate proportionate minimum*, not an undifferentiated one-size-fits-all.

## The objection

ICH E6(R3) **Principle 7** requires that quality-management activities
be **proportionate to the risks** to participant safety and result
reliability, and is explicit that a *one-size-fits-all* approach is **not
acceptable**. Yet every `gcp-critical` repo here gets the *same* branch
protection (signed commits, mandatory PR review, approver ≠ last pusher,
zero bypass) and the *same* GxP traceability gate, regardless of whether
a given feature is a high-risk randomisation algorithm or a low-risk
read-only report. Is that not precisely the one-size-fits-all posture
the regulation forbids?

## The answer: the uniform controls are the floor; proportionality lives above it

The repo-level controls are not the whole quality system — they are its
**irreducible minimum**. Any system classified `gcp-critical` can, by
definition, corrupt clinical-trial data or endpoints. For *that*
population, the controls in `cctc-gcp-critical` (attributable signed
history, contemporaneous review, segregation of duties, traceable
Risk ID → Requirement ID linkage) are the floor below which no such
system may sit — there is no risk gradient on which "unsigned commits"
or "no traceability" becomes acceptable for a system that can alter trial
data. Proportionality does not mean *weakening* this floor for
lower-risk features; it means applying **finer, feature-level** controls
*on top of it* where the risk warrants.

Principle 7 proportionality is therefore satisfied by the layering, not
by per-feature branch rules:

| Where risk is assessed | Mechanism | What it proportions |
| --- | --- | --- |
| Trial level | **CCTU/SOP040** risk evaluation (likelihood × consequence × detectability) | Which factors are Critical-to-Quality at all, and how they are monitored |
| Factor level | **CCTU/FRM129** Critical / Important / neither classification | The tier recorded in `ctq_factors` and the board `Critical-to-Quality` field |
| Feature level | The three-tier `Critical-to-Quality` field + Test Type rule | Critical → Test Type must include PQ; Important → a verification Test Type (PQ not required); No → no constraint |
| System level | `regulatory_tier` → ruleset selection | `gcp-critical` gets Ruleset A; lower-risk buckets get `cctc-regulated-non-critical`; `none` gets baseline only |

The system-level row is itself proportionate: the *reason* there are two
rulesets (and a bare baseline) rather than one is that the regulatory
bucket already grades the population by risk. Within the `gcp-critical`
bucket, the remaining proportionality is delegated downward to FRM129
tiering and SOP040 risk evaluation, which is where the trial's risk
assessors — not the branch-protection config — belong.

## The traceability chain that demonstrates proportionate control selection

An inspector can read proportionality off the artefacts, end to end:

1. **`ctq_factors`** (in `.compliance.yml`) anchors the system to its
   FRM129 entry and tier — *which* Critical-to-Quality factor this system
   safeguards, and whether it is `critical` or `important`.
2. **Risk register / SOP040 assessment** records the likelihood,
   consequence and detectability behind that tier — *why* the factor sits
   where it does.
3. **Requirement ID** ties the factor to a specific user requirement on
   the validated feature card.
4. **Test Type tier** proportions the verification: a Critical factor's
   requirement must be exercised by a PQ-bearing Test Type; an Important
   factor needs verification but not PQ.
5. **V&V evidence** (`csv_evidence`: URS / FS / IQ / OQ / PQ) closes the
   loop with the executed proof.

The control applied to each requirement is thus *selected by its risk
tier*, while the branch-protection floor guarantees that the history of
the code implementing it is attributable and traceable. That is
proportionality in the Principle 7 sense — graded effort where the risk
is, on a non-negotiable integrity base.

## What this justifies

- Applying `cctc-gcp-critical` uniformly to every `gcp-critical` repo:
  the controls are the minimum for *any* system that can corrupt trial
  data, so there is no proportionate basis for a weaker variant within
  the bucket.
- Delegating finer proportionality to **FRM129** (factor tiering, mirrored
  by the three-tier `Critical-to-Quality` field), **SOP040** (risk
  evaluation), and the `cctc-regulated-non-critical` ruleset for
  lower-risk regulatory buckets — rather than encoding per-feature branch
  rules that no inspector could trace back to a documented risk decision.
- The decision *not* to add per-feature exemptions to the gate or
  ruleset: an exemption is a risk decision, and risk decisions belong in
  the QMS risk assessment, not in branch-protection configuration.
