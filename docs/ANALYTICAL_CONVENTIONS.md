# V2 analytical conventions

The [current specification](v2/SPECIFICATION.md) is the product boundary. These are operational conventions, not claims that every dataset or interpretation can be validated automatically.

| Area | Current convention |
| --- | --- |
| Input | One CSV/Parquet table; 25 MiB source, 50,000 rows, 80 fields and 80 MiB decoded memory. No joins or lineage. |
| Source fidelity | Immutable source bytes, SHA-256 fingerprint, physical field/row IDs, preserved duplicate labels, leading-zero codes and large integer strings. Numeric coercion requires all nonmissing values to parse. |
| Missingness | Empty cells are missing by default; literal `NA` is preserved unless declared a missing token. Nonfinite numerical values are excluded and disclosed. Missing values are never silently changed to zero. |
| Inferred roles | Number, category, time, identifier or text are useful starting hints. The user can correct supported roles. A role is not a business meaning. |
| Meaning | Unknown/additive/nonadditive, optional unit, note and value entity. Summing requires additive permission; entity amounts must be constant at that entity. A model hypothesis cannot grant permission. |
| Aggregation | Recorded-row count, distinct identifiers, sum, mean, median and explicit weighted mean. Weights must be nonnegative with positive support. Estimator, support, grain and denominator remain inspectable. |
| Group membership | Distinct entities can overlap groups. Full-credit incidence is not a 100% partition. Grouped repeated amounts require explicit equal/full attribution when membership overlaps. |
| Distributions | Full-source linear quantiles and histogram arithmetic; equal-width bins, up to 30. Group curves share bins and use within-group proportions. Box summaries use saved minimum, quartiles, median and maximum; these are not Tukey outlier fences. Quantile views preserve numerical value on the horizontal axis. |
| Categories | Ranked zero-baseline bars; bounded groups with a source-recomputed Other. Treemaps require a positive, nonnegative, nonoverlapping additive composition. Averages, signed parts and overlapping full-credit totals do not become parts of a whole. |
| Relationships | Complete-pair statistics use all eligible rows. Any deterministic scatter display reduction is disclosed separately. Inner scatter regions are square; numerical axes retain their independent units. Pooled and within-group statistics do not establish causality. |
| Time | Day/week/month intervals, at most 1,200 periods. Absent periods and explicit all-missing quantities remain unknown. Zero fill requires whole-table complete event recording, an additive count/sum and complete-through boundary; it does not fill explicit NULLs. |
| Time representations | Bars or lines for recorded intervals; share normalization only for a positive, nonnegative additive series; trailing three-period means require a full nonmissing window. Smoothing reveals trend. Deviation from that mean is a separate transformation. Calendar heatmaps show recorded weekday/hour combinations; unequal recording exposure remains a limitation. |
| Space | Only explicit latitude/longitude degrees within valid bounds; no guessed geocoding or claim that a map is useful simply because coordinates exist. A map shows recorded locations and can reveal spatial hypotheses. |
| Categorical relations | Small multiples with explicit within-group denominators, up to eight groups and sixteen categories; common axes preserve comparison. |
| Many measures | Ranked profiles use up to four numerical fields and twelve items, ordered on the first measure. Parallel coordinates use two to six fields and a disclosed fixed display sample. Axes keep separate units/ranges; crossings are not verified clusters. |
| Comparisons | One active categorical cohort/reference comparison under identical definitions, common bins and compatible domains. Membership, reference overlap and per-population denominators are recorded. |
| Assistance | Four distinct explicit requests per upload, surviving ordinary edits; bounded metadata, current result and up to three allowed candidates. One optional matched analytical image. No generated code executes and no provider decides business meaning. |
| Jev | Atomic source-support/relevance judgments retain uncertain and failed outcomes. Fixed probability thresholds are engineering defaults, not measured accuracy guarantees. |
| Prediction | One explicit retrospective experiment, 200–5,000 labelled rows, one to forty requested predictors, fixed 75/25 row/group/time partition with minimum support. Training-only target-copy/component screening and preprocessing. Actual mean/majority reference and Ridge/logistic baseline; optional hosted TabPFN. All model results remain visible. |
| Prediction boundaries | Declared repeated target entities require the matching group split. Chronological timestamps stay ordered. Hosted training never receives held-out labels. A successful diagnostic establishes neither future availability nor causality. |
| Records | Up to 24 immutable kept observations with original roles, meanings, memberships, requests and result tables. Subsequent declarations do not rewrite saved evidence. |
| Export/import | Checksummed bounded JSON/Markdown/optional original bytes; 35 MiB compressed and 100 MiB expanded import limit. Source-free inspection differs from source-backed deterministic recomputation. No provider calls, code execution, model refitting or silent V1 migration. |

Working sessions and request limits are not durable accounts or global quota enforcement. Provider failures preserve local analysis. Checksums detect modification, not authorship or business truth. Hypotheses and human interpretations remain separate from measured evidence; the app makes no automatic causal, statistical-significance or future-performance claim.

## Rules and guidance have different authority

Python enforces source membership, arithmetic, aggregation gates, weight validity, zero-fill coverage declarations, comparable scales, finite representations, allowed candidate/field/result IDs, literal context quotations, fixed prediction splits and request budgets. A model response cannot bypass these rules.

Prompts guide Jev and Terra toward relevant questions, visual hypotheses, concise explanations, cautious causal language and warm pedagogy. Those qualities are not proved by a structured response or a cited result ID. An interpretation can still be mistaken. The app labels it as a model interpretation and keeps it separate from calculated facts and human declarations. Field-role/unit hints and Jev relevance thresholds are fallible starting points, not validated business meanings or calibrated accuracy guarantees.

Earlier research is retained under [archive/v1/docs/research](../archive/v1/docs/research/). Its methodological findings inform V2, while historical feature inventories and budgets apply only to the archived release.
