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
