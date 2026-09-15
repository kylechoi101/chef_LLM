"""XiaChuFang corpus (Liu et al., EMNLP 2022; 1,479,764 Chinese recipes, pre-Dec 2020)
-> contract Parquet. Bulk dataset, no scraping. Streams the 1.9 GB JSONL in batches.

Source: https://github.com/xxxiaol/counterfactual-recipe-generation (recipe_corpus_finetune.zip)
Fields per line: name, dish (curated dish label or "Unknown"), description,
recipeIngredient, recipeInstructions, author (anonymised), keywords.
No ratings, dates, or comments: rows enter as low-confidence positives (plan step 2)
until a reproduction signal (e.g. Bilibili engagement) is joined.
"""
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

DATA = Path(__file__).resolve().parent.parent / "data"
SRC = DATA / "raw" / "xiachufang" / "recipe_corpus_finetune.json"
OUT = DATA / "corpus" / "xiachufang.parquet"
BATCH = 100_000

SCHEMA = pa.schema([
    ("id", pa.int64()), ("source", pa.string()), ("source_kind", pa.string()), ("lang", pa.string()),
    ("title", pa.string()), ("dish", pa.string()), ("description", pa.string()),
    ("ingredients", pa.list_(pa.string())), ("steps", pa.list_(pa.string())),
    ("n_ingredients", pa.int64()), ("minutes", pa.int64()),
    ("calories", pa.float64()), ("rating_mean", pa.float64()), ("rating_n", pa.int64()),
    ("author", pa.string()), ("keywords", pa.list_(pa.string())), ("url", pa.string()),
])


def to_row(idx: int, d: dict) -> dict | None:
    ings = [str(x).strip() for x in d.get("recipeIngredient") or [] if str(x).strip()]
    steps = [str(x).strip() for x in d.get("recipeInstructions") or [] if str(x).strip()]
    title = (d.get("name") or "").strip()
    if not title or not (ings or steps):
        return None
    dish = (d.get("dish") or "").strip()
    return {
        "id": idx, "source": "xiachufang", "source_kind": "dataset", "lang": "zh",
        "title": title, "dish": "" if dish == "Unknown" else dish,
        "description": (d.get("description") or "").strip(),
        "ingredients": ings, "steps": steps, "n_ingredients": len(ings),
        "minutes": 0, "calories": None, "rating_mean": None, "rating_n": 0,
        "author": d.get("author") or "", "keywords": [str(k) for k in d.get("keywords") or []],
        "url": "",
    }


def ingest(src: Path = SRC, out: Path = OUT) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(out, SCHEMA, compression="zstd")
    stats = {"lines": 0, "rows": 0, "skipped": 0, "with_dish": 0}
    batch: list[dict] = []

    def flush():
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
            batch.clear()

    with open(src, encoding="utf-8") as f:
        for i, line in enumerate(f):
            stats["lines"] += 1
            try:
                row = to_row(i, json.loads(line))
            except json.JSONDecodeError:
                row = None
            if row is None:
                stats["skipped"] += 1
                continue
            stats["rows"] += 1
            stats["with_dish"] += bool(row["dish"])
            batch.append(row)
            if len(batch) >= BATCH:
                flush()
    flush()
    writer.close()
    return stats


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    st = ingest(src, out)
    print(json.dumps(st), "->", out, file=sys.stderr)
