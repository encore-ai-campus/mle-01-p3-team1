"""Run a Ragas evaluation of the live Neo4j-backed LangGraph graph route.

From the repository root:
    uv run python -m src.evaluation.langgraph.ragas_eval --check-only
    uv run python -m src.evaluation.langgraph.ragas_eval
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import local
from time import perf_counter
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv
from src.evaluation.timing import timing_summary


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVALSET = PROJECT_ROOT / "evaluations" / "datasets" / "supervisor_v2" / "Supervisor_Ragas_v2_draft.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "evaluation" / "langgraph_ragas"
NEO4J_EVALSET_DIR = PROJECT_ROOT / "evaluations" / "datasets" / "neo4j"
NEO4J_OUTPUT = PROJECT_ROOT / "outputs" / "evaluation" / "neo4j_multihop_ragas"
REQUIRED_COLUMNS = {
    "question_id",
    "category",
    "user_input",
    "answerable",
    "reference",
    "reference_contexts",
    "gold_museum_ids",
    "gold_museum_names",
    "evidence_quote",
    "label_status",
}
METRIC_NAMES = (
    "faithfulness",
    "context_recall",
    "context_precision_with_reference",
    "factual_correctness",
)


def _ragas_context(item: Mapping[str, Any]) -> str:
    """Pass returned graph properties to Ragas as well as the text span."""
    passage = str(item.get("text") or "").strip()
    fields = (
        "museum_id", "name", "sido", "sigungu", "ownership_type",
        "adult_fee", "youth_fee", "child_fee", "adult_fee_status", "fee_notes",
        "span_id", "source_doc_ids", "source_locators", "source_locator", "source_type",
        "source_urls", "evidence_role", "source_count", "graph_path",
        "matched_span_id", "matched_span_text", "related_span_id", "related_span_text",
    )
    structured = {
        key: item[key]
        for key in fields
        if key in item and item[key] not in (None, "", [], {})
    }
    if not structured:
        return passage
    returned_fields = "[Neo4j 반환 구조화 필드] " + json.dumps(
        structured, ensure_ascii=False, sort_keys=True, default=str
    )
    return f"{passage}\n{returned_fields}" if passage else returned_fields


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the live Neo4j-backed LangGraph route with Ragas."
    )
    parser.add_argument("--evalset", type=Path, default=DEFAULT_EVALSET)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Maximum concurrent GraphRAG questions (default: 8).",
    )
    parser.add_argument("--judge-model", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Base directory for run outputs; defaults based on the evaluation set folder.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate the dataset, dependencies, credentials, and Neo4j connection without Ragas API calls.",
    )
    args = parser.parse_args(argv)
    if args.top_k < 1:
        parser.error("--top-k must be at least 1.")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")
    return args


def resolve_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def default_output_for_evalset(evalset_path: Path) -> Path:
    """Keep Neo4j-only evaluation runs separate from the general LangGraph runs."""
    try:
        evalset_path.resolve().relative_to(NEO4J_EVALSET_DIR.resolve())
    except ValueError:
        return DEFAULT_OUTPUT
    return NEO4J_OUTPUT


def read_evaluation_set(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"Ragas evaluation CSV not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if not rows:
        raise SystemExit(f"Ragas evaluation CSV is empty: {path}")
    if missing:
        raise SystemExit(f"Required columns missing: {', '.join(sorted(missing))}")

    ids: set[str] = set()
    for row in rows:
        row["question_id"] = row["question_id"].strip()
        row["user_input"] = row["user_input"].strip()
        row["answerable"] = row["answerable"].strip().lower()
        row["reference"] = row["reference"].strip()
        if not row["question_id"] or row["question_id"] in ids:
            raise SystemExit("question_id values must be non-empty and unique.")
        ids.add(row["question_id"])
        if not row["user_input"]:
            raise SystemExit(f"{row['question_id']}: user_input is empty.")
        if row["answerable"] not in {"yes", "no"}:
            raise SystemExit(f"{row['question_id']}: answerable must be 'yes' or 'no'.")
        if not row["reference"]:
            raise SystemExit(f"{row['question_id']}: reference is empty.")
        try:
            reference_contexts = json.loads(row["reference_contexts"] or "[]")
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{row['question_id']}: reference_contexts must be JSON: {exc}") from exc
        if not isinstance(reference_contexts, list) or any(
            not isinstance(context, str) for context in reference_contexts
        ):
            raise SystemExit(f"{row['question_id']}: reference_contexts must be a JSON string array.")
        row["reference_contexts_parsed"] = reference_contexts
        if row["answerable"] == "yes" and not reference_contexts:
            raise SystemExit(f"{row['question_id']}: answerable rows need reference_contexts.")
    return rows


def build_evaluation_dataset(
    gold_rows: Sequence[Mapping[str, Any]],
    graph_results: Sequence[Mapping[str, Any]],
):
    """Build Ragas v0.4 samples for answerable rows using graph output and gold references."""
    from ragas.dataset_schema import EvaluationDataset, SingleTurnSample

    results_by_id = {str(row["question_id"]): row for row in graph_results}
    if len(results_by_id) != len(graph_results):
        raise ValueError("graph result question_id values must be unique.")

    samples = []
    for gold in gold_rows:
        if str(gold["answerable"]).lower() != "yes":
            continue
        question_id = str(gold["question_id"])
        if question_id not in results_by_id:
            raise ValueError(f"Missing graph result for {question_id}.")
        result = results_by_id[question_id]
        evidence = result.get("evidence") or []
        contexts = [_ragas_context(item) for item in evidence]
        contexts = [context for context in contexts if context]
        samples.append(
            SingleTurnSample(
                user_input=str(gold["user_input"]),
                response=str(result.get("answer", "")),
                retrieved_contexts=contexts,
                reference=str(gold["reference"]),
                reference_contexts=list(gold.get("reference_contexts_parsed") or []),
            )
        )
    if not samples:
        raise ValueError("Ragas evaluation needs at least one answerable question.")
    return EvaluationDataset(samples=samples)


def build_graph_app(
    driver: Any,
    database: str,
    top_k: int,
    *,
    model: str | None = None,
):
    from src.agent.graph import build_graph
    from src.agent.neo4j_demo import _verify_smoke_answer
    from src.agent.neo4j_text2cypher import Neo4jText2Cypher

    graph_search = Neo4jText2Cypher(driver, database, model=model)
    return build_graph(
        vector_search=lambda question, k: [],
        graph_search=graph_search.search,
        route_question=lambda question: "graph",
        make_answer=graph_search.make_answer,
        verify_answer=_verify_smoke_answer,
        top_k=top_k,
        max_retries=0,
    )


def collect_graph_results(
    app_or_factory: Any,
    rows: Sequence[Mapping[str, Any]],
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    if not rows:
        return []

    shared_app = (
        app_or_factory
        if callable(getattr(app_or_factory, "invoke", None))
        else None
    )
    if shared_app is None and not callable(app_or_factory):
        raise TypeError(
            "app_or_factory must be a LangGraph app or a zero-argument app factory."
        )

    thread_apps = local()

    def run_one(row: Mapping[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        try:
            if shared_app is not None:
                app = shared_app
            else:
                app = getattr(thread_apps, "app", None)
                if app is None:
                    app = app_or_factory()
                    thread_apps.app = app
            state = app.invoke({"question": row["user_input"]})
        except Exception as exc:
            raise RuntimeError(
                f"{row['question_id']} GraphRAG 검색/답변 생성 실패: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return {
            "question_id": row["question_id"],
            "route_trace": state.get("route_trace", []),
            "verified": bool(state.get("verified", False)),
            "failure_reason": state.get("failure_reason", ""),
            "answer": state.get("answer", ""),
            "evidence": state.get("evidence", []),
            "duration_ms": (perf_counter() - started) * 1000,
        }

    # Legacy callers that pass one app instance remain sequential. The live
    # evaluation path passes a factory so each worker gets its own graph app.
    max_workers = 1 if shared_app is not None else batch_size
    results_by_index: dict[int, dict[str, Any]] = {}
    durations_ms: list[float] = []
    print("[GraphRAG] 시간: 검색·답변 생성 기준 (Ragas 채점 시간 제외)", flush=True)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        completed = 0
        for start in range(0, len(rows), max_workers):
            batch_indexes = range(start, min(start + max_workers, len(rows)))
            future_indexes = {
                executor.submit(run_one, rows[index]): index
                for index in batch_indexes
            }
            for future in as_completed(future_indexes):
                index = future_indexes[future]
                try:
                    result = future.result()
                except Exception:
                    for pending in future_indexes:
                        if pending is not future:
                            pending.cancel()
                    raise
                results_by_index[index] = result
                durations_ms.append(result["duration_ms"])
                completed += 1
                print(
                    f"[GraphRAG] {completed}/{len(rows)} complete "
                    f"(question_id={result['question_id']}) "
                    f"{result['duration_ms'] / 1000:.2f}초 · {timing_summary(durations_ms)}",
                    flush=True,
                )

    print(f"[GraphRAG] 전체 문항 검색·답변 시간: {timing_summary(durations_ms)}", flush=True)
    return [results_by_index[index] for index in range(len(rows))]


def build_ragas_metrics(
    model_name: str,
    client: Any = None,
    *,
    cache_dir: Path | None = None,
) -> list[Any]:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    # Ragas 0.4.x's top-level evaluate() accepts legacy Metric subclasses;
    # collections metrics implement the newer BaseMetric interface instead.
    from ragas.metrics import (
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
        LLMContextPrecisionWithReference,
    )

    judge_client = client or AsyncOpenAI()
    llm_options: dict[str, Any] = {}
    # Newer reasoning models reject an explicit temperature parameter. Keep
    # deterministic temperature for the GPT-4 family and omit it elsewhere.
    if not model_name.casefold().startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")):
        llm_options["temperature"] = 0
    if cache_dir is not None:
        from ragas.cache import DiskCacheBackend

        cache_dir.mkdir(parents=True, exist_ok=True)
        llm_options["cache"] = DiskCacheBackend(str(cache_dir))
    evaluator_llm = llm_factory(model_name, client=judge_client, **llm_options)
    context_precision = LLMContextPrecisionWithReference(llm=evaluator_llm)
    # Keep the result column name used by reports and METRIC_NAMES.
    context_precision.name = "context_precision_with_reference"
    return [
        Faithfulness(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
        context_precision,
        FactualCorrectness(llm=evaluator_llm),
    ]


def evaluate_with_ragas(dataset: Any, model_name: str):
    from ragas import evaluate

    return evaluate(
        dataset=dataset,
        metrics=build_ragas_metrics(model_name),
        show_progress=True,
    )


def _normalise_score(value: Any) -> float | str:
    if value is None:
        return ""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if math.isnan(score) else score


def _split_ids(value: Any) -> set[str]:
    if value is None:
        return set()
    return {part.strip() for part in str(value).split(";") if part.strip()}


def _joined_evidence_values(evidence: Sequence[Mapping[str, Any]], field: str) -> str:
    values: list[str] = []
    for item in evidence:
        value = item.get(field)
        if value is None or value == "":
            continue
        candidates = value if isinstance(value, (list, tuple)) else [value]
        values.extend(str(candidate).strip() for candidate in candidates
                      if candidate is not None and str(candidate).strip())
    return ";".join(dict.fromkeys(values))


def assemble_question_rows(
    gold_rows: Sequence[Mapping[str, Any]],
    graph_results: Sequence[Mapping[str, Any]],
    ragas_frame,
) -> list[dict[str, Any]]:
    results_by_id = {str(row["question_id"]): row for row in graph_results}
    answerable_rows = [row for row in gold_rows if row["answerable"] == "yes"]
    if len(answerable_rows) != len(ragas_frame):
        raise ValueError("Ragas score rows do not match answerable evaluation rows.")
    scores_by_id = {}
    for gold, (_, score_row) in zip(answerable_rows, ragas_frame.iterrows()):
        scores_by_id[str(gold["question_id"])] = {
            metric: _normalise_score(score_row.get(metric, "")) for metric in METRIC_NAMES
        }

    output = []
    for gold in gold_rows:
        graph = results_by_id[str(gold["question_id"])]
        evidence = graph.get("evidence") or []
        metrics = scores_by_id.get(str(gold["question_id"]), {})
        retrieved_museum_ids = list(dict.fromkeys(
            str(item.get("museum_id", "")).strip()
            for item in evidence if str(item.get("museum_id", "")).strip()
        ))
        gold_museum_ids = _split_ids(gold.get("gold_museum_ids"))
        retrieved_museum_id_set = set(retrieved_museum_ids)
        museum_id_recall = (
            len(gold_museum_ids & retrieved_museum_id_set) / len(gold_museum_ids)
            if gold_museum_ids else ""
        )
        expected_answerable = gold["answerable"] == "yes"
        output.append({
            "question_id": gold["question_id"],
            "category": gold["category"],
            "user_input": gold["user_input"],
            "answerable": gold["answerable"],
            "label_status": gold["label_status"],
            "gold_museum_ids": gold["gold_museum_ids"],
            "retrieved_museum_ids": ";".join(retrieved_museum_ids),
            "gold_museum_recall": museum_id_recall,
            "retrieved_source_doc_ids": _joined_evidence_values(evidence, "source_doc_ids"),
            "retrieved_source_locators": ";".join(dict.fromkeys(
                value
                for item in evidence
                for value in (
                    _joined_evidence_values([item], "source_locators").split(";")
                    + _joined_evidence_values([item], "source_locator").split(";")
                )
                if value
            )),
            "retrieved_span_ids": ";".join(dict.fromkeys(
                str(item.get(field, "")).strip()
                for item in evidence
                for field in ("span_id", "matched_span_id", "related_span_id")
                if str(item.get(field, "")).strip()
            )),
            "evidence_count": len(evidence),
            "evidence_presence_correct": int(bool(evidence) == expected_answerable),
            "route_trace": ">".join(graph.get("route_trace", [])),
            "verified_id_check": graph.get("verified", False),
            "answer": graph.get("answer", ""),
            "duration_seconds": round(graph["duration_ms"] / 1000, 3) if isinstance(graph.get("duration_ms"), (int, float)) else "",
            **{metric: metrics.get(metric, "") for metric in METRIC_NAMES},
        })
    return output


def _score_means(question_rows: Sequence[Mapping[str, Any]]) -> dict[str, float | str]:
    means: dict[str, float | str] = {}
    for metric in METRIC_NAMES:
        values = [float(row[metric]) for row in question_rows if row.get(metric) != ""]
        means[metric] = statistics.mean(values) if values else ""
    return means


def write_outputs(
    question_rows: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
    output_base: Path,
    *,
    evalset_path: Path,
    top_k: int,
    judge_model: str,
    graph_model: str | None = None,
    ragas_scoring_seconds: float | None = None,
) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_base / f"run_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=False)

    fields = list(question_rows[0])
    with (output_dir / "per_question.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(question_rows)

    answerable_count = sum(row["answerable"] == "yes" for row in gold_rows)
    unanswerable_count = len(gold_rows) - answerable_count
    evidence_presence_accuracy = statistics.mean(
        int(row["evidence_presence_correct"]) for row in question_rows
    )
    statuses = dict(Counter(str(row["label_status"]) for row in gold_rows))
    museum_id_recall_values = [
        float(row["gold_museum_recall"])
        for row in question_rows
        if row.get("gold_museum_recall") not in ("", None)
    ]
    museum_id_recall = statistics.mean(museum_id_recall_values) if museum_id_recall_values else ""
    duration_values = [float(row["duration_seconds"]) for row in question_rows
                       if row.get("duration_seconds") not in ("", None)]
    summary = {
        "run_id": run_id,
        "question_count": len(gold_rows),
        "answerable_questions": answerable_count,
        "unanswerable_questions": unanswerable_count,
        "label_status": statuses,
        "judge_model": judge_model,
        "graph_model": graph_model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "top_k": top_k,
        "avg_duration_seconds": statistics.mean(duration_values) if duration_values else "",
        "max_duration_seconds": max(duration_values) if duration_values else "",
        "ragas_scoring_seconds": ragas_scoring_seconds,
        "metrics": _score_means(question_rows),
        "evidence_presence_accuracy": evidence_presence_accuracy,
        "gold_museum_id_recall": museum_id_recall,
        "evalset": str(evalset_path),
        "note": "Ragas scores are run on answerable rows. Evidence-presence accuracy covers all rows. Draft labels make these scores provisional.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = [
        "# LangGraph Ragas 평가",
        "",
        f"- 질문 수: {len(gold_rows)} (답변 가능 {answerable_count}, 근거 부족 {unanswerable_count})",
        f"- Judge 모델: {judge_model}",
        f"- GraphRAG 생성 모델: {graph_model or os.getenv('OPENAI_CHAT_MODEL', 'gpt-4o-mini')}",
        f"- 검색 top-k: {top_k}",
        f"- 검색·답변 시간: {timing_summary([value * 1000 for value in duration_values])}",
        f"- Ragas 전체 채점 시간: {ragas_scoring_seconds:.2f}초" if ragas_scoring_seconds is not None else "- Ragas 전체 채점 시간: N/A",
        f"- 라벨 상태: `{json.dumps(statuses, ensure_ascii=False)}`",
        f"- 전체 evidence presence accuracy: {evidence_presence_accuracy:.3f}",
        f"- 정답 박물관 ID recall: {museum_id_recall:.3f}" if museum_id_recall != "" else "- 정답 박물관 ID recall: N/A",
        "",
        "| Ragas 지표 | 평균 |",
        "|---|---:|",
    ]
    report.extend(
        f"| {metric} | {summary['metrics'][metric]:.3f} |"
        if summary["metrics"][metric] != ""
        else f"| {metric} | N/A |"
        for metric in METRIC_NAMES
    )
    report.extend([
        "",
        "Ragas 점수는 답변 가능 문항에 대해서만 계산했습니다. `evidence_presence_accuracy`는 답변 가능/불가능 정답 라벨과 검색 결과 유무를 비교합니다.",
        "`gold_museum_id_recall`은 정답 박물관 ID 중 검색 결과에 포함된 비율이며, 정답 후보를 찾았는지 Ragas 점수와 별도로 확인합니다.",
        "라벨이 `draft_needs_human_review`인 문항은 검수 전 잠정 점수입니다.",
        "",
    ])
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    return output_dir


def _required_environment(*, require_openai: bool) -> list[str]:
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"]
    if require_openai:
        required.append("OPENAI_API_KEY")
    return [key for key in required if not os.getenv(key)]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    evalset_path = resolve_path(args.evalset)
    output_base = resolve_path(args.output) if args.output is not None else default_output_for_evalset(evalset_path)
    try:
        gold_rows = read_evaluation_set(evalset_path)
        missing = _required_environment(require_openai=not args.check_only)
        if missing:
            raise SystemExit(f"루트 .env에 다음 값이 필요합니다: {', '.join(missing)}")
        judge_model = args.judge_model or os.getenv("RAGAS_JUDGE_MODEL", "gpt-4o-mini")
        from src.agent.neo4j_text2cypher import resolve_openai_model

        graph_model = resolve_openai_model()
        label_status = dict(Counter(row["label_status"] for row in gold_rows))
        print(
            f"Evaluation set: {len(gold_rows)} questions; "
            f"answerable={sum(row['answerable'] == 'yes' for row in gold_rows)}; "
            f"label_status={label_status}"
        )
        if any(status != "human_verified" for status in label_status):
            print("WARNING: evaluation labels are not all human-verified; Ragas scores will be provisional.")

        if args.check_only:
            from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
            from ragas.metrics import (
                ContextRecall,
                FactualCorrectness,
                Faithfulness,
                LLMContextPrecisionWithReference,
            )

        from src.agent.neo4j_tls import load_graph_database

        graph_database = load_graph_database()
        answerable_count = sum(row["answerable"] == "yes" for row in gold_rows)
        print(
            f"Running GraphRAG with {graph_model} and Ragas with {judge_model} "
            f"on {answerable_count} answerable rows. OpenAI API usage may incur charges.",
            flush=True,
        )
        print("[1/2] Checking Neo4j connectivity...", flush=True)
        with graph_database.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            connection_timeout=10,
            max_transaction_retry_time=3.0,
        ) as driver:
            driver.verify_connectivity()
            if args.check_only:
                print("Read-only Neo4j connection check passed. No Ragas/OpenAI evaluation calls were made.")
                print(f"Judge model for full evaluation: {judge_model}")
                return 0

            print(
                f"[1/2] GraphRAG collection started: {len(gold_rows)} questions; "
                f"concurrency={args.batch_size}.",
                flush=True,
            )

            def app_factory():
                return build_graph_app(
                    driver,
                    os.environ["NEO4J_DATABASE"],
                    args.top_k,
                    model=graph_model,
                )

            graph_results = collect_graph_results(
                app_factory,
                gold_rows,
                batch_size=args.batch_size,
            )

        print(
            f"[1/2] GraphRAG collection complete: "
            f"{len(graph_results)}/{len(gold_rows)}.",
            flush=True,
        )
        dataset = build_evaluation_dataset(gold_rows, graph_results)
        print(
            f"[2/2] Ragas scoring started: {len(dataset)} answerable questions; "
            f"{len(METRIC_NAMES)} metrics.",
            flush=True,
        )
        scoring_started = perf_counter()
        evaluation = evaluate_with_ragas(dataset, judge_model)
        scoring_seconds = perf_counter() - scoring_started
        print(f"[2/2] Ragas scoring complete: {scoring_seconds:.2f}초 (전체 채점)", flush=True)
        scored_frame = evaluation.to_pandas()
        question_rows = assemble_question_rows(gold_rows, graph_results, scored_frame)
        output_dir = write_outputs(
            question_rows,
            gold_rows,
            output_base,
            evalset_path=evalset_path,
            top_k=args.top_k,
            judge_model=judge_model,
            graph_model=graph_model,
            ragas_scoring_seconds=scoring_seconds,
        )
        print(f"Ragas evaluation complete. Reports: {output_dir}")
        print(json.dumps(_score_means(question_rows), ensure_ascii=False, indent=2))
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"LangGraph Ragas evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
