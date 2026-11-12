"""Evaluate the local museum Chroma collection against a reviewed CSV gold set."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import Counter
from pathlib import Path

import chromadb
from dotenv import load_dotenv


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DB_DIR = ROOT / "data" / "vector_db" / "museum_chroma"
DEFAULT_EVALSET = ROOT / "evaluations" / "datasets" / "vector_db" / "VectorDB_평가셋_30문항.csv"
COLLECTION_NAME = "museum_documents"
EMBEDDING_MODEL = "text-embedding-3-small"
REQUIRED_COLUMNS = {
    "question_id",
    "category",
    "question",
    "answerable",
    "gold_museum_ids",
    "gold_museum_names",
    "label_status",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the existing museum_documents Chroma collection."
    )
    parser.add_argument("--evalset", type=Path, default=DEFAULT_EVALSET)
    parser.add_argument("--db-dir", type=Path, default=DB_DIR)
    parser.add_argument("--collection", default=COLLECTION_NAME)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("outputs/evaluation/vector_db"))
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check local inputs without calling the embedding API.",
    )
    args = parser.parse_args()
    if args.top_k < 10:
        parser.error("--top-k must be at least 10 for MRR@10.")
    return args


def resolve(base: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def find_evalset(path: Path | None) -> Path:
    if path is not None:
        result = resolve(ROOT, path)
        if not result.is_file():
            raise SystemExit(f"Evaluation CSV not found: {result}")
        return result
    if not DEFAULT_EVALSET.is_file():
        raise SystemExit(f"Evaluation CSV not found: {DEFAULT_EVALSET}")
    return DEFAULT_EVALSET


def read_goldset(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise SystemExit(f"Evaluation CSV is empty: {path}")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise SystemExit(f"Required columns missing: {', '.join(sorted(missing))}")
    ids = [row["question_id"].strip() for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("question_id must be unique.")
    for row in rows:
        row["question_id"] = row["question_id"].strip()
        row["question"] = row["question"].strip()
        row["answerable"] = row["answerable"].strip().lower()
        if not row["question"] or row["answerable"] not in {"yes", "no"}:
            raise SystemExit(f"Invalid question or answerable value: {row['question_id']}")
        if row["answerable"] == "yes" and not parse_ids(row["gold_museum_ids"]):
            raise SystemExit(f"Missing gold_museum_ids: {row['question_id']}")
    return rows


def parse_ids(value: str | None) -> set[str]:
    return {part.strip() for part in (value or "").split(";") if part.strip()}


def open_collection(db_dir: Path, name: str):
    if not db_dir.is_dir():
        raise SystemExit(f"Chroma directory not found: {db_dir}")
    client = chromadb.PersistentClient(path=str(db_dir))
    try:
        collection = client.get_collection(name=name)
    except Exception as exc:
        raise SystemExit(f"Could not open collection {name}: {exc}") from exc
    if collection.count() == 0:
        raise SystemExit(f"Collection {name} is empty.")
    return collection


def readiness(goldset: list[dict[str, str]], collection) -> bool:
    db_ids = set(collection.get(include=[])["ids"])
    gold_ids = {
        museum_id
        for row in goldset
        if row["answerable"] == "yes"
        for museum_id in parse_ids(row["gold_museum_ids"])
    }
    missing = sorted(gold_ids - db_ids)
    statuses = Counter(row.get("label_status", "") for row in goldset)
    print(f"Documents in DB: {collection.count()}")
    print(f"Questions: {len(goldset)}; answerable: {sum(r['answerable'] == 'yes' for r in goldset)}")
    print(f"Gold IDs present: {len(gold_ids) - len(missing)}/{len(gold_ids)}")
    print(f"Label statuses: {dict(statuses)}")
    if missing:
        print(f"Missing IDs: {', '.join(missing)}")
        return False
    if any(status != "human_verified" for status in statuses):
        print("WARNING: labels are not all human-verified; scores will be provisional.")
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; required only for the full evaluation.")
    metadata = collection.metadata or {}
    if not metadata.get("embedding_model"):
        print(f"WARNING: verify that the index was built with {EMBEDDING_MODEL}.")
    return True


def ranking_scores(retrieved: list[str], gold: set[str]) -> dict[str, int | float | str]:
    first = next(
        (rank for rank, value in enumerate(retrieved[:10], 1) if value in gold),
        None,
    )
    found5 = len(set(retrieved[:5]) & gold)
    return {
        "first_relevant_rank": first or "",
        "Hit@1": int(bool(set(retrieved[:1]) & gold)),
        "Hit@3": int(bool(set(retrieved[:3]) & gold)),
        "Hit@5": int(found5 > 0),
        "Recall@5": found5 / len(gold),
        "MRR@10": 1 / first if first else 0.0,
    }


def evaluate(goldset: list[dict[str, str]], collection, top_k: int) -> list[dict]:
    from langchain_openai import OpenAIEmbeddings

    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectors = embedder.embed_documents([row["question"] for row in goldset])
    found = collection.query(
        query_embeddings=vectors,
        n_results=top_k,
        include=["metadatas", "distances"],
    )
    rows = []
    for i, gold_row in enumerate(goldset):
        ids = found["ids"][i]
        metadata = found["metadatas"][i] or [{} for _ in ids]
        distances = found["distances"][i]
        details = [
            {
                "rank": rank,
                "museum_id": museum_id,
                "name": (meta or {}).get("name", ""),
                "distance": float(distance),
            }
            for rank, (museum_id, meta, distance) in enumerate(
                zip(ids, metadata, distances), 1
            )
        ]
        row = {
            "question_id": gold_row["question_id"],
            "category": gold_row["category"],
            "question": gold_row["question"],
            "answerable": gold_row["answerable"],
            "gold_museum_ids": gold_row["gold_museum_ids"],
            "gold_museum_names": gold_row["gold_museum_names"],
            "label_status": gold_row.get("label_status", ""),
            "first_relevant_rank": "",
            "Hit@1": "",
            "Hit@3": "",
            "Hit@5": "",
            "Recall@5": "",
            "MRR@10": "",
            "top1_distance": details[0]["distance"] if details else "",
            "retrieved_museum_ids": ";".join(ids),
            "retrieved_museum_names": ";".join(str(d["name"]) for d in details),
            "top_k_detail_json": json.dumps(details, ensure_ascii=False),
        }
        if gold_row["answerable"] == "yes":
            row.update(ranking_scores(ids, parse_ids(gold_row["gold_museum_ids"])))
        rows.append(row)
    return rows


def write_outputs(rows: list[dict], args: argparse.Namespace, evalset: Path) -> None:
    output = resolve(ROOT, args.output)
    output.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with (output / "per_question.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    missed = [r for r in rows if r["answerable"] == "yes" and int(r["Hit@5"]) == 0]
    with (output / "missed_at_5.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(missed)

    answerable = [r for r in rows if r["answerable"] == "yes"]
    keys = ("Hit@1", "Hit@3", "Hit@5", "Recall@5", "MRR@10")
    summary = {
        "question_count": len(rows),
        "answerable_questions": len(answerable),
        "unanswerable_questions": len(rows) - len(answerable),
        "label_status": dict(Counter(r["label_status"] for r in rows)),
        "metrics": {
            key: statistics.mean(float(r[key]) for r in answerable)
            for key in keys
        },
        "collection": args.collection,
        "embedding_model": EMBEDDING_MODEL,
        "evalset": str(evalset),
        "note": "Retrieval ranking only; labels not human_verified are provisional.",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# Vector DB 검색 평가",
        "",
        f"- 컬렉션: {args.collection}",
        f"- 질의 임베딩: {EMBEDDING_MODEL}",
        f"- 답변 가능 문항: {len(answerable)}",
        f"- 근거 부족 문항: {len(rows) - len(answerable)} (순위 지표 제외)",
        "",
        "| 지표 | 평균 |",
        "|---|---:|",
    ]
    report.extend(f"| {key} | {summary['metrics'][key]:.3f} |" for key in keys)
    report.extend(
        [
            "",
            "라벨 검수 상태는 summary.json에서 확인하세요. 이 평가는 검색 순위만 측정하며 LLM 답변 품질은 측정하지 않습니다.",
            "",
        ]
    )
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Reports written to: {output}")


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    evalset = find_evalset(args.evalset)
    goldset = read_goldset(evalset)
    db_dir = resolve(ROOT, args.db_dir)
    collection = open_collection(db_dir, args.collection)
    if args.top_k > collection.count():
        raise SystemExit("--top-k cannot exceed the collection size.")
    if not readiness(goldset, collection):
        raise SystemExit("Readiness check failed.")
    if args.check_only:
        print("Readiness check complete. No embedding API calls were made.")
        return
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the project-root .env or environment.")
    rows = evaluate(goldset, collection, args.top_k)
    write_outputs(rows, args, evalset)


if __name__ == "__main__":
    main()
