"""Draw supervisor-hybrid-flow-clarified.png (matplotlib only, no external tools).

Run from the repository root:
    python docs/architecture/images/draw_supervisor_flow.py docs/architecture/images/supervisor-hybrid-flow-clarified.png

The structure is the same as ../supervisor-hybrid-flow-clarified.mmd (Mermaid source). The PNG is NOT rendered
from the .mmd file, so when the flow changes, update both.
"""
import sys
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch

for name in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break
plt.rcParams["axes.unicode_minus"] = False

STYLE = {
    "main": ("#eef4ff", "#25324a", 1.8),
    "search": ("#f4f7fb", "#526581", 1.3),
    "new": ("#fdece2", "#c2410c", 1.8),
    "rerank": ("#fff2d8", "#a66a00", 1.8),
    "data": ("#e8f5ee", "#31724c", 1.3),
}
INK, EDGE, ACCENT = "#172033", "#4a5468", "#c2410c"

fig, ax = plt.subplots(figsize=(11.5, 15.5), dpi=170)
ax.set_xlim(-2, 104)
ax.set_ylim(-19, 132)
ax.axis("off")


def box(cx, cy, w, h, text, kind="search", size=9.5, bold=False):
    fill, line, lw = STYLE[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0.25,rounding_size=1.2",
                                fc=fill, ec=line, lw=lw, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size, color=INK, zorder=4,
            fontweight="bold" if bold else "normal", linespacing=1.35)
    return (cx, cy, w, h)


def arrow(p, q, color=EDGE, style="-|>", ls="-", rad=0.0, lw=1.3):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=11, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", zorder=2, shrinkA=0, shrinkB=0))


def polyline(points, color=EDGE, ls="-", lw=1.3):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, ls=ls, lw=lw, zorder=2, solid_capstyle="butt")
    arrow(points[-2], points[-1], color=color, ls=ls, lw=lw)


def label(x, y, text, color=EDGE, size=8, ha="center", rotation=0, bold=False):
    ax.text(x, y, text, ha=ha, va="center", fontsize=size, color=color, rotation=rotation, zorder=5,
            fontweight="bold" if bold else "normal", linespacing=1.3,
            bbox=dict(fc="white", ec="none", pad=1.2))


# ---------------------------------------------------------------- entry
box(50, 125, 30, 6, "사용자 질문\nSupervisor CLI", "main")
box(50, 114, 40, 6, "입력 가드레일 (실패 시 1회 재시도)", "main")
box(90, 114, 18, 6, "차단 안내", "main")
arrow((50, 122), (50, 117))
arrow((70, 114), (81, 114))
label(75.5, 116.5, "차단")
box(50, 103, 40, 7, "Supervisor 경로 선택", "main", bold=True)
arrow((50, 111), (50, 106.5))
label(53, 109, "허용")

# ---------------------------------------------------------------- hybrid frame
ax.add_patch(Rectangle((14, 37), 56, 59, fc="#f8f9fc", ec="#8892a6", lw=1.4, zorder=1))
ax.text(16, 93.2, "Hybrid 검색 Agent", fontsize=10.5, fontweight="bold", color=INK, va="center", zorder=4)

box(30, 86, 27, 8, "0. 온톨로지 후보 필터\n편의시설 · 개관 요일 (+ 지역)", "new", 9)
box(58, 88, 20, 6.5, "로컬 조회표 (기본)\nrules.py · CSV", "new", 8.2)
box(58, 79, 20, 6.5, "Neo4j v2\n같은 규칙 · 선택", "data", 8.2)
arrow((48, 88), (43.5, 87.2), color=ACCENT)
arrow((48, 80), (43, 83), color=ACCENT, ls=(0, (3, 3)))

box(28, 69, 24, 6, "Chroma Vector 검색", "search")
box(58, 69, 20, 6, "BM25 키워드 검색", "search")
arrow((27, 82), (28, 72.2), color=ACCENT)
arrow((35, 82), (55, 72.2), color=ACCENT)
label(24.5, 77.5, "후보 ID", ACCENT, 8, bold=True)
label(47, 77.5, "후보 ID", ACCENT, 8, bold=True)

box(42, 60.5, 34, 6, "가중 RRF · 후보 결합", "search")
arrow((30, 66), (36, 63.8))
arrow((56, 66), (50, 63.8))
box(42, 52, 44, 6.5, "이름 보장\n질문에 적힌 시설명을 후보에 포함", "new", 8.8)
arrow((42, 57.5), (42, 55.6))
box(42, 43.5, 44, 6.5, "Cross-Encoder 재정렬\n확신이 낮으면 RRF 순서 유지", "rerank", 8.8)
arrow((42, 48.6), (42, 47.2))

# routes out of the supervisor
polyline([(50, 99.5), (50, 98), (40, 98), (34, 98), (32, 90.2)], color=ACCENT)
label(52, 97.4, "① 편의시설 · 개관 요일 조건", ACCENT, 8, ha="left", bold=True)
polyline([(30, 100.5), (9, 100.5), (9, 69), (16, 69)])
label(9, 85, "② 단순 지역+주제\n③ 설명형 질문(LLM)", EDGE, 7.6, rotation=90)

# ---------------------------------------------------------------- graph branch
box(86, 88, 26, 8, "Neo4j Graph 검색\n준비된 쿼리 · Text-to-Cypher", "search", 8.8)
polyline([(70, 105), (86, 105), (86, 92)])
label(88, 98.6, "④ 준비된 쿼리\n· 관계 · 출처\n(Graph 연결 시)", EDGE, 7.6, ha="left")
box(86, 72, 26, 7, "Neo4j Aura\n기존 그래프 + v2", "data", 8.8)
arrow((86, 84), (86, 75.6), style="<|-|>")

# ---------------------------------------------------------------- evidence / answer / verify
box(47, 30, 36, 6, "CSV 출처 · 속성 근거 연결", "search")
arrow((42, 40.2), (42, 33.2))
box(15, 30, 14, 6.5, "museum_final\n_738.csv", "data", 8)
arrow((22, 30), (29, 30))
box(50, 21, 36, 6, "답변 생성", "main")
arrow((46, 27), (48, 24.2))
polyline([(99, 88), (101, 88), (101, 21), (68, 21)])

box(50, 11.5, 40, 7, "근거 · 답변 검증", "main", bold=True)
arrow((50, 17.8), (50, 15.2))
box(22, 0, 24, 6.5, "답변과 출처", "main")
box(80, 0, 30, 7.5, "답변 보류\n없는 조건을 안내", "search", 8.8)
arrow((38, 8.2), (24, 3.4))
label(29.5, 6.6, "통과")
arrow((62, 8.2), (76, 3.9))
label(88, 9.4, "재시도 소진 또는\n조건을 만족하는 기록 0건", EDGE, 7.6)

# retry loop back to the supervisor
polyline([(30, 11.5), (3, 11.5), (3, 106), (30, 106)])
label(3, 58, "근거 부족 → 재시도 1회 (직전이 Graph면 Hybrid로)", EDGE, 7.8, rotation=90)

box(50, -10, 36, 6, "출력 가드레일", "main")
polyline([(22, -3.6), (22, -10), (32, -10)])
polyline([(80, -4), (80, -10), (68, -10)])
ax.text(50, -16.6, "출력 가드레일을 통과하면 최종 결과를 반환하고, 차단되면 안내 문구를 반환합니다.",
        ha="center", fontsize=8.2, color=EDGE)

ax.text(-1, 129.5, "Supervisor · Hybrid · 선택 Neo4j 흐름 (2026-11-14 기준)", fontsize=12, fontweight="bold", color=INK)
ax.text(104, 129.5, "주황색 = 이번에 추가된 부분", ha="right", fontsize=8.5, color=ACCENT, fontweight="bold")

fig.savefig(sys.argv[1], bbox_inches="tight", facecolor="white")
print("saved", sys.argv[1])
