import math

from etl.quality import shrunk_rating


def test_unrated_recipe_gets_prior():
    assert shrunk_rating(float("nan"), 0, prior_mean=4.4) == 4.4

def test_heavily_rated_recipe_keeps_its_mean():
    assert math.isclose(shrunk_rating(3.0, 10_000, prior_mean=4.4), 3.0, abs_tol=0.01)

def test_lightly_rated_recipe_pulled_toward_prior():
    s = shrunk_rating(5.0, 2, prior_mean=4.4)
    assert 4.4 < s < 4.6  # 5.0x2 must NOT beat a battle-tested 4.8
