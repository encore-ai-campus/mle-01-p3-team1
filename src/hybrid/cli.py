"""Actual project CLI. Needs project dependencies, Chroma data and LLM key.

Usage:
    python -m src.hybrid.cli "독립운동 박물관" --no-rerank
    python -m src.hybrid.cli "독립운동 박물관" --corpus data/spans.jsonl
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace

from .config import HybridConfig
from .factory import build_hybrid_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Museum BM25 + Vector Hybrid Search")
    parser.add_argument("query", help="사용자 질문")
    parser.add_argument("--corpus", help="TextSpan JSONL/CSV. 생략하면 기존 Chroma 문서로 BM25 색인을 생성")
    parser.add_argument("--no-rerank", action="store_true", help="Cross-Encoder를 실행하지 않고 RRF만 평가")
    parser.add_argument("--vector-weight", type=float)
    parser.add_argument("--bm25-weight", type=float)
    parser.add_argument("--fusion-top-k", type=int)
    parser.add_argument("--final-top-k", type=int)
    parser.add_argument("--show-fusion", action="store_true")
    parser.add_argument("--no-ontology-filter", action="store_true",
                        help="구조 조건 후보 필터 없이 전체 코퍼스에서 검색")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    cfg = HybridConfig.from_env()
    overrides = {"vector_weight": args.vector_weight, "bm25_weight": args.bm25_weight,
                 "fusion_top_k": args.fusion_top_k, "final_top_k": args.final_top_k}
    cfg = replace(cfg, **{key: value for key, value in overrides.items() if value is not None})
    hybrid = build_hybrid_service(
        corpus_source="file" if args.corpus else "chroma",
        corpus_path=args.corpus,
        config=cfg,
        **({"candidate_filter": None} if args.no_ontology_filter else {}),
    )
    result = hybrid.search(args.query, rerank=not args.no_rerank, include_fusion_candidates=args.show_fusion)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
