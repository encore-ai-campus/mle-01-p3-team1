"""Read-only smoke test: run a real Neo4j search through the LangGraph graph route.

From the repository root:
    uv run python -m src.agent.neo4j_demo --question "서울 전통문화" --top-k 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph
from .neo4j_tls import load_graph_database
from .state import Evidence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _configure_output_stream(stream) -> None:
    """Keep JSON output printable when Windows' active code page lacks a character."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(errors="backslashreplace")


def _format_exception_chain(error: BaseException) -> list[str]:
    messages: list[str] = []
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        messages.append(f"{type(current).__name__}: {current}")
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        elif current.__context__ is not None:
            pending.append(current.__context__)
    return messages


def _make_smoke_answer(question: str, evidence: list[Evidence]) -> str:
    return "\n".join(
        f"[{item.get('museum_id', '')}] {item.get('name', '')} — "
        f"{item.get('sido', '')} {item.get('sigungu', '')}\n"
        f"근거: {item.get('text', '')[:240]}\n"
        f"출처: {item.get('source_url') or ', '.join(item.get('source_locators', [])) or item.get('source_locator') or ', '.join(item.get('source_doc_ids', []))}"
        for item in evidence
    )


def _verify_smoke_answer(question: str, answer: str, evidence: list[Evidence]) -> bool:
    """Check that displayed results retain their IDs; this is not fact verification."""
    museum_ids = [str(item.get("museum_id", "")) for item in evidence]
    return bool(museum_ids) and all(
        museum_id and f"[{museum_id}]" in answer for museum_id in museum_ids
    )


def main(argv: list[str] | None = None) -> int:
    _configure_output_stream(sys.stdout)
    _configure_output_stream(sys.stderr)

    parser = argparse.ArgumentParser(description="Read-only Neo4j-backed LangGraph smoke test")
    parser.add_argument("--question", default="서울 전통문화", help="질문 또는 박물관 검색 키워드")
    parser.add_argument("--top-k", type=int, default=5, help="가져올 근거 수")
    args = parser.parse_args(argv)

    try:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        required = (
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "NEO4J_DATABASE",
            "OPENAI_API_KEY",
        )
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"루트 .env에 다음 값이 필요합니다: {', '.join(missing)}")

        # Aura uses TLS. On this Windows environment its CA chain is trusted
        # by the OS store, so install that store before importing Neo4j.
        graph_database = load_graph_database()
        from .neo4j_text2cypher import Neo4jText2Cypher

        database = os.environ["NEO4J_DATABASE"]
        with graph_database.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            connection_timeout=10,
            max_transaction_retry_time=3.0,
        ) as driver:
            graph_search = Neo4jText2Cypher(driver, database)
            app = build_graph(
                vector_search=lambda question, k: [],
                graph_search=graph_search.search,
                route_question=lambda question: "graph",
                make_answer=graph_search.make_answer,
                verify_answer=_verify_smoke_answer,
                top_k=args.top_k,
                max_retries=0,
            )
            result = app.invoke({"question": args.question})

        print(json.dumps({
            "question": result["question"],
            "route_trace": result["route_trace"],
            "verified": result["verified"],
            "failure_reason": result.get("failure_reason", ""),
            "evidence_count": len(result.get("evidence", [])),
            "generated_cypher": graph_search.last_cypher,
            "cypher_parameters": graph_search.last_parameters,
            "llm_model": graph_search.model,
            "evidence": result.get("evidence", []),
            "answer": result.get("answer", ""),
            "note": "verified only means the answer retained evidence museum IDs; it is not factual or citation verification.",
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print("Neo4j LangGraph smoke test failed:", file=sys.stderr)
        for message in _format_exception_chain(exc):
            print(f"- {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
