# Phase 1 step 1 — lint flags vs reproduction evidence

Source: `foodcom.parquet`, 231637 recipes. `ratio_rated>=10_vs_pass` < 1 means flagged recipes are reproduced less than lint-passing ones (flag carries executability signal); ~1 means the flag is a linter artifact.

| flag | n | share_rated | share_rated>=10 | median_rating_n | mean_rating_n | mean_stars(rated) | ratio_rated>=10_vs_pass |
|---|---|---|---|---|---|---|---|
| PASS (baseline) | 184499.0 | 0.979 | 0.09 | 2.0 | 4.8 | 4.582 | 1.0 |
| calorie_outlier | 64.0 | 0.953 | 0.141 | 2.0 | 5.4 | 4.555 | 1.57 |
| no_steps | 1.0 | 1.0 | 0.0 | 2.0 | 2.0 | 4.5 | 0.0 |
| time_insane | 256.0 | 0.91 | 0.055 | 1.0 | 3.2 | 4.713 | 0.61 |
| time_missing | 1094.0 | 0.969 | 0.087 | 2.0 | 3.9 | 4.389 | 0.97 |
| too_few_steps | 2442.0 | 0.98 | 0.072 | 2.0 | 3.7 | 4.604 | 0.8 |
| unused_ingredient | 44358.0 | 0.975 | 0.074 | 2.0 | 4.1 | 4.577 | 0.83 |

## Reading

- **No flag carries executability signal.** The largest flag, `unused_ingredient`
  (44,358 recipes, 19% of the corpus), has the same star mean as lint-passing
  recipes (4.577 vs 4.582) and 83% of their rate of reaching 10 ratings. It
  zeroed every one of those recipes' `q_score` in Phase 0 for no measurable
  reason. `calorie_outlier` recipes are reproduced *more* than passing ones.
- **Reproduction evidence is thin everywhere.** The median lint-passing recipe
  has 2 ratings and only 9% reach 10. Positive-confidence tiers (plan step 2)
  therefore need review text and remake language, not just `rating_n`.
- **Decision:** `lint_pass` is demoted from a gate to a diagnostic column.
  Nothing downstream multiplies by it. The only flags worth keeping as hard
  exclusions are structural (`no_steps`, `no_ingredients`), and those are
  near-empty on this corpus.
- Run: default DSMLP CPU pod (no `-W`), 2 cores, 6 GB, ~15 s. Command:
  `python3 -m etl.lint_audit data/corpus/foodcom.parquet`.
