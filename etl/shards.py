"""Sharded parquet writer + append-only resume log, shared by the crawlers."""
from pathlib import Path

import pandas as pd


class DoneSet:
    """`key \\t status` per line; membership = already processed (any status)."""

    def __init__(self, path: Path):
        self.path = path
        self.keys: set[str] = set()
        if path.exists():
            self.keys = {ln.split("\t")[0] for ln in path.read_text().splitlines() if ln}

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def __len__(self) -> int:
        return len(self.keys)

    def with_status(self, status: str) -> set[str]:
        if not self.path.exists():
            return set()
        last: dict[str, str] = {}
        for ln in self.path.read_text().splitlines():
            if ln and "\t" in ln:
                k, st = ln.split("\t", 1)
                last[k] = st
        return {k for k, st in last.items() if st == status}

    def add(self, key: str, status: str = "ok") -> None:
        self.keys.add(key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{key}\t{status}\n")


class ShardWriter:
    def __init__(self, directory: Path, prefix: str, flush_every: int = 200):
        self.dir, self.prefix, self.flush_every = directory, prefix, flush_every
        directory.mkdir(parents=True, exist_ok=True)
        self.n = len(list(directory.glob(f"{prefix}-*.parquet")))
        self.buf: list[dict] = []
        self.written = 0

    def add(self, row: dict) -> None:
        self.buf.append(row)
        if len(self.buf) >= self.flush_every:
            self.flush()

    def flush(self) -> Path | None:
        if not self.buf:
            return None
        out = self.dir / f"{self.prefix}-{self.n:05d}.parquet"
        pd.DataFrame(self.buf).to_parquet(out, index=False)
        self.n += 1
        self.written += len(self.buf)
        self.buf = []
        return out


def read_shards(directory: Path, prefix: str) -> pd.DataFrame:
    files = sorted(directory.glob(f"{prefix}-*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()
