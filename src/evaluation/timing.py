"""Formatting helpers for per-question retrieval and answer timing."""
from __future__ import annotations

from collections.abc import Sequence


def timing_summary(durations_ms: Sequence[float]) -> str:
    if not durations_ms:
        return "평균 - · 최대 -"
    return f"평균 {sum(durations_ms) / len(durations_ms) / 1000:.2f}초 · 최대 {max(durations_ms) / 1000:.2f}초"
