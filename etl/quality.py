"""Quality v0: IMDb-style Bayesian shrinkage x lint gate. Spec 5."""
import sys
from pathlib import Path

import pandas as pd

PRIOR_N = 20  # ponytail: fixed pseudo-count; tune against held-out reproduction signals in Phase 1


def shrunk_rating(mean, n, prior_mean, prior_n=PRIOR_N) -> float:
    if not n or pd.isna(mean):
        return prior_mean
    return (n * mean + prior_n * prior_mean) / (n + prior_n)


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    prior = df.loc[df["rating_n"] > 0, "rating_mean"].mean()
    df["q_rating"] = [shrunk_rating(m, n, prior) for m, n in zip(df["rating_mean"], df["rating_n"])]
    df["q_score"] = (df["q_rating"] / 5.0) * df["lint_pass"].astype(float)
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = score_frame(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    print(df["q_score"].describe().to_string())
