from src.evaluation.hybrid.ragas_eval import run_one


def test_supervisor_partial_answer_is_not_reported_as_abstained():
    class Supervisor:
        def invoke(self, payload):
            return {
                "evidence": [{"museum_id": "M1", "text": "기본요금 0원", "source_doc_ids": ["D1"]}],
                "answer": "기본요금 0원으로 기록됐으나 조건 확인이 필요합니다. [E1]",
                "route": "graph", "verified": False, "status": "partial",
            }

    row = {"question_id": "Q1", "user_input": "강원도 무료인 곳", "answerable": "yes", "gold_museum_ids": "M1"}
    result = run_one("supervisor", row, top_k=5, service=None, answer_client=None,
                     answer_model="unused", precomputed={}, supervisor_app=Supervisor())
    assert result["answer_status"] == "partial"
    assert result["supervisor_verified"] is False
