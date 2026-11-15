"""Validate the museum CSV and build Neo4j parameter payloads.

Run a preflight without database writes: python load_neo4j.py --dry-run
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
import csv


class ValidationError(ValueError):
    """The CSV cannot safely be loaded."""


@dataclass(frozen=True)
class ParsedData:
    museums: list[dict]
    sources: list[dict]
    spans: list[dict]
    evidence: list[dict]


INTEGER_FIELDS = {
    "adult_fee", "youth_fee", "child_fee",
    "official_verified_field_count", "text_length", "source_doc_count",
    "removed_duplicate_sentence_count",
}
FLOAT_FIELDS = {"latitude", "longitude"}
BOOLEAN_FIELDS = {"requires_manual_review"}
REQUIRED_FIELDS = {
    "museum_id", "name", "sido", "sigungu", "text", "text_length",
    "text_sha256", "source_doc_count", "source_documents_json", "text_spans_json",
    "latitude", "longitude", "requires_manual_review",
}


def _required(row: Mapping[str, str], key: str, museum_id: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        raise ValidationError(f"{museum_id}: missing {key}")
    return value


def _json_list(value: str, key: str, museum_id: str) -> list:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{museum_id}: invalid {key}") from exc
    if not isinstance(parsed, list):
        raise ValidationError(f"{museum_id}: {key} must be a list")
    return parsed


def _museum_properties(row: Mapping[str, str], museum_id: str) -> dict:
    result = {}
    for key, value in row.items():
        if key is None or value is None:
            raise ValidationError(f"{museum_id}: malformed CSV row")
        if not value.strip():
            result[key] = None
        elif key in INTEGER_FIELDS:
            try:
                result[key] = int(value)
            except ValueError as exc:
                raise ValidationError(f"{museum_id}: invalid integer {key}") from exc
        elif key in FLOAT_FIELDS:
            try:
                result[key] = float(value)
            except ValueError as exc:
                raise ValidationError(f"{museum_id}: invalid float {key}") from exc
        elif key in BOOLEAN_FIELDS:
            if value not in {"True", "False"}:
                raise ValidationError(f"{museum_id}: invalid boolean {key}")
            result[key] = value == "True"
        else:
            result[key] = value
    return result


def parse_rows(rows: Iterable[Mapping[str, str]]) -> ParsedData:
    """Validate all rows before returning any write payloads."""
    museums: list[dict] = []
    sources: list[dict] = []
    spans: list[dict] = []
    evidence: list[dict] = []
    museum_ids: set[str] = set()
    source_ids: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        missing_columns = REQUIRED_FIELDS - row.keys()
        if missing_columns:
            raise ValidationError(f"row {row_number}: missing columns {sorted(missing_columns)}")
        museum_id = _required(row, "museum_id", f"row {row_number}")
        if museum_id in museum_ids:
            raise ValidationError(f"duplicate museum_id: {museum_id}")
        museum_ids.add(museum_id)
        for key in ("name", "sido", "sigungu", "text", "text_sha256"):
            _required(row, key, museum_id)
        text = row["text"]
        if str(len(text)) != row["text_length"]:
            raise ValidationError(f"{museum_id}: text_length mismatch")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != row["text_sha256"]:
            raise ValidationError(f"{museum_id}: text_sha256 mismatch")

        documents = _json_list(row["source_documents_json"], "source_documents_json", museum_id)
        text_spans = _json_list(row["text_spans_json"], "text_spans_json", museum_id)
        if str(len(documents)) != row["source_doc_count"]:
            raise ValidationError(f"{museum_id}: source_doc_count mismatch")
        local_doc_ids: set[str] = set()
        for document in documents:
            if not isinstance(document, dict) or not isinstance(document.get("doc_id"), str) or not document["doc_id"]:
                raise ValidationError(f"{museum_id}: invalid source document")
            doc_id = document["doc_id"]
            if doc_id in source_ids:
                raise ValidationError(f"duplicate doc_id: {doc_id}")
            source_ids.add(doc_id)
            local_doc_ids.add(doc_id)
            properties = {
                key if key != "original_representative_description" else "original_representative_description_json":
                json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else (value or None)
                for key, value in document.items()
            }
            sources.append({"museum_id": museum_id, "doc_id": doc_id, "properties": properties})

        for index, span in enumerate(text_spans):
            if not isinstance(span, dict):
                raise ValidationError(f"{museum_id}: invalid text span")
            start, end, doc_ids = span.get("start"), span.get("end"), span.get("doc_ids")
            if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text):
                raise ValidationError(f"{museum_id}: invalid text span range")
            if (
                not isinstance(doc_ids, list)
                or not doc_ids
                or any(not isinstance(doc_id, str) for doc_id in doc_ids)
                or len(set(doc_ids)) != len(doc_ids)
                or not set(doc_ids).issubset(local_doc_ids)
            ):
                raise ValidationError(f"{museum_id}: invalid span doc_ids")
            span_id = f"{museum_id}:{index:03d}"
            spans.append({
                "museum_id": museum_id,
                "span_id": span_id,
                "properties": {"span_id": span_id, "start": start, "end": end, "text": text[start:end]},
            })
            evidence.extend({"span_id": span_id, "doc_id": doc_id} for doc_id in doc_ids)

        properties = _museum_properties(row, museum_id)
        latitude, longitude = properties["latitude"], properties["longitude"]
        if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValidationError(f"{museum_id}: invalid coordinates")
        museums.append({
            "museum_id": museum_id,
            "sido": row["sido"],
            "sigungu": row["sigungu"],
            "region_key": json.dumps([row["sido"], row["sigungu"]], ensure_ascii=False),
            "properties": properties,
        })

    if not museums:
        raise ValidationError("CSV has no museum rows")
    return ParsedData(museums=museums, sources=sources, spans=spans, evidence=evidence)


def parse_csv(path: Path) -> ParsedData:
    """Read a UTF-8 CSV and validate the complete file."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            return parse_rows(csv.DictReader(file))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationError(f"cannot read CSV {path}: {exc}") from exc
