"""Deterministic classification rules for ontology v2.

Every rule reads raw CSV values and returns derived labels only. Nothing here
writes to the CSV or to Neo4j; build_cypher.py turns the results into Cypher.
Rule outputs are heuristics, so generated relationships carry a method name and
a verification status instead of being presented as confirmed facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ONTOLOGY_VERSION = "v2"

# ---------------------------------------------------------------------------
# Shared text helpers
# ---------------------------------------------------------------------------


def clean_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def compact_key(value: str) -> str:
    """Identity key: whitespace-insensitive comparison of a normalized name."""
    return re.sub(r"\s+", "", value)


# ---------------------------------------------------------------------------
# Facility type (Museum property, derived from the facility name)
# ---------------------------------------------------------------------------

FACILITY_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("박물관", "박물관"),
    ("미술관", "미술관"),
    ("기념관", "기념관"),
    ("전시관", "전시관"),
    ("과학관", "과학관"),
    ("역사관", "역사관"),
    ("문학관", "문학관"),
    ("체험관", "체험관"),
    ("자료관", "전시관"),
    ("사료관", "전시관"),
    ("민속관", "전시관"),
    ("뮤지엄", "박물관"),
    ("뮤지움", "박물관"),
    ("museum", "박물관"),
    ("아트센터", "미술관"),
    ("갤러리", "미술관"),
    ("아트", "미술관"),
    ("공원", "공원·야외전시"),
    ("파크", "공원·야외전시"),
    ("정원", "공원·야외전시"),
    ("동산", "공원·야외전시"),
    ("마을", "공원·야외전시"),
    ("민속촌", "공원·야외전시"),
    ("힐", "공원·야외전시"),
    ("월드", "공원·야외전시"),
    ("타운", "공원·야외전시"),
    ("방림원", "공원·야외전시"),
    ("문화촌", "공원·야외전시"),
    ("천문대", "과학관"),
    ("아쿠아리움", "아쿠아리움"),
)
_SUFFIX_TYPES = {"박물관", "미술관", "기념관", "전시관", "과학관", "역사관", "문학관", "체험관"}


def classify_facility_type(name: str) -> tuple[str, str]:
    """Return (facility_type, method). The latest keyword in the name wins."""
    text = re.sub(r"\s+", "", re.sub(r"\(.*?\)", "", name)).lower()
    best: tuple[int, str, str] | None = None
    for keyword, facility_type in FACILITY_TYPE_KEYWORDS:
        position = text.rfind(keyword.lower())
        if position < 0:
            continue
        end = position + len(keyword)
        if best is None or end > best[0]:
            best = (end, facility_type, keyword)
    if best is None and "(" in name:
        return classify_facility_type(name.replace("(", " ").replace(")", " "))
    if best is None:
        if text.endswith("관"):
            return "전시관", "name_generic_suffix"
        return "기타", "fallback"
    _, facility_type, keyword = best
    method = "name_suffix" if keyword in _SUFFIX_TYPES else "name_keyword"
    return facility_type, method


# ---------------------------------------------------------------------------
# Organization (OPERATED_BY / MANAGED_BY / PART_OF_ORG)
# ---------------------------------------------------------------------------

# Raw spellings that appear as organization prefixes. Region equivalence is
# handled by query-time code, so organizations keep the spelling they were
# recorded with.
SIDO_NAMES = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "세종특별시", "경기도", "강원특별자치도", "강원도",
    "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도", "전남광주통합특별시",
    "경상북도", "경상남도", "제주특별자치도",
)
_SIDO_RE = "|".join(sorted(SIDO_NAMES, key=len, reverse=True))
_GOV_SGG_RE = re.compile(
    rf"(?P<sido>{_SIDO_RE})\s*(?P<sgg>[가-힣]+?(?:시|군|구))(?:청)?(?:\s+(?P<rest>.+))?"
)
_GOV_SIDO_RE = re.compile(rf"(?P<sido>{_SIDO_RE})(?:청)?(?:\s+(?P<rest>.+))?")
_GOV_LOCAL_RE = re.compile(r"(?P<sgg>[가-힣]+?(?:시|군|구))(?:청)?(?:\s+(?P<rest>.+))?")
_MUNICIPAL_PREFIX_RE = re.compile(r"(?P<sgg>[가-힣]+?(?:시|군|구))(?:립)")
_DEPARTMENT_RE = re.compile(r"(?:과|팀|계|부|국|단|실)$")
_AFFILIATE_RE = re.compile(
    r"(재단|공단|공사|문화원|센터|사업소|사무소|박물관|미술관|기념관|문학관|전시관|역사관|회관|원)$"
)
_PARENT_DEPT_RE = re.compile(r"(?P<parent>.+?)\s+(?P<dept>\S+(?:팀|부|과))$")
_PARENT_AFFILIATE_RE = re.compile(r"(?P<parent>.+?)\s+(?P<child>\S+(?:원|센터|사업소))$")
_CORP_PREFIX_RE = re.compile(r"^(?:\(주\)|㈜|주식회사|\(재\)|\(사\)|재단법인|사단법인)\s*")
_CORP_SUFFIX_RE = re.compile(r"\s*(?:\(주\)|㈜)$")

# Manually confirmed spelling variants of the same organization.
ORG_ALIASES = {
    "경기도 문화재단": "경기문화재단",
    "양주시회암사지박물관": "양주시립회암사지박물관",
    "울산남구도시관리공단": "울산광역시 남구 도시관리공단",
    "동아방송예술대학": "동아방송예술대학교",
    "한국잠사플레이팜 농업회사법인㈜": "한국잠사플레이팜",
    "충청북도교욱문화원 충북교육박물관": "충청북도교육문화원 충북교육박물관",
    "(사)한국미술 양평지부": "(사)한국미술협회 양평지부",
}

# Values recorded in the organization columns that are not organization names.
NON_ORG_VALUES = {"사립"}

# Affiliate names that are only meaningful together with their parent
# (e.g. every city has a 농업기술센터); their key is qualified by the parent.
GENERIC_AFFILIATES = {
    "농업기술센터", "문화시설사업소", "시설관리공단", "도시관리공단", "교육청", "박물관",
    "문화예술센터", "평생학습원", "문화재연구원", "종합시설관리사업소", "유적전시관",
    "유적전시관-마한관",
}

CENTRAL_AGENCIES = {
    "문화체육관광부", "국가보훈부", "국가유산청", "관세청", "국세청", "기상청", "산림청",
    "행정안전부", "해양수산부", "환경부", "여성가족부", "농림축산식품부", "국토교통부",
    "국회사무처", "국회기록원", "우정사업본부", "보훈청", "서울지방국토관리청", "국토지리정보원",
}
RELIGIOUS_EXACT = {"구인사", "월정사", "대흥사", "은해사", "명주사", "용문사", "불갑사"}

ORG_TYPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("국립기관", re.compile(r"^국립")),
    ("대학·학교법인", re.compile(r"대학교|대학$|카이스트|학교법인|학원$|대학교?\s")),
    ("종교단체", re.compile(r"불교|교회|천주교|원불교|조계종|교구|기독교")),
    ("재단·비영리법인", re.compile(r"재단|\(재\)|\(사\)|사단법인|협회|사업회|숭모회|보존회|협동조합|문화사랑회")),
    ("기업", re.compile(r"\(주\)|㈜|주식회사|농업회사법인")),
    ("공공기관", re.compile(r"교육청|경찰청|공단|공사$|진흥원|위원회|사업소|센터|문화원|관리사무소|본부|연구원|기술원|학습원|한국은행|면사무소|사적관리소")),
    ("개인", re.compile(r"^개인")),
    ("문화시설", re.compile(r"박물관|미술관|기념관|뮤지엄|뮤지움|전시관|문학관|역사관|아트|갤러리|공원|동산|마을|민속촌|힐$|숲$|사관$|부엌$|월드$|타운$|관$")),
    ("기업", re.compile(r"은행|백화점|호텔|삼성|현대|신한|미래엔|페이퍼|JDC|KT&G|넥슨|롯데|아모레")),
)


@dataclass(frozen=True)
class Org:
    org_key: str
    name: str
    org_type: str
    level: str  # 광역지자체 | 기초지자체 | 지자체 부서 | 소속기관 | 부서 | 기관
    sido: str | None = None


@dataclass(frozen=True)
class OrgResolution:
    """org is what the museum column points to; edges are (child, parent) pairs."""

    org: Org
    edges: tuple[tuple[Org, Org], ...] = ()
    method: str = "name_rule_v1"
    raw_name: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def parent(self) -> Org | None:
        return next((parent for child, parent in self.edges if child == self.org), None)


def _plain_org_name(name: str) -> str:
    name = _CORP_PREFIX_RE.sub("", name)
    return clean_space(_CORP_SUFFIX_RE.sub("", name))


def classify_org_type(name: str) -> str:
    if name in CENTRAL_AGENCIES:
        return "중앙행정기관"
    if name in RELIGIOUS_EXACT:
        return "종교단체"
    for org_type, pattern in ORG_TYPE_RULES:
        if pattern.search(name):
            return org_type
    return "기타"


def _gov(sido: str, sgg: str | None) -> Org:
    if sgg:
        name = f"{sido} {sgg}"
        return Org(compact_key(name), name, "지방자치단체", "기초지자체", sido)
    return Org(compact_key(sido), sido, "지방자치단체", "광역지자체", sido)


def _standalone(name: str) -> Org:
    plain = _plain_org_name(name)
    level = "부서" if _DEPARTMENT_RE.search(plain) and not _AFFILIATE_RE.search(plain) else "기관"
    return Org(compact_key(plain), plain, classify_org_type(name), level)


def _affiliate(parent: Org, child_name: str) -> Org:
    child = _standalone(child_name)
    if child.name in GENERIC_AFFILIATES:
        name = f"{parent.name} {child.name}"
        return Org(compact_key(name), name, child.org_type, "소속기관", parent.sido)
    return Org(child.org_key, child.name, child.org_type, "소속기관", parent.sido)


def _department(parent: Org, dept: str) -> Org:
    name = f"{parent.name} {dept}"
    level = "지자체 부서" if parent.org_type == "지방자치단체" else "부서"
    return Org(compact_key(name), name, parent.org_type, level, parent.sido)


def _child_of(parent: Org, rest: str) -> tuple[Org, list[tuple[Org, Org]], str]:
    """Resolve the text after a parent organization name."""
    rest = clean_space(rest)
    edges: list[tuple[Org, Org]] = []
    if re.search(r"대학|학교", rest):
        return _standalone(rest), edges, "university_detached"
    municipal = _MUNICIPAL_PREFIX_RE.match(rest)
    if municipal and parent.level == "광역지자체":
        city = _gov(parent.sido or parent.name, municipal.group("sgg"))
        edges.append((city, parent))
        parent = city
    head, _, tail = rest.partition(" ")
    if tail and (_AFFILIATE_RE.search(head) or head in GENERIC_AFFILIATES):
        # e.g. "교육청 교육정책과": a department of an affiliate, not of the city.
        affiliate = _affiliate(parent, head)
        dept = _department(affiliate, tail)
        edges += [(affiliate, parent), (dept, affiliate)]
        return dept, edges, "affiliate_department"
    if _DEPARTMENT_RE.search(rest) and not _AFFILIATE_RE.search(rest):
        dept = _department(parent, rest)
        edges.append((dept, parent))
        return dept, edges, "department"
    affiliate = _affiliate(parent, rest)
    edges.append((affiliate, parent))
    return affiliate, edges, "affiliate"


def resolve_org(raw_name: str, museum_sido: str) -> OrgResolution | None:
    """Map one raw organization string to an Organization and its parent chain.

    Returns None for values that are not organization names (see NON_ORG_VALUES).
    """
    raw = clean_space(raw_name)
    if not raw or raw in NON_ORG_VALUES:
        return None
    name = clean_space(ORG_ALIASES.get(raw, raw))
    notes: list[str] = []
    if name != raw:
        notes.append("manual_alias")

    def gov_result(parent: Org, rest: str | None) -> OrgResolution:
        if not rest:
            return OrgResolution(parent, (), "gov_name_rule_v1", raw, tuple(notes))
        org, edges, kind = _child_of(parent, rest)
        return OrgResolution(org, tuple(edges), f"gov_{kind}_rule_v1", raw, tuple(notes))

    for pattern, has_sgg in ((_GOV_SGG_RE, True), (_GOV_SIDO_RE, False)):
        match = pattern.fullmatch(name)
        if match:
            parent = _gov(match.group("sido"), match.group("sgg") if has_sgg else None)
            return gov_result(parent, match.group("rest"))

    local = _GOV_LOCAL_RE.fullmatch(name)
    if local and museum_sido:
        notes.append("sido_from_museum_row")
        return gov_result(_gov(museum_sido, local.group("sgg")), local.group("rest"))

    for pattern, group in ((_PARENT_DEPT_RE, "dept"), (_PARENT_AFFILIATE_RE, "child")):
        match = pattern.fullmatch(name)
        if not match:
            continue
        parent_name = match.group("parent")
        if re.fullmatch(r"\(주\)|㈜|주식회사|\(재\)|\(사\)|재단법인|사단법인|학교법인", parent_name):
            break
        parent = _standalone(parent_name)
        if group == "dept":
            org = _department(parent, match.group("dept"))
        else:
            org = _affiliate(parent, match.group("child"))
        return OrgResolution(org, ((org, parent),), f"name_{group}_rule_v1", raw, tuple(notes))

    return OrgResolution(_standalone(name), (), "name_rule_v1", raw, tuple(notes))


def is_self_named(org_name: str, museum_name: str) -> bool:
    return compact_key(_plain_org_name(org_name)) == compact_key(museum_name)


# ---------------------------------------------------------------------------
# Amenity (controlled vocabulary mapped from amenities_raw)
# ---------------------------------------------------------------------------

AMENITY_CATEGORIES = {
    "주차장": "교통·주차",
    "장애인 주차구역": "접근성",
    "전기차 충전": "교통·주차",
    "자전거 보관대": "교통·주차",
    "장애인 화장실": "접근성",
    "엘리베이터·리프트": "접근성",
    "휠체어 대여·이용": "접근성",
    "장애인 편의시설": "접근성",
    "수유실": "가족·어린이",
    "유모차 대여": "가족·어린이",
    "어린이 놀이·체험공간": "가족·어린이",
    "카페": "식음·쇼핑",
    "식당": "식음·쇼핑",
    "매점·편의점": "식음·쇼핑",
    "기념품점": "식음·쇼핑",
    "물품보관": "편의",
    "휴게공간": "편의",
    "무선인터넷": "편의",
    "의무실": "편의",
    "해설·안내 서비스": "관람 지원",
    "도서·자료실": "학습 공간",
    "강당·교육실": "학습 공간",
    "야외공간·정원": "야외",
    "숙박": "편의",
}

# (amenity, include pattern, exclude pattern). One raw token may map to several.
AMENITY_RULES: tuple[tuple[str, str, str | None], ...] = (
    ("장애인 주차구역", r"장애인\s*주차|장애인 편의시설 및 주차장|장애인\d", None),
    ("주차장", r"주차|주자장", None),
    ("전기차 충전", r"전기차|전기충전", None),
    ("자전거 보관대", r"자전거", None),
    ("장애인 화장실", r"장애인\s*(용\s*)?화장실|장애인용 포함", None),
    ("엘리베이터·리프트", r"엘리베이터|승강기|리프트", None),
    ("휠체어 대여·이용", r"휠체어|훨체어", None),
    ("장애인 편의시설", r"장애인 편의시설|장애인 전담|사회적약자", None),
    ("수유실", r"수유|기저귀|아기방", None),
    ("유모차 대여", r"유모차", None),
    ("어린이 놀이·체험공간", r"어린이|유아|놀이방|놀이시설|놀이터|장난감", None),
    ("카페", r"카페|까페|커피|찻집|스낵바", r"카페테리아"),
    ("카페", r"카페테리아|카페테리어", None),
    ("식당", r"식당|레스토랑|푸드코트|취사장", None),
    ("매점·편의점", r"매점|편의점|자판기|마켓|상점", None),
    ("기념품점", r"뮤지엄\s*[샵숍샾]|뮤지업샵|아트\s*[샵숍]|기념품|문화상품|상품\s*판매", None),
    ("물품보관", r"물품보관", None),
    ("휴게공간", r"휴게|휴식|쉼터|정자|벤치|파고라|누마루|테라스|사랑방", None),
    ("무선인터넷", r"무선인터넷|와이파이", None),
    ("의무실", r"의무실|응급|처치실", r"강아지"),
    ("해설·안내 서비스", r"해설|음성안내|안내 앱|모바일서비스|도우미", None),
    ("도서·자료실", r"도서|자료실|라이브러리|library|아카이브|북카페|북파크", None),
    ("강당·교육실", r"강당|강의실|세미나실|교육실|시청각|회의실|컨퍼런스|다목적", None),
    ("야외공간·정원", r"공원|정원|산책로|연못|야외전시|조각공원|분수|폭포", None),
    ("숙박", r"숙박|게스트\s*하우스|템플스테이|캠핑", None),
)


def split_amenity_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"\+|,(?![^()]*\))", raw)
    return [clean_space(part) for part in parts if clean_space(part)]


def map_amenity_token(token: str) -> list[str]:
    found: list[str] = []
    lowered = token.lower()
    for amenity, include, exclude in AMENITY_RULES:
        if re.search(include, lowered) and not (exclude and re.search(exclude, lowered)):
            if amenity not in found:
                found.append(amenity)
    return found


# ---------------------------------------------------------------------------
# Theme / Topic / activity types (keyword evidence in TextSpan text)
# ---------------------------------------------------------------------------

THEMES = (
    "역사", "미술·예술", "과학·기술", "자연·생태", "문학",
    "생활문화·민속", "전쟁·평화", "산업·직업", "사진·영상", "종교",
)

# topic -> (theme, keywords). Avoid one-syllable keywords that hide inside other
# words (e.g. 술 in 미술, 화장 in 화장실).
TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "선사·고고학": ("역사", ("선사", "구석기", "신석기", "청동기", "고인돌", "패총", "고분", "발굴조사", "출토", "고고학")),
    "독립운동": ("역사", ("독립운동", "항일", "의병", "3·1운동", "삼일운동", "임시정부", "독립투사", "애국지사")),
    "지역사": ("역사", ("지역사", "향토사", "향토사료", "고장의 역사", "지역의 역사", "읍성")),
    "근현대사": ("역사", ("근현대사", "근대사", "개항", "근대도시", "근대 문화")),
    "인물기념": ("역사", ("생가", "생애와 업적", "업적을 기리", "정신을 기리", "뜻을 기리", "선생의 생애")),
    "현대미술": ("미술·예술", ("현대미술", "동시대 미술", "컨템포러리", "설치미술", "미디어아트", "미디어 아트")),
    "회화": ("미술·예술", ("회화", "서양화", "한국화", "수묵", "유화", "화백")),
    "조각": ("미술·예술", ("조각", "조소")),
    "서예·서화": ("미술·예술", ("서예", "서화", "글씨", "현판", "추사")),
    "민화": ("미술·예술", ("민화",)),
    "도자기": ("미술·예술", ("도자", "청자", "백자", "분청", "옹기", "도요지", "도기")),
    "공예": ("미술·예술", ("공예", "자수", "옻칠", "칠기", "장신구", "매듭", "유리 공예", "유리공예")),
    "음악·공연": ("미술·예술", ("음악", "악기", "국악", "인형극", "공연예술", "소리")),
    "천문·우주": ("과학·기술", ("천문", "우주", "별자리", "천체", "망원경")),
    "과학기술사": ("과학·기술", ("과학기술", "과학사", "발명", "측량", "고지도", "지적")),
    "통신·미디어": ("과학·기술", ("통신", "전화기", "방송", "신문", "라디오", "우편")),
    "화석·지질": ("자연·생태", ("화석", "지질", "공룡", "암석", "광물", "지오")),
    "곤충·생물": ("자연·생태", ("곤충", "나비", "동물", "생물", "식물", "표본", "자연사", "조가비", "패류")),
    "생태·환경": ("자연·생태", ("생태", "습지", "갯벌", "환경")),
    "작가·문학": ("문학", ("문학", "시인", "소설가", "문인", "시집", "소설")),
    "민속·전통생활": ("생활문화·민속", ("민속", "전통생활", "생활사", "생활유물", "생활 유물", "세시풍속", "전통 부엌")),
    "음식·차": ("생활문화·민속", ("음식", "김치", "떡", "커피", "차 문화", "다도", "전통주", "양조", "인삼", "약초", "한방", "초콜릿")),
    "복식·화장": ("생활문화·민속", ("복식", "의상", "한복", "화장품", "화장 문화", "색동", "장신구")),
    "교육사": ("생활문화·민속", ("교육사", "교과서", "옛 학교", "교육박물관")),
    "책·인쇄": ("생활문화·민속", ("인쇄", "출판", "활자", "고서", "한지", "종이", "잡지")),
    "6·25전쟁": ("전쟁·평화", ("6·25", "6.25", "한국전쟁", "625전쟁")),
    "전쟁사·호국": ("전쟁·평화", ("전쟁사", "전투", "호국", "전적지", "격전지", "전쟁기념")),
    "평화·인권": ("전쟁·평화", ("평화", "인권", "위안부", "강제동원", "4·3")),
    "산업사": ("산업·직업", ("산업", "탄광", "광산", "공업", "섬유", "염색")),
    "교통": ("산업·직업", ("철도", "항공기", "항공", "자동차", "기차", "선박", "등대", "항로표지")),
    "농업·어업": ("산업·직업", ("농업", "농경", "농사", "농요", "어업", "해녀", "잠사", "양잠")),
    "금융·경제": ("산업·직업", ("화폐", "금융", "은행", "조세", "세금", "관세")),
    "사진": ("사진·영상", ("사진",)),
    "영상·카메라": ("사진·영상", ("카메라", "영화", "영상예술")),
    "불교": ("종교", ("불교", "사찰", "불화", "불상", "성보", "사리")),
    "기독교·천주교": ("종교", ("기독교", "천주교", "성서", "선교사", "교회")),
}

ACTIVITY_TYPES: dict[str, tuple[str, ...]] = {
    "체험": ("체험",),
    "교육": ("교육 프로그램", "교육프로그램", "강좌", "아카데미", "교육을 운영", "교육 운영", "학습 프로그램", "교육과정"),
    "공연": ("공연",),
    "해설": ("해설", "도슨트"),
}

# facility_type -> Theme it implies on its own.
FACILITY_THEME = {"미술관": "미술·예술", "문학관": "문학", "과학관": "과학·기술", "역사관": "역사"}


@dataclass(frozen=True)
class TopicMatch:
    topic: str
    theme: str
    hit_count: int
    name_hit: bool
    terms: tuple[str, ...]
    span_ids: tuple[str, ...]

    @property
    def confidence(self) -> str:
        if self.name_hit:
            return "high"
        return "medium" if self.hit_count >= 3 else "low"


MIN_TEXT_HITS = 2


def match_topics(museum_name: str, spans: list[tuple[str, str]]) -> list[TopicMatch]:
    """spans: [(span_id, text)]. Keep a topic on a name hit or >= MIN_TEXT_HITS hits."""
    results: list[TopicMatch] = []
    for topic, (theme, keywords) in TOPICS.items():
        name_hit = any(keyword in museum_name for keyword in keywords)
        hits = 0
        terms: list[str] = []
        span_ids: list[str] = []
        for span_id, text in spans:
            span_hits = 0
            for keyword in keywords:
                count = text.count(keyword)
                if count:
                    span_hits += count
                    if keyword not in terms:
                        terms.append(keyword)
            if span_hits:
                hits += span_hits
                span_ids.append(span_id)
        if name_hit or hits >= MIN_TEXT_HITS:
            results.append(TopicMatch(topic, theme, hits, name_hit, tuple(terms), tuple(span_ids[:5])))
    return results


def match_activity_types(spans: list[tuple[str, str]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for activity, keywords in ACTIVITY_TYPES.items():
        span_ids = [span_id for span_id, text in spans if any(k in text for k in keywords)]
        if span_ids:
            found[activity] = span_ids[:5]
    return found


# ---------------------------------------------------------------------------
# Opening rule (Museum properties parsed from closure_rule_raw)
# ---------------------------------------------------------------------------

WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
_WEEKDAY_RE = re.compile(r"(?<![0-9가-힣.])(월|화|수|목|금|토|일)(?:요일)?(?![가-힣0-9])")


def parse_closure(raw: str | None) -> dict:
    text = clean_space(raw)
    result = {
        "closure_weekdays": [],
        "open_all_year": False,
        "closed_new_year": False,
        "closed_seollal": False,
        "closed_chuseok": False,
        "closed_public_holidays": False,
        "holiday_closure_exception": False,
        "closure_parse_status": "empty",
    }
    if not text:
        return result
    result["closure_parse_status"] = "parsed"
    if re.search(r"연중\s*무휴", text):
        result["open_all_year"] = True
        return result
    if re.search(r"\([^)]*공휴일[^)]*\)|공휴일인 월요일|공휴일이면", text):
        result["holiday_closure_exception"] = True
    body = re.sub(r"\([^)]*\)", " ", text)
    body = re.sub(r"매주\s*", " ", body)
    body = re.sub(r"휴관", " ", body)
    body = body.replace("주말", " 토 일 ")
    weekdays = [day for day in WEEKDAYS if day in set(_WEEKDAY_RE.findall(body))]
    if re.search(r"째\s*주|째주", body):
        result["closure_parse_status"] = "partial"
        weekdays = []
    result["closure_weekdays"] = weekdays
    result["closed_new_year"] = bool(re.search(r"1월\s*1일|1\.1(?!\d)|신정", text))
    result["closed_seollal"] = bool(re.search(r"(?<!시)설(?!치)", body))
    result["closed_chuseok"] = "추석" in text
    result["closed_public_holidays"] = bool(
        re.search(r"(법정|국정)?\s*공휴일(?!\s*(익일|다음날))", body)
    )
    if not weekdays and not any(
        result[key] for key in ("closed_new_year", "closed_seollal", "closed_chuseok", "closed_public_holidays")
    ):
        result["closure_parse_status"] = "unparsed"
    return result
