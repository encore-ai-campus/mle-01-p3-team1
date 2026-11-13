"""Cross-Encoder reranking using a pre-fetched, local-only model.

Run `uv run python -m src.hybrid.prepare_models` once after `uv sync`.
The retrieval path deliberately never downloads models from Hugging Face.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any

from .model_store import has_model_files, is_prepared, prepared_files_dir, resolve_model_dir


class CrossEncoderReranker:
    """Lazy-load from the prepared local directory and reuse within the process."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        *,
        batch_size: int = 8,
        device: str | None = None,
        model: Any | None = None,
        local_model_dir: str | None = None,
        revision: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self.revision = revision
        model_root = resolve_model_dir(model_name, local_model_dir)
        # A first-time setup can adopt the global HF cache without downloading
        # another multi-GB copy. Runtime still loads from the absolute snapshot
        # path with local_files_only=True.
        self.model_path = prepared_files_dir(model_root) if is_prepared(model_root, model_name, revision) else model_root
        self._model = model
        self.last_score_timings: dict[str, Any] = {}

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            self.last_score_timings = {"model_load_ms": 0.0, "inference_ms": 0.0}
            return []
        load_ms = 0.0
        if self._model is None:
            if not has_model_files(self.model_path):
                raise FileNotFoundError(
                    f"Cross-Encoder 모델이 준비되지 않았습니다: {self.model_path}. "
                    "프로젝트 루트에서 `uv run python -m src.hybrid.prepare_models`를 실행하세요."
                )
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers가 설치되지 않았습니다. "
                    "pyproject.toml에 의존성을 추가한 뒤 uv sync를 실행하세요."
                ) from exc
            start = perf_counter()
            kwargs: dict[str, Any] = {"local_files_only": True}
            if self.device is not None:
                kwargs["device"] = self.device
            # Load from a filesystem path, not a Hugging Face repo ID.
            # This guarantees that retrieval never fetches weights or tokenizer.
            self._model = CrossEncoder(str(self.model_path), max_length=512, **kwargs)
            load_ms = (perf_counter() - start) * 1000

        pairs = [(query, passage) for passage in passages]
        start = perf_counter()
        raw = self._model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        infer_ms = (perf_counter() - start) * 1000
        self.last_score_timings = {
            "model_load_ms": round(load_ms, 2),
            "inference_ms": round(infer_ms, 2),
            "model_path": str(self.model_path),
            "model_source": "local_only",
        }
        return [float(score) for score in raw]


def build_passage(hit: Mapping[str, Any], *, max_chars: int = 2000) -> str:
    """Include both retrieval evidence texts; never lose BM25 snippet to a long vector doc."""
    name = str(hit.get("name") or "").strip()
    vector = str(hit.get("vector_document") or "").strip()
    bm25 = str(hit.get("bm25_document") or "").strip()
    if not vector and not bm25:
        vector = str(hit.get("document") or "").strip()
    prefix = f"박물관: {name}\n" if name else ""
    budget = max(0, max_chars - len(prefix))
    if vector and bm25 and vector != bm25:
        vec_budget = budget // 2
        bm_budget = budget - vec_budget
        body = f"설명: {vector[:max(0, vec_budget - 5)]}\n검색 근거: {bm25[:max(0, bm_budget - 8)]}"
    else:
        body = vector or bm25
    return (prefix + body)[:max_chars]
