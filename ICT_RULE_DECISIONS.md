# ICT research: policy decision and implementation gate

Status: PROPOSED, NOT IMPLEMENTED. No new strategy backtest or independent final approval has been performed for this document.
This is a research interpretation, not a canonical ICT/SMC definition or equivalence claim to CoreICT 5.19.

## Evidence boundary

Historical reference: Stage9 SPEC version 1, BTCUSDT-named 4h/15m inputs, cutoff 2026-09-10T16:30:00Z.
Previously inspected baseline manifest SHA256: f87b9924a141028afa9de7ca0b265e4c31d4637deda628a759e5652cff26fc9f.
This document uses the prior recorded review; that baseline is not present in this public monitor repository. The project execution environment was unavailable while drafting this document. Findings below must be rechecked against the frozen baseline before implementation.

The public scheduled workflow executes only synthetic acceptance-gate software tests. It does not implement the Stage9 strategy, check these proposed trading rules, generate live signals, or execute five LLM roles. Its green result must not be used as approval of this document.

## Decisions required before a new strategy version

| ID | Prior recorded evidence | Proposed research change | Current disposition |
| --- | --- | --- | --- |
| SWEEP_CAP | Original V53Config declares maximum penetration 0.80 ATR; original SweepEngine applies the cap. Stage9 active causal pipeline checks minimum penetration without that inherited maximum. Trade reference 4412 measured about 0.8207358483 ATR. | Restore an explicit maximum of 0.80 ATR for this candidate experiment, retaining the original formula and causal ATR convention after source verification. | Proposed; not applied. Do not assert this trade violates the current Stage9 specification, which does not clearly adopt the cap. |
| SEED_CLASS | Original ReversalEngine restricts seed liquidity to L1/L2/L3. Stage9 can seed from L4; trade references 3718 and 4484 use L4. | Restrict new reversal seeds to L1/L2/L3 for this candidate experiment. Preserve other uses of L4 unless separately specified. | Proposed; not applied. These are intended-policy questions, not demonstrated nonconformance to an explicit Stage9 prohibition. |
| LTF_FRESHNESS | HTF uses virgin-first raw-close crossing; LTF permits a new buffered crossing after subthreshold break/retrace. | Keep the current difference explicitly documented until chart adjudication decides whether the two timeframes should share a policy. | Unresolved; no automatic harmonization. |
| PROTECTION_DEPENDENCY | Later protection invalidation does not automatically cancel frozen candidates/MSS under the current Stage9 policy. | Specify prospective cancellation of pending dependent scenarios, tie precedence and in-position treatment before changing behavior. Preserve historical event facts. | Unresolved; no retroactive deletion or silent cancellation. |

The proposed cap/class experiment is motivated by the inherited-rule divergence, not observed profits. User-intended trading policy and independent review remain necessary. Do not rename this proposal as an approved specification.

## Required tests for the cap/class experiment

1. Verify the original penetration and ATR predicates from source, including ATR availability at Sweep close. Use identical predicates in the new frozen specification.
2. Test penetration just below, exactly at, and just above 0.80 ATR, with mirrored bullish/bearish witnesses. Verify minimum penetration and all other preconditions separately.
3. Reject NaN/inf and invalid/zero denominators; do not divide before input validation.
4. For otherwise identical inputs, exercise L1, L2, L3, and L4 seed decisions and verify deterministic priority/tie behavior.
5. Replay references 4412, 3718 and 4484 as regression witnesses. Their old causal paths may disappear or change; do not assume a particular replacement trade or PnL.
6. Compare full replay with historical prefixes at matching horizons and mutate future suffixes within the frozen input contract.
7. Recompute all raw-event semantics, signal/unique-opportunity counts, execution dispositions, fees and ledger independently.
8. Run the full original acceptance suite and any new tests from a fresh extraction. Record code/spec/data hashes and skipped/missing checks. Initialize acceptance false and keep execution eligibility false.

## Review and promotion

Architect: propose an isolated implementation against a preserved baseline.
Logic auditor: adjudicate accepted/rejected chart witnesses, distinguishing hidden future bars from outcome-blindness.
Data auditor: verify raw source provenance, alignment and causality.
Trade evaluator: reconstruct all trades and costs; quantify sample limits without optimizing this in-sample result.
Supervisor: issue a new bounded final verdict after all four reports. The earlier supervisor's final report was interrupted by a usage limit; partial independent checks are not a completed verdict.

Do not overwrite the prior Stage9 outputs. A new implementation/specification requires a new baseline manifest and run ID. Every previously inspected period remains development evidence. Outside-sample evaluation follows rule adjudication and realistic execution validation.
