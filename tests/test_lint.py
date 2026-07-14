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


# --- real-data failure modes of the v0 head-noun matcher (72% fire rate on Food.com) ---

def _unused(steps, ingredients):
    return "unused_ingredient" in lint_recipe("t", 30, steps, ingredients, 100.0)


def test_plural_singular_mismatch_not_flagged():
    # "tomatoes" listed, steps say "tomato paste" — v0 stemmed to "tomatoe" and missed
    assert not _unused(["stir in the tomato paste", "simmer gently"], ["tomatoes"])


def test_any_content_word_counts_as_used():
    # v0 matched only the LAST word ("breasts"); steps naming "chicken" must count
    assert not _unused(["brown the chicken until golden", "rest and serve"],
                       ["boneless skinless chicken breasts"])


def test_catchall_step_disables_check():
    # "combine all ingredients" can't be verified item-by-item — never flag
    assert not _unused(["combine all ingredients in a bowl", "bake 20 minutes"],
                       ["flour", "eggs", "obscure spice blend"])


def test_season_to_taste_covers_salt_and_pepper():
    assert not _unused(["grill the steak", "season to taste and serve"],
                       ["steak", "salt", "black pepper"])


def test_genuinely_unused_still_detected():
    assert _unused(["saute the onion", "serve warm"], ["onion", "saffron"])
