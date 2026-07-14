"""Exact dups + dish families v0. Spec 4.2 stage 5: dedup in ingredient space, keep variants."""
import re
import sys
from pathlib import Path

import pandas as pd
from datasketch import MinHash, MinHashLSH

PERM = 128


def _norm_title(t: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z]+", t.lower())))


def _ing_set(ings) -> frozenset:
    return frozenset(re.sub(r"[^a-z ]", "", i.lower()).strip() for i in ings)


def _minhash(items) -> MinHash:
    m = MinHash(num_perm=PERM)
    for x in items:
        m.update(x.encode())
    return m


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    keys = [(_norm_title(t), _ing_set(i)) for t, i in zip(df["title"], df["ingredients"])]

    # exact dups: identical normalized title + ingredient set
    seen, dup_group = {}, []
    for k in keys:
        dup_group.append(seen.setdefault(k, len(seen)))
    counts = pd.Series(dup_group).value_counts()
    df["dup_group"] = [g if counts[g] > 1 else -1 for g in dup_group]

    # families: LSH candidates on ingredient sets, verified by Jaccard >= 0.6, union-find
    lsh = MinHashLSH(threshold=0.6, num_perm=PERM)
    hashes = [_minhash(k[1]) for k in keys]
    for idx, mh in enumerate(hashes):
        lsh.insert(str(idx), mh)
    parent = list(range(len(df)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for idx, mh in enumerate(hashes):
        for cand in lsh.query(mh):
            j = int(cand)
            a, b = keys[idx][1], keys[j][1]
            if idx != j and a and len(a & b) / len(a | b) >= 0.6:
                parent[find(idx)] = find(j)
    df["family_id"] = [find(i) for i in range(len(df))]
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1])
    df = assign_groups(pd.read_parquet(path))
    df.to_parquet(path, index=False)
    n, fams = len(df), df["family_id"].nunique()
    print(f"{n} recipes | exact-dup rate {(df['dup_group'] >= 0).mean():.1%} | {fams} families")
    top = df.groupby("family_id").agg(n=("id", "size"), title=("title", "first")).nlargest(10, "n")
    print(top.to_string())
