"""벡터 검색 후보 박물관을 한국어 BM25 점수와 RRF로 재정렬한다.

Chroma와 Neo4j를 직접 조회하지 않는다. 전체 TextSpan으로 재정렬기를 한 번 만든 뒤
벡터 검색 순서대로 정렬된 박물관 ID를 ``rerank``에 전달한다. 반환된
``best_span_id``를 실제 출처 근거에 연결하는 작업은 호출자가 담당한다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite

from rank_bm25 import BM25Okapi


@dataclass(frozen=True, slots=True)
class SpanDocument:
    """BM25 코퍼스에 넣을 본문 구간 한 건.

    ``museum_id``는 구간 소유 박물관, ``span_id``는 Neo4j TextSpan의 고유 ID,
    ``text``는 실제 점수를 계산할 본문이다.
    """

    museum_id: str
    span_id: str
    text: str


@dataclass(frozen=True, slots=True)
class RankedMuseum:
    """박물관별 벡터·BM25 순위, 결합 점수, 대표 본문 구간.

    ``vector_rank``는 입력된 벡터 검색 순위이고 ``bm25_score``는 대표 구간의
    원점수다. ``bm25_rank``와 대표 구간은 양수 BM25 점수가 없으면 ``None``이다.
    ``rrf_score``는 두 원점수가 아닌 각 순위를 결합한 최종 점수다.
    """

    museum_id: str
    vector_rank: int
    bm25_rank: int | None
    bm25_score: float
    rrf_score: float
    best_span_id: str | None
    best_span_text: str | None


def _kiwi_tokenizer() -> Callable[[str], list[str]]:
    """본문과 질문에 동일하게 적용할 한국어 형태소 토큰화 함수를 만든다.

    명사·용언·수식언과 영문·숫자·어근을 남기고 조사·어미·문장부호는 제외한다.
    """
    from kiwipiepy import Kiwi

    kiwi = Kiwi()

    def tokenize(text: str) -> list[str]:
        """Kiwi 분석 결과에서 검색에 사용할 형태소 문자열을 반환한다."""
        return [
            token.form.casefold()
            for token in kiwi.tokenize(text)
            if token.tag.startswith(("N", "V", "M")) or token.tag in {"SL", "SN", "XR"}
        ]

    return tokenize


def _nonnegative_finite(value: float, name: str) -> float:
    """RRF 설정값이 유한한 0 이상의 수인지 확인하고 실수로 변환한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


class BM25Reranker:
    """전체 본문 구간의 BM25 통계를 유지하며 후보 박물관 순위를 결합한다.

    생성 시 전체 코퍼스로 IDF를 계산한다. 검색마다 후보 구간만으로 BM25를
    다시 구성하면 점수 기준이 달라지므로 인스턴스를 재사용해야 한다.
    """

    def __init__(
        self,
        spans: Sequence[SpanDocument],
        *,
        tokenize: Callable[[str], list[str]] | None = None,
    ) -> None:
        """전체 구간을 검증하고 BM25 인덱스를 한 번 구성한다.

        ``spans``에는 검색 후보뿐 아니라 그래프의 전체 TextSpan을 전달한다.
        ``tokenize``를 생략하면 Kiwi 형태소 분석을 사용한다. 빈 코퍼스는
        허용하며, 이 경우 검색 결과는 벡터 순위만 따른다.
        """
        if tokenize is not None and not callable(tokenize):
            raise TypeError("tokenize must be callable")
        self._tokenize = tokenize or _kiwi_tokenizer()
        if any(not isinstance(span, SpanDocument) for span in spans):
            raise TypeError("spans must contain SpanDocument values")
        # 구간 ID 순서로 고정해 BM25 동점일 때 대표 구간 선택을 재현 가능하게 한다.
        self._spans = tuple(sorted(spans, key=lambda span: span.span_id))
        span_ids: set[str] = set()
        by_museum: dict[str, list[int]] = defaultdict(list)
        for index, span in enumerate(self._spans):
            if not span.museum_id or not span.span_id or not span.text.strip():
                raise ValueError("each span needs a museum_id, span_id, and text")
            if span.span_id in span_ids:
                raise ValueError(f"duplicate span_id: {span.span_id}")
            span_ids.add(span.span_id)
            by_museum[span.museum_id].append(index)
        self._by_museum = by_museum

        # IDF는 매 요청의 후보가 아닌 전체 본문 구간을 기준으로 계산한다.
        tokenized = [self._tokenize(span.text) for span in self._spans]
        self._bm25 = BM25Okapi(tokenized) if any(tokenized) else None

    def rerank(
        self,
        question: str,
        vector_museum_ids: Sequence[str],
        *,
        top_k: int = 5,
        rrf_constant: float = 60,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0,
    ) -> list[RankedMuseum]:
        """벡터 순서와 BM25 순서를 RRF로 결합해 상위 박물관을 반환한다.

        ``vector_museum_ids``는 벡터 검색 순서대로 전달한다. 각 박물관에 속한
        구간 가운데 BM25 점수가 가장 높은 한 건을 대표 구간으로 선택한다.
        BM25 점수가 0인 후보는 어휘 순위에 포함하지 않으므로, 모두 0점이면
        벡터 순서가 유지된다. 반환 수는 ``top_k``로 제한한다.
        """
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a nonempty string")
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        rrf_constant = _nonnegative_finite(rrf_constant, "rrf_constant")
        if rrf_constant == 0:
            raise ValueError("rrf_constant must be positive")
        vector_weight = _nonnegative_finite(vector_weight, "vector_weight")
        bm25_weight = _nonnegative_finite(bm25_weight, "bm25_weight")
        if vector_weight == bm25_weight == 0:
            raise ValueError("at least one rank weight must be positive")

        if isinstance(vector_museum_ids, (str, bytes)):
            raise ValueError("vector_museum_ids must be a sequence of IDs")
        museum_ids = list(dict.fromkeys(vector_museum_ids))
        if any(not isinstance(mid, str) or not mid.strip() for mid in museum_ids):
            raise ValueError("vector_museum_ids must contain nonempty strings")
        if not museum_ids:
            return []

        query_tokens = self._tokenize(question)
        scores = self._bm25.get_scores(query_tokens) if self._bm25 and query_tokens else ()
        best: dict[str, tuple[float, SpanDocument]] = {}
        # 전체 코퍼스의 점수를 계산하되 벡터 후보 박물관의 구간만 비교한다.
        for museum_id in museum_ids:
            for index in self._by_museum.get(museum_id, ()):
                score = float(scores[index]) if len(scores) else 0.0
                if score > 0 and (museum_id not in best or score > best[museum_id][0]):
                    best[museum_id] = (score, self._spans[index])

        vector_ranks = {museum_id: rank for rank, museum_id in enumerate(museum_ids, 1)}
        # 양수 BM25 점수에만 어휘 순위를 부여한다. 동점이면 벡터 순위가 앞선다.
        lexical_ids = sorted(best, key=lambda mid: (-best[mid][0], vector_ranks[mid], mid))
        bm25_ranks = {museum_id: rank for rank, museum_id in enumerate(lexical_ids, 1)}

        fused: list[RankedMuseum] = []
        for museum_id in museum_ids:
            vector_rank = vector_ranks[museum_id]
            bm25_rank = bm25_ranks.get(museum_id)
            bm25_score, span = best.get(museum_id, (0.0, None))
            # 서로 단위가 다른 원점수를 더하지 않고 각 검색기의 순위를 합산한다.
            rrf_score = vector_weight / (rrf_constant + vector_rank)
            if bm25_rank is not None:
                rrf_score += bm25_weight / (rrf_constant + bm25_rank)
            fused.append(RankedMuseum(
                museum_id=museum_id,
                vector_rank=vector_rank,
                bm25_rank=bm25_rank,
                bm25_score=bm25_score,
                rrf_score=rrf_score,
                best_span_id=span.span_id if span else None,
                best_span_text=span.text if span else None,
            ))
        fused.sort(key=lambda item: (-item.rrf_score, item.vector_rank, item.museum_id))
        return fused[:top_k]
