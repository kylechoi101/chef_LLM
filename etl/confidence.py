"""Phase 1 step 2: positive-confidence tiers.

Answers "how sure are we this recipe is a real survivor?", NOT "how delicious
is it". Signals: reproduction (ratings + remake language in reviews), copies by
distinct authors, longevity, source/contest discount, structural failure.
Evidence pools across cosmetic copies (identical normalized ingredient set).
Star mean is deliberately absent — it is only used pairwise in step 6.
"""
import re
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

REMAKE_RE = re.compile(
    r"\b("
    r"made (this|it|these|them) (again|twice|several times|many times|countless times|\d+ times|a dozen)"
    r"|make (this|it|these) (again|all the time|weekly|every week|every|often|regularly|constantly)"
    r"|(be making|making) (this|it|these) again"
    r"|(a|real|definite|definitely a) keeper"
    r"|go[- ]to( recipe)?"
    r"|(family|house|weeknight) (favorite|favourite|staple)"
    r"|(in|into) (the|our|my) (regular )?rotation"
    r"|again and again"
    r")\b",
    re.IGNORECASE,
)
CONTEST_RE = re.compile(r"\brsc\b", re.IGNORECASE)  # Food.com "Ready Set Cook" entries
STRUCTURAL = {"no_steps", "no_ingredients"}  # only flags that survive step 1's audit as exclusions
TIER_WEIGHT = {0: 0.0, 1: 0.25, 2: 0.6, 3: 1.0}


def _copy_key(ings) -> str:
    return "|".join(sorted({re.sub(r"[^a-z ]", "", str(i).lower()).strip() for i in ings}))


def _tier(row) -> int:
    if row["structural_fail"] or row["safety_fail"]:
        return 0
    r, m, y, a = row["pooled_rating_n"], row["pooled_remake_n"], row["years_active"], row["n_authors"]
    if r >= 20 or m >= 3 or (r >= 10 and y >= 3):
        return 3
    if r >= 3 or m >= 1 or a >= 2:
        return 2
    return 1


def score_confidence(df: pd.DataFrame, meta: pd.DataFrame, inter: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    meta = meta[["id", "contributor_id", "submitted"]].copy()
    meta["submitted"] = pd.to_datetime(meta["submitted"], errors="coerce")
    df = df.merge(meta, on="id", how="left")

    inter = inter.copy()
    inter["date"] = pd.to_datetime(inter["date"], errors="coerce")
    inter["remake"] = inter["review"].fillna("").astype(str).map(lambda s: bool(REMAKE_RE.search(s)))
    per = inter.groupby("recipe_id").agg(remake_n=("remake", "sum"), last_review=("date", "max"))
    df = df.merge(per, left_on="id", right_index=True, how="left")
    df["remake_n"] = df["remake_n"].fillna(0).astype("int64")
    df["years_active"] = ((df["last_review"] - df["submitted"]).dt.days / 365.25).fillna(0).clip(lower=0)

    df["copy_group"] = df["ingredients"].map(_copy_key)
    grp = df.groupby("copy_group")
    df["n_copies"] = grp["id"].transform("size")
    df["n_authors"] = grp["contributor_id"].transform("nunique")
    df["pooled_rating_n"] = grp["rating_n"].transform("sum")
    df["pooled_remake_n"] = grp["remake_n"].transform("sum")

    df["is_contest"] = df["title"].astype(str).str.contains(CONTEST_RE)
    df["structural_fail"] = df["lint_flags"].map(lambda fl: bool(STRUCTURAL & set(fl)))
    df["safety_fail"] = df["safety_flags"].map(bool) if "safety_flags" in df else False  # step 3 slot

    df["pos_tier"] = df.apply(_tier, axis=1).astype("int8")
    df["pos_weight"] = df["pos_tier"].map(TIER_WEIGHT)
    return df.drop(columns=["last_review", "submitted", "contributor_id"])


def _report(df: pd.DataFrame) -> str:
    tiers = df.groupby("pos_tier").agg(
        n=("id", "size"), median_rating_n=("rating_n", "median"),
        mean_remake=("remake_n", "mean"), contest_share=("is_contest", "mean"))
    tiers["share"] = (tiers["n"] / len(df)).round(3)
    copies = df.drop_duplicates("copy_group")
    lines = [
        "# Phase 1 step 2 — positive-confidence tiers", "",
        f"{len(df)} recipes | {df['copy_group'].nunique()} distinct ingredient sets "
        f"| {int((copies['n_copies'] > 1).sum())} copy groups with >1 recipe "
        f"| {int(df['remake_n'].sum())} remake-language reviews "
        f"| {int(df['is_contest'].sum())} contest entries", "",
        "Tier 3 = loud yes (pooled ratings >= 20, or >= 3 remake reviews, or >= 10 ratings and >= 3 years active). "
        "Tier 2 = ordinary (>= 3 ratings, or a remake review, or >= 2 distinct authors). "
        "Tier 1 = whisper. Tier 0 = structural/safety exclusion.", "",
        "```", tiers.round(3).to_string(), "```", "",
        "## Largest copy groups (distinct authors)", "```",
        df.groupby("copy_group").agg(n=("id", "size"), authors=("n_authors", "first"),
                                     title=("title", "first")).nlargest(8, "n").to_string(), "```", "",
        "## Sample tier 3", "",
        "; ".join(df[df["pos_tier"] == 3].nlargest(8, "pooled_remake_n")["title"]), "",
        "## Sample tier 1 with most ratings (whispers that almost made it)", "",
        "; ".join(df[df["pos_tier"] == 1].nlargest(5, "rating_n")["title"]), "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = pd.read_parquet(path)
    df["lint_flags"] = df["lint_flags"].map(list)
    meta = pd.read_csv(DATA / "raw" / "RAW_recipes.csv", usecols=["id", "contributor_id", "submitted"])
    inter = pd.read_csv(DATA / "raw" / "RAW_interactions.csv", usecols=["recipe_id", "date", "review"])
    df = score_confidence(df, meta, inter)
    df.to_parquet(path, index=False)
    out = DATA.parent / "docs" / "reports" / "phase1-step2-confidence.md"
    out.write_text(_report(df))
    print(_report(df))
    print("wrote", out.relative_to(DATA.parent))
