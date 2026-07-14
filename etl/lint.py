"""Lint v0: referential integrity + sanity. Spec 4.2 stage 3."""
import re
import sys
from pathlib import Path

import pandas as pd

WEEK_MIN = 10080


# prep/state/size words that never identify an ingredient on their own
_DESCRIPTORS = frozenset("""
fresh dried ground minced chopped sliced diced grated shredded crushed melted
softened frozen canned cooked uncooked boneless skinless seedless peeled
large small medium extra light dark sweet hot mild plain whole half lean
low reduced nonfat fat free sodium purpose all optional packed firmly finely
coarsely thinly roughly cut into pieces
""".split())

_CATCHALL = frozenset({"ingredient", "everything"})  # "combine all ingredients", "mix everything"


def _stem(w: str) -> str:
    # ponytail: 3-rule singularizer, applied to BOTH sides so consistency beats correctness
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("es"):
        return w[:-2]
    if len(w) > 2 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower())}


def _ingredient_used(name: str, body: set[str]) -> bool:
    content = _tokens(name) - {_stem(w) for w in _DESCRIPTORS}
    if not content or content & body:
        return True
    # compound-word fallback: "corn flakes" ~ "cornflakes", "gingerroot" ~ "ginger root";
    # len>3 on both sides so "oil" never matches "boil"
    long_body = [b for b in body if len(b) > 3]
    return any(t in b or b in t for t in content if len(t) > 3 for b in long_body)


def lint_recipe(title, minutes, steps, ingredients, calories) -> list[str]:
    flags = []
    steps = [s for s in (steps or []) if s.strip()]
    ingredients = list(ingredients or [])
    if not steps:
        flags.append("no_steps")
    elif len(steps) < 2:
        flags.append("too_few_steps")
    if not ingredients:
        flags.append("no_ingredients")
    if len(set(i.lower() for i in ingredients)) < len(ingredients):
        flags.append("dup_ingredient")
    body = _tokens(" ".join(steps))
    if "season" in body or "taste" in body:
        body |= {"salt", "pepper", "seasoning"}
    if steps and ingredients and not (body & _CATCHALL) and any(
        not _ingredient_used(i, body) for i in ingredients
    ):
        flags.append("unused_ingredient")
    if minutes is None or minutes <= 0:
        flags.append("time_missing")
    elif minutes > WEEK_MIN:
        flags.append("time_insane")
    if calories is not None and not pd.isna(calories) and (calories <= 0 or calories > 30000):
        flags.append("calorie_outlier")
    return flags


def lint_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["lint_flags"] = [
        lint_recipe(t, m, list(s), list(i), c)
        for t, m, s, i, c in zip(df["title"], df["minutes"], df["steps"],
                                 df["ingredients"], df["calories"])
    ]
    df["lint_pass"] = df["lint_flags"].map(len) == 0
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = lint_frame(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    n = len(df)
    print(f"{n} recipes, pass rate {df['lint_pass'].mean():.1%}")
    print(df["lint_flags"].explode().value_counts().to_string())
