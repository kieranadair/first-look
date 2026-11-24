# Minimum useful v2 verification

Test count is a consequence of risk, not a target. Retire all 327 v1 tests from active CI together with the retired implementation; preserve them in the v1 reference. Do not copy tests that freeze the old navigation, helper structure or historical features. Do not collapse unrelated checks into one giant test to manufacture a small count.

The initial minimum is **18 focused behavioural tests**:

1. Upload fidelity: exact identifiers, large integer strings, duplicate labels, literal missing markers and limits.
2. Full-source profiles and initial eligible views on numeric/categorical/all-missing inputs.
3. Histogram/quantile arithmetic and missing support against independent values.
4. Additivity/value-grain gates and row-versus-entity numerical oracle.
5. Group denominators, repeated/overlapping memberships and explicit attribution.
6. Pooled/within-group relationship and exact complete-pair memberships.
7. Time absence/explicit NULL/zero-filling eligibility and complete-through boundary.
8. Matched cohort/reference definitions, common bins/domains and unmodified source population.
9. Meaning/context changes invalidate current work but preserve saved definitions/results.
10. Failed/stale declarations and provider results cannot partially mutate working state.
11. Automatic review deduplication, context caching, privacy and fixed prediction holdout survive ordinary edits; dataset replacement resets correctly.
12. Evidence source-free inspection, source-backed replay and checksum/source tampering rejection.
13. Actual OpenAI SDK controlled transport: structured bounded output, exact IDs, privacy and sanitized failure.
14. Actual TypeSafe SDK controlled transport: both services are attempted without provider-off switches; independent judgments, uncertainty and no semantic permission.
15. Prediction train-only preparation, fixed row/group/time memberships and reference/local comparison.
16. Always-included hosted prediction boundary: no held-out labels, aligned outputs and invalid shape/failure handling.
17. Native welcome/upload-first/own-data flow with automatic reviews, cached returns, scope-correct comparisons, no provider setup and no duplicate calls on reruns.
18. Native consequential choice/comparison → immutable record/note/export journey.

The conditional spatial/multivariate/alternate representations add one distinct risk beyond this initial minimum: **representation changes must preserve analytical meaning and support**. Add one focused test of valid composition gating, explicit geographical coordinates, aligned categorical denominators or saved multivariate support as appropriate to the final implementation. This makes the planned suite approximately **19 focused tests**, not a quota to satisfy by hiding unrelated cases inside giant functions.

Some fixtures can cover several related boundary cases without multiplying every UI permutation. Expand only when a new capability or distinct unresolved failure requires it. Numerical, scope and privacy failures are essential; exact copy, chart pixel snapshots and archived helper coverage are not.

Supplement with one real localhost runtime walkthrough and a small screenshot perusal at desktop/narrow widths. These are build validation, not a committed browser-matrix suite or a user study. Keep generated files under ignored reports. No live paid provider calls are necessary for this build; controlled official SDK transports establish integration shape, not model effectiveness.
