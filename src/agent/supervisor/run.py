"""CLI: real LangGraph demo, or connect a teammate's module:function.

Run from repository root. Demo retrieval and verification are SYNTHETIC.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from . import AnswerDraft, RouteDecision, VerificationResult, adapt_hybrid, build_supervisor


def build_demo_supervisor(*, empty: bool = False):
    def hybrid(state):
        if empty:
            return {"evidence": [], "vector_search_status": "no_results"}
        return {"evidence": [{"museum_id": "DEMO_M1", "name": "Demo Museum",
                "text": "Synthetic museum evidence used only to test the orchestration.",
                "span_id": "DEMO_S1", "source_doc_ids": ["DEMO_DOC1"],
                "retriever": "hybrid"}],
                "vector_search_status": "partial",
                "vector_search_diagnostics": {"warnings": ["Synthetic demo, not real retrieval"]},
                "hybrid_search_diagnostics": {"demo": True}}
    return build_supervisor(
        hybrid_search=adapt_hybrid(hybrid),
        route_question=lambda s,c: RouteDecision("hybrid", "Demo fixed route; no LLM decision"),
        answer_question=lambda s,c: AnswerDraft("DEMO ONLY: synthetic evidence [E1]", ["E1"]),
        verify_answer=lambda s,c: VerificationResult(True, "DEMO fixture check, not factual verification", []),
        max_retries=1,
    )


def load_callable(value: str):
    module_name, separator, attr = value.partition(":")
    if not separator or not module_name or not attr:
        raise ValueError("Expected actual_team_module:function_name")
    fn = getattr(importlib.import_module(module_name), attr)
    if not callable(fn):
        raise TypeError("Hybrid entry point must be callable")
    return fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Museum Supervisor")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--hybrid", metavar="MODULE:FUNCTION", help="Actual teammate entry point, not a placeholder")
    parser.add_argument("--question", default="museum information")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--route", choices=["auto", "vector", "graph", "hybrid"], default="auto")
    parser.add_argument("--empty-demo", action="store_true")
    parser.add_argument("--model", help="Team-selected structured-output model")
    parser.add_argument("--with-vector", action="store_true", help="Also connect documented VectorSearchRetriever")
    parser.add_argument("--hybrid-accepts-config", action="store_true")
    parser.add_argument("--out", help="Optional JSON output under outputs/supervisor/")
    args = parser.parse_args()

    if args.demo:
        app = build_demo_supervisor(empty=args.empty_demo)
    else:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
        from .connect import build_connected_supervisor
        vector = None
        if args.with_vector:
            from src.service.vector_search_rag_agent import VectorSearchRetriever
            vector = VectorSearchRetriever()
        app = build_connected_supervisor(
            hybrid_node=load_callable(args.hybrid), vector_retriever=vector,
            model_name=args.model, hybrid_accepts_config=args.hybrid_accepts_config,
        )

    result = app.invoke({"question": args.question, "top_k": args.top_k,
                         "route_override": args.route},
                        config={"run_name": "museum_supervisor", "tags": ["demo" if args.demo else "real"],
                                "recursion_limit": 30})
    if args.demo:
        print("DEMO: actual LangGraph orchestration; fake retrieval and fake factual verdict.")
    print(result["answer"])
    print("status:", result["status"], "retry_count:", result["retry_count"])
    print("trajectory:", " -> ".join(event["step"] for event in result["trace"]))
    if result["failure_reason"]:
        print("reason:", result["failure_reason"])
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
