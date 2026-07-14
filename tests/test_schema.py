import json
from pathlib import Path

from etl.schema import RecipeIR

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"


def test_fixture_loads_as_recipe_ir():
    records = json.loads(FIXTURE.read_text())
    recipes = [RecipeIR.from_dict(r) for r in records]
    assert len(recipes) == 8
    r = recipes[0]
    assert r.id == 1 and r.source == "foodcom"
    assert isinstance(r.steps, list) and isinstance(r.ingredients, list)
    assert recipes[6].steps == []  # id 7: planted empty-steps defect
