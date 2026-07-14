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


def test_rating_zero_rows_are_excluded(tmp_path):
    df = ingest(FIX / "RAW_recipes_mini.csv", FIX / "RAW_interactions_mini.csv",
                tmp_path / "corpus.parquet").set_index("id")
    # id 101 has ratings [5, 4, 0]: the 0 is a review-without-rating, not a score
    assert df.loc[101, "rating_n"] == 2 and df.loc[101, "rating_mean"] == 4.5
    # id 104's only interaction is a rating-0 review -> counts as unrated
    assert df.loc[104, "rating_n"] == 0 and pd.isna(df.loc[104, "rating_mean"])
