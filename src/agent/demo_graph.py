"""실제 DB나 LLM 없이 LangGraph 흐름을 확인하는 데모."""

from .graph import build_graph


def fake_vector_search(question: str, k: int):
    return [
        {
            "museum_id": "M0001",
            "text": "[데모] 박물관 소개글",
            "source_doc_ids": ["D1"],
            "chunk_id": "D1-0",
            "retriever": "vector",
        }
    ][:k]


def fake_graph_search(question: str, k: int):
    return [
        {
            "museum_id": "M0002",
            "text": "[데모] 같은 시군구의 박물관",
            "span_id": "S2-0",
            "retriever": "graph",
        }
    ][:k]


def router(question: str):
    if "같은" in question or "운영기관" in question:
        return "graph"
    if "지역" in question and "관련" in question:
        return "hybrid"
    return "vector"


def answer_fn(question: str, evidence: list[dict]) -> str:
    return "[데모 답변] " + ", ".join(item.get("museum_id", "") for item in evidence)


def verifier_fn(question: str, answer: str, evidence: list[dict]) -> bool:
    # 분기 데모용 확인이며 실제 사실·인용 검증을 대체하지 않는다.
    return bool(answer.strip() and evidence)


def main() -> None:
    app = build_graph(
        vector_search=fake_vector_search,
        graph_search=fake_graph_search,
        route_question=router,
        make_answer=answer_fn,
        verify_answer=verifier_fn,
    )
    result = app.invoke({"question": "전통문화 관련 박물관 추천"})
    print("route_trace:", result["route_trace"])
    print("verified:", result["verified"])
    print("answer:", result["answer"])


if __name__ == "__main__":
    main()
