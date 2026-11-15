import unittest

from src.agent.ragas_testset import build_evaluation_rows, build_knowledge_graph


class RagasTestsetTests(unittest.TestCase):
    def test_builds_ragas_chunk_nodes_with_terms_and_source_metadata(self):
        documents = [{
            "page_content": "부산 근대역사박물관은 부산의 근대 역사와 항만 문화를 전시합니다.",
            "metadata": {
                "museum_id": "M31",
                "museum_name": "부산근대역사박물관",
                "sido": "부산광역시",
                "sigungu": "중구",
                "span_id": "M31:000",
                "source_doc_ids": ["D31"],
            },
        }]

        graph = build_knowledge_graph(documents)

        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(graph.nodes[0].type.name, "CHUNK")
        self.assertEqual(
            graph.nodes[0].get_property("page_content"),
            documents[0]["page_content"],
        )
        self.assertIn("부산근대역사박물관", graph.nodes[0].get_property("entities"))
        self.assertEqual(
            graph.nodes[0].get_property("document_metadata")["span_id"],
            "M31:000",
        )

    def test_merges_seed_rows_deduplicates_generated_questions_and_maps_gold_sources(self):
        seed_rows = [{
            "question_id": "Q030",
            "category": "direct",
            "user_input": "기존에 있던 질문",
            "answerable": "yes",
            "reference": "기존 정답",
            "reference_contexts": '["기존 근거"]',
            "gold_museum_ids": "M30",
            "gold_museum_names": "기존 박물관",
            "evidence_doc_ids": "D30",
            "evidence_quote": "기존 근거",
            "label_status": "draft_needs_human_review",
            "notes": "기존 초안",
        }]
        generated_samples = [
            {
                "user_input": "기존에 있던 질문",
                "reference": "중복 정답",
                "reference_contexts": ["중복 근거"],
                "synthesizer_name": "single_hop",
            },
            {
                "user_input": "새 질문은 어떤 박물관에 관한 건가요?",
                "reference": "새 박물관은 부산에 있습니다.",
                "reference_contexts": ["새 박물관은 부산에 있습니다."],
                "synthesizer_name": "single_hop",
            },
        ]
        source_documents = [{
            "page_content": "새 박물관은 부산에 있습니다.",
            "metadata": {
                "museum_id": "M31",
                "museum_name": "새 박물관",
                "span_id": "M31:000",
                "source_doc_ids": ["D31"],
            },
        }]

        rows = build_evaluation_rows(
            seed_rows,
            generated_samples,
            source_documents,
            total_count=2,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["question_id"], "Q031")
        self.assertEqual(rows[1]["category"], "single_hop")
        self.assertEqual(rows[1]["gold_museum_ids"], "M31")
        self.assertEqual(rows[1]["gold_museum_names"], "새 박물관")
        self.assertEqual(rows[1]["evidence_doc_ids"], "D31")
        self.assertEqual(rows[1]["label_status"], "draft_needs_human_review")


if __name__ == "__main__":
    unittest.main()
