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
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVALSET = PROJECT_ROOT / "evaluations" / "datasets" / "langgraph" / "LangGraph_Ragas_평가셋_300문항.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "evaluation" / "langgraph_ragas"
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
        contexts = [str(item.get("text", "")).strip() for item in evidence]
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
        }

    # Legacy callers that pass one app instance remain sequential. The live
    # evaluation path passes a factory so each worker gets its own graph app.
    max_workers = 1 if shared_app is not None else batch_size
    results_by_index: dict[int, dict[str, Any]] = {}
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
                completed += 1
                print(
                    f"[GraphRAG] {completed}/{len(rows)} complete "
                    f"(question_id={result['question_id']})",
                    flush=True,
                )

    return [results_by_index[index] for index in range(len(rows))]


def build_ragas_metrics(model_name: str, client: Any = None) -> list[Any]:
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
    evaluator_llm = llm_factory(model_name, client=judge_client, temperature=0)
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
        expected_answerable = gold["answerable"] == "yes"
        output.append({
            "question_id": gold["question_id"],
            "category": gold["category"],
            "user_input": gold["user_input"],
            "answerable": gold["answerable"],
            "label_status": gold["label_status"],
            "gold_museum_ids": gold["gold_museum_ids"],
            "retrieved_museum_ids": ";".join(dict.fromkeys(
                str(item.get("museum_id", "")) for item in evidence if item.get("museum_id")
            )),
            "retrieved_span_ids": ";".join(
                str(item.get("span_id", "")) for item in evidence if item.get("span_id")
            ),
            "evidence_count": len(evidence),
            "evidence_presence_correct": int(bool(evidence) == expected_answerable),
            "route_trace": ">".join(graph.get("route_trace", [])),
            "verified_id_check": graph.get("verified", False),
            "answer": graph.get("answer", ""),
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
    summary = {
        "run_id": run_id,
        "question_count": len(gold_rows),
        "answerable_questions": answerable_count,
        "unanswerable_questions": unanswerable_count,
        "label_status": statuses,
        "judge_model": judge_model,
        "graph_model": graph_model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        "top_k": top_k,
        "metrics": _score_means(question_rows),
        "evidence_presence_accuracy": evidence_presence_accuracy,
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
        f"- 라벨 상태: `{json.dumps(statuses, ensure_ascii=False)}`",
        f"- 전체 evidence presence accuracy: {evidence_presence_accuracy:.3f}",
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
        evaluation = evaluate_with_ragas(dataset, judge_model)
        print("[2/2] Ragas scoring complete.", flush=True)
        scored_frame = evaluation.to_pandas()
        question_rows = assemble_question_rows(gold_rows, graph_results, scored_frame)
        output_dir = write_outputs(
            question_rows,
            gold_rows,
            resolve_path(args.output),
            evalset_path=evalset_path,
            top_k=args.top_k,
            judge_model=judge_model,
            graph_model=graph_model,
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
