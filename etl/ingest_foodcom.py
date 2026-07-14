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


def _calories(s):
    v = _listify(s)
    try:
        return float(v[0]) if v else None
    except ValueError:
        return None


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
        "calories": rec["nutrition"].map(_calories).astype("float64"),
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
