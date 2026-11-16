"""Render the shared-evidence flow with a plain-language note beside every node.

Run from the repository root:
    python docs/architecture/images/draw_evidence_context_flow_explained.py
"""
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.family"] = "Malgun Gothic"

BLUE, BLUE_EDGE = "#edf3fb", "#35516f"
ORANGE, ORANGE_EDGE = "#fff1d6", "#b07820"
GREEN, GREEN_EDGE = "#e8f3ed", "#3f7758"
GRAY = "#f4f4f4"
WRAP = 44
LINE = 2.05      # vertical units per text line
PAD = 1.6

# (badge, title, note, kind)
ROWS = [
    ("1", "사용자 질문\n→ 입력 가드레일",
     "질문이 안전한지 먼저 검사합니다. 허용되면 다음 단계로 가고, 차단되면 안내 문구만 돌려주고 끝납니다.", "blue"),
    ("2", "Supervisor\n경로 선택",
     "질문을 보고 어떤 검색 방법을 쓸지 정합니다. 확인 순서: 사용자 지정 → 단순 지역+주제 → 편의시설·요일 조건(후보 필터) → 준비된 그래프 질의 → LLM 판단.", "blue"),
    ("3-A", "Hybrid",
     "문서에서 의미 검색(Vector)과 키워드 검색(BM25)을 함께 하고, 두 순위를 RRF로 합친 뒤 Cross-Encoder로 다시 정렬합니다. 전시·유물·설명 질문에 씁니다.", "blue"),
    ("3-B", "Vector\n(연결된 경우만)",
     "의미 검색만 사용하는 경로입니다. 연결해 둔 경우에만 쓸 수 있습니다.", "blue"),
    ("3-C", "Graph",
     "Neo4j에서 관계와 속성을 조회합니다. 준비된 질의를 쓰고, 맞는 게 없으면 LLM이 질의문을 만듭니다(Text-to-Cypher). \"같은 기관이 운영하는 시설\" 같은 질문에 씁니다.", "blue"),
    ("3-D", "Combined\n(합친 경로)",
     "관계와 설명이 둘 다 필요한 질문용입니다. ① Graph로 후보 시설 ID를 먼저 찾고 ② 그 시설들 안에서만 문서를 검색하고 ③ 문서 근거와 관계 근거를 점수를 섞지 않고 이어 붙입니다. 관계를 입증하는 근거가 없으면 검증에서 보류됩니다.", "blue"),
    ("4", "최종 근거 정규화\n· 출처 연결",
     "검색 결과를 CSV의 해당 시설 행과 맞춰 보고, 일치하면 주소·요금·휴관일·편의시설 같은 속성을 출처와 함께 붙입니다. Graph 결과는 출처·속성·기준 시설(앵커)을 그대로 보존합니다.", "blue"),
    ("5", "공통 evidence_context()\ngrounded-evidence-v2",
     "★ 핵심 단계. 근거 1건을 같은 모양의 JSON 한 덩어리로 통일합니다. 담는 것: 시설 ID, 이름, 전체 본문, 인용 번호(E1), 출처, 출처가 연결된 CSV 속성. 답변 생성·검증·평가 심판이 모두 이 같은 근거를 보므로 \"답은 맞는데 심판이 근거를 못 봐서 점수가 낮은\" 문제가 줄어듭니다. 검색 점수와 원시 후보는 사실 근거에서 뺍니다.", "orange"),
    ("5+", "주의 사항",
     "출처가 연결됐다는 것은 데이터에 그렇게 기록돼 있다는 뜻이지, 사람이 검수했거나 최신 정보라는 보증이 아닙니다. Streamlit 화면은 아직 이 흐름을 쓰지 않습니다(별도 경로).", "orange"),
    ("6", "답변 생성",
     "공통 근거만 사용해 답을 씁니다. 사실을 말하는 문장마다 [E1] 같은 근거 번호를 달고, 실제로 쓴 번호 목록도 함께 냅니다.", "blue"),
    ("7", "동일 근거로\n답변·출처 검증",
     "답변 내용이 근거와 맞는지, 인용한 번호가 실제 근거에 있는지 검사합니다. 답변을 만들 때 쓴 것과 같은 근거로 검사합니다.", "blue"),
    ("8", "Supervisor 검토",
     "통과 → 출력 가드레일로. 실패했고 재시도 가능 → 경로 선택으로 돌아가 다른 방법으로 1회 다시 찾기(왼쪽 화살표). 재시도할 수 없거나 combined 검증 실패 → 답변 보류.", "blue"),
    ("9", "답변 보류",
     "\"확인 가능한 근거가 부족하여 답변을 보류했습니다\"와 함께 확인하지 못한 내용을 이유로 알려 줍니다.", "blue"),
    ("10", "출력 가드레일\n→ 최종 응답",
     "응답이 안전한지 마지막으로 검사한 뒤 사용자에게 전달합니다.", "blue"),
]
COLORS = {"blue": (BLUE, BLUE_EDGE), "orange": (ORANGE, ORANGE_EDGE), "green": (GREEN, GREEN_EDGE)}

wrapped = [textwrap.wrap(note, WRAP) for _, _, note, _ in ROWS]
heights = [max(len(lines) * LINE, (title.count("\n") + 1) * LINE * 1.2) + PAD * 2
           for lines, (_, title, _, _) in zip(wrapped, ROWS)]
GAP = 2.4
TOP = 7.5
total = TOP + sum(heights) + GAP * (len(ROWS) - 1) + 3

fig, ax = plt.subplots(figsize=(14, total * 0.19), dpi=150)
ax.set(xlim=(-5, 100), ylim=(total, 0))
ax.axis("off")
ax.text(50, 2.0, "Supervisor · 동일 근거 기반 답변과 평가 (노드별 설명)", ha="center", va="center",
        fontsize=19, weight="bold")
ax.text(50, 4.6, "왼쪽: 흐름의 각 단계  |  오른쪽: 그 단계가 하는 일  |  주황색 = 공통 근거 단계",
        ha="center", va="center", fontsize=10, color="#43566b")

LEFT_X, LEFT_W, NOTE_X, NOTE_W = 4, 27, 36.5, 59.5
y = TOP
centers = []
for (badge, title, _, kind), lines, h in zip(ROWS, wrapped, heights):
    face, edge = COLORS[kind]
    ax.add_patch(FancyBboxPatch((LEFT_X, y), LEFT_W, h, boxstyle="round,pad=0.2,rounding_size=0.9",
                                facecolor=face, edgecolor=edge, linewidth=1.5))
    ax.text(LEFT_X + 2.2, y + h / 2, badge, ha="center", va="center", fontsize=9, color="white", weight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=edge, edgecolor="none"))
    ax.text(LEFT_X + 5.2, y + h / 2, title, ha="left", va="center", fontsize=11, weight="bold", linespacing=1.4)
    ax.add_patch(FancyBboxPatch((NOTE_X, y), NOTE_W, h, boxstyle="round,pad=0.2,rounding_size=0.9",
                                facecolor="white", edgecolor=edge, linewidth=1.0, linestyle=(0, (4, 2))))
    ax.text(NOTE_X + 1.6, y + h / 2, "\n".join(lines), ha="left", va="center", fontsize=10.5, linespacing=1.55)
    centers.append((y, h))
    y += h + GAP

def arrow(x1, y1, x2, y2, style="-", rad=0.0, color=BLUE_EDGE):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, color=color,
                                 linewidth=1.4, linestyle=style, connectionstyle=f"arc3,rad={rad}"))

mid = LEFT_X + LEFT_W / 2
idx = {r[0]: i for i, r in enumerate(ROWS)}
bottom = lambda k: centers[idx[k]][0] + centers[idx[k]][1]
top = lambda k: centers[idx[k]][0]
for a, b in [("1", "2"), ("2", "3-A"), ("3-D", "4"), ("4", "5"), ("6", "7"), ("7", "8"), ("8", "9"), ("9", "10")]:
    arrow(mid, bottom(a), mid, top(b))
arrow(mid, bottom("5"), mid, top("5+"), color=ORANGE_EDGE)
arrow(mid + 9, bottom("5+"), mid + 9, top("6"), color=ORANGE_EDGE)
# 3-A..3-D are alternatives: a bar marks them as "pick one"
bar_x = LEFT_X - 1.6
ax.plot([bar_x, bar_x], [top("3-A"), bottom("3-D")], color="#35516f", linewidth=3)
ax.text(bar_x - 0.6, (top("3-A") + bottom("3-D")) / 2, "질문마다 이 중 하나를 선택", rotation=90, ha="center",
        va="center", fontsize=9.5, color="#35516f", weight="bold")
# retry loop: review (8) -> route selection (2), kept inside the canvas
x_loop = LEFT_X - 3.6
y8 = centers[idx["8"]][0] + centers[idx["8"]][1] / 2
y2 = centers[idx["2"]][0] + centers[idx["2"]][1] / 2
ax.plot([LEFT_X, x_loop, x_loop], [y8, y8, y2], color="#a33", linewidth=1.4, linestyle="--")
arrow(x_loop, y2, LEFT_X, y2, style="--", color="#a33")
ax.text(x_loop - 0.8, (y8 + y2) / 2, "재시도 (1회)", rotation=90, ha="center", va="center", fontsize=9.5, color="#a33")
# pass path: review (8) -> output guardrail (10), skipping the abstain box
x_pass = LEFT_X + LEFT_W + 1.4
y10 = centers[idx["10"]][0] + centers[idx["10"]][1] / 2
ax.plot([LEFT_X + LEFT_W, x_pass, x_pass], [y8, y8, y10], color="#2b7a4b", linewidth=1.4)
arrow(x_pass, y10, LEFT_X + LEFT_W, y10, color="#2b7a4b")
ax.text(x_pass + 0.5, (y8 + y10) / 2, "통과", rotation=90, ha="left", va="center", fontsize=9.5, color="#2b7a4b")
ax.text(mid + 3, bottom("8") + GAP / 2 + 0.1, "실패 → 보류", fontsize=8.5, color="#555", ha="left", va="center")

ax.text(50, total - 1.2, "참고: 점수·근거 번호 확인 위치는 docs/evaluation/hybrid-ragas.md 와 src/agent/supervisor/evidence_context.py",
        ha="center", va="center", fontsize=9, color="#667")
out = Path(__file__).with_name("evidence-context-flow-explained.png")
fig.savefig(out, bbox_inches="tight", facecolor="white")
print(out)
