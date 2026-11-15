"""탭 이동 공용 함수.

탭을 상태 추적 위젯(key + on_change)으로 만들면 다시 그릴 때마다 화면이 맨 위로 올라간다.
그래서 평소에는 상태 없는 탭을 쓰고, 이동이 필요할 때만 key 를 바꿔 탭을 새로 만들면서
default 로 열 탭을 지정한다. (버튼의 on_click 콜백에서 호출)
"""
import streamlit as st

TABS = ["Dashboard", "Chatbot", "Map", "Themes"]
CHAT_TAB = "Chatbot"


def ask_chatbot(question: str) -> None:
    """질문을 챗봇에 넘기고 Chatbot 탭으로 이동 (버튼 on_click 콜백용)."""
    st.session_state["chat_prefill"] = question
    st.session_state["tab_default"] = CHAT_TAB
    st.session_state["tab_nonce"] = st.session_state.get("tab_nonce", 0) + 1


def tabs():
    """메인 탭. 평소엔 같은 key 라 사용자가 고른 탭이 유지되고, ask_chatbot 직후에만 새로 만들어진다."""
    return st.tabs(
        TABS,
        default=st.session_state.get("tab_default"),
        key=f"main_tab_{st.session_state.get('tab_nonce', 0)}",
    )
