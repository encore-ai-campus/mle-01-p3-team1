import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.agent.ragas_eval import (
    DEFAULT_EVALSET,
    assemble_question_rows,
    build_evaluation_dataset,
    build_ragas_metrics,
    collect_graph_results,
    read_evaluation_set,
    write_outputs,
)


class RagasEvalTests(unittest.TestCase):
    def test_project_ragas_set_has_300_provisional_questions(self):
        rows = read_evaluation_set(DEFAULT_EVALSET)

        self.assertEqual(len(rows), 300)
        self.assertEqual(sum(row["answerable"] == "yes" for row in rows), 294)
        self.assertEqual(sum(row["answerable"] == "no" for row in rows), 6)
        self.assertTrue(all(row["label_status"] == "draft_needs_human_review" for row in rows))

    def test_reads_answerable_and_unanswerable_reference_rows(self):
        fields = [
            "question_id",
            "category",
            "user_input",
            "answerable",
            "reference",
            "reference_contexts",
            "gold_museum_ids",
            "gold_museum_names",
            "evidence_quote",
            "label_status",
            "notes",
        ]
        rows = [
            {
                "question_id": "Q1",
                "category": "direct",
                "user_input": "어느 박물관인가요?",
                "answerable": "yes",
                "reference": "예시 박물관은 서울에 있습니다.",
                "reference_contexts": '["예시 박물관은 서울에 있습니다."]',
                "gold_museum_ids": "M1",
                "gold_museum_names": "예시 박물관",
                "evidence_quote": "예시 박물관은 서울에 있습니다.",
                "label_status": "human_verified",
                "notes": "",
            },
            {
                "question_id": "Q2",
                "category": "unanswerable",
                "user_input": "관련 기록이 있나요?",
                "answerable": "no",
                "reference": "데이터에서 관련 근거를 찾을 수 없습니다.",
                "reference_contexts": "[]",
                "gold_museum_ids": "",
                "gold_museum_names": "",
                "evidence_quote": "",
                "label_status": "draft_needs_human_review",
                "notes": "",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            loaded = read_evaluation_set(path)

        self.assertEqual([row["question_id"] for row in loaded], ["Q1", "Q2"])
        self.assertEqual([row["answerable"] for row in loaded], ["yes", "no"])
        self.assertEqual(loaded[0]["reference"], "예시 박물관은 서울에 있습니다.")
        self.assertEqual(loaded[0]["reference_contexts_parsed"], ["예시 박물관은 서울에 있습니다."])

    def test_ragas_dataset_uses_graph_context_and_skips_unanswerable_samples(self):
        gold_rows = [
            {
                "question_id": "Q1",
                "user_input": "예시 박물관은 어디에 있나요?",
                "answerable": "yes",
                "reference": "예시 박물관은 서울에 있습니다.",
                "reference_contexts_parsed": ["예시 박물관은 서울에 있습니다."],
            },
            {
                "question_id": "Q2",
                "user_input": "기록이 없는 내용을 물어봅니다.",
                "answerable": "no",
                "reference": "데이터에서 관련 근거를 찾을 수 없습니다.",
                "reference_contexts_parsed": [],
            },
        ]
        graph_results = [
            {
                "question_id": "Q1",
                "answer": "예시 박물관은 서울에 있습니다.",
                "evidence": [{"text": "예시 박물관은 서울에 있습니다."}],
            },
            {
                "question_id": "Q2",
                "answer": "현재 근거가 없습니다.",
                "evidence": [],
            },
        ]

        dataset = build_evaluation_dataset(gold_rows, graph_results)
        frame = dataset.to_pandas()

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.loc[0, "user_input"], gold_rows[0]["user_input"])
        self.assertEqual(frame.loc[0, "response"], graph_results[0]["answer"])
        self.assertEqual(frame.loc[0, "retrieved_contexts"], ["예시 박물관은 서울에 있습니다."])
        self.assertEqual(frame.loc[0, "reference"], gold_rows[0]["reference"])

    def test_builds_current_ragas_llm_metrics_without_network_calls(self):
        from openai import AsyncOpenAI

        metrics = build_ragas_metrics("gpt-4o-mini", client=AsyncOpenAI(api_key="test-key"))

        self.assertEqual(
            [metric.name for metric in metrics],
            [
                "faithfulness",
                "context_recall",
                "context_precision_with_reference",
                "factual_correctness",
            ],
        )

    def test_collects_graph_route_and_writes_per_question_ragas_report(self):
        class FakeGraphApp:
            def __init__(self):
                self.questions = []

            def invoke(self, state):
                question = state["question"]
                self.questions.append(question)
                if question == "답할 수 있는 질문":
                    return {
                        "route_trace": ["graph"],
                        "verified": True,
                        "failure_reason": "",
                        "answer": "박물관은 서울에 있습니다.",
                        "evidence": [{
                            "museum_id": "M1",
                            "span_id": "M1:000",
                            "text": "박물관은 서울에 있습니다.",
                        }],
                    }
                return {
                    "route_trace": ["graph"],
                    "verified": False,
                    "failure_reason": "검색된 근거가 없음",
                    "answer": "현재 근거가 없습니다.",
                    "evidence": [],
                }

        gold_rows = [
            {
                "question_id": "Q1",
                "category": "direct",
                "user_input": "답할 수 있는 질문",
                "answerable": "yes",
                "reference": "박물관은 서울에 있습니다.",
                "label_status": "human_verified",
                "gold_museum_ids": "M1",
            },
            {
                "question_id": "Q2",
                "category": "unanswerable",
                "user_input": "근거가 없는 질문",
                "answerable": "no",
                "reference": "근거를 찾을 수 없습니다.",
                "label_status": "human_verified",
                "gold_museum_ids": "",
            },
        ]
        app = FakeGraphApp()
        graph_results = collect_graph_results(app, gold_rows)
        self.assertEqual(app.questions, ["답할 수 있는 질문", "근거가 없는 질문"])

        scored_frame = pd.DataFrame([{
            "faithfulness": 0.9,
            "context_recall": 0.8,
            "context_precision_with_reference": 0.7,
            "factual_correctness": 0.6,
        }])
        question_rows = assemble_question_rows(gold_rows, graph_results, scored_frame)
        self.assertEqual(question_rows[0]["retrieved_span_ids"], "M1:000")
        self.assertEqual(question_rows[0]["faithfulness"], 0.9)
        self.assertEqual(question_rows[1]["evidence_presence_correct"], 1)
        self.assertEqual(question_rows[1]["context_recall"], "")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = write_outputs(
                question_rows,
                gold_rows,
                Path(directory),
                evalset_path=DEFAULT_EVALSET,
                top_k=5,
                judge_model="gpt-4o-mini",
            )
            self.assertTrue((output_dir / "per_question.csv").is_file())
            self.assertTrue((output_dir / "summary.json").is_file())
            self.assertTrue((output_dir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
