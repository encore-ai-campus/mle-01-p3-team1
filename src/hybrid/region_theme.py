"""Recognize a single, unambiguous region (시·도, optionally 시·군·구) in a question.

The region becomes a hard search filter before ranking, so a wrong guess silently drops
the right facilities. Everything uncertain therefore returns None and the question takes
its usual path instead:

- a region name that is part of a facility name (경기도박물관, 서울대박물관),
- more than one region, or a sido and a district that do not belong together,
- wording that changes what the region means (negation, nearby, same-operator relations),
- conditions this filter cannot express (fees, operating organisation).

2026-11-14: only the form "경기도에 있고 자연과 관련된 곳" was recognised, so
"경기도에서 역사를 알 수 있는 곳 10개 추천" searched the whole country and returned
Seoul, Gwangju and Gangwon facilities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.hybrid.ontology_filter import _SIDO_TERMS, _sigungu_table, sido_spellings


@dataclass(frozen=True)
class Region:
    sido: str
    sigungu: str | None = None


def _sido_terms() -> dict[str, str]:
    terms = dict(_SIDO_TERMS)
    for canonical in set(_SIDO_TERMS.values()):
        terms[canonical] = canonical
        for spelling in sido_spellings(canonical):
            terms[spelling] = canonical
    for short in ("서울", "부산", "대구", "인천", "대전", "울산"):
        terms[f"{short}시"] = _SIDO_TERMS[short]
    terms.update({"강원도": "강원특별자치도", "제주도": "제주특별자치도", "경기도": "경기도"})
    return terms


# Names that look like a district but are usually read as another place.
_AMBIGUOUS = {"광주", "광주시"}

# After a region name only a particle, a space or the end may follow. A Hangul letter
# straight after it means the name belongs to something longer (경기도박물관, 서울대).
_AFTER = r"(?=$|[\s,.?!]|에서|에는|에도|에|의|으로|로|권|쪽|지역|내|소재|인|이|가|은|는|을|를|과|와|랑|만|도\s)"
# A fee condition cannot be expressed as a search filter here; it needs the graph's fee
# properties. recognize_region() therefore leaves such questions alone unless asked.
_FEE_WORDS = re.compile(r"무료|공짜|유료|입장료|관람료|요금")
_EXCLUDING_WORDS = re.compile(
    r"아닌|말고|제외|빼고|이외|외에|가격|저렴|언제|날짜|할인|"
    r"근처|주변|인근|가까운|가까이|떨어진|거리|"
    r"같은\s*(?:기관|시|군|구|지역|시도|도)|운영하는|운영\s*기관|비교|보다|차이|사이"
)


def _pattern(terms: dict[str, str] | dict[str, tuple[str, str]], *, strict: bool = True) -> re.Pattern[str]:
    names = sorted((name for name in terms if name not in _AMBIGUOUS), key=len, reverse=True)
    return re.compile("(?<![가-힣])(?:" + "|".join(map(re.escape, names)) + ")" + (_AFTER if strict else ""))


def recognize_region(question: str, *, allow_fee: bool = False) -> Region | None:
    """The one region the question asks about, or None when it is not clear-cut.

    Fee words (무료, 입장료 ...) make the question unclear unless allow_fee is set.
    """
    if not isinstance(question, str) or not question.strip():
        return None
    text = " ".join(question.split())
    if _EXCLUDING_WORDS.search(text) or (not allow_fee and _FEE_WORDS.search(text)):
        return None
    sido_terms = _sido_terms()
    districts = _sigungu_table()
    # Any region-like word that is not followed by a particle (경기도박물관, 부산까지) makes
    # the question unclear: it is either part of a name or a second place.
    for terms in (sido_terms, districts):
        loose = {m.group(0) for m in _pattern(terms, strict=False).finditer(text)}
        strict = {m.group(0) for m in _pattern(terms).finditer(text)}
        if loose != strict:
            return None
    sidos = {sido_terms[m.group(0)] for m in _pattern(sido_terms).finditer(text)}
    places = {districts[m.group(0)] for m in _pattern(districts).finditer(text)}
    sidos |= {sido for sido, _ in places}
    if len(sidos) != 1 or len(places) > 1:
        return None
    sido = next(iter(sidos))
    if not places:
        return Region(sido)
    place_sido, sigungu = next(iter(places))
    return Region(place_sido, sigungu) if place_sido == sido else None


def simple_region_theme(question: str) -> str | None:
    """The 시·도 of a clearly regional question (kept for callers that only need that)."""
    region = recognize_region(question)
    return region.sido if region else None


def region_with_fee(question: str) -> Region | None:
    """The region of a "region + fee condition" question (서울에서 무료로 갈 수 있는 곳)."""
    if not isinstance(question, str) or not _FEE_WORDS.search(question):
        return None
    return recognize_region(question, allow_fee=True)


def mentions_region(question: str) -> bool:
    """True when any 시·도 or 시·군·구 name appears, even inside a longer word."""
    text = str(question or "")
    return any(_pattern(terms, strict=False).search(text) for terms in (_sido_terms(), _sigungu_table()))


def is_fee_question(question: str) -> bool:
    """A fee condition with one clear region, or with no region at all (무료인 곳 추천해줘)."""
    if not isinstance(question, str) or not _FEE_WORDS.search(question) or _EXCLUDING_WORDS.search(question):
        return False
    return region_with_fee(question) is not None or not mentions_region(question)

