from pathlib import Path

import pandas as pd

from etl.ingest_xiachufang import ingest, to_row

FIX = Path(__file__).parent / "fixtures" / "xiachufang_mini.jsonl"


def test_ingest_maps_contract_and_skips_empty(tmp_path):
    out = tmp_path / "x.parquet"
    st = ingest(FIX, out)
    assert st == {"lines": 3, "rows": 2, "skipped": 1, "with_dish": 1}
    df = pd.read_parquet(out)
    r = df.iloc[0]
    assert r["title"] == "西班牙金枪鱼沙拉" and r["dish"] == "金枪鱼沙拉" and r["lang"] == "zh"
    assert list(r["ingredients"]) == ["超市罐头装半盒金枪鱼", "2大片生菜", "5个圣女果"] and r["n_ingredients"] == 3
    assert len(r["steps"]) == 3 and r["rating_n"] == 0 and pd.isna(r["rating_mean"])
    assert df.iloc[1]["dish"] == ""          # "Unknown" normalised to empty
    assert df["source_kind"].eq("dataset").all()


def test_to_row_rejects_title_only():
    assert to_row(0, {"name": "x", "recipeIngredient": [], "recipeInstructions": []}) is None
