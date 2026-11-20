# Analytical conventions

| Area | Bound or convention |
| --- | --- |
| Import | One flat table; 25 MiB file; 50,000 rows; 80 fields; 80 MiB decoded table; chunked CSV guard |
| Missing values | Empty cells by default; literal `NA` preserved; optional explicit tokens; failed numeric parsing is counted |
| Numeric inference | At least 95% parseable; leading-zero codes preserved; proposed semantic roles remain editable |
| Statistics | Linear quantiles, sample standard deviation (`ddof=1`), pairwise finite correlations, explicit support |
| Discovery | Up to 300 numeric pairs; 24 conditional-shape screens; 12 active findings; seeded 20,000-row association sample; up to 5,000 visible scatter points |
| Groups | At least 20 paired rows/group for distribution comparisons; 30 for subgroup correlations; at most eight displayed groups, with omissions recorded |
| Views | Eight constrained templates; at most 1,200 time periods; ECDF at most 1,200 exact cumulative locations |
| Challenges | Up to three automatic checks on each of three leading findings; Terra may add at most two eligible checks |
| Models | At most 10,000 labeled rows; 40 predictors; bounded encoding and model iterations; 70/30 split; two experiments/context |
| Providers | At most four Jev decisions and three Terra requests per provider instance; automatic loop normally uses two Terra requests, plus an optional separate semantic review; one TabPFN fit/predict per experiment |
| Visual review | Three PNGs; 1.5 MiB/image; at most 600 plotted records/image; 48,000 text characters/request; reduced views are regenerated with matching tables |
| Execution | Two admitted workers globally; one task/session; 360-second application deadline; finite provider transport/poll timeouts; five follow-up questions/context |
| Reproducibility | Seed 20261120 for analysis; examples declare their own seed; exact source bytes, parser, semantics and row membership recorded |

Cancellation detaches from remote results and stops later stages; an already accepted remote operation can remain billable. No provider retry starts a fresh remote fit automatically. A chronological split is an exploration protocol, not a guarantee of future performance; a row holdout does not establish independence. The automatic shortlist does not attach selected-winner p-values or causal conclusions. Ranking weights, thresholds and budgets are visible engineering defaults.
