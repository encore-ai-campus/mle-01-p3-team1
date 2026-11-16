"""Render the code-native shared evidence flow; run from repository root."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams['font.family'] = 'Malgun Gothic'
fig, ax = plt.subplots(figsize=(13, 12), dpi=150)
ax.set(xlim=(0, 100), ylim=(0, 100))
ax.axis('off')

def box(x, y, w, h, text, color='#edf3fb'):
    ax.add_patch(FancyBboxPatch((x-w/2, y-h/2), w, h,
        boxstyle='round,pad=0.4,rounding_size=1.1', facecolor=color,
        edgecolor='#35516f', linewidth=1.3))
    ax.text(x, y, text, ha='center', va='center', fontsize=10, linespacing=1.5)

def arrow(x, y, u, v, dashed=False):
    ax.add_patch(FancyArrowPatch((x,y),(u,v),arrowstyle='-|>',mutation_scale=14,
        color='#35516f', linewidth=1.4, linestyle='--' if dashed else '-'))

ax.text(50, 98, 'Supervisor · 동일 근거 기반 답변과 평가', ha='center', fontsize=19, weight='bold')
ax.text(50, 94.5, '2026-11-16  |  grounded-evidence-v2  |  Streamlit은 별도 경로', ha='center', fontsize=10)
box(50, 88, 58, 7, '사용자 질문 → 입력 가드레일 → Supervisor 경로 선택')
box(18, 75, 29, 12, 'Hybrid / Vector\n문서 검색 · Hybrid는 BM25 결합\nRRF → Cross-Encoder')
box(50, 75, 27, 12, 'Graph\nNeo4j 관계·속성 조회\n준비된 쿼리 / Text-to-Cypher')
box(82, 75, 29, 12, 'Combined\nGraph 후보 → 제한된 문서 검색\n문서·관계 근거 통합')
for x in (18,50,82):
    arrow(50,84,x,81.5)
    arrow(x,68.5,50,63.5)
box(50, 59, 86, 8, '최종 근거 정규화 · 출처 연결\nCSV 행 매칭 / Graph 출처 · 속성 · 앵커 보존', '#e8f3ed')
arrow(50,54.5,50,51)
box(50, 45, 86, 11, '공통 evidence_context() → 동일 JSON 근거\n시설 ID·이름·전체 본문·인용 ID·출처·출처가 연결된 속성\n원시 후보·검색 점수 제외 / 원문 자동 매칭 ≠ 사람 검수', '#fff1d6')
arrow(30,39,26,34)
arrow(70,39,75,27,True)
box(26, 29, 41, 9, '답변 생성 → 같은 근거로 검증\n통과 / 재검색 / 보류', '#edf3fb')
arrow(26,24,26,20)
box(26, 16, 41, 7, '출력 가드레일 → 사용자 응답')
box(75, 22, 41, 12, '별도 RAGAS 평가\n동일 근거 + 최종 응답\n질문 + 평가셋 reference', '#e8f3ed')
arrow(47,16,54,20,True)
arrow(75,15.5,75,11)
box(75, 7, 41, 7, '새 실행 폴더에 점수·근거·버전 저장\n이전 형식 체크포인트 이어하기 차단')
ax.text(26, 7, '재검색 시 최종 근거로 다시 평가\nRAGAS는 챗봇 응답 시 실행하지 않음', ha='center', fontsize=9, color='#43566b')
destination = Path(__file__).with_name('evidence-context-flow.png')
fig.savefig(destination, bbox_inches='tight', facecolor='white')
print(destination)
