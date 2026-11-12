"""CLI smoke test; run with Python 3.12 unittest discover."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_neo4j import kst_timestamp  # noqa: E402


class LoaderCliTests(unittest.TestCase):
    def test_report_timestamp_has_korea_offset_without_tzdata(self) -> None:
        self.assertTrue(kst_timestamp().endswith("+09:00"))

    def test_dry_run_reports_validated_counts_without_database_access(self) -> None:
        script = Path(__file__).resolve().parent / "load_neo4j.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        counts = json.loads(completed.stdout)
        self.assertEqual(counts["museums"], 738)
        self.assertEqual(counts["sources"], 1027)
        self.assertEqual(counts["spans"], 3260)
        self.assertEqual(counts["evidence"], 3270)


if __name__ == "__main__":
    unittest.main()
