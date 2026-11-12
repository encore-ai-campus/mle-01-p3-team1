"""박물관 안내 서비스 Streamlit UI.

실행 (프로젝트 루트에서):
    uv run streamlit run src/service/app.py
"""
from dotenv import load_dotenv
import streamlit as st

from ui.data import PROJECT_ROOT, load_museums

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(page_title="Museum Navi", page_icon="🏛️", layout="wide")

from ui import chatbot, dashboard, graph_rag, map_view  # noqa: E402
from ui import style as S  # noqa: E402

S.inject_css()
S.topbar("MUSEUM ", "NAVI")

df = load_museums()
tab_dash, tab_chat, tab_map, tab_graph = st.tabs(["Dashboard", "Chatbot", "Map", "GraphRAG"])

with tab_dash:
    dashboard.render(df)
with tab_chat:
    chatbot.render(df)
with tab_map:
    map_view.render(df)
with tab_graph:
    graph_rag.render()
