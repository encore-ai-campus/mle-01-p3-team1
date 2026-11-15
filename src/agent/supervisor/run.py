"""CLI: real LangGraph demo, or connect a teammate's module:function.

Run from repository root. Demo retrieval and verification are SYNTHETIC.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter

from . import AnswerDraft, RouteDecision, VerificationResult, adapt_hybrid, build_supervisor


def print_timings(result: dict, request_ms: float) -> None:
    names = {"guard_input": "입력 가드레일", "supervisor": "경로 판단", "hybrid_search": "Hybrid 검색",
             "graph_search": "Graph 검색", "vector_search": "Vector 검색", "answer": "답변 생성",
             "verify": "답변·출처 검증", "guard_output": "출력 가드레일"}
    stage_names = {"query_analysis": "질문 분석", "vector_retrieval": "Vector 검색",
                   "bm25_retrieval": "BM25 검색", "rrf_fusion": "RRF 결합",
                   "cross_encoder_rerank": "Cross-Encoder 재정렬"}
    print(f"\n[소요 시간] 전체 {request_ms / 1000:.2f}초")
    for event in result.get("trace", []):
        step = event.get("step")
        duration = event.get("duration_ms")
        if step not in names or not isinstance(duration, (int, float)):
            continue
        attempt = event.get("retry_count", 0) + 1
        print(f"  {attempt}차 {names[step]}: {duration / 1000:.2f}초")
        details = event.get("search_timings") or {}
        if step == "graph_search" and "cypher_generation_ms" in details:
            print(f"    Cypher 생성: {details['cypher_generation_ms'] / 1000:.2f}초 ({details.get('cypher_generation_calls', 0)}회)")
            print(f"    Neo4j 조회: {details['neo4j_query_ms'] / 1000:.2f}초 ({details.get('neo4j_query_calls', 0)}회)")
            print(f"    준비된 쿼리 확인: {details.get('prepared_query_ms', 0) / 1000:.2f}초")
        if step == "hybrid_search":
            for stage in details.get("stages") or []:
                if not isinstance(stage, dict) or not isinstance(stage.get("duration_ms"), (int, float)):
                    continue
                print(f"    {stage_names.get(stage.get('stage'), stage.get('stage', '검색 단계'))}: {stage['duration_ms'] / 1000:.2f}초")
                if stage.get("stage") == "cross_encoder_rerank":
                    for key, label in (("model_load_ms", "모델 로딩"), ("inference_ms", "추론")):
                        if isinstance(stage.get(key), (int, float)):
                            print(f"      {label}: {stage[key] / 1000:.2f}초")
    print("  검색 세부 시간은 검색 전체에 포함되며, 병렬 검색 시간은 서로 겹칠 수 있습니다.")


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
    mode.add_argument("--team-hybrid", action="store_true", help="Connect the team's BM25 + vector hybrid retriever")
    mode.add_argument("--hybrid", metavar="MODULE:FUNCTION", help="Actual teammate entry point, not a placeholder")
    parser.add_argument("--question", default="museum information")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Keep the Supervisor process alive and reuse loaded models for multiple questions",
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        help="Print total request time and Hybrid retrieval stage timings",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--route", choices=["auto", "vector", "graph", "hybrid"], default="auto")
    parser.add_argument("--empty-demo", action="store_true")
    parser.add_argument("--model", help="Team-selected structured-output model")
    parser.add_argument("--with-vector", action="store_true", help="Also connect documented VectorSearchRetriever")
    parser.add_argument("--with-neo4j", action="store_true", help="Connect Neo4j Text2Cypher as a Supervisor route")
    parser.add_argument("--hybrid-accepts-config", action="store_true")
    parser.add_argument("--no-ontology-filter", action="store_true",
                        help="Hybrid 구조 조건 후보 필터와 그에 따른 고정 라우팅을 끔")
    parser.add_argument("--out", help="Optional JSON output under outputs/supervisor/")
    args = parser.parse_args()
    if args.interactive and args.out:
        parser.error("--out cannot be used with --interactive")
    if args.no_ontology_filter:
        # Read by the Hybrid factory and the Supervisor routing check.
        os.environ["HYBRID_ONTOLOGY_FILTER"] = "off"
    if args.demo and (args.with_vector or args.with_neo4j):
        parser.error("--with-vector and --with-neo4j require a connected, non-demo backend")
    if args.route == "graph" and not args.with_neo4j:
        parser.error("--route graph requires --with-neo4j")
    if not args.demo and args.route == "auto" and not args.with_neo4j:
        print("Warning: Neo4j is not connected; graph route requests will fall back to Hybrid.", flush=True)

    with ExitStack() as resources:
        if args.demo:
            app = build_demo_supervisor(empty=args.empty_demo)
        else:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[3] / ".env")
            from .connect import build_connected_supervisor
            vector = None
            graph = None
            if args.with_vector:
                from src.service.vector_search_rag_agent import VectorSearchRetriever
                vector = VectorSearchRetriever()
            if args.with_neo4j:
                required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE")
                missing = [key for key in required if not os.getenv(key)]
                if missing:
                    raise ValueError(f"Set these .env values first: {', '.join(missing)}")
                from src.agent.neo4j_tls import load_graph_database
                from src.agent.neo4j_text2cypher import Neo4jText2Cypher

                graph_database = load_graph_database()
                driver = resources.enter_context(graph_database.driver(
                    os.environ["NEO4J_URI"],
                    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
                    connection_timeout=10,
                    max_transaction_retry_time=3.0,
                ))
                driver.verify_connectivity()
                graph = Neo4jText2Cypher(driver, os.environ["NEO4J_DATABASE"])
                print("Neo4j Graph route connected.", flush=True)
            app = build_connected_supervisor(
                hybrid_node=load_callable(args.hybrid) if args.hybrid else None,
                vector_retriever=vector,
                graph_retriever=graph,
                model_name=args.model,
                hybrid_accepts_config=args.hybrid_accepts_config,
            )

        def answer(question: str) -> None:
            request_started = perf_counter()
            result = app.invoke(
                {"question": question, "top_k": args.top_k, "route_override": args.route},
                config={
                    "run_name": "museum_supervisor",
                    "tags": ["demo" if args.demo else "real"],
                    "recursion_limit": 30,
                },
            )
            request_ms = (perf_counter() - request_started) * 1000
            result["timing_request_ms"] = round(request_ms, 2)
            if args.demo:
                print("DEMO: actual LangGraph orchestration; fake retrieval and fake factual verdict.")
            print(result["answer"])
            print("status:", result["status"], "retry_count:", result["retry_count"])
            print("trajectory:", " -> ".join(event["step"] for event in result["trace"]))
            for event in result["trace"]:
                if event.get("step") == "supervisor":
                    print(f"route: {event.get('route', '')} · reason: {event.get('reason', '')}")
            if args.timings:
                print_timings(result, request_ms)
            if result["failure_reason"]:
                print("reason:", result["failure_reason"])
            if args.out:
                path = Path(args.out)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        if args.interactive:
            print("Supervisor ready. Enter a question; type q to exit.")
            while True:
                try:
                    question = input("질문> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if question.casefold() in {"q", "quit", "exit"}:
                    break
                if not question:
                    continue
                try:
                    answer(question)
                except Exception as exc:
                    print(f"Supervisor failed: {type(exc).__name__}: {exc}")
        else:
            answer(args.question)


if __name__ == "__main__":
    main()
