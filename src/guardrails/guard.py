"""NeMo Guardrails 로 사용자 입력과 챗봇 답변을 검사한다.

사용법:
    from src.guardrails import get_guardrails

    guard = get_guardrails()
    verdict = guard.check_input(question)
    if not verdict.allowed:
        show(verdict.message)          # 차단 안내 문구
    ...
    verdict = guard.check_output(question, answer)

차단 대상(입력·출력 공통): 탈옥·프롬프트 인젝션, 개인정보, 욕설·혐오.
규칙은 config/config.yml(정규식)과 config/prompts.yml(LLM 자기검사)에 있다.

동작 원칙:
- OPENAI_API_KEY 가 없으면 정규식(개인정보) 검사만 한다. 이때 챗봇은 LLM 없이
  DB 검색 결과만 보여 주므로 탈옥·욕설로 유해한 답이 만들어질 경로가 없다.
- 검사 도중 오류(네트워크·API 장애 등)가 나면 통과시키지 않고 차단한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from collections.abc import Callable, Coroutine, Iterable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent / "config"
MODEL_ENV = "GUARDRAILS_MODEL"
CHECK_TIMEOUT_SEC = 30

MSG_PII = (
    "개인정보(전화번호·주민등록번호·카드번호·이메일 등)가 들어 있는 내용은 처리하지 않습니다. "
    "해당 부분을 빼고 다시 물어봐 주세요."
)
MSG_INPUT_BLOCKED = (
    "죄송하지만, 그 요청은 도와드릴 수 없습니다. "
    "박물관·전시·관람 정보에 대해 편하게 물어봐 주세요!"
)
MSG_OUTPUT_BLOCKED = (
    "답변에 부적절하거나 민감한 내용이 포함될 수 있어 보여 드리지 않았습니다. "
    "질문을 조금 바꿔서 다시 물어봐 주세요."
)
MSG_ERROR = "지금은 안전 검사를 할 수 없어 답변을 드리기 어려워요. 잠시 후 다시 시도해 주세요."


@dataclass(frozen=True)
class GuardResult:
    """검사 결과. 차단되면 ``message`` 를 사용자에게 그대로 보여 주면 된다."""

    allowed: bool
    message: str = ""
    rail: str | None = None  # 차단한 rail 이름(기록·디버깅용)


ALLOWED = GuardResult(allowed=True)


class _LoopThread:
    """모든 검사를 백그라운드 스레드의 이벤트 루프 하나에서 실행한다.

    NeMo 의 HTTP 클라이언트는 처음 사용한 이벤트 루프에 묶인다. 동기 ``check()`` 처럼
    호출마다 새 루프를 만들면 'Event loop is closed' 재시도가 반복되고, 재시도가 바닥나면
    정상 질문까지 오류로 차단된다. Streamlit 은 재실행마다 다른 스레드를 쓰므로 특히 문제다.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name="guardrails-loop", daemon=True).start()

    def run(self, coro: Coroutine[Any, Any, Any], timeout: float) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise


def _load_config():
    from nemoguardrails import RailsConfig

    config = RailsConfig.from_path(str(CONFIG_DIR))
    model = os.getenv(MODEL_ENV, "").strip()
    if model:
        for m in config.models:
            if m.type == "main":
                m.model = model
    return config


class Guardrails:
    """입력·출력 가드레일. ``rails`` 를 주입하면 테스트에서 실제 LLM 없이 쓸 수 있다."""

    def __init__(self, rails: Any | None = None, *, use_llm: bool | None = None):
        self._config = _load_config()
        self._use_llm = bool(os.getenv("OPENAI_API_KEY")) if use_llm is None else use_llm
        self._rails = rails
        self._loop: _LoopThread | None = None
        self._init_lock = threading.Lock()
        regex = self._config.rails.config.regex_detection
        self._input_patterns: list[re.Pattern[str]] = list(regex.input.compiled_patterns)
        self._output_patterns: list[re.Pattern[str]] = list(regex.output.compiled_patterns)

    @property
    def uses_llm(self) -> bool:
        return self._use_llm

    def _ensure_ready(self):
        with self._init_lock:
            if self._rails is None:
                from nemoguardrails import LLMRails

                self._rails = LLMRails(self._config)
            if self._loop is None:
                self._loop = _LoopThread()
        return self._rails, self._loop

    def _run(self, messages: list[dict], rail_type: str, blocked_message: str) -> GuardResult:
        from nemoguardrails.rails.llm.options import RailStatus, RailType

        try:
            rails, loop = self._ensure_ready()
            result = loop.run(
                rails.check_async(messages, rail_types=[RailType(rail_type)]),
                timeout=CHECK_TIMEOUT_SEC,
            )
        except Exception:
            log.exception("가드레일 %s 검사 실패 → 차단", rail_type)
            return GuardResult(allowed=False, message=MSG_ERROR, rail="error")

        if result.status == RailStatus.BLOCKED:
            rail = result.rail or ""
            log.info("가드레일 %s 차단: rail=%s", rail_type, rail)
            message = MSG_PII if rail.startswith("regex") else blocked_message
            return GuardResult(allowed=False, message=message, rail=rail)
        return ALLOWED

    @staticmethod
    def _regex_only(text: str, patterns: list[re.Pattern[str]], direction: str) -> GuardResult:
        if any(p.search(text) for p in patterns):
            return GuardResult(allowed=False, message=MSG_PII, rail=f"regex check {direction}")
        return ALLOWED

    def check_input(self, question: str) -> GuardResult:
        """사용자 질문 한 건을 검사한다."""
        if not question or not question.strip():
            return ALLOWED
        if not self._use_llm:
            return self._regex_only(question, self._input_patterns, "input")
        return self._run([{"role": "user", "content": question}], "input", MSG_INPUT_BLOCKED)

    def check_output(self, question: str, answer: str) -> GuardResult:
        """질문 맥락과 함께 챗봇 답변을 검사한다."""
        if not answer or not answer.strip():
            return ALLOWED
        if not self._use_llm:
            return self._regex_only(answer, self._output_patterns, "output")
        messages = [
            {"role": "user", "content": question or ""},
            {"role": "assistant", "content": answer},
        ]
        return self._run(messages, "output", MSG_OUTPUT_BLOCKED)

    def scan_output_pii(self, text: str) -> GuardResult:
        """답변 속 개인정보를 정규식으로만 검사한다(로컬, 즉시). 스트리밍 중 조각마다 쓴다."""
        return self._regex_only(text or "", self._output_patterns, "output")

    def stream_output(self, tokens: Iterable[str]) -> PiiSafeStream:
        """LLM 토큰을 흘려보내면서 개인정보가 화면에 나가기 전에 막는 스트림을 만든다."""
        return PiiSafeStream(tokens, self)

    def graph_hooks(self) -> dict[str, Callable[..., str | None]]:
        """``build_graph(**guard.graph_hooks())`` 로 LangGraph 에 연결한다.

        각 훅은 통과하면 None, 차단하면 사용자에게 보여 줄 안내 문구를 돌려준다.
        """

        def check_input(question: str) -> str | None:
            verdict = self.check_input(question)
            return None if verdict.allowed else verdict.message

        def check_output(question: str, answer: str) -> str | None:
            verdict = self.check_output(question, answer)
            return None if verdict.allowed else verdict.message

        return {"check_input": check_input, "check_output": check_output}


class PiiSafeStream:
    """스트리밍 절충안: 토큰은 바로 내보내되, 개인정보 정규식 검사를 통과한 부분만 내보낸다.

    - 끝부분 ``HOLD`` 글자는 아직 숫자가 이어질 수 있으므로 붙잡아 둔다(띄어 쓴 전화·카드번호 대비).
    - 내보내는 지점은 공백 직후로 맞춘다. 띄어쓰기 없이 길게 이어지는 이메일이 반쯤 보이지 않게 하기 위해서다.
    - 개인정보가 보이면 즉시 멈추고 ``blocked`` 에 결과를 남긴다(붙잡아 둔 부분은 화면에 나가지 않는다).

    욕설·탈옥 같은 LLM 판정은 답변이 끝난 뒤 ``check_output`` 으로 한 번 더 해야 한다.
    """

    HOLD = 24  # 가장 긴 패턴(구분자 포함 카드번호 19자)보다 길게

    def __init__(self, tokens: Iterable[str], guard: Guardrails):
        self._tokens = tokens
        self._guard = guard
        self.text = ""
        self.blocked: GuardResult | None = None

    def _safe_end(self) -> int:
        limit = len(self.text) - self.HOLD
        if limit <= 0:
            return 0
        cut = max(self.text.rfind(ch, 0, limit) for ch in (" ", "\n", "\t"))
        return cut + 1 if cut >= 0 else 0

    def __iter__(self) -> Iterator[str]:
        shown = 0
        try:
            for token in self._tokens:
                self.text += token or ""
                verdict = self._guard.scan_output_pii(self.text)
                if not verdict.allowed:
                    self.blocked = verdict
                    return
                end = self._safe_end()
                if end > shown:
                    yield self.text[shown:end]
                    shown = end
            if len(self.text) > shown:
                yield self.text[shown:]
        finally:
            close = getattr(self._tokens, "close", None)
            if close:  # 중간에 멈추면 LLM 스트림도 닫는다
                close()


@lru_cache(maxsize=1)
def get_guardrails() -> Guardrails:
    """프로세스당 하나의 가드레일 인스턴스를 재사용한다."""
    return Guardrails()
