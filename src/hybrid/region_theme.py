"""Recognize only simple, unambiguous region-plus-theme questions."""
from __future__ import annotations

import re

_REGIONS = {
    "경기": "경기도", "경기도": "경기도", "서울": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산광역시": "부산광역시", "대구": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천광역시": "인천광역시", "대전": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산광역시": "울산광역시", "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "강원도": "강원특별자치도", "강원": "강원특별자치도",
}
_PATTERN = re.compile(
    r"^\s*(?P<region>경기도|경기|서울특별시|서울|부산광역시|부산|대구광역시|대구|인천광역시|인천|대전광역시|대전|울산광역시|울산|제주도|제주|강원도|강원)"
    r"\s*권?\s*(?:에|에서)\s*(?:있고|있는|위치한|위치하고)\s*"
    r"(?P<theme>자연|역사|문화|사진|미술|과학|예술|생태)(?:과|와)?\s*관련(?:된|이\s*있는)?\s*"
    r"(?:곳|박물관|미술관)(?:이면\s*좋겠음|이면\s*좋겠어요|\s*(?:추천해줘|추천해주세요|알려줘|알려주세요))?\s*[?!.]*\s*$"
)


def simple_region_theme(question: str) -> str | None:
    match = _PATTERN.fullmatch(question) if isinstance(question, str) else None
    return _REGIONS[match.group("region")] if match else None
