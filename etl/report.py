"""Emit the Phase 0 deliverable report. Spec 10 Phase 0."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def write_report(df: pd.DataFrame, out_md: Path) -> None:
    flags = df["lint_flags"].explode().value_counts()
    fams = df.groupby("family_id").agg(n=("id", "size"), title=("title", "first"))
    rated = df[df["rating_n"] > 0]
    lines = [
        f"# Phase 0 Corpus Report — {date.today()}",
        f"\n{len(df)} recipes | {int(df['rating_n'].sum())} ratings | {len(rated)} rated recipes",
        "\n## Lint",
        f"pass rate: {df['lint_pass'].mean():.1%}",
        "```\n" + (flags.to_string() if len(flags) else "no flags") + "\n```",
        "\n## Dedup",
        f"exact-dup rate: {(df['dup_group'] >= 0).mean():.1%} | families: {df['family_id'].nunique()}",
        "```\n" + fams.nlargest(10, "n").to_string() + "\n```",
        "\n## Quality",
        "```\n" + df["q_score"].quantile([.1, .25, .5, .75, .9, .99]).to_string() + "\n```",
        "\ntop: " + "; ".join(df.nlargest(3, "q_score")["title"]),
        "\nbottom: " + "; ".join(df.nsmallest(3, "q_score")["title"]),
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines))


if __name__ == "__main__":
    df = pd.read_parquet(sys.argv[1])
    out = ROOT / "docs" / "reports" / "phase0-foodcom.md"
    write_report(df, out)
    print("wrote", out)
