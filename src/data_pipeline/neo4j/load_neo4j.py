#!/usr/bin/env python3
"""Load the museum CSV into Neo4j with provenance.

From the repository root, run:
    uv run python -m src.data_pipeline.neo4j.load_neo4j --dry-run
    uv run python -m src.data_pipeline.neo4j.load_neo4j
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from .graph_db import GraphStore
    from .parsing import parse_csv
else:  # Support direct execution as well as `python -m`.
    from graph_db import GraphStore
    from parsing import parse_csv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_CSV = ROOT / "data" / "processed" / "museum_final_738.csv"


def kst_timestamp() -> str:
    """Return an ISO timestamp without requiring Windows tzdata."""
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")


def _expected_counts(data) -> dict[str, int]:
    return {
        "museums": len(data.museums),
        "sources": len(data.sources),
        "spans": len(data.spans),
        "evidence": len(data.evidence),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and load museum_final_738.csv into Neo4j")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV input path")
    parser.add_argument("--batch-size", type=int, default=50, help="Museums per transaction")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV without connecting to Neo4j")
    parser.add_argument("--verify-only", action="store_true", help="Read back counts without writing")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "outputs" / "neo4j" / "load_result.json",
        help="Verified result JSON",
    )
    args = parser.parse_args(argv)

    try:
        if args.batch_size < 1:
            raise ValueError("--batch-size must be positive")
        data = parse_csv(args.csv)
        expected = _expected_counts(data)
        if args.dry_run:
            print(json.dumps(expected, ensure_ascii=False))
            return 0

        try:
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("Install neo4j and python-dotenv in Python 3.12 first") from exc

        load_dotenv(ROOT / ".env")
        required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE")
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing Neo4j environment variables: {', '.join(missing)}")

        with GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            connection_timeout=15,
        ) as driver:
            driver.verify_connectivity()
            store = GraphStore(driver, os.environ["NEO4J_DATABASE"])
            batches = 0
            if not args.verify_only:
                store.create_schema()
                batches = store.load(data, batch_size=args.batch_size)
            actual = store.verify(data)

        result = {
            "status": "verified",
            "mode": "verify-only" if args.verify_only else "load",
            "loaded_at": kst_timestamp(),
            "database": os.environ["NEO4J_DATABASE"],
            "input_file": str(args.csv.resolve()),
            "input_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "batch_size": args.batch_size,
            "batches_written": batches,
            "expected": expected,
            "actual": actual,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
