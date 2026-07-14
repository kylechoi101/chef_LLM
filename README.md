# chef_LLM

Digitizing taste by treating **recipes as code**: recipes are programs, cooking is execution, taste is the runtime output. Goal: a generative chef LLM that invents new, executable, delicious recipes — backed by a verifier stack, because taste has no cheap test oracle.

- **Design spec:** [`docs/specs/2026-07-05-chef-llm-design.md`](docs/specs/2026-07-05-chef-llm-design.md) — the umbrella document (architecture, ETL, quality model, training plan, benchmarks, compute).
- **Current plan:** [`docs/plans/2026-07-13-phase0-corpus-linter.md`](docs/plans/2026-07-13-phase0-corpus-linter.md) — Phase 0 (corpus + linter), implemented.
- **Latest result:** [`docs/reports/phase0-foodcom.md`](docs/reports/phase0-foodcom.md) — real-run metrics on 231,637 Food.com recipes.

## Quickstart

```bash
uv sync
uv run pytest -q                     # 13 tests
uv run python -m etl.fetch           # Food.com dump (Kaggle serves it anonymously)
uv run python -m etl.ingest_foodcom
uv run python -m etl.lint    data/corpus/foodcom.parquet
uv run python -m etl.dedup   data/corpus/foodcom.parquet
uv run python -m etl.quality data/corpus/foodcom.parquet
uv run python -m etl.report  data/corpus/foodcom.parquet   # -> docs/reports/phase0-foodcom.md
```

`data/` is git-ignored and fully regenerable from the commands above (~minutes) — losing a machine loses nothing but cached downloads.

## Layout

```
etl/          pipeline stages: schema -> fetch -> ingest_foodcom -> lint -> dedup -> quality -> report
tests/        pytest suite + fixture corpus with planted defects
docs/specs/   design documents
docs/plans/   implementation plans
docs/reports/ generated corpus reports (committed: they're the deliverables)
```

## Compute

Dev + ETL run anywhere (laptop or a basic UCSD DataHub pod). GPU work (Phase 1 critic onward) targets DSMLP — see spec §6.1 for tiers and the run strategy. Workflow: edit/plan locally, push; `git pull` + run on the pod; commit generated reports back after every real run (pods are ephemeral — GitHub is the source of truth).
