"""Canonical display names and equivalence groups for museum Sido values.

These aliases are applied at query/evidence time. They do not mutate Neo4j or ChromaDB.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.region_aliases import SIDO_ALIAS_FAMILIES, canonicalize_sido, sido_aliases


def matching_sido_family(text: str) -> tuple[str, ...]:
    """Find the one alias family explicitly named in text, if unambiguous."""
    matched = {
        canonical
        for canonical, aliases in SIDO_ALIAS_FAMILIES.items()
        if any(alias in text for alias in aliases)
    }
    if len(matched) != 1:
        return ()
    return SIDO_ALIAS_FAMILIES[next(iter(matched))]


def expand_sido_terms(terms: Iterable[str]) -> list[str]:
    """Expand exact region keywords so old and current graph rows are searchable."""
    expanded: list[str] = []
    for term in terms:
        aliases = sido_aliases(term)
        for alias in aliases or (term,):
            if alias and alias not in expanded:
                expanded.append(alias)
    return expanded
