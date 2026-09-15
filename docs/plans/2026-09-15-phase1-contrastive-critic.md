# Phase 1: Contrastive Critic — Plan

**Date:** 2026-09-15
**Status:** Proposed
**Supersedes the quality-score design of** `docs/plans/2026-07-13-phase0-corpus-linter.md` Task 5.
**Runs on:** UCSD DSMLP (repo at `~/private/Chef_LLM`; CPU pods for steps 1–7, any free 24 GB GPU for steps 8–10). See spec §6.1 for the storage playbook.

## Why this plan exists (Phase 0 diagnosis)

The core idea is contrastive: a recipe's existence is the positive label
("people wrote it down because the taste was worth recreating"), negatives
are manufactured or scraped, guidelines (NIH, food safety, culinary rules)
are constraints, and deliciousness is what separates the two classes.

Phase 0 replaced that with a regression on star ratings inside a
survivor-only corpus. Every Food.com recipe is already a positive, so the
star mean can only rank positives against each other. The committed report
(`docs/reports/phase0-foodcom.md`) shows the resulting `q_score` is
degenerate:

| q_score percentile | value | implied stars |
|---|---|---|
| 10th | 0.000 | lint failure |
| 25th | 0.897 | 4.48 |
| 50th | 0.917 | 4.59 |
| 90th | 0.930 | 4.65 |
| 99th | 0.949 | 4.75 |

`q_score ≈ lint_pass × constant`. Consequences:

- Zero negatives were built; the spec (§6 L2) lists them but the plan deferred them.
- The lint gate is inverted evidence: a recipe with 500 ratings was executed
  500 times, which is stronger executability evidence than a 3-rule stemmer.
  The linter was never cross-tabbed against ratings.
- Effort went to dedup families (a Phase 3 novelty concern) instead of the
  positive/negative contrast that is the crux.
- Spec §5 says axes "must not be collapsed into one score"; Task 5 multiplied them.

Two definitions that must stay separate from here on:

- **Positive confidence** — how sure we are the survival label is real
  (reproduction count, source tier, longevity, guideline pass). Used as a
  sample weight and SFT-slice selector.
- **Deliciousness** — what the critic learns from positives vs. negatives.
  Star ratings enter only as pairwise, within-family preferences.

## The 10 steps

1. **Validate the linter against reproduction data.** On a DSMLP CPU pod, cross-tab each lint flag against rating count in the existing parquet. Demote any flag whose flagged recipes rate and get reproduced like the passed ones, since that flag is an artifact.

   **Done 2026-09-15** — `docs/reports/phase1-step1-lint-vs-rating.md`. No flag carries signal; `unused_ingredient` (19% of corpus) rates identically to pass. `lint_pass` is demoted to a diagnostic column.

2. **Replace the quality score with a positive-confidence tier.** Compute a per-recipe weight from reproduction count, source tier, longevity, and guideline pass, and drop star mean from the global score. Three tiers are enough for now.

   Evidence pools across a family's cosmetic variants: reposts by different authors and step reorderings that leave the dataflow graph unchanged are the same recipe, and distinct-author copy count is itself a reproduction signal (count authors, not pages, to blunt content farms).

   **Done 2026-09-15** — `etl/confidence.py`, `docs/reports/phase1-step2-confidence.md`. Tier 3 = 9.6%, tier 2 = 39.2%, tier 1 = 51.1%. 140k reviews carry remake language. Copy pooling under an exact ingredient-set key is rare (1.7k groups); family-level pooling deferred to the step-graph work.

3. **Add guidelines as hard lint gates.** Encode food-safety rules and the NIH dietary constraints as deterministic checks alongside the sanity flags. Anything failing safety is excluded from positives regardless of ratings.

4. **Build synthetic negatives from high-confidence positives.** Write mutation operators such as drop the acid, ten-times the salt, remove leavening, and emulsify after the boil. Tag every negative with its failure mode so the critic can be audited per mode.

5. **Scrape natural negatives.** Pull Cooking StackExchange failure questions with accepted answers and the pre-fix versions implied by review complaints. Grade these by confidence, since a low-rated recipe on a survivor site is a weaker negative than a mutation.

6. **Mine within-family preference pairs.** From the dedup families, select variant pairs where both sides have many ratings and the edit between them is small. Those pairs are the only place star ratings carry taste information.

   Pairs are formed only across meaningful edits, where the swapped or changed steps share a dependency edge in the step graph; cosmetic variants pool under step 2 and never form a pair.

7. **Add a second positive source.** Extract recipes from YouTube cooking transcripts with engagement as the reproduction proxy, or ingest RecipeNLG for breadth. Both go through the same IR and confidence tiers so sources stay comparable.

8. **Train critic v0 on DSMLP.** Fit an encoder with a contrastive or energy objective, weighting positives by confidence and mixing all negative sources. This fits on any free 24 GB GPU and needs no generator.

9. **Calibrate the critic before trusting it.** Report separation AUC on held-out natural negatives, not just mutations, to catch corruption-artifact learning. Report Spearman on the held-out within-family pairs for the taste gradient.

10. **Start generation only after calibration.** Run a base LLM with rejection sampling against the critic on constrained briefs and measure compile rate, constraint pass@k, and novelty. Use the pilot results to decide whether continued pretraining is even needed.

## Column contract additions (extends the Phase 0 table)

| Column | Type | Written by | Step |
|---|---|---|---|
| `safety_flags` | list[str] | lint | 3 |
| `pos_tier` | int8 (0 = excluded, 1–3 = confidence) | confidence | 2 |
| `pos_weight` | float64 | confidence | 2 |
| `neg_source` | str (`mutation` / `stackexchange` / `review_before` / `low_rated`) | negatives | 4–5 |
| `neg_mode` | str (failure mode tag; mutations only) | negatives | 4 |
| `neg_confidence` | float64 | negatives | 4–5 |

Preference pairs (step 6) are a separate table: `(family_id, id_a, id_b, rating_n_a, rating_n_b, edit_summary, preferred)`.

## Out of scope

- Thermomix / Rezeptwelt ingest (spec §9.1) — unchanged; the beachhead
  question is orthogonal to fixing the label definition.
- Ratio-space normalization — Food.com has no quantities; revisit when
  RecipeNLG lands in step 7.
- Continued pretraining — gated on step 10's pilot.
