"""Shared, code-only Sido aliases for retrieval and display.

These aliases normalize query/result copies. They never rewrite source CSVs or
persisted ChromaDB/Neo4j records.
"""

from __future__ import annotations

from typing import Any

SIDO_ALIAS_FAMILIES: dict[str, tuple[str, ...]] = {
    "전북특별자치도": ("전북특별자치도", "전라북도", "전북", "전라북"),
    "전남광주특별자치도": (
        "전남광주특별자치도", "전남광주통합특별시", "전라남도", "전남", "전라남",
    ),
}

SIDO_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in SIDO_ALIAS_FAMILIES.items()
    for alias in aliases
}


def canonicalize_sido(value: Any) -> str:
    """Return the preferred current label for a stored or requested alias."""
    if value is None:
        return ""
    label = str(value).strip()
    return SIDO_TO_CANONICAL.get(label, label)


def sido_aliases(value: Any) -> tuple[str, ...]:
    """Return all stored spellings equivalent to an exact Sido label."""
    label = str(value).strip() if value is not None else ""
    canonical = canonicalize_sido(label)
    return SIDO_ALIAS_FAMILIES.get(canonical, (label,) if label else ())
