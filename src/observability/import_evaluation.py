"""Publish existing per_question.csv results as *offline* Langfuse evaluation traces.

This does not claim to connect to an earlier live inference trace: each
(mode, question_id, run_id) becomes a reproducible retrospective evaluation trace.
Do not confuse retrospectively created spans with live latency/LLM call traces.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import math
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

METRICS = (
    "ragas_faithfulness", "ragas_context_recall", "ragas_context_precision_with_reference",
    "ragas_factual_correctness", "ragas_answer_relevancy", "hit_at_1", "hit_at_3",
    "hit_at_5", "recall_at_5", "mrr_at_10",
)


def _metric(value: str | None) -> float | None:
    if not value or value.strip().upper() in {"N/A", "NONE", "NULL", "NAN"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _trace_id(run: str, mode: str, qid: str) -> str:
    # OpenTelemetry requires a 32-character lowercase hex trace ID, not all zero.
    return uuid.uuid5(uuid.NAMESPACE_URL, f"mle3:offline-ragas:{run}:{mode}:{qid}").hex


def _score_id(run: str, mode: str, qid: str, metric: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"mle3:score:{run}:{mode}:{qid}:{metric}").hex


def _score_timestamp(run: str) -> datetime:
    """Stable score timestamp for safe re-import (ID alone is insufficient)."""
    try:
        return datetime.strptime(run, "%Y%m%d_%H%M%S_%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Import already computed RAGAS scores into Langfuse as offline traces")
    parser.add_argument("--csv", required=True, type=Path, help="outputs/evaluation/hybrid_ragas/run_*/per_question.csv")
    parser.add_argument("--limit", type=int, default=0, help="0 means all rows")
    parser.add_argument("--dry-run", action="store_true", help="validate rows, send nothing")
    parser.add_argument("--include-answer", action="store_true", help="send final answers; OFF by default")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 2
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            required = {"run_id", "mode", "question_id"}
            if not required.issubset(reader.fieldnames or []):
                print(f"Missing columns: {sorted(required - set(reader.fieldnames or []))}", file=sys.stderr)
                return 2
            rows = list(reader)
    except (OSError, csv.Error) as exc:
        print(f"Cannot read evaluation CSV: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.limit:
        rows = rows[:args.limit]
    usable = sum(any(_metric(row.get(k)) is not None for k in METRICS) for row in rows)
    print(f"CSV: {csv_path.name}; rows={len(rows)}, rows with scores={usable}")
    if args.dry_run:
        print("Dry run: no Langfuse calls made.")
        return 0

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("LANGFUSE_ENABLED", os.getenv("LANGFUSE_TRACING_ENABLED", "false")).lower() not in {"1", "true", "yes", "on"}:
        print("Set LANGFUSE_ENABLED=true in the project .env before importing.", file=sys.stderr)
        return 2
    if not os.getenv("LANGFUSE_SECRET_KEY") or not os.getenv("LANGFUSE_PUBLIC_KEY"):
        print("Missing Langfuse API keys in project .env.", file=sys.stderr)
        return 2
    try:
        from langfuse import get_client
        client = get_client()
        if not client.auth_check():
            print("Langfuse auth_check failed; verify BASE_URL and keys.", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"Langfuse connection error: {type(exc).__name__}", file=sys.stderr)
        return 2

    # Refuse duplicate row keys within the same CSV; duplicate trace inputs are ambiguous.
    keys = [(r.get("run_id"), r.get("mode"), r.get("question_id")) for r in rows]
    if len(keys) != len(set(keys)):
        print("Duplicate (run_id, mode, question_id) records detected; abort.", file=sys.stderr)
        return 2
    score_count, trace_count = 0, 0
    for row in rows:
        scores = {k: _metric(row.get(k)) for k in METRICS}
        scores = {k: v for k, v in scores.items() if v is not None}
        if not scores:
            continue
        run, mode, qid = (str(row[k]).strip() for k in ("run_id", "mode", "question_id"))
        if not (run and mode and qid):
            continue
        trace_id = _trace_id(run, mode, qid)
        inputs = {"question_id": qid, "mode": mode, "dataset_label_status": row.get("label_status", "")}
        output = {
            "answer_status": row.get("answer_status", ""),
            "retrieval_status": row.get("retrieval_status", ""),
            "route": row.get("route", ""),
            "retrieved_museum_ids": str(row.get("retrieved_museum_ids") or "")[:500],
        }
        if args.include_answer:
            output["answer"] = row.get("answer", "")
        try:
            with client.start_as_current_observation(
                as_type="span", name="offline-ragas-evaluation",
                trace_context={"trace_id": trace_id}, input=inputs,
                metadata={"origin": "csv_import", "run_id": run, "mode": mode, "question_id": qid},
            ) as span:
                span.update(output=output)
            for metric, value in scores.items():
                client.create_score(
                    trace_id=trace_id, name=metric, value=float(value),
                    score_id=_score_id(run, mode, qid, metric),
                    timestamp=_score_timestamp(run),
                    comment="Imported from per_question.csv; provisional if labels are not human-verified",
                )
            trace_count += 1
            score_count += len(scores)
        except Exception as exc:
            print(f"Failed for {mode}/{qid}: {type(exc).__name__}", file=sys.stderr)
            try:
                client.flush()
            except Exception:
                pass
            return 1
    try:
        client.flush()
    except Exception as exc:
        print(f"Flush failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Imported {trace_count} offline evaluation traces and {score_count} scores. See Tracing / Scores in Langfuse.")
    print("Note: importing again can add an observation; scores use stable IDs and timestamps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
