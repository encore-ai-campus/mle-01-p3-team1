"""ChromaDB 검색 도구: LLM 없이 검증된 검색 계획만 실행한다.

기존 DB를 읽기만 하며 새 Collection을 만들거나 데이터를 수정하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .vector_search_analyzer import MetadataFilters, PROJECT_ROOT


# 프로젝트 루트를 기준으로 경로를 고정한다(실행하는 디렉터리와 무관).
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vector_db" / "museum_chroma"
DEFAULT_COLLECTION = "museum_documents"

# 박물관 데이터에서 쓰는 시/도 표기를 기준으로 약칭을 변환한다.
# 실제 데이터에 과거/신규 행정구역 표기가 섞인 경우 두 표기를 허용한다.
_SIDO_ALIASES: dict[str, tuple[str, ...]] = {
    "서울": ("서울특별시",),
    "서울시": ("서울특별시",),
    "인천": ("인천광역시",),
    "인천시": ("인천광역시",),
    "부산": ("부산광역시",),
    "대구": ("대구광역시",),
    "대전": ("대전광역시",),
    "광주": ("광주광역시",),
    "울산": ("울산광역시",),
    "경기": ("경기도",),
    "강원": ("강원특별자치도",),
    "강원도": ("강원특별자치도",),
    "충북": ("충청북도",),
    "충남": ("충청남도",),
    "경북": ("경상북도",),
    "경남": ("경상남도",),
    "전북": ("전북특별자치도", "전라북도"),
    "전라북도": ("전북특별자치도", "전라북도"),
    "전북특별자치도": ("전북특별자치도", "전라북도"),
    "전남": ("전라남도",),
    "제주": ("제주특별자치도",),
    "제주도": ("제주특별자치도",),
    "세종": ("세종특별자치시", "세종특별시"),
    "세종특별자치시": ("세종특별자치시", "세종특별시"),
    "세종특별시": ("세종특별자치시", "세종특별시"),
}


def build_chroma_where(filters: MetadataFilters) -> dict[str, Any] | None:
    """허용된 메타데이터 조건을 ChromaDB where 문법으로 변환한다."""
    conditions: list[dict[str, Any]] = []

    # 단일 시/도와 복수 시/도를 같은 경로에서 처리한다.
    # 사용자가 "경기도나 인천"을 지정하면 둘 중 한 곳인 경우만 허용한다.
    requested_sidos = filters.sidos or ([filters.sido] if filters.sido else [])
    if requested_sidos:
        variants: list[str] = []
        for raw_sido in requested_sidos:
            sido = raw_sido.strip()
            variants.extend(_SIDO_ALIASES.get(sido, (sido,)))

        # 별칭 확장 과정에서 중복된 지역은 제거한다.
        variants = list(dict.fromkeys(variants))
        if len(variants) == 1:
            conditions.append({"sido": {"$eq": variants[0]}})
        else:
            # $in은 같은 필드에서 여러 값 중 하나를 허용하는 OR 조건이다.
            conditions.append({"sido": {"$in": variants}})

    if filters.sigungu:
        conditions.append({"sigungu": {"$eq": filters.sigungu.strip()}})

    if filters.ownership_type:
        conditions.append({"ownership_type": {"$eq": filters.ownership_type}})

    for field, operator, value in (
        ("adult_fee", "$gte", filters.adult_fee_min),
        ("adult_fee", "$lte", filters.adult_fee_max),
        ("youth_fee", "$lte", filters.youth_fee_max),
        ("child_fee", "$lte", filters.child_fee_max),
    ):
        if value is not None:
            conditions.append({field: {operator: value}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class ChromaSearchTool:
    """확장된 검색어/메타데이터 필터/후보 ID를 받아 검색만 수행하는 도구."""

    def __init__(
        self,
        *,
        embeddings: Any | None = None,
        db_path: str | Path | None = None,
        collection_name: str = DEFAULT_COLLECTION,
        collection: Any | None = None,
    ):
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        self._embeddings = embeddings

        # 외부에서 상대 경로를 넘겨도 프로젝트 루트 기준으로 해석한다.
        path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path = path if path.is_absolute() else PROJECT_ROOT / path

        if collection is not None:
            # 이미 연결된 Collection 주입: 단위 테스트 및 의존성 주입에 사용
            self.collection = collection
        else:
            import chromadb

            if not self.db_path.is_dir():
                raise FileNotFoundError(f"ChromaDB 폴더를 찾을 수 없습니다: {self.db_path}")
            client = chromadb.PersistentClient(path=str(self.db_path))
            # get_collection: DB가 잘못 비어 있어도 새 컬렉션을 생성하지 않는다.
            self.collection = client.get_collection(name=collection_name)

    def _embed_query(self, text: str) -> list[float]:
        """저장할 때 사용한 모델과 동일한 모델로 질문 1개를 임베딩한다."""
        if self._embeddings is None:
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        return self._embeddings.embed_query(text)

    def search(
        self,
        *,
        semantic_query: str = "",
        filters: MetadataFilters | None = None,
        top_k: int = 5,
        candidate_ids: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """세 검색 모드 지원: 벡터 / 메타데이터 / 두 조건 결합."""
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 50:
            raise ValueError("top_k는 1~50 사이의 정수여야 합니다.")

        where = build_chroma_where(filters or MetadataFilters())
        semantic_query = semantic_query.strip()

        if candidate_ids is not None:
            # GraphDB에서 넘어온 ID 목록은 중복 없이 사용한다.
            candidate_ids = list(dict.fromkeys(candidate_ids))
            if not candidate_ids:
                return where, []

        if not semantic_query and where is None and candidate_ids is None:
            raise ValueError("의미 검색어, 메타데이터 조건 또는 후보 ID 중 하나는 필요합니다.")

        if semantic_query:
            # 실제 name + text 임베딩은 이미 DB에 저장됨.
            # 검색 시에는 확장 검색어만 임베딩하고 DB를 다시 쓰지 않는다.
            query_embedding = self._embed_query(semantic_query)
            kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where is not None:
                kwargs["where"] = where
            if candidate_ids is not None:
                kwargs["ids"] = candidate_ids

            response = self.collection.query(**kwargs)
            return where, [
                {
                    "museum_id": mid,
                    "document": doc,
                    "metadata": metadata or {},
                    "distance": distance,
                }
                for mid, doc, metadata, distance in zip(
                    response["ids"][0],
                    response["documents"][0],
                    response["metadatas"][0],
                    response["distances"][0],
                )
            ]

        # 필터 조건만 있는 질문에서는 비용을 아끼기 위해 임베딩 API를 호출하지 않는다.
        kwargs = {"include": ["documents", "metadatas"], "limit": top_k}
        if where is not None:
            kwargs["where"] = where
        if candidate_ids is not None:
            kwargs["ids"] = candidate_ids

        response = self.collection.get(**kwargs)
        return where, [
            {
                "museum_id": mid,
                "document": doc,
                "metadata": metadata or {},
                "distance": None,  # 메타데이터 조회에는 벡터 유사도 순위가 없다.
            }
            for mid, doc, metadata in zip(
                response["ids"], response["documents"], response["metadatas"]
            )
        ]
