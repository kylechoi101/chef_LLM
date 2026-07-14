"""Lint v0: referential integrity + sanity. Spec 4.2 stage 3."""
import re
import sys
from pathlib import Path

import pandas as pd

WEEK_MIN = 10080


def _head_noun(name: str) -> str:
    words = re.findall(r"[a-z]+", name.lower())
    return (words[-1].rstrip("s") if words else "")  # ponytail: last-word + strip plural; real NER when it misses


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
    body = " ".join(steps).lower()
    if steps and ingredients and any(
        _head_noun(i) and _head_noun(i) not in body for i in ingredients
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
