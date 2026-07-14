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
