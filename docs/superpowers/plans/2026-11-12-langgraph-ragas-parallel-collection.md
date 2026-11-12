# LangGraph Ragas 병렬 평가 및 진행 표시 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 30문항과 300문항 GraphRAG 평가를 최대 8문항씩 병렬 실행하고, GraphRAG 및 Ragas 진행 상황을 실행 중 확인할 수 있게 한다.

**Architecture:** `collect_graph_results`는 앱 팩토리를 받아 작업 스레드마다 LangGraph 앱을 하나 생성하고 재사용한다. Future 완료 순서와 무관하게 반환값은 CSV 입력 순서를 유지하며, 진행 로그는 완료 즉시 메인 스레드에서 출력한다. Ragas `evaluate()`에는 `show_progress=True`를 명시한다.

**Tech Stack:** Python 3.10+, `concurrent.futures.ThreadPoolExecutor`, `threading.local`, LangGraph, Neo4j Python Driver, Ragas 0.4.3

**Spec:** `docs/superpowers/specs/2026-11-12-langgraph-ragas-parallel-collection-design.md`

## Global Constraints

- 기본 동시 실행 수는 8이며, `--batch-size N`으로 바꿀 수 있다. 값은 1 이상이어야 한다.
- 한 스레드에서 실행되는 문항은 같은 LangGraph 앱을 재사용한다. 스레드 간에는 앱을 공유하지 않는다.
- 결과의 순서와 각 결과의 `question_id`는 평가셋 입력 순서를 보존한다.
- GraphRAG 문항이 끝날 때마다 완료/전체 수와 해당 `question_id`를 표시한다.
- Ragas 채점 직전에 채점 문항 수를 표시하고 `show_progress=True`로 진행 막대를 보여준다.
- Ragas 채점과 기존 CSV/JSON/Markdown 결과물은 계속 동일하게 실행한다.

## Review Focus

- `--batch-size 1`: 순차 실행과 같은 결과 순서 및 정상 진행 표시.
- 서로 다른 시간에 완료되는 질문: 결과는 원본 CSV 순서로 반환.
- 한 질문의 그래프 예외: 오류 메시지에 해당 `question_id` 포함.
- 기존 테스트에서 앱 인스턴스를 직접 전달하는 경로: 기존 순차 호출 동작 보존.
- OpenAI rate limit: 실행자는 동시성을 낮출 수 있고 실패 원인이 질문 ID와 함께 드러남.

---

### Task 1: GraphRAG 문항 동시 수집과 진행 표시

**Files:**
- Modify: `src/evaluation/langgraph/ragas_eval.py`

**Interfaces:**
- CLI option: `--batch-size` (`int`, default `8`, minimum `1`).
- `collect_graph_results(app_or_factory, rows, batch_size=8)` returns graph result dictionaries in input order.
- Main passes an app factory; legacy direct app instances remain sequential for current callers.

- [x] Add bounded worker execution using `ThreadPoolExecutor` and thread-local app reuse for app factories.
- [x] Store results by input index; report each completed `question_id` and completed/total count.
- [x] Print the evaluation and GraphRAG phase start before any network calls, including total rows and concurrency.
- [x] Preserve question-specific exception messages.
- [x] Run a Python syntax compilation check.

### Task 2: Ragas progress display and usage documentation

**Files:**
- Modify: `src/evaluation/langgraph/ragas_eval.py`
- Modify: `docs/evaluation/langgraph_ragas.md`

**Interfaces:**
- Before scoring, report answerable sample count and metric count.
- Call Ragas `evaluate(..., show_progress=True)` and report scoring completion.

- [x] Add explicit Ragas scoring start/completion messages.
- [x] Document default concurrency `8`, `--batch-size` overrides, progress output, and reducing concurrency after rate limits.
- [x] Run a Python syntax compilation check and inspect the final diff.

