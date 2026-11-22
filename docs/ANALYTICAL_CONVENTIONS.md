# Analytical conventions

| Area | Bound or convention |
| --- | --- |
| Import | One flat table; 25 MiB file; 50,000 rows; 80 fields; 80 MiB decoded table; chunked CSV guard |
| Missing values | Empty cells by default; literal `NA` preserved; optional explicit tokens; failed numeric parsing is counted |
| Numeric inference | At least 95% parseable; leading-zero codes preserved; proposed semantic roles remain editable |
| Statistics | Linear quantiles, sample standard deviation (`ddof=1`), pairwise finite correlations, explicit support |
| Semantic profiling | At most eight automatic ID entities, ten dimensions, eighty retained relationship proposals; exact checks over the bounded family; no exhaustive dependency claim |
| Semantic metrics | Typed metric algebra; at most two group fields and twenty displayed groups; Other recomputes source components; source definitions and scope are recorded |
| Observation process | Preserve by default; compatible confirmed fill policy; at most 200 source series, 20,000 expanded cells and 1,200 output periods; explicit NULL is not an absent observation |
| Discovery | Up to 300 numeric pairs; 24 conditional-shape screens; 12 automatic findings; at most 18 interactive working views, with pinned snapshots preserved; seeded 20,000-row association sample; up to 5,000 visible scatter points |
| Groups | At least 20 paired rows/group for distribution comparisons; 30 for subgroup correlations; at most eight displayed groups, with omissions recorded |
| Views | Eight constrained templates; at most 1,200 time periods; ECDF at most 1,200 exact cumulative locations |
| Challenges | Up to three automatic checks on three leading findings plus up to two additional metric views; Terra may add at most two eligible checks |
| Models | At most 10,000 labeled rows; 40 predictors; bounded encoding and model iterations; 70/30 split; two experiments/context |
| Providers | At most four Jev decisions and three Terra requests per provider instance; automatic loop normally uses two Terra requests, plus an optional separate semantic review; one TabPFN fit/predict per experiment |
| Visual review | Three PNGs; 1.5 MiB/image; at most 600 plotted records/image; 48,000 text characters/request; reduced views are regenerated with matching tables |
| Execution | Two admitted workers globally; one task/session; 360-second application deadline; finite provider transport/poll timeouts; five follow-up questions/context |
| Reproducibility | Seed 20261120 for analysis; examples declare their own seed; exact source bytes, parser, semantics and row membership recorded |

Cancellation detaches from remote results and stops later stages; an already accepted remote operation can remain billable. No provider retry starts a fresh remote fit automatically. A chronological split is an exploration protocol, not a guarantee of future performance; a row holdout does not establish independence. The automatic shortlist does not attach selected-winner p-values or causal conclusions. Ranking weights, thresholds and budgets are visible engineering defaults.

Semantic declarations belong to the exact uploaded table. The observed interval is not an expected schedule. Business meaning, weight/exposure and recording completeness require human knowledge. A selected-row context does not inherit the whole table’s gap-fill coverage. Ratios compose untransformed, non-temporal component metrics; temporal snapshot/counter nesting is not supported. State snapshots aggregate latest entity observations, not sums of daily stock levels. Currency bases are recorded without automatic conversion. Circular means require degrees and a defined resultant. No join, external entity resolution, holiday calendar, joint group/time split, causal model or lineage system is implied.
