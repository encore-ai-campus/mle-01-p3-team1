import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

for name in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break
plt.rcParams["axes.unicode_minus"] = False

INK, EDGE, ACCENT = "#172033", "#4a5468", "#c2410c"
STYLE = {
    "main": ("#eef4ff", "#25324a", 1.6),
    "search": ("#f4f7fb", "#526581", 1.2),
    "new": ("#fdece2", "#c2410c", 2.0),
    "data": ("#e8f5ee", "#31724c", 1.3),
    "rerank": ("#fff2d8", "#a66a00", 1.4),
}
fig, ax = plt.subplots(figsize=(11.5, 15.2), dpi=170)
ax.set_xlim(0, 100); ax.set_ylim(0, 124); ax.axis("off")


def box(cx, cy, w, h, text, kind="search", size=9.2, bold=False):
    fill, line_c, lw = STYLE[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0.2,rounding_size=1.1",
                                fc=fill, ec=line_c, lw=lw, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size, color=INK, zorder=4,
            fontweight="bold" if bold else "normal", linespacing=1.35)


def arrow(p, q, color=EDGE, ls="-", style="-|>", lw=1.3):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=11, color=color, lw=lw, ls=ls, zorder=2,
                                 shrinkA=0, shrinkB=0))


def line(points, color=EDGE, lw=1.3, ls="-"):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, ls=ls, zorder=2, solid_capstyle="butt")
    arrow(points[-2], points[-1], color=color, ls=ls, lw=lw)


def label(x, y, text, color=EDGE, size=8, ha="center", bold=False):
    ax.text(x, y, text, ha=ha, va="center", fontsize=size, color=color, zorder=5, fontweight="bold" if bold else "normal",
            linespacing=1.3, bbox=dict(fc="white", ec="none", pad=1.2))


ax.text(1, 121.5, "벡터·그래프 하이브리드 설계안: 관계 + 설명 질문", fontsize=13, fontweight="bold", color=INK)
ax.text(99, 121.5, "주황색 = 새로 추가", ha="right", fontsize=9, color=ACCENT, fontweight="bold")

# entry row
box(12, 112, 18, 6.5, "사용자 질문\nSupervisor CLI", "main")
box(40, 112, 20, 6.5, "입력 가드레일", "main")
box(74, 112, 30, 6.5, "Supervisor 경로 판단", "main", bold=True)
arrow((21, 112), (30, 112)); arrow((50, 112), (59, 112))

# route cards
box(17, 96, 27, 11.5, "① 문서 검색 단독\n설명형 · 조건형 질문\n지금과 같음\n근거 부족이면 1회 재시도", "search", 8.8)
box(50, 96, 27, 11.5, "② 그래프 단독\n같은 기관 등 관계 질문\n지금과 같음\n근거 부족이면 1회 재시도", "search", 8.8)
box(83, 96, 27, 11.5, "③ 하이브리드 (신규)\n관계 + 설명이 함께 필요\n예) 같은 기관이 운영하는\n시설 중 전시를 볼 수 있는 곳", "new", 8.6)
line([(74, 108.7), (74, 104), (17, 104), (17, 101.9)])
line([(74, 104), (50, 104), (50, 101.9)])
line([(74, 104), (83, 104), (83, 101.9)], color=ACCENT)
label(31, 105.6, "조건 · 설명", EDGE, 8)
label(62, 105.6, "관계 구조", EDGE, 8)
label(88, 105.6, "둘 다 필요", ACCENT, 8, bold=True)

# combined frame
ax.add_patch(Rectangle((4, 27), 92, 62, fc="#fffaf6", ec=ACCENT, lw=1.6, ls=(0, (5, 3)), zorder=1))
ax.text(6, 86.8, "③ 하이브리드: 그래프가 후보 시설을 정하고, 문서 검색이 그 안에서 설명을 찾음", fontsize=10.2,
        fontweight="bold", color=ACCENT, va="center", zorder=4)
line([(83, 90.2), (83, 83.8), (40, 83.8), (40, 78.2)], color=ACCENT)
label(54, 83.8, "먼저 실행", ACCENT, 8.4, bold=True)

# step 1: graph (left)
ax.text(7, 81.0, "1단계  그래프 (지금의 Graph)", fontsize=9.5, fontweight="bold", color=INK, va="center", zorder=4)
box(24, 74.5, 38, 7.4, "준비된 쿼리 / Text-to-Cypher\n같은 기관 · 관계 · 출처 조회", "search", 8.8)
box(24, 62, 38, 6.4, "Neo4j Aura  (기존 그래프 + v2)", "data", 8.8)
arrow((24, 70.8), (24, 65.2), style="<|-|>")
arrow((24, 58.8), (24, 53.6))
label(24, 50.6, "관계 근거 (점수 없음)\n+ 후보 시설 ID  (기준 시설 제외)", EDGE, 8.4)

# step 2: document search (right)
ax.text(52, 81.0, "2단계  문서 검색 (그래프가 찾은 시설 안에서만)", fontsize=9.5, fontweight="bold", color=INK, va="center", zorder=4)
box(73, 75.5, 38, 6.6, "0. 후보 필터  지역 · 편의시설 · 개관 요일\nNeo4j 우선, 실패 시 로컬 · 그래프 후보와 교집합", "new", 8.2)
box(73, 66, 38, 5.4, "1. Vector + BM25", "search", 8.8)
box(73, 58, 38, 5.4, "2. 가중 RRF 결합", "search", 8.8)
box(73, 50, 38, 5.4, "3. 이름 보장 · Cross-Encoder 재정렬", "rerank", 8.8)
arrow((73, 72.2), (73, 68.8)); arrow((73, 63.3), (73, 60.8)); arrow((73, 55.3), (73, 52.8))
arrow((73, 47.2), (73, 45.6))
label(73, 43.4, "본문 근거 (재정렬 순위 있음)", EDGE, 8.4)

# graph ids -> document search
line([(43, 62), (48, 62), (48, 75.5), (53.8, 75.5)], color=ACCENT)
label(48, 69, "후보\n시설 ID", ACCENT, 8, bold=True)

# merge
box(50, 32.5, 84, 8.2, "근거 통합   점수를 섞지 않고 출처 표시를 붙여 나란히 이음\n문서 계열 근거 먼저, 그래프 계열 근거 뒤  ·  같은 시설의 같은 본문은 중복 제거  ·  한쪽이 실패하면 다른 쪽만 사용", "new", 8.6)
line([(24, 47.0), (24, 38.2), (30, 38.2), (30, 36.9)], color=ACCENT)
line([(73, 41.0), (73, 38.2), (66, 38.2), (66, 36.9)], color=ACCENT)

# bottom row
arrow((22, 28.4), (22, 22.2), color=ACCENT)
box(22, 19, 24, 6.2, "Answer Agent", "main")
box(50, 19, 24, 6.2, "Verifier Agent", "main", bold=True)
box(78, 19, 24, 6.2, "출력 가드레일", "main")
arrow((34, 19), (38, 19)); arrow((62, 19), (66, 19))
box(78, 7, 36, 6.2, "출처가 표시된 답변 또는 보류", "main")
arrow((78, 15.9), (78, 10.1))
label(36, 10.6, "검증 실패 시 ③은 재시도 없이 보류\n(문서 검색만 다시 하면 그래프 관계를 잃음)\n① ②는 Supervisor로 돌아가 1회 재시도", EDGE, 8.0)
ax.text(1, 2.5, "Answer가 [E1] [E2]로 인용할 때 근거마다 '문서 계열' 또는 '그래프 계열' 표시가 붙습니다.", fontsize=8.2, color=EDGE)

fig.savefig(sys.argv[1], bbox_inches="tight", facecolor="white")
print("saved", sys.argv[1])
