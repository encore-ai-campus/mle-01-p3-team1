"""박물관 안내 서비스 Streamlit UI.

실행 (프로젝트 루트에서):
    uv run streamlit run src/service/app.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

# Streamlit adds this script's directory to sys.path. Add the repository root
# before importing shared `src.*` modules from the UI.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ui.data import PROJECT_ROOT, load_museums

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(page_title="Museum Navi", page_icon="🏛️", layout="wide")

from ui import chatbot, dashboard, map_view, themes  # noqa: E402
from ui import style as S  # noqa: E402

S.inject_css()
S.topbar("MUSEUM ", "NAVI")

df = load_museums()
tab_dash, tab_chat, tab_map, tab_theme = st.tabs(["Dashboard", "Chatbot", "Map", "Themes"])

with tab_dash:
    dashboard.render(df)
with tab_chat:
    chatbot.render(df)
with tab_map:
    map_view.render(df)
with tab_theme:
    themes.render(df)
