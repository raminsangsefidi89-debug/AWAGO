"""Near-duplicate detection & event-thread clustering (addendum C).

Method: character 3-gram shingles + Jaccard similarity; union-find
clustering at a threshold. Deterministic, dependency-free, inspectable.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.news.normalize import normalize_fa

SHINGLE_N = 3
DEFAULT_THRESHOLD = 0.5


def shingles(text: str, n: int = SHINGLE_N) -> set[str]:
    t = normalize_fa(text)
    pad = f" {t} "
    return {pad[i : i + n] for i in range(max(0, len(pad) - n + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def cluster_docs(
    titles: Sequence[str], bodies: Sequence[str] | None = None, threshold: float = DEFAULT_THRESHOLD
) -> list[int]:
    """Return cluster id per document (0-based, deterministic order)."""
    bodies = bodies or [""] * len(titles)
    sets = [shingles(f"{t} {b}") for t, b in zip(titles, bodies, strict=False)]
    uf = _UnionFind(len(sets))
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            if jaccard(sets[i], sets[j]) >= threshold:
                uf.union(i, j)
    root_to_cluster: dict[int, int] = {}
    out: list[int] = []
    for i in range(len(sets)):
        r = uf.find(i)
        if r not in root_to_cluster:
            root_to_cluster[r] = len(root_to_cluster)
        out.append(root_to_cluster[r])
    return out
