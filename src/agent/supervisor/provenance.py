"""Match retrieved full text to the source records in the original CSV."""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from src.region_aliases import canonicalize_sido


DEFAULT_PROVENANCE_CSV = Path(__file__).resolve().parents[3] / "data/processed/museum_final_738.csv"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
METADATA_FIELDS = ("name", "sido", "sigungu", "address", "ownership_type", "adult_fee", "youth_fee",
                   "child_fee", "adult_fee_status", "weekday_open", "weekday_close", "holiday_open",
                   "holiday_close", "closure_rule_raw",
                   # Lets the verifier check ontology-filter matches (metadata.structured_match).
                   "amenities_raw")
FEE_FIELDS = {"adult_fee", "youth_fee", "child_fee"}


def _same_value(field: str, left: Any, right: str) -> bool:
    if isinstance(left, bool):
        return False
    if field in FEE_FIELDS:
        try:
            a, b = Decimal(str(left).strip()), Decimal(right.strip())
            return a.is_finite() and b.is_finite() and a == b
        except (InvalidOperation, ValueError):
            return False
    if field == "sido" and isinstance(left, str):
        return canonicalize_sido(left) == canonicalize_sido(right)
    return isinstance(left, str) and left.strip() == right.strip()


def _http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


class CsvProvenanceIndex:
    """Attach recorded source documents only when ID and full text agree.

    Source spans must cover every non-whitespace character. Invalid, duplicate,
    missing or stale records never produce provenance. This traces the stored
    source; it does not assert that the source or the facts were human verified.
    """

    def __init__(self, path: str | Path = DEFAULT_PROVENANCE_CSV):
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] | None = None
        self.error: str | None = None

    @property
    def status(self) -> str:
        if self._records is None:
            return "not_checked"
        return "unavailable" if self.error else "ready"

    @staticmethod
    def _parse(row: Mapping[str, str]) -> dict[str, Any] | None:
        museum_id, text, expected_hash = (row.get(key, "") for key in ("museum_id", "text", "text_sha256"))
        if not museum_id or not text or hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_hash:
            return None
        try:
            documents = json.loads(row.get("source_documents_json", ""))
            spans = json.loads(row.get("text_spans_json", ""))
        except (TypeError, ValueError):
            return None
        if not isinstance(documents, list) or not isinstance(spans, list) or not spans:
            return None
        by_id = {}
        for doc in documents:
            if not isinstance(doc, dict) or not isinstance(doc.get("doc_id"), str) or not doc["doc_id"].strip():
                return None
            if doc["doc_id"] in by_id:
                return None
            by_id[doc["doc_id"]] = doc
        coverage = bytearray(len(text))
        referenced = []
        for span in spans:
            if not isinstance(span, dict):
                return None
            start, end, ids = span.get("start"), span.get("end"), span.get("doc_ids")
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or not isinstance(ids, list) or not ids
                    or any(not isinstance(doc_id, str) or doc_id not in by_id for doc_id in ids)):
                return None
            coverage[start:end] = b"\x01" * (end - start)
            for doc_id in ids:
                if doc_id not in referenced:
                    referenced.append(doc_id)
        if any(not covered and not char.isspace() for covered, char in zip(coverage, text)):
            return None
        details = []
        for doc_id in referenced:
            doc = by_id[doc_id]
            detail = {key: doc[key] for key in (
                "doc_id", "source_type", "source_record_id", "source_locator", "source_url", "match_trust"
            ) if isinstance(doc.get(key), str) and doc[key]}
            if "source_url" in detail and not _http_url(detail["source_url"]):
                del detail["source_url"]
            details.append(detail)
        return {"text": text, "source_doc_ids": referenced, "source_documents": details, "source_spans": spans}

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._records is not None:
            return self._records
        records: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"museum_id", "text", "text_sha256", "source_documents_json", "text_spans_json"}
                if not required.issubset(reader.fieldnames or ()):
                    raise ValueError("CSV is missing provenance columns")
                for record_number, row in enumerate(reader, start=2):
                    museum_id = row.get("museum_id", "")
                    if museum_id in seen:
                        records.pop(museum_id, None)
                        continue
                    seen.add(museum_id)
                    parsed = self._parse(row)
                    if parsed is not None:
                        parsed["record_number"] = record_number
                        parsed["metadata_fields"] = {key: row[key].strip() for key in METADATA_FIELDS
                                                     if isinstance(row.get(key), str) and row[key].strip()}
                        parsed["base_data_date"] = (row.get("base_data_date") or "").strip()
                        records[museum_id] = parsed
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            self.error = type(exc).__name__
            records = {}
        self._records = records
        return records

    def attach(self, item: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(item)
        result.pop("metadata_provenance", None)
        if isinstance(result.get("metadata"), Mapping):
            result["metadata"] = dict(result["metadata"])
            result["metadata"].pop("metadata_provenance", None)
        record = self._load().get(item.get("museum_id"))
        text = item.get("text") or item.get("document")
        if record is None or text != record["text"]:
            return result
        result["source_doc_ids"] = list(record["source_doc_ids"])
        result["source_scope"] = "text"
        result["source_documents"] = [dict(doc) for doc in record["source_documents"]]
        result["source_spans"] = [dict(span) for span in record["source_spans"]]
        urls = [doc.get("source_url", "") for doc in record["source_documents"]]
        result["source_urls"] = list(dict.fromkeys(url for url in urls if _http_url(url)))
        locators = [doc.get("source_locator", "") for doc in record["source_documents"]]
        result["source_locator"] = next((locator for locator in locators if locator), "")
        metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}
        fields = record["metadata_fields"]
        conflicts = any(
            not _same_value(key, supplied, value)
            for key, value in fields.items()
            for supplied in (result.get(key), metadata.get(key))
            if supplied is not None and supplied != ""
        )
        if fields and not conflicts:
            try:
                locator = self.path.resolve().relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                locator = str(self.path.resolve())
            result["metadata_provenance"] = {
                "source_kind": "derived_csv_row", "source_locator": f"{locator}#record={record['record_number']}",
                "fields": dict(fields), "base_data_date": record["base_data_date"],
                "trust": "derived_dataset_not_human_verified",
            }
            source_sido = fields.get("sido", "")
            for supplied in (result.get("sido"), metadata.get("sido")):
                if (source_sido and isinstance(supplied, str) and supplied.strip()
                        and supplied.strip() != source_sido
                        and _same_value("sido", supplied, source_sido)):
                    result["metadata_provenance"]["normalizations"] = {
                        "sido": {"source_value": source_sido, "matched_value": supplied.strip(),
                                 "rule": "configured_sido_alias"}
                    }
                    break
        return result
