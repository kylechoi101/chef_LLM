"""Phase 1 step 1: cross-tab each lint flag against reproduction evidence.

A flag is a real executability failure only if flagged recipes get reproduced
(rated) less than passed ones. A flag whose flagged set looks like the passed
set on rating_n is a linter artifact and must not gate anything.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def audit(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rated10"] = df["rating_n"] >= 10
    df["rated1"] = df["rating_n"] >= 1
    base = df[df["lint_pass"]]
    rows = [_row("PASS (baseline)", base, base)]
    flags = sorted({f for fl in df["lint_flags"] for f in fl})
    for f in flags:
        sub = df[df["lint_flags"].map(lambda fl, f=f: f in fl)]
        rows.append(_row(f, sub, base))
    return pd.DataFrame(rows).set_index("flag")


def _row(name, sub, base):
    rated = sub[sub["rating_n"] > 0]
    return {
        "flag": name,
        "n": len(sub),
        "share_rated": round(sub["rated1"].mean(), 3),
        "share_rated>=10": round(sub["rated10"].mean(), 3),
        "median_rating_n": float(sub["rating_n"].median()),
        "mean_rating_n": round(sub["rating_n"].mean(), 1),
        "mean_stars(rated)": round(rated["rating_mean"].mean(), 3) if len(rated) else float("nan"),
        "ratio_rated>=10_vs_pass": round(sub["rated10"].mean() / base["rated10"].mean(), 2),
    }


def _markdown(t: pd.DataFrame) -> str:
    cols = [t.index.name or "flag"] + list(t.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, r in t.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in r.tolist()]) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = pd.read_parquet(path, columns=["lint_flags", "lint_pass", "rating_n", "rating_mean"])
    df["lint_flags"] = df["lint_flags"].map(list)
    table = audit(df)
    md = _markdown(table)
    print(md)
    out = ROOT / "docs" / "reports" / "phase1-step1-lint-vs-rating.md"
    out.write_text(
        "# Phase 1 step 1 — lint flags vs reproduction evidence\n\n"
        f"Source: `{path.name}`, {len(df)} recipes. `ratio_rated>=10_vs_pass` < 1 means flagged "
        "recipes are reproduced less than lint-passing ones (flag carries executability signal); "
        "~1 means the flag is a linter artifact.\n\n" + md + "\n"
    )
    print("wrote", out.relative_to(ROOT))
