# Phase 0: Corpus + Linter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clean, quality-scored recipe corpus (Food.com, 230k recipes + 1.1M reviews) with lint metrics, dedup/dish-family clustering, and a generated corpus report — the Phase 0 deliverable of `docs/specs/2026-07-05-chef-llm-design.md`.

**Architecture:** A flat `etl/` Python package: each pipeline stage is one module that reads/writes Parquet with a pinned column contract. Stages: ingest → lint → dedup/families → quality score → report. Everything runs on a laptop or a 10 GB DataHub pod (Food.com fits in memory; nothing here needs a GPU).

**Tech Stack:** Python ≥3.12 (dev on 3.14.5), uv, pandas + pyarrow, datasketch (MinHash LSH, Task 4 only), pytest.

## Global Constraints

- v1 is **text-only** (spec §6.1: Recipe1M+ images exceed the 100 GB DataHub quota).
- Must run in ≤10 GB RAM (spec §6.1 Tier 0: DataHub pod). Food.com is ~700 MB in memory — fine without chunking; do not add streaming machinery. `# ponytail: in-memory pandas; chunk when RecipeNLG (2.2M rows) lands`
- `data/` is never committed (raw dumps + Parquet output live there).
- Paths are repo-relative; the repo root is `/Users/kylechoi/chef_LLM`.
- Kaggle credentials (`~/.kaggle/kaggle.json`) are a user-supplied prerequisite for real-data runs; every stage must also run on the checked-in fixture without credentials.
- RecipeNLG, Rezeptwelt/Thermomix grammar, ratio-space normalization, and all of Phase 1 (critics) are **out of scope** — see "Out of scope" at the bottom.

## Parquet column contract (the interface between all tasks)

| Column | Type | Written by |
|---|---|---|
| `id` | int64 | ingest |
| `source` | str (`"foodcom"`) | ingest |
| `title` | str | ingest |
| `minutes` | int64 | ingest |
| `tags` | list[str] | ingest |
| `steps` | list[str] | ingest |
| `ingredients` | list[str] (names only; Food.com dump has no quantities) | ingest |
| `n_ingredients` | int64 | ingest |
| `calories` | float64 | ingest |
| `rating_mean` | float64 (NaN if unrated) | ingest |
| `rating_n` | int64 | ingest |
| `lint_flags` | list[str] | lint |
| `lint_pass` | bool | lint |
| `dup_group` | int64 (−1 = unique) | dedup |
| `family_id` | int64 | dedup |
| `q_rating` | float64 | quality |
| `q_score` | float64 | quality |

---

### Task 1: Scaffold + schema + fixture corpus

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `etl/__init__.py`, `etl/schema.py`, `tests/fixtures/recipes_fixture.json`, `tests/test_schema.py`

**Interfaces:**
- Produces: `etl.schema.RecipeIR` dataclass with fields exactly matching the ingest-written columns above (`id:int, source:str, title:str, minutes:int, tags:list[str], steps:list[str], ingredients:list[str], n_ingredients:int, calories:float|None, rating_mean:float|None, rating_n:int`), classmethod `RecipeIR.from_dict(d)->RecipeIR`.
- Produces: fixture of 8 recipes, 4 clean + 4 with planted defects (used by every later task's tests): id 1–4 clean; id 5 = ingredient `"saffron"` never used in steps; id 6 = `minutes=1051200` (troll time); id 7 = empty steps list; id 8 = exact duplicate of id 1 (same ingredients+title, different id).

- [ ] **Step 1: Scaffold**

```bash
cd /Users/kylechoi/chef_LLM
git init
uv init --bare --name chef-llm
uv add pandas pyarrow
uv add --dev pytest
mkdir -p etl tests/fixtures data/raw data/corpus
touch etl/__init__.py
printf 'data/\n.venv/\n__pycache__/\n*.egg-info/\n' > .gitignore
```

- [ ] **Step 2: Write the failing test** (`tests/test_schema.py`)

```python
import json
from pathlib import Path

from etl.schema import RecipeIR

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"


def test_fixture_loads_as_recipe_ir():
    records = json.loads(FIXTURE.read_text())
    recipes = [RecipeIR.from_dict(r) for r in records]
    assert len(recipes) == 8
    r = recipes[0]
    assert r.id == 1 and r.source == "foodcom"
    assert isinstance(r.steps, list) and isinstance(r.ingredients, list)
    assert recipes[6].steps == []  # id 7: planted empty-steps defect
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -q` — Expected: FAIL (`ModuleNotFoundError` / missing fixture).

- [ ] **Step 4: Write fixture** (`tests/fixtures/recipes_fixture.json`) — 8 records, defects as specified in Interfaces. Clean recipe shape:

```json
{"id": 1, "source": "foodcom", "title": "classic tomato soup", "minutes": 40,
 "tags": ["soup", "vegetarian"],
 "steps": ["dice the onion and garlic", "saute onion and garlic in butter",
           "add tomatoes and stock, simmer 25 minutes", "blend until smooth, season with salt"],
 "ingredients": ["onion", "garlic", "butter", "canned tomatoes", "vegetable stock", "salt"],
 "n_ingredients": 6, "calories": 180.0, "rating_mean": 4.6, "rating_n": 312}
```

(id 5: append `"saffron"` to ingredients, never mention it in steps, `rating_mean: 3.1, rating_n: 2`; id 6: copy of a clean recipe with `minutes: 1051200`; id 7: `"steps": []`; id 8: identical title+ingredients to id 1, `id: 8`, `rating_mean: 4.4, rating_n: 55`.)

- [ ] **Step 5: Implement** (`etl/schema.py`)

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecipeIR:
    id: int
    source: str
    title: str
    minutes: int
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    n_ingredients: int = 0
    calories: float | None = None
    rating_mean: float | None = None
    rating_n: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "RecipeIR":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})
```

- [ ] **Step 6: Run test to verify it passes** — `uv run pytest -q` → PASS.

- [ ] **Step 7: Commit** — `git add -A && git commit -m "feat: scaffold etl package, RecipeIR schema, fixture corpus"` *(commits deferred until user green-lights git usage).*

---

### Task 2: Food.com fetch + ingest → Parquet

**Files:**
- Create: `etl/fetch.py`, `etl/ingest_foodcom.py`, `tests/test_ingest.py`, `tests/fixtures/RAW_recipes_mini.csv`, `tests/fixtures/RAW_interactions_mini.csv`

**Interfaces:**
- Consumes: nothing from Task 1 at runtime (reads Kaggle CSVs directly); fixture CSVs mimic the real Kaggle column format exactly, including stringified Python lists.
- Produces: `etl.ingest_foodcom.ingest(recipes_csv: Path, interactions_csv: Path, out_parquet: Path) -> pd.DataFrame` writing the ingest-owned columns of the contract table; CLI `uv run python -m etl.ingest_foodcom`.

Real Kaggle files (dataset `shuyangli94/food-com-recipes-and-user-interactions`):
- `RAW_recipes.csv`: `name,id,minutes,contributor_id,submitted,tags,nutrition,n_steps,steps,description,ingredients,n_ingredients` — `tags`/`steps`/`ingredients` are stringified Python lists; `nutrition` is a stringified 7-list `[calories, fat_pdv, sugar_pdv, sodium_pdv, protein_pdv, sat_fat_pdv, carbs_pdv]`.
- `RAW_interactions.csv`: `user_id,recipe_id,date,rating,review` (rating 0–5; 0 means review-without-rating → exclude from the mean).

- [ ] **Step 1: Fetch script** (`etl/fetch.py`)

```python
"""Download the Food.com dump. Needs ~/.kaggle/kaggle.json (kaggle.com → Account → Create API Token)."""
import subprocess
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATASET = "shuyangli94/food-com-recipes-and-user-interactions"

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    if not (Path.home() / ".kaggle" / "kaggle.json").exists():
        sys.exit("Missing ~/.kaggle/kaggle.json — create an API token at kaggle.com/settings, then rerun.")
    subprocess.run(
        ["uvx", "--from", "kaggle", "kaggle", "datasets", "download", DATASET,
         "-p", str(RAW), "--unzip"],
        check=True,
    )
    print("done:", sorted(p.name for p in RAW.iterdir()))
```

- [ ] **Step 2: Write fixture CSVs** — 5 recipe rows + 8 interaction rows in the exact real format (stringified lists, one rating-0 row to verify exclusion, one recipe with no interactions to verify NaN mean). Example recipe row:

```csv
name,id,minutes,contributor_id,submitted,tags,nutrition,n_steps,steps,description,ingredients,n_ingredients
classic tomato soup,101,40,999,2019-01-01,"['soup','easy']","[180.0, 10.0, 20.0, 30.0, 5.0, 8.0, 12.0]",4,"['dice the onion','saute in butter','add tomatoes','blend and season with salt']",cozy,"['onion','butter','canned tomatoes','salt']",4
```

- [ ] **Step 3: Write the failing test** (`tests/test_ingest.py`)

```python
from pathlib import Path

import pandas as pd

from etl.ingest_foodcom import ingest

FIX = Path(__file__).parent / "fixtures"


def test_ingest_joins_ratings_and_parses_lists(tmp_path):
    out = tmp_path / "corpus.parquet"
    df = ingest(FIX / "RAW_recipes_mini.csv", FIX / "RAW_interactions_mini.csv", out)
    assert out.exists() and len(df) == 5
    r = df.set_index("id").loc[101]
    assert r["title"] == "classic tomato soup"
    assert isinstance(r["steps"], list) and r["steps"][0] == "dice the onion"
    assert r["calories"] == 180.0
    assert r["rating_n"] > 0 and 0 < r["rating_mean"] <= 5
    unrated = df.set_index("id").loc[105]          # planted: no interactions
    assert unrated["rating_n"] == 0 and pd.isna(unrated["rating_mean"])
```

- [ ] **Step 4: Run test to verify it fails** — `uv run pytest tests/test_ingest.py -q` → FAIL.

- [ ] **Step 5: Implement** (`etl/ingest_foodcom.py`)

```python
"""Food.com Kaggle dump -> contract Parquet (ingest-owned columns)."""
import ast
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def _listify(s):
    try:
        v = ast.literal_eval(s) if isinstance(s, str) else s
        return [str(x) for x in v] if isinstance(v, list) else []
    except (ValueError, SyntaxError):
        return []


def ingest(recipes_csv: Path, interactions_csv: Path, out_parquet: Path) -> pd.DataFrame:
    rec = pd.read_csv(recipes_csv)
    inter = pd.read_csv(interactions_csv, usecols=["recipe_id", "rating"])
    rated = inter[inter["rating"] > 0]                       # rating 0 = unrated review
    agg = rated.groupby("recipe_id")["rating"].agg(rating_mean="mean", rating_n="count")

    df = pd.DataFrame({
        "id": rec["id"].astype("int64"),
        "source": "foodcom",
        "title": rec["name"].fillna("").astype(str),
        "minutes": rec["minutes"].fillna(0).astype("int64"),
        "tags": rec["tags"].map(_listify),
        "steps": rec["steps"].map(_listify),
        "ingredients": rec["ingredients"].map(_listify),
        "n_ingredients": rec["n_ingredients"].fillna(0).astype("int64"),
        "calories": rec["nutrition"].map(lambda s: (_listify(s) or [None])[0]).astype("float64"),
    })
    df = df.merge(agg, left_on="id", right_index=True, how="left")
    df["rating_n"] = df["rating_n"].fillna(0).astype("int64")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_parquet, index=False)
    return df


if __name__ == "__main__":
    df = ingest(DATA / "raw" / "RAW_recipes.csv", DATA / "raw" / "RAW_interactions.csv",
                DATA / "corpus" / "foodcom.parquet")
    print(f"{len(df)} recipes -> data/corpus/foodcom.parquet", file=sys.stderr)
```

- [ ] **Step 6: Run test to verify it passes** — `uv run pytest -q` → PASS (note: `calories` in `_listify` returns strings; cast via `float(x)` — the test catches this if wrong).

- [ ] **Step 7: Real run (requires kaggle.json)** — `uv run python -m etl.fetch && uv run python -m etl.ingest_foodcom` — Expected: `231637 recipes -> data/corpus/foodcom.parquet`.

- [ ] **Step 8: Commit** — `git add -A && git commit -m "feat: food.com fetch + ingest to contract parquet"`.

---

### Task 3: Linter v0

**Files:**
- Create: `etl/lint.py`, `tests/test_lint.py`

**Interfaces:**
- Consumes: contract Parquet from Task 2 (or fixture recipes via `RecipeIR`-shaped dicts).
- Produces: `etl.lint.lint_recipe(title, minutes, steps, ingredients, calories) -> list[str]` (flag names), `etl.lint.lint_frame(df) -> df` adding `lint_flags` + `lint_pass`; CLI `uv run python -m etl.lint <parquet>` printing a flag-count summary table.

Flags (v0, spec §4.2 stage 3 — referential integrity + sanity only; chemistry/safety rules need quantities → next plan):
`no_steps`, `too_few_steps` (<2), `no_ingredients`, `dup_ingredient`, `unused_ingredient`, `time_missing` (≤0), `time_insane` (>10080 min = 1 week), `calorie_outlier` (≤0 or >30000).

- [ ] **Step 1: Write the failing test** (`tests/test_lint.py`)

```python
import json
from pathlib import Path

from etl.lint import lint_recipe

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"
RECIPES = {r["id"]: r for r in json.loads(FIXTURE.read_text())}


def flags(rid):
    r = RECIPES[rid]
    return lint_recipe(r["title"], r["minutes"], r["steps"], r["ingredients"], r["calories"])


def test_clean_recipe_has_no_flags():
    assert flags(1) == []

def test_unused_ingredient_detected():
    assert "unused_ingredient" in flags(5)          # saffron never used

def test_troll_time_detected():
    assert "time_insane" in flags(6)                # 1051200 minutes

def test_empty_steps_detected():
    assert "no_steps" in flags(7)

def test_head_noun_matching_tolerates_prep_words():
    # "canned tomatoes" must count as used when steps say "add tomatoes"
    assert "unused_ingredient" not in flags(1)
```

- [ ] **Step 2: Run test to verify it fails** — `uv run pytest tests/test_lint.py -q` → FAIL.

- [ ] **Step 3: Implement** (`etl/lint.py`)

```python
"""Lint v0: referential integrity + sanity. Spec 4.2 stage 3."""
import re
import sys
from pathlib import Path

import pandas as pd

WEEK_MIN = 10080


def _head_noun(name: str) -> str:
    words = re.findall(r"[a-z]+", name.lower())
    return (words[-1].rstrip("s") if words else "")  # ponytail: last-word + strip plural; real NER when it misses


def lint_recipe(title, minutes, steps, ingredients, calories) -> list[str]:
    flags = []
    steps = [s for s in (steps or []) if s.strip()]
    ingredients = list(ingredients or [])
    if not steps:
        flags.append("no_steps")
    elif len(steps) < 2:
        flags.append("too_few_steps")
    if not ingredients:
        flags.append("no_ingredients")
    if len(set(i.lower() for i in ingredients)) < len(ingredients):
        flags.append("dup_ingredient")
    body = " ".join(steps).lower()
    if steps and ingredients and any(
        _head_noun(i) and _head_noun(i) not in body for i in ingredients
    ):
        flags.append("unused_ingredient")
    if minutes is None or minutes <= 0:
        flags.append("time_missing")
    elif minutes > WEEK_MIN:
        flags.append("time_insane")
    if calories is not None and not pd.isna(calories) and (calories <= 0 or calories > 30000):
        flags.append("calorie_outlier")
    return flags


def lint_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["lint_flags"] = [
        lint_recipe(t, m, list(s), list(i), c)
        for t, m, s, i, c in zip(df["title"], df["minutes"], df["steps"],
                                 df["ingredients"], df["calories"])
    ]
    df["lint_pass"] = df["lint_flags"].map(len) == 0
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = lint_frame(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    n = len(df)
    print(f"{n} recipes, pass rate {df['lint_pass'].mean():.1%}")
    print(df["lint_flags"].explode().value_counts().to_string())
```

- [ ] **Step 4: Run test to verify it passes** — `uv run pytest -q` → PASS.

- [ ] **Step 5: Real run** — `uv run python -m etl.lint data/corpus/foodcom.parquet` — Expected: pass rate printed + per-flag counts (this is the first real Phase 0 metric; record it in the Task 6 report).

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: lint v0 (referential integrity + sanity flags)"`.

---

### Task 4: Dedup + dish families v0

**Files:**
- Create: `etl/dedup.py`, `tests/test_dedup.py`
- Modify: `pyproject.toml` (add `datasketch`)

**Interfaces:**
- Consumes: linted Parquet (Task 3 columns).
- Produces: `etl.dedup.assign_groups(df) -> df` adding `dup_group` (int64, −1 = unique; ≥0 = exact-dup group id) and `family_id` (int64, connected component over MinHash-LSH candidate pairs with ingredient-Jaccard ≥ 0.6); CLI `uv run python -m etl.dedup <parquet>`.

- [ ] **Step 1: Add dependency** — `uv add datasketch`.

- [ ] **Step 2: Write the failing test** (`tests/test_dedup.py`)

```python
import json
from pathlib import Path

import pandas as pd

from etl.dedup import assign_groups

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"


def test_exact_dup_and_families():
    df = pd.DataFrame(json.loads(FIXTURE.read_text()))
    out = assign_groups(df)
    g = out.set_index("id")
    # id 8 is an exact duplicate of id 1 (same title + ingredient set)
    assert g.loc[1, "dup_group"] == g.loc[8, "dup_group"] != -1
    # duplicates share a family; unrelated clean recipes don't
    assert g.loc[1, "family_id"] == g.loc[8, "family_id"]
    assert g.loc[1, "family_id"] != g.loc[2, "family_id"]
```

- [ ] **Step 3: Run test to verify it fails** — FAIL (`etl.dedup` missing).

- [ ] **Step 4: Implement** (`etl/dedup.py`)

```python
"""Exact dups + dish families v0. Spec 4.2 stage 5: dedup in ingredient space, keep variants."""
import re
import sys
from pathlib import Path

import pandas as pd
from datasketch import MinHash, MinHashLSH

PERM = 128


def _norm_title(t: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z]+", t.lower())))


def _ing_set(ings) -> frozenset:
    return frozenset(re.sub(r"[^a-z ]", "", i.lower()).strip() for i in ings)


def _minhash(items) -> MinHash:
    m = MinHash(num_perm=PERM)
    for x in items:
        m.update(x.encode())
    return m


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    keys = [(_norm_title(t), _ing_set(i)) for t, i in zip(df["title"], df["ingredients"])]

    # exact dups: identical normalized title + ingredient set
    seen, dup_group = {}, []
    for k in keys:
        h = hash(k)
        dup_group.append(seen.setdefault(h, len(seen)))
    counts = pd.Series(dup_group).value_counts()
    df["dup_group"] = [g if counts[g] > 1 else -1 for g in dup_group]

    # families: LSH candidates on ingredient sets, verified by Jaccard >= 0.6, union-find
    lsh = MinHashLSH(threshold=0.6, num_perm=PERM)
    hashes = [_minhash(k[1]) for k in keys]
    for idx, mh in enumerate(hashes):
        lsh.insert(str(idx), mh)
    parent = list(range(len(df)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for idx, mh in enumerate(hashes):
        for cand in lsh.query(mh):
            j = int(cand)
            a, b = keys[idx][1], keys[j][1]
            if idx != j and a and len(a & b) / len(a | b) >= 0.6:
                parent[find(idx)] = find(j)
    df["family_id"] = [find(i) for i in range(len(df))]
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = assign_groups(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    n, fams = len(df), df["family_id"].nunique()
    print(f"{n} recipes | exact-dup rate {(df['dup_group'] >= 0).mean():.1%} | {fams} families")
    top = df.groupby("family_id").agg(n=("id", "size"), title=("title", "first")).nlargest(10, "n")
    print(top.to_string())
```

- [ ] **Step 5: Run test to verify it passes** — `uv run pytest -q` → PASS.

- [ ] **Step 6: Real run** — `uv run python -m etl.dedup data/corpus/foodcom.parquet` — Expected: dup rate, family count, top-10 largest dish families. `# ponytail: O(n·candidates) union-find in memory; fine at 231k, revisit at RecipeNLG scale`

- [ ] **Step 7: Commit** — `git add -A && git commit -m "feat: exact dedup + minhash dish families"`.

---

### Task 5: Quality score v0

**Files:**
- Create: `etl/quality.py`, `tests/test_quality.py`

**Interfaces:**
- Consumes: Parquet with `rating_mean`, `rating_n`, `lint_pass` columns.
- Produces: `etl.quality.shrunk_rating(mean, n, prior_mean, prior_n=20) -> float`; `etl.quality.score_frame(df) -> df` adding `q_rating` (Bayesian-shrunk rating, spec §5) and `q_score` (= `q_rating/5 * lint_pass` — executability gates hedonics); CLI `uv run python -m etl.quality <parquet>`.

- [ ] **Step 1: Write the failing test** (`tests/test_quality.py`)

```python
import math

from etl.quality import shrunk_rating


def test_unrated_recipe_gets_prior():
    assert shrunk_rating(float("nan"), 0, prior_mean=4.4) == 4.4

def test_heavily_rated_recipe_keeps_its_mean():
    assert math.isclose(shrunk_rating(3.0, 10_000, prior_mean=4.4), 3.0, abs_tol=0.01)

def test_lightly_rated_recipe_pulled_toward_prior():
    s = shrunk_rating(5.0, 2, prior_mean=4.4)
    assert 4.4 < s < 4.6  # 5.0x2 must NOT beat a battle-tested 4.8
```

- [ ] **Step 2: Run test to verify it fails** — FAIL.

- [ ] **Step 3: Implement** (`etl/quality.py`)

```python
"""Quality v0: IMDb-style Bayesian shrinkage x lint gate. Spec 5."""
import sys
from pathlib import Path

import pandas as pd

PRIOR_N = 20  # ponytail: fixed pseudo-count; tune against held-out reproduction signals in Phase 1


def shrunk_rating(mean, n, prior_mean, prior_n=PRIOR_N) -> float:
    if not n or pd.isna(mean):
        return prior_mean
    return (n * mean + prior_n * prior_mean) / (n + prior_n)


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    prior = df.loc[df["rating_n"] > 0, "rating_mean"].mean()
    df["q_rating"] = [shrunk_rating(m, n, prior) for m, n in zip(df["rating_mean"], df["rating_n"])]
    df["q_score"] = (df["q_rating"] / 5.0) * df["lint_pass"].astype(float)
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = score_frame(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    print(df["q_score"].describe().to_string())
```

- [ ] **Step 4: Run test to verify it passes** — `uv run pytest -q` → PASS.

- [ ] **Step 5: Real run** — `uv run python -m etl.quality data/corpus/foodcom.parquet` → q_score distribution stats.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: bayesian-shrunk quality score v0"`.

---

### Task 6: Corpus report (the Phase 0 deliverable)

**Files:**
- Create: `etl/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: fully-annotated Parquet (all contract columns present).
- Produces: `etl.report.write_report(df, out_md: Path) -> None` emitting `docs/reports/phase0-foodcom.md` with sections: Corpus size, Lint (per-flag counts + pass rate), Dedup (dup rate, family count, top-10 families), Quality (q_score deciles), and 3 sample high-q / 3 low-q titles; CLI `uv run python -m etl.report <parquet>`.

- [ ] **Step 1: Write the failing test** (`tests/test_report.py`)

```python
import json
from pathlib import Path

import pandas as pd

from etl.dedup import assign_groups
from etl.lint import lint_frame
from etl.quality import score_frame
from etl.report import write_report

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"


def test_end_to_end_report_on_fixture(tmp_path):
    df = pd.DataFrame(json.loads(FIXTURE.read_text()))
    df = score_frame(assign_groups(lint_frame(df)))
    out = tmp_path / "report.md"
    write_report(df, out)
    text = out.read_text()
    for section in ["# Phase 0 Corpus Report", "## Lint", "## Dedup", "## Quality"]:
        assert section in text
    assert "unused_ingredient" in text  # planted defect surfaces in the report
```

- [ ] **Step 2: Run test to verify it fails** — FAIL.

- [ ] **Step 3: Implement** (`etl/report.py`)

```python
"""Emit the Phase 0 deliverable report. Spec 10 Phase 0."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def write_report(df: pd.DataFrame, out_md: Path) -> None:
    flags = df["lint_flags"].explode().value_counts()
    fams = df.groupby("family_id").agg(n=("id", "size"), title=("title", "first"))
    rated = df[df["rating_n"] > 0]
    lines = [
        f"# Phase 0 Corpus Report — {date.today()}",
        f"\n{len(df)} recipes | {int(df['rating_n'].sum())} ratings | {len(rated)} rated recipes",
        "\n## Lint",
        f"pass rate: {df['lint_pass'].mean():.1%}",
        "```\n" + (flags.to_string() if len(flags) else "no flags") + "\n```",
        "\n## Dedup",
        f"exact-dup rate: {(df['dup_group'] >= 0).mean():.1%} | families: {df['family_id'].nunique()}",
        "```\n" + fams.nlargest(10, "n").to_string() + "\n```",
        "\n## Quality",
        "```\n" + df["q_score"].quantile([.1, .25, .5, .75, .9, .99]).to_string() + "\n```",
        "\ntop: " + "; ".join(df.nlargest(3, "q_score")["title"]),
        "\nbottom: " + "; ".join(df.nsmallest(3, "q_score")["title"]),
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines))


if __name__ == "__main__":
    df = pd.read_parquet(sys.argv[1])
    out = ROOT / "docs" / "reports" / "phase0-foodcom.md"
    write_report(df, out)
    print("wrote", out)
```

- [ ] **Step 4: Run test to verify it passes** — `uv run pytest -q` → PASS (7+ tests green total).

- [ ] **Step 5: Real run (full pipeline)**

```bash
uv run python -m etl.fetch
uv run python -m etl.ingest_foodcom
uv run python -m etl.lint    data/corpus/foodcom.parquet
uv run python -m etl.dedup   data/corpus/foodcom.parquet
uv run python -m etl.quality data/corpus/foodcom.parquet
uv run python -m etl.report  data/corpus/foodcom.parquet
```

Expected: `docs/reports/phase0-foodcom.md` with real numbers on 231,637 recipes. **That file is the Phase 0 deliverable.**

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: phase 0 corpus report"`.

---

## Out of scope (next plans, with triggers)

- **RecipeNLG ingest + quantity parsing + ratio-space** — trigger: manual download from recipenlg.cs.put.poznan.pl (terms form; can't be scripted). Needed before any ratio/chemistry lint rules.
- **Rezeptwelt/Thermomix corpus + TM step grammar IR** — trigger: ToS check (spec §9.3).
- **Phase 1 critics plan** (quality weak-supervision classifier, JEPA encoder + energy head, Spearman calibration) — trigger: this plan's report exists, so critic design can key off real rating/cluster distributions. GPU side runs on DSMLP (spec §6.1).

## Self-review

- **Spec coverage:** §4.2 stages 1–5 → Tasks 2–4 (stage 2 normalization is minimal — lowercase/head-noun only — because the dump has no quantities; recorded in Out of scope). Stage 6 decontamination deferred until a benchmark exists. §5 quality axes → Task 5 (executability × shrunk hedonics; provenance constant at T1 single-source). §10 Phase 0 deliverable → Task 6.
- **Placeholder scan:** clean — every step has code or an exact command.
- **Type consistency:** column contract table is the single source; `lint_frame`/`assign_groups`/`score_frame` all take+return `pd.DataFrame` and are composed in exactly that order in Task 6's test.
