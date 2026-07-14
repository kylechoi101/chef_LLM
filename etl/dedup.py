"""Exact dups + dish families v0. Spec 4.2 stage 5: dedup in ingredient space, keep variants."""
import re
import sys
from pathlib import Path

import pandas as pd
from datasketch import MinHash, MinHashLSH

PERM = 128
JACCARD_MIN = 0.6        # exact-verified family membership bar
LSH_INDEX_THRESHOLD = 0.4  # indexed looser than JACCARD_MIN: LSH recalls candidates, exact check gates


def _norm_title(t: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z]+", t.lower())))


def _ing_set(ings) -> frozenset:
    return frozenset(re.sub(r"[^a-z ]", "", i.lower()).strip() for i in ings)


def _minhash(items) -> MinHash:
    m = MinHash(num_perm=PERM)
    for x in items:
        m.update(x.encode())
    return m


_TITLE_STOP = frozenset("""
the a an and or with in of for on to best easy quick simple classic my
homemade style old fashioned ever perfect ultimate great favorite
""".split())


def _title_tokens(t: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z]+", str(t).lower()) if w not in _TITLE_STOP)


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ing_sets = [_ing_set(i) for i in df["ingredients"]]
    title_toks = [_title_tokens(t) for t in df["title"]]
    keys = [(_norm_title(t), s) for t, s in zip(df["title"], ing_sets)]

    # exact dups: identical normalized title + ingredient set
    seen, dup_group = {}, []
    for k in keys:
        dup_group.append(seen.setdefault(k, len(seen)))
    counts = pd.Series(dup_group).value_counts()
    df["dup_group"] = [g if counts[g] > 1 else -1 for g in dup_group]

    # families: leader clustering — a recipe joins only by similarity to a
    # family's LEADER (ingredient Jaccard >= 0.6 AND >= 1 shared title token),
    # so single-linkage chaining (the 22k mega-family bug) is impossible.
    # Highest-rated recipes are processed first and anchor dish families,
    # matching the spec's "canonical center + variants" genealogy (4.2 stage 5).
    hashes = [_minhash(s) for s in ing_sets]
    lsh = MinHashLSH(threshold=LSH_INDEX_THRESHOLD, num_perm=PERM)  # indexes leaders only
    order = (-df["rating_n"].fillna(0).to_numpy()).argsort(kind="stable")
    family = [0] * len(df)
    for idx in order:
        idx = int(idx)
        leader = None
        for cand in lsh.query(hashes[idx]):
            j = int(cand)
            a, b = ing_sets[idx], ing_sets[j]
            if a and (title_toks[idx] & title_toks[j]) and len(a & b) / len(a | b) >= JACCARD_MIN:
                leader = j
                break
        if leader is None:
            lsh.insert(str(idx), hashes[idx])
            leader = idx
        family[idx] = leader
    df["family_id"] = family
    return df
    # ponytail: LSH recall is probabilistic near the 0.6 boundary; move to
    # embedding-based families only if split-leakage audits demand tighter recall


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = assign_groups(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    n, fams = len(df), df["family_id"].nunique()
    print(f"{n} recipes | exact-dup rate {(df['dup_group'] >= 0).mean():.1%} | {fams} families")
    top = df.groupby("family_id").agg(n=("id", "size"), title=("title", "first")).nlargest(10, "n")
    print(top.to_string())
