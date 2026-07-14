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


def _mini(rows):
    return pd.DataFrame(
        [{"id": i, "title": t, "ingredients": ing, "rating_n": n}
         for i, (t, ing, n) in enumerate(rows, start=1)]
    )


def test_no_transitive_chaining():
    # A~B and B~C are each similar, but A~C is not (Jaccard 0.43).
    # Union-find (the 22k mega-family bug) merges all three; leader
    # clustering must keep C out because it only compares to the leader A.
    df = _mini([
        ("classic chicken rice", ["chicken", "rice", "onion", "garlic", "stock"], 300),  # leader
        ("easy chicken rice", ["chicken", "rice", "onion", "garlic", "butter"], 100),    # joins A (J=0.67)
        ("chicken rice peas skillet", ["chicken", "rice", "onion", "butter", "peas"], 10),  # J to A = 0.43
    ])
    g = assign_groups(df).set_index("id")
    assert g.loc[1, "family_id"] == g.loc[2, "family_id"]
    assert g.loc[3, "family_id"] != g.loc[1, "family_id"]


def test_title_guard_blocks_coincidental_pantry_overlap():
    # Near-identical ingredient sets but zero shared title tokens = different dishes
    df = _mini([
        ("hoppin john", ["black eyed peas", "rice", "onion", "bacon", "stock"], 80),
        ("southern peas and bacon skillet", ["black eyed peas", "rice", "onion", "bacon", "butter"], 20),
    ])
    g = assign_groups(df).set_index("id")
    assert g.loc[1, "family_id"] != g.loc[2, "family_id"]
