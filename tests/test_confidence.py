import pandas as pd

from etl.confidence import REMAKE_RE, score_confidence


def _corpus():
    return pd.DataFrame([
        # ids 1 and 8: same ingredient set, different authors -> one copy group
        {"id": 1, "title": "classic tomato soup", "ingredients": ["onion", "canned tomatoes", "salt"],
         "rating_n": 15, "lint_flags": []},
        {"id": 8, "title": "tomato soup", "ingredients": ["Onion", "canned tomatoes", "salt"],
         "rating_n": 10, "lint_flags": []},
        {"id": 2, "title": "garlic pasta", "ingredients": ["spaghetti", "garlic"],
         "rating_n": 4, "lint_flags": []},
        {"id": 3, "title": "lonely cake  rsc", "ingredients": ["flour", "egg"],
         "rating_n": 0, "lint_flags": []},
        {"id": 7, "title": "mystery casserole", "ingredients": ["beef"],
         "rating_n": 50, "lint_flags": ["no_steps"]},
    ])


def _meta():
    return pd.DataFrame({
        "id": [1, 8, 2, 3, 7],
        "contributor_id": [100, 200, 300, 400, 500],
        "submitted": ["2015-01-01", "2016-01-01", "2019-01-01", "2020-01-01", "2010-01-01"],
    })


def _interactions():
    return pd.DataFrame({
        "recipe_id": [1, 1, 2, 2, 7],
        "date": ["2015-06-01", "2020-06-01", "2019-02-01", "2019-03-01", "2011-01-01"],
        "rating": [5, 5, 4, 0, 5],
        "review": ["Perfect.", "I've made this again and again, a keeper!",
                   "fine", "haven't made it yet", "yum"],
    })


def test_copies_pool_and_count_distinct_authors():
    out = score_confidence(_corpus(), _meta(), _interactions()).set_index("id")
    assert out.loc[1, "copy_group"] == out.loc[8, "copy_group"]
    assert out.loc[1, "n_authors"] == 2
    assert out.loc[1, "pooled_rating_n"] == 25 == out.loc[8, "pooled_rating_n"]


def test_remake_language_detected_and_pooled():
    assert REMAKE_RE.search("i've made this again and again")
    assert REMAKE_RE.search("this is a keeper")
    assert not REMAKE_RE.search("haven't made it yet but looks great")
    out = score_confidence(_corpus(), _meta(), _interactions()).set_index("id")
    assert out.loc[1, "remake_n"] == 1 and out.loc[8, "pooled_remake_n"] == 1


def test_tiers():
    out = score_confidence(_corpus(), _meta(), _interactions()).set_index("id")
    assert out.loc[1, "pos_tier"] == 3          # pooled 25 ratings, 5 years active
    assert out.loc[2, "pos_tier"] == 2          # 4 ratings
    assert out.loc[3, "pos_tier"] == 1 and out.loc[3, "is_contest"]
    assert out.loc[7, "pos_tier"] == 0          # structural failure beats ratings
    assert out.loc[1, "pos_weight"] > out.loc[2, "pos_weight"] > out.loc[3, "pos_weight"] > 0
    assert out.loc[7, "pos_weight"] == 0
