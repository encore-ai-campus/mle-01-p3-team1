"""Run with Python 3.12 unittest discover."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


class MultiHopCliTests(unittest.TestCase):
    def test_dry_run_validates_input_without_database_connection(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "src.data_pipeline.neo4j.validate_multihop", "--dry-run"],
            cwd=Path(__file__).resolve().parents[4],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["museums"], 738)
        self.assertEqual(result["evidence"], 3270)


if __name__ == "__main__":
    unittest.main()
