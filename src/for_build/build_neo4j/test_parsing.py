"""Run with: python -m unittest discover -s src/for_build/build_neo4j -p 'test_*.py'."""

import copy
import csv
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from parsing import ValidationError, parse_rows  # noqa: E402


class ParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (HERE.parent / "museum_final_738.csv").open(encoding="utf-8-sig", newline="") as file:
            cls.rows = list(csv.DictReader(file))

    def test_real_file_produces_graph_records_with_typed_values(self) -> None:
        data = parse_rows(self.rows)
        self.assertEqual(len(data.museums), 738)
        self.assertEqual(len(data.sources), 1027)
        self.assertEqual(len(data.spans), 3260)
        self.assertEqual(len(data.evidence), 3270)
        self.assertEqual(data.museums[0]["properties"]["adult_fee"], 0)
        self.assertIs(data.museums[0]["properties"]["requires_manual_review"], True)
        self.assertIsInstance(data.museums[0]["properties"]["latitude"], float)
        self.assertEqual(data.spans[0]["properties"]["text"], self.rows[0]["text"][:94])

    def test_changed_text_hash_fails_before_loading(self) -> None:
        row = copy.deepcopy(self.rows[0])
        row["text"] += "changed"
        row["text_length"] = str(len(row["text"]))
        with self.assertRaisesRegex(ValidationError, "text_sha256"):
            parse_rows([row])

    def test_unknown_span_source_fails_before_loading(self) -> None:
        row = copy.deepcopy(self.rows[0])
        spans = json.loads(row["text_spans_json"])
        spans[0]["doc_ids"] = ["unknown-doc"]
        row["text_spans_json"] = json.dumps(spans)
        with self.assertRaisesRegex(ValidationError, "doc_ids"):
            parse_rows([row])

    def test_malformed_span_source_fails_with_validation_error(self) -> None:
        row = copy.deepcopy(self.rows[0])
        spans = json.loads(row["text_spans_json"])
        spans[0]["doc_ids"] = [{"bad": "id"}]
        row["text_spans_json"] = json.dumps(spans)
        with self.assertRaisesRegex(ValidationError, "doc_ids"):
            parse_rows([row])

    def test_duplicate_museum_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate museum_id"):
            parse_rows([self.rows[0], self.rows[0]])


if __name__ == "__main__":
    unittest.main()
