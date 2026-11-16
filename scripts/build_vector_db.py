"""Chroma 벡터 DB를 명령 한 줄로 다시 만든다.

notebooks/vector_db/vector_db_builder.ipynb 의 적재 셀과 같은 방식이다.
- 입력: data/processed/museum_final_738.csv
- 임베딩: OpenAI text-embedding-3-small, 입력은 "박물관명 + 박물관 설명"
- 출력: data/vector_db/museum_chroma/ 의 컬렉션 museum_documents (cosine)

실행 (프로젝트 루트):
    uv run python scripts/build_vector_db.py                 # 기본 경로에 구축 (컬렉션이 이미 있으면 중단)
    uv run python scripts/build_vector_db.py --force         # 기존 컬렉션을 지우고 다시 구축
    uv run python scripts/build_vector_db.py --db-path tmp/chroma_test   # 다른 경로에 구축

OpenAI 임베딩 API를 호출하므로 .env 의 OPENAI_API_KEY 가 필요하고 사용료가 발생한다.
평가나 챗봇이 같은 DB를 쓰는 중에는 --force 로 덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "processed" / "museum_final_738.csv"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vector_db" / "museum_chroma"
COLLECTION_NAME = "museum_documents"
EMBEDDING_MODEL = "text-embedding-3-small"

CHROMA_COLUMNS = [
    "museum_id", "text",
    "name", "ownership_type", "sido", "sigungu", "address", "latitude", "longitude", "homepage_url",
    "adult_fee", "youth_fee", "child_fee", "adult_fee_status", "fee_notes",
    "weekday_open", "weekday_close", "holiday_open", "holiday_close", "closure_rule_raw",
    "amenities_raw", "transport_notes", "image_url", "image_copyright",
    "source_types", "requires_manual_review",
]
NUMERIC_COLUMNS = {"latitude", "longitude", "adult_fee", "youth_fee", "child_fee"}


def make_metadata(row: pd.Series) -> dict:
    """Chroma 메타데이터는 str·int·float·bool만 받으므로 값을 정리한다."""
    metadata = {}
    for col, value in row.items():
        if col in ("museum_id", "text") or pd.isna(value):
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        if col in NUMERIC_COLUMNS:
            value = pd.to_numeric(value, errors="coerce")
            if pd.isna(value) or not np.isfinite(value):
                continue
            value = float(value)
        elif col == "requires_manual_review":
            if isinstance(value, str):
                if value.lower() not in ("true", "false"):
                    continue
                value = value.lower() == "true"
            else:
                value = bool(value)
        elif isinstance(value, (np.bool_, bool)):
            value = bool(value)
        elif isinstance(value, (np.integer, int)):
            value = int(value)
        elif isinstance(value, (np.floating, float)):
            value = float(value)
        else:
            value = str(value)
        metadata[col] = value
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Chroma 벡터 DB 재구축")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="DB 폴더 (기본: data/vector_db/museum_chroma)")
    parser.add_argument("--force", action="store_true", help="기존 컬렉션을 지우고 다시 만든다")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 가 없습니다. .env 에 키를 입력하세요.", file=sys.stderr)
        return 1

    import chromadb
    from langchain_openai import OpenAIEmbeddings

    started = time.perf_counter()
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")[CHROMA_COLUMNS].copy()
    assert df["museum_id"].notna().all() and df["museum_id"].is_unique, "museum_id 가 비었거나 중복입니다."
    assert df["text"].notna().all() and df["name"].notna().all(), "name 또는 text 가 비어 있습니다."

    ids = df["museum_id"].astype(str).tolist()
    documents = df["text"].astype(str).tolist()
    embedding_inputs = [f"박물관명: {name}\n박물관 설명: {text}" for name, text in zip(df["name"], documents)]
    metadatas = [make_metadata(row) for _, row in df.iterrows()]

    db_path = args.db_path if args.db_path.is_absolute() else PROJECT_ROOT / args.db_path
    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path))
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        if not args.force:
            print(f"{db_path} 에 컬렉션 {COLLECTION_NAME} 이 이미 있습니다. 다시 만들려면 --force 를 붙이세요.",
                  file=sys.stderr)
            return 1
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_strategy": "name_plus_text", "embedding_model": EMBEDDING_MODEL},
    )
    print(f"임베딩 생성 중: {len(ids)}건 ({EMBEDDING_MODEL})")
    vectors = OpenAIEmbeddings(model=EMBEDDING_MODEL).embed_documents(embedding_inputs)
    collection.add(ids=ids, documents=documents, embeddings=vectors, metadatas=metadatas)

    stored = chromadb.PersistentClient(path=str(db_path)).get_collection(COLLECTION_NAME)
    assert stored.count() == len(ids), f"건수 불일치: {stored.count()} / {len(ids)}"
    print(f"완료: {stored.count()}건, 임베딩 차원 {len(vectors[0])}, {time.perf_counter() - started:.0f}초")
    print(f"저장 위치: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
