#!/usr/bin/env python3
"""Read-only two- to four-hop validation of the loaded Aura graph.

From the repository root:
    uv run python -m src.data_pipeline.neo4j.validate_multihop --dry-run
    uv run python -m src.data_pipeline.neo4j.validate_multihop
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if __package__:
    from .graph_db import GraphStore
    from .load_neo4j import DEFAULT_CSV, HERE, ROOT, kst_timestamp
    from .parsing import parse_csv
else:  # Support direct execution as well as `python -m`.
    from graph_db import GraphStore
    from load_neo4j import DEFAULT_CSV, HERE, ROOT, kst_timestamp
    from parsing import parse_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate multi-hop paths in the loaded Neo4j graph")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV used for ID and path expectations")
    parser.add_argument("--dry-run", action="store_true", help="Validate input without connecting to Neo4j")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "outputs" / "neo4j" / "multihop_result.json",
    )
    args = parser.parse_args(argv)

    try:
        data = parse_csv(args.csv)
        if args.dry_run:
            print(json.dumps({
                "museums": len(data.museums),
                "sources": len(data.sources),
                "spans": len(data.spans),
                "evidence": len(data.evidence),
            }))
            return 0

        from dotenv import load_dotenv
        from neo4j import GraphDatabase

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
            baseline = store.verify(data)
            multihop = store.verify_multihop(data)

        result = {
            "status": "verified",
            "checked_at": kst_timestamp(),
            "database": os.environ["NEO4J_DATABASE"],
            "input_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "scope": "museum_final_738.csv imported IDs",
            "baseline_counts": baseline,
            "multihop_counts": multihop,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Multi-hop validation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
