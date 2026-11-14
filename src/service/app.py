"""박물관 안내 서비스 Streamlit UI.

실행 (프로젝트 루트에서):
    uv run streamlit run src/service/app.py
"""
import truststore

# Python 기본 인증서 목록(/etc/ssl/cert.pem)에 Neo4j Aura 인증서 발급 기관(SSL.com 2022)이 없어
# 접속이 거부된다 → 운영체제 인증서 목록(macOS 키체인 / Windows 저장소)을 쓰게 한다.
truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402
import streamlit as st  # noqa: E402

from ui.data import PROJECT_ROOT, load_museums  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(  # 탭 아이콘 = 로고의 박물관 심볼
    page_title="mupick", page_icon=str(PROJECT_ROOT / "src" / "service" / "static" / "favicon.png"), layout="wide"
)

from ui import chatbot, dashboard, map_view, nav, themes  # noqa: E402
from ui import style as S  # noqa: E402

S.inject_css()
S.topbar()

df = load_museums()
# 다른 탭의 "챗봇에게 물어보기" 버튼이 Chatbot 탭으로 바로 이동시킬 수 있게 만든 탭 (ui/nav.py)
tab_dash, tab_chat, tab_map, tab_theme = nav.tabs()

with tab_dash:
    dashboard.render(df)
with tab_chat:
    chatbot.render(df)
with tab_map:
    map_view.render(df)
with tab_theme:
    themes.render(df)
