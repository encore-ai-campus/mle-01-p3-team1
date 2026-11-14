from src.evaluation.timing import timing_summary


def test_timing_summary_converts_milliseconds_and_reports_mean_and_max():
    assert timing_summary([1000.0, 3000.0]) == "평균 2.00초 · 최대 3.00초"


def test_timing_summary_handles_empty_values():
    assert timing_summary([]) == "평균 - · 최대 -"


def test_graph_collection_prints_each_question_and_timing(capsys):
    from src.evaluation.langgraph.ragas_eval import collect_graph_results

    class App:
        def invoke(self, state):
            return {"answer": state["question"], "evidence": []}

    rows = [{"question_id": "Q1", "user_input": "하나"},
            {"question_id": "Q2", "user_input": "둘"}]
    results = collect_graph_results(App(), rows)
    output = capsys.readouterr().out
    assert "question_id=Q1" in output and "question_id=Q2" in output
    assert "평균" in output and "최대" in output and "Ragas 채점 시간 제외" in output
    assert all(item["duration_ms"] >= 0 for item in results)


def test_hybrid_collection_prints_every_question(monkeypatch, tmp_path, capsys):
    from src.evaluation.hybrid import ragas_eval

    def run_one(mode, row, **kwargs):
        return {"question_id": row["question_id"], "duration_ms": 1000,
                "retrieval_status": "ok", "answer_status": "answered"}

    monkeypatch.setattr(ragas_eval, "run_one", run_one)
    rows = [{"question_id": "Q1"}, {"question_id": "Q2"}]
    ragas_eval._collect_mode_rows(
        "vector", rows, {}, workers=1, top_k=5, service=None,
        answer_client=None, answer_model="test", precomputed={}, run_dir=tmp_path,
    )
    output = capsys.readouterr().out
    assert "Q1" in output and "Q2" in output
    assert "1.00초" in output and "평균 1.00초 · 최대 1.00초" in output


def test_hybrid_summary_saves_maximum_duration():
    from src.evaluation.hybrid.ragas_eval import summarize_mode

    rows = [{"question_id": "Q1", "answerable": "yes"},
            {"question_id": "Q2", "answerable": "yes"}]
    records = {"Q1": {"duration_ms": 1000, "retrieval_status": "ok"},
               "Q2": {"duration_ms": 3000, "retrieval_status": "ok"}}
    summary = summarize_mode(rows, records, {})
    assert summary["avg_duration_ms"] == 2000
    assert summary["max_duration_ms"] == 3000
