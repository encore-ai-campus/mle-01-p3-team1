"""Exact museum-name lookup so a facility named in the question is never lost.

Vector and BM25 can miss a facility even when the question names it (e.g. the
name "소수박물관" starts with the common word 소수). When the question contains a
recorded facility name verbatim, HybridSearchService puts that facility into
the candidate list before Cross-Encoder reranking. The Cross-Encoder still
decides the final order.

Names come from the read-only processed CSV. Matching ignores spaces and a
trailing parenthetical (e.g. seasonal "(11월~2월)" entries) and keeps only the
longest match, so "국립중앙박물관" does not also match "중앙박물관".
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = PROJECT_ROOT / "data" / "processed" / "museum_final_738.csv"
MIN_NAME_LENGTH = 4  # shorter names (e.g. "바움") collide with ordinary words


def normalize_name(name: str) -> str:
    name = re.sub(r"\([^)]*\)\s*$", "", str(name or ""))
    return re.sub(r"\s+", "", name).casefold()


class MuseumNameIndex:
    def __init__(self, names: dict[str, list[str]]):
        # normalized name -> museum ids (several ids share a name, e.g. seasonal rows)
        self._names = {key: list(dict.fromkeys(ids)) for key, ids in names.items() if len(key) >= MIN_NAME_LENGTH}
        self._ordered = sorted(self._names, key=len, reverse=True)

    @classmethod
    def from_csv(cls, path: str | Path = DEFAULT_CSV) -> MuseumNameIndex:
        names: dict[str, list[str]] = {}
        with Path(path).open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                names.setdefault(normalize_name(row["name"]), []).append(row["museum_id"])
        return cls(names)

    def match(self, question: str) -> list[tuple[str, list[str]]]:
        """Return [(normalized name, museum ids)] for names written in the question."""
        text = normalize_name(question)
        found: list[tuple[str, list[str]]] = []
        covered: list[tuple[int, int]] = []
        for name in self._ordered:
            start = text.find(name)
            while start >= 0:
                end = start + len(name)
                # Skip any overlap with a longer name already found: with spaces removed,
                # "서대문자연사박물관 수유실" must not also yield the facility "박물관 수".
                if not any(start < e and s < end for s, e in covered):
                    covered.append((start, end))
                    found.append((name, self._names[name]))
                    break
                start = text.find(name, start + 1)
        return found


_DEFAULT_INDEX: MuseumNameIndex | None = None
_LOCK = Lock()


def default_name_index() -> MuseumNameIndex | None:
    """CSV-backed index unless HYBRID_NAME_MATCH=off."""
    if os.getenv("HYBRID_NAME_MATCH", "on").strip().lower() in {"0", "off", "false", "no"}:
        return None
    global _DEFAULT_INDEX
    with _LOCK:
        if _DEFAULT_INDEX is None:
            _DEFAULT_INDEX = MuseumNameIndex.from_csv()
    return _DEFAULT_INDEX
