"""Create a human-reviewable Ragas testset from the museum source spans.

From the repository root:
    uv run python -m src.agent.ragas_testset --count 300
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

from .ragas_eval import PROJECT_ROOT, read_evaluation_set, resolve_path


DEFAULT_SOURCE = PROJECT_ROOT / "src" / "for_build" / "museum_final_738.csv"
DEFAULT_SEED_SET = PROJECT_ROOT / "vector_db_평가셋" / "LangGraph_Ragas_평가셋_30문항.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "vector_db_평가셋" / "LangGraph_Ragas_평가셋_300문항.csv"
OUTPUT_COLUMNS = (
    "question_id",
    "category",
    "user_input",
    "answerable",
    "reference",
    "reference_contexts",
    "gold_museum_ids",
    "gold_museum_names",
    "evidence_doc_ids",
    "evidence_quote",
    "label_status",
    "notes",
)
_SPACE = re.compile(r"\s+")


def _normalise_question(value: str) -> str:
    return _SPACE.sub(" ", value).strip().casefold()


def load_source_documents(path: Path, *, max_chunks: int = 600, seed: int = 42):
    from langchain_core.documents import Document

    if max_chunks < 1:
        raise ValueError("max_chunks must be at least 1.")
    documents = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            text = row.get("text", "")
            try:
                spans = json.loads(row.get("text_spans_json", "[]"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{row.get('museum_id', 'unknown')}: invalid text_spans_json") from exc
            candidates = []
            for index, span in enumerate(spans):
                start, end = span.get("start"), span.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text):
                    continue
                content = text[start:end].strip()
                if len(content) < 80:
                    continue
                candidates.append((content, index, span))
            if not candidates:
                continue
            content, index, span = max(candidates, key=lambda item: len(item[0]))
            documents.append(
                Document(
                    id=f"{row['museum_id']}:{index:03d}",
                    page_content=content,
                    metadata={
                        "museum_id": row["museum_id"],
                        "museum_name": row["name"],
                        "sido": row["sido"],
                        "sigungu": row["sigungu"],
                        "span_id": f"{row['museum_id']}:{index:03d}",
                        "source_doc_ids": list(span.get("doc_ids") or []),
                    },
                )
            )
    if not documents:
        raise ValueError(f"No usable text spans in {path}")
    if len(documents) > max_chunks:
        documents = random.Random(seed).sample(documents, max_chunks)
    return sorted(documents, key=lambda document: document.metadata["museum_id"])


def build_knowledge_graph(documents: Sequence[Any]):
    """Create Ragas chunk nodes with deterministic search terms and source metadata."""
    from ragas.testset.graph import KnowledgeGraph, Node, NodeType

    from .neo4j_search import extract_search_terms

    nodes = []
    for document in documents:
        content, metadata = _document_parts(document)
        if not content.strip():
            continue
        museum_name = str(metadata.get("museum_name", ""))
        try:
            terms = extract_search_terms(f"{museum_name} {content}", max_terms=12)
        except ValueError:
            continue
        nodes.append(
            Node(
                type=NodeType.CHUNK,
                properties={
                    "page_content": content,
                    "document_metadata": dict(metadata),
                    "entities": terms,
                },
            )
        )
    if not nodes:
        raise ValueError("No usable chunk nodes to generate Ragas questions.")
    return KnowledgeGraph(nodes=nodes)


def _document_parts(document: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(document, Mapping):
        return str(document.get("page_content", "")), document.get("metadata") or {}
    return str(getattr(document, "page_content", "")), getattr(document, "metadata", {}) or {}


def _match_contexts(
    contexts: Sequence[str], documents: Sequence[Any]
) -> tuple[list[str], list[str], list[str]]:
    museum_ids: list[str] = []
    museum_names: list[str] = []
    doc_ids: list[str] = []
    normalized_docs = [
        (_SPACE.sub(" ", _document_parts(document)[0]).strip().casefold(), _document_parts(document)[1])
        for document in documents
    ]
    for context in contexts:
        normalized_context = _SPACE.sub(" ", context).strip().casefold()
        if not normalized_context:
            continue
        for normalized_doc, metadata in normalized_docs:
            if normalized_context in normalized_doc or normalized_doc in normalized_context:
                museum_id = str(metadata.get("museum_id", ""))
                museum_name = str(metadata.get("museum_name", ""))
                if museum_id and museum_id not in museum_ids:
                    museum_ids.append(museum_id)
                if museum_name and museum_name not in museum_names:
                    museum_names.append(museum_name)
                for doc_id in metadata.get("source_doc_ids", []) or []:
                    value = str(doc_id)
                    if value and value not in doc_ids:
                        doc_ids.append(value)
    return museum_ids, museum_names, doc_ids


def build_evaluation_rows(
    seed_rows: Sequence[Mapping[str, Any]],
    generated_samples: Sequence[Mapping[str, Any]],
    source_documents: Sequence[Any],
    *,
    total_count: int,
) -> list[dict[str, str]]:
    if total_count < len(seed_rows):
        raise ValueError("total_count cannot be smaller than the seed evaluation set.")
    rows: list[dict[str, str]] = []
    seen_questions: set[str] = set()
    next_number = 1
    for seed_row in seed_rows:
        row = {column: str(seed_row.get(column, "")) for column in OUTPUT_COLUMNS}
        rows.append(row)
        seen_questions.add(_normalise_question(row["user_input"]))
        match = re.fullmatch(r"Q(\d+)", row["question_id"])
        if match:
            next_number = max(next_number, int(match.group(1)) + 1)

    for sample in generated_samples:
        if len(rows) >= total_count:
            break
        user_input = str(sample.get("user_input", "")).strip()
        reference = str(sample.get("reference", "")).strip()
        contexts = sample.get("reference_contexts") or []
        if isinstance(contexts, str):
            try:
                contexts = json.loads(contexts)
            except json.JSONDecodeError:
                continue
        if not isinstance(contexts, list):
            continue
        contexts = [str(context).strip() for context in contexts if str(context).strip()]
        normalized = _normalise_question(user_input)
        if not user_input or not reference or not contexts or normalized in seen_questions:
            continue
        seen_questions.add(normalized)
        museum_ids, museum_names, doc_ids = _match_contexts(contexts, source_documents)
        row = {
            "question_id": f"Q{next_number:03d}",
            "category": str(sample.get("synthesizer_name") or "ragas_synthetic"),
            "user_input": user_input,
            "answerable": "yes",
            "reference": reference,
            "reference_contexts": json.dumps(contexts, ensure_ascii=False),
            "gold_museum_ids": ";".join(museum_ids),
            "gold_museum_names": ";".join(museum_names),
            "evidence_doc_ids": ";".join(doc_ids),
            "evidence_quote": "\n\n---\n\n".join(contexts),
            "label_status": "draft_needs_human_review",
            "notes": "Ragas 합성 문항; 질문·정답·근거·박물관 ID를 사람이 검수해야 합니다.",
        }
        rows.append(row)
        next_number += 1

    if len(rows) != total_count:
        raise ValueError(
            f"Need {total_count - len(seed_rows)} unique generated rows, "
            f"but only {len(rows) - len(seed_rows)} were usable."
        )
    return rows


def write_evaluation_set(rows: Sequence[Mapping[str, Any]], path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path}; pass --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Ragas museum evaluation set.")
    parser.add_argument("--count", type=int, default=300, help="Total set size, including the existing 30 seed questions.")
    parser.add_argument("--max-chunks", type=int, default=600)
    parser.add_argument("--model", default=None)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--seed-set", type=Path, default=DEFAULT_SEED_SET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output CSV.")
    args = parser.parse_args(argv)
    if args.count < 1 or args.max_chunks < 1:
        parser.error("--count and --max-chunks must be positive integers.")
    return args


def generate_testset(documents: Sequence[Any], count: int, model_name: str):
    from openai import AsyncOpenAI, OpenAI
    from ragas.embeddings import OpenAIEmbeddings
    from ragas.llms import llm_factory
    from ragas.run_config import RunConfig
    from ragas.testset.persona import Persona
    from ragas.testset.synthesizers.generate import TestsetGenerator
    from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer

    class PreparedSingleHopSynthesizer(SingleHopSpecificQuerySynthesizer):
        """Avoid one extra LLM call per source span for theme/persona matching."""

        async def _generate_scenarios(self, n, knowledge_graph, persona_list, callbacks):
            nodes = self.get_node_clusters(knowledge_graph)
            if not nodes:
                raise ValueError("No Ragas chunk nodes contain searchable terms.")
            samples_per_node = math.ceil(n / len(nodes))
            scenarios = []
            for node in nodes:
                if len(scenarios) >= n:
                    break
                themes = self._extract_themes_from_items(
                    node.properties.get(self.property_name, [])
                )
                if not themes:
                    continue
                # Every extracted source term is relevant to the fixed museum visitor persona.
                persona_concepts = {persona.name: themes for persona in persona_list}
                combinations = self.prepare_combinations(
                    node, themes, personas=persona_list, persona_concepts=persona_concepts
                )
                scenarios.extend(
                    self.sample_combinations(
                        combinations, min(samples_per_node, n - len(scenarios))
                    )
                )
            if len(scenarios) < n:
                raise ValueError(
                    f"Could only build {len(scenarios)} Ragas scenarios from {len(nodes)} source spans; requested {n}."
                )
            return scenarios[:n]

    # Bound individual HTTP calls: Ragas' Instructor adapter does not pass its
    # RunConfig timeout through to the OpenAI client.
    llm_client = AsyncOpenAI(timeout=45, max_retries=2)
    embedding_client = OpenAI(timeout=45, max_retries=0)
    llm = llm_factory(model_name, client=llm_client, temperature=0)
    persona = Persona(
        name="한국 박물관 관람객",
        role_description="한국 박물관의 전시 주제와 지역 문화 정보를 찾는 일반 관람객.",
    )
    synthesizer = PreparedSingleHopSynthesizer(
        llm=llm,
        llm_context=(
            "질문과 답변은 반드시 자연스러운 한국어로 작성하세요. 질문은 제공된 박물관 설명에서 "
            "답할 수 있어야 하며, 답변에는 설명에 직접 근거한 사실만 사용하세요."
        ),
    )
    synthesizer.generate_query_reference_prompt.language = "Korean"
    generator = TestsetGenerator(
        llm=llm,
        embedding_model=OpenAIEmbeddings(client=embedding_client, model="text-embedding-3-small"),
        knowledge_graph=build_knowledge_graph(documents),
        persona_list=[persona],
    )
    testset = generator.generate(
        testset_size=count,
        query_distribution=[(synthesizer, 1.0)],
        num_personas=1,
        run_config=RunConfig(timeout=60, max_retries=2, max_wait=5, max_workers=8),
        batch_size=32,
        raise_exceptions=True,
    )
    return testset.to_list()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    output_path = resolve_path(args.output)
    if output_path.exists() and not args.force:
        print(f"Refusing to overwrite {output_path}; pass --force to replace it.", file=sys.stderr)
        return 2
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in the project-root .env or environment.", file=sys.stderr)
        return 2

    try:
        seed_rows = read_evaluation_set(resolve_path(args.seed_set))
        if args.count < len(seed_rows):
            raise ValueError(f"--count must be at least the {len(seed_rows)} seed rows.")
        source_path = resolve_path(args.source)
        documents = load_source_documents(source_path, max_chunks=args.max_chunks)
        needed_count = args.count - len(seed_rows)
        # Generate a small buffer so near-duplicate questions can be removed safely.
        generated_count = needed_count + max(10, math.ceil(needed_count * 0.12))
        print(
            f"Generating {generated_count} Ragas questions from {len(documents)} museum text spans. "
            f"Model={args.model or os.getenv('RAGAS_GENERATION_MODEL', 'gpt-4o-mini')}; "
            "OpenAI generation and embedding usage may incur charges."
        )
        samples = generate_testset(
            documents,
            generated_count,
            args.model or os.getenv("RAGAS_GENERATION_MODEL", "gpt-4o-mini"),
        )
        rows = build_evaluation_rows(seed_rows, samples, documents, total_count=args.count)
        write_evaluation_set(rows, output_path, force=args.force)
        print(f"Created {len(rows)} rows at {output_path}")
        print(f"Ragas generated rows: {len(rows) - len(seed_rows)}; all new rows need human review.")
        return 0
    except Exception as exc:
        print(f"Ragas evaluation-set generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
