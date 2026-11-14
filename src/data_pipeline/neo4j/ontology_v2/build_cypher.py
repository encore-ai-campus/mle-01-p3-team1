#!/usr/bin/env python3
"""Generate additive ontology v2 Cypher scripts from the read-only museum CSV.

The CSV is only read. The generated scripts add new labels, relationships and
Museum properties to the existing graph; they never modify or delete the
existing Museum/Sido/Sigungu/SourceDocument/TextSpan data. Every new node and
relationship carries ontology_version = "v2" so 99_rollback.cypher can remove
exactly what was added.

From the repository root:
    uv run python -m src.data_pipeline.neo4j.ontology_v2.build_cypher
    uv run python -m src.data_pipeline.neo4j.ontology_v2.build_cypher --out outputs/neo4j/ontology_v2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from ..parsing import parse_csv
from .rules import (
    AMENITY_CATEGORIES,
    FACILITY_THEME,
    ONTOLOGY_VERSION,
    THEMES,
    TOPICS,
    Org,
    classify_facility_type,
    is_self_named,
    map_amenity_token,
    match_activity_types,
    match_topics,
    parse_closure,
    resolve_org,
    split_amenity_tokens,
)

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CSV = ROOT / "data" / "processed" / "museum_final_738.csv"
DEFAULT_OUT = ROOT / "outputs" / "neo4j" / "ontology_v2"
CHUNK_SIZE = 200
V = ONTOLOGY_VERSION

OPENING_PROPERTIES = (
    "closure_weekdays", "open_all_year", "closed_new_year", "closed_seollal",
    "closed_chuseok", "closed_public_holidays", "holiday_closure_exception",
    "closure_parse_status", "closure_parse_method",
)
ADDED_MUSEUM_PROPERTIES = (
    "facility_type", "facility_type_method",
    "activity_types", "activity_evidence_span_ids", "activity_method",
    *OPENING_PROPERTIES,
)


# ---------------------------------------------------------------------------
# Cypher literal helpers
# ---------------------------------------------------------------------------


def lit(value: Any) -> str:
    """Render a Python value as a Cypher literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(lit(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {lit(item)}" for key, item in value.items()) + "}"
    raise TypeError(f"unsupported Cypher literal: {type(value)!r}")


def unwind(rows: list[dict], body: str) -> list[str]:
    """Split rows into UNWIND statements of CHUNK_SIZE rows."""
    statements = []
    for start in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[start:start + CHUNK_SIZE]
        literal = "[\n  " + ",\n  ".join(lit(row) for row in chunk) + "\n]"
        statements.append(f"UNWIND {literal} AS row\n{body.strip()}")
    return statements


def write_script(path: Path, header: str, statements: Iterable[str]) -> int:
    statements = list(statements)
    comment = "\n".join(f"// {line}" if line else "//" for line in header.strip().splitlines())
    path.write_text(comment + "\n\n" + ";\n\n".join(statements) + ";\n", encoding="utf-8")
    return len(statements)


# ---------------------------------------------------------------------------
# Derivation from the CSV
# ---------------------------------------------------------------------------


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def build_organizations(rows: list[dict[str, str]]) -> dict[str, Any]:
    orgs: dict[str, Org] = {}
    raw_names: dict[str, set[str]] = defaultdict(set)
    edges: dict[tuple[str, str], str] = {}
    operated: list[dict] = []
    managed: list[dict] = []
    skipped: Counter[str] = Counter()

    def register(org: Org) -> None:
        existing = orgs.get(org.org_key)
        if existing and existing != org:
            # Same identity reached through different rules: keep the most specific level.
            if existing.level == "기관" and org.level != "기관":
                orgs[org.org_key] = org
            return
        orgs.setdefault(org.org_key, org)

    for row in rows:
        resolutions = {}
        for column in ("operator_name", "manager_name"):
            raw = row.get(column) or ""
            if not raw.strip():
                continue
            resolution = resolve_org(raw, row["sido"])
            if resolution is None:
                skipped[raw.strip()] += 1
                continue
            resolutions[column] = resolution
            register(resolution.org)
            raw_names[resolution.org.org_key].add(resolution.raw_name)
            for child, parent in resolution.edges:
                register(child)
                register(parent)
                edges[(child.org_key, parent.org_key)] = resolution.method

        operator = resolutions.get("operator_name")
        manager = resolutions.get("manager_name")
        if operator:
            operated.append({
                "museum_id": row["museum_id"],
                "org_key": operator.org.org_key,
                "raw_name": operator.raw_name,
                "self_named": is_self_named(operator.raw_name, row["name"]),
                "method": operator.method,
            })
        if manager:
            managed.append({
                "museum_id": row["museum_id"],
                "org_key": manager.org.org_key,
                "raw_name": manager.raw_name,
                "same_as_operator": bool(operator) and operator.org.org_key == manager.org.org_key,
                "method": manager.method,
            })

    nodes = [
        {
            "org_key": org.org_key,
            "name": org.name,
            "org_type": org.org_type,
            "level": org.level,
            "sido": org.sido,
            "raw_names": sorted(raw_names.get(key, ())),
        }
        for key, org in sorted(orgs.items())
    ]
    part_of = [
        {"child_key": child, "parent_key": parent, "method": method}
        for (child, parent), method in sorted(edges.items())
        if child != parent
    ]
    return {"nodes": nodes, "part_of": part_of, "operated": operated, "managed": managed, "skipped": skipped}


def build_amenities(rows: list[dict[str, str]]) -> dict[str, Any]:
    links: list[dict] = []
    unmapped: Counter[str] = Counter()
    for row in rows:
        mapped: dict[str, list[str]] = defaultdict(list)
        for token in split_amenity_tokens(row.get("amenities_raw")):
            names = map_amenity_token(token)
            if not names:
                unmapped[token] += 1
            for name in names:
                if token not in mapped[name]:
                    mapped[name].append(token)
        links.extend(
            {"museum_id": row["museum_id"], "amenity": name, "raw_tokens": tokens}
            for name, tokens in mapped.items()
        )
    nodes = [{"name": name, "category": category} for name, category in AMENITY_CATEGORIES.items()]
    return {"nodes": nodes, "links": links, "unmapped": unmapped}


def build_topics(rows: list[dict[str, str]], spans_by_museum: dict[str, list[tuple[str, str]]]) -> dict[str, Any]:
    links: list[dict] = []
    mentions: list[dict] = []
    activities: list[dict] = []
    for row in rows:
        museum_id = row["museum_id"]
        spans = spans_by_museum.get(museum_id, [])
        for match in match_topics(row["name"], spans):
            links.append({
                "museum_id": museum_id,
                "topic": match.topic,
                "hit_count": match.hit_count,
                "name_hit": match.name_hit,
                "matched_terms": list(match.terms),
                "evidence_span_ids": list(match.span_ids),
                "confidence": match.confidence,
            })
            mentions.extend({"span_id": span_id, "topic": match.topic} for span_id in match.span_ids)
        found = match_activity_types(spans)
        if found:
            evidence = sorted({span_id for span_ids in found.values() for span_id in span_ids})
            activities.append({
                "museum_id": museum_id,
                "activity_types": list(found),
                "evidence_span_ids": evidence,
            })
    topics = [
        {"name": name, "theme": theme, "keywords": list(keywords)}
        for name, (theme, keywords) in TOPICS.items()
    ]
    return {"topics": topics, "links": links, "mentions": mentions, "activities": activities}


# ---------------------------------------------------------------------------
# Script bodies
# ---------------------------------------------------------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT organization_key_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.org_key IS UNIQUE",
    "CREATE CONSTRAINT amenity_name_unique IF NOT EXISTS FOR (a:Amenity) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT theme_name_unique IF NOT EXISTS FOR (t:Theme) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
    "CREATE INDEX museum_facility_type IF NOT EXISTS FOR (m:Museum) ON (m.facility_type)",
    "CREATE INDEX organization_type IF NOT EXISTS FOR (o:Organization) ON (o.org_type)",
]


def facility_statements(rows: list[dict[str, str]]) -> tuple[list[str], Counter[str]]:
    data = []
    counts: Counter[str] = Counter()
    for row in rows:
        facility_type, method = classify_facility_type(row["name"])
        counts[facility_type] += 1
        data.append({"museum_id": row["museum_id"], "facility_type": facility_type, "method": method})
    body = """
MATCH (m:Museum {museum_id: row.museum_id})
SET m.facility_type = row.facility_type,
    m.facility_type_method = row.method"""
    return unwind(data, body), counts


def organization_statements(org: dict[str, Any]) -> list[str]:
    statements = unwind(org["nodes"], f"""
MERGE (o:Organization {{org_key: row.org_key}})
SET o.name = row.name,
    o.org_type = row.org_type,
    o.level = row.level,
    o.sido = row.sido,
    o.raw_names = row.raw_names,
    o.classification_method = "org_type_rule_v1",
    o.verification_status = "UNVERIFIED",
    o.ontology_version = "{V}" """)
    statements += unwind(org["part_of"], f"""
MATCH (c:Organization {{org_key: row.child_key}})
MATCH (p:Organization {{org_key: row.parent_key}})
MERGE (c)-[r:PART_OF_ORG]->(p)
SET r.method = row.method,
    r.verification_status = "UNVERIFIED",
    r.ontology_version = "{V}" """)
    statements += unwind(org["operated"], f"""
MATCH (m:Museum {{museum_id: row.museum_id}})
MATCH (o:Organization {{org_key: row.org_key}})
MERGE (m)-[r:OPERATED_BY]->(o)
SET r.raw_name = row.raw_name,
    r.source_column = "operator_name",
    r.self_named = row.self_named,
    r.resolution_method = row.method,
    r.verification_status = "SOURCE_RECORDED",
    r.ontology_version = "{V}" """)
    statements += unwind(org["managed"], f"""
MATCH (m:Museum {{museum_id: row.museum_id}})
MATCH (o:Organization {{org_key: row.org_key}})
MERGE (m)-[r:MANAGED_BY]->(o)
SET r.raw_name = row.raw_name,
    r.source_column = "manager_name",
    r.same_as_operator = row.same_as_operator,
    r.resolution_method = row.method,
    r.verification_status = "UNVERIFIED",
    r.ontology_version = "{V}" """)
    return statements


def amenity_statements(amenity: dict[str, Any]) -> list[str]:
    statements = unwind(amenity["nodes"], f"""
MERGE (a:Amenity {{name: row.name}})
SET a.category = row.category,
    a.ontology_version = "{V}" """)
    statements += unwind(amenity["links"], f"""
MATCH (m:Museum {{museum_id: row.museum_id}})
MATCH (a:Amenity {{name: row.amenity}})
MERGE (m)-[r:HAS_AMENITY]->(a)
SET r.raw_tokens = row.raw_tokens,
    r.source_column = "amenities_raw",
    r.method = "amenity_dict_v1",
    r.ontology_version = "{V}" """)
    return statements


def topic_statements(topic: dict[str, Any]) -> list[str]:
    statements = unwind([{"name": name} for name in THEMES], f"""
MERGE (t:Theme {{name: row.name}})
SET t.ontology_version = "{V}" """)
    statements += unwind(topic["topics"], f"""
MERGE (t:Topic {{name: row.name}})
SET t.keywords = row.keywords,
    t.ontology_version = "{V}"
WITH t, row
MATCH (th:Theme {{name: row.theme}})
MERGE (t)-[r:BELONGS_TO]->(th)
SET r.ontology_version = "{V}" """)
    statements += unwind(topic["links"], f"""
MATCH (m:Museum {{museum_id: row.museum_id}})
MATCH (t:Topic {{name: row.topic}})
MERGE (m)-[r:HAS_TOPIC]->(t)
SET r.hit_count = row.hit_count,
    r.name_hit = row.name_hit,
    r.matched_terms = row.matched_terms,
    r.evidence_span_ids = row.evidence_span_ids,
    r.confidence = row.confidence,
    r.method = "topic_keyword_v1",
    r.verification_status = "UNVERIFIED",
    r.ontology_version = "{V}" """)
    statements += unwind(topic["mentions"], f"""
MATCH (s:TextSpan {{span_id: row.span_id}})
MATCH (t:Topic {{name: row.topic}})
MERGE (s)-[r:MENTIONS_TOPIC]->(t)
SET r.method = "topic_keyword_v1",
    r.ontology_version = "{V}" """)
    statements.append(f"""MATCH (m:Museum)-[:HAS_TOPIC]->(:Topic)-[:BELONGS_TO]->(th:Theme)
WITH DISTINCT m, th
MERGE (m)-[r:HAS_THEME]->(th)
SET r.via_topic = true,
    r.ontology_version = "{V}" """.strip())
    statements += unwind(
        [{"facility_type": ft, "theme": theme} for ft, theme in FACILITY_THEME.items()],
        f"""
MATCH (m:Museum {{facility_type: row.facility_type}})
MATCH (th:Theme {{name: row.theme}})
MERGE (m)-[r:HAS_THEME]->(th)
SET r.via_facility_type = true,
    r.ontology_version = "{V}" """,
    )
    return statements


def activity_statements(topic: dict[str, Any]) -> list[str]:
    return unwind(topic["activities"], """
MATCH (m:Museum {museum_id: row.museum_id})
SET m.activity_types = row.activity_types,
    m.activity_evidence_span_ids = row.evidence_span_ids,
    m.activity_method = "activity_keyword_v1" """)


def opening_statements(rows: list[dict[str, str]]) -> tuple[list[str], Counter[str]]:
    data = []
    status: Counter[str] = Counter()
    for row in rows:
        parsed = parse_closure(row.get("closure_rule_raw"))
        parsed["closure_parse_method"] = "closure_rule_v1"
        status[parsed["closure_parse_status"]] += 1
        data.append({"museum_id": row["museum_id"], "props": parsed})
    body = """
MATCH (m:Museum {museum_id: row.museum_id})
SET m += row.props"""
    return unwind(data, body), status


def verify_statements(expected: dict[str, int]) -> list[str]:
    checks = [
        ("Organization nodes", "MATCH (n:Organization {ontology_version: 'v2'})", "n"),
        ("OPERATED_BY", "MATCH (:Museum)-[r:OPERATED_BY {ontology_version: 'v2'}]->(:Organization)", "r"),
        ("MANAGED_BY", "MATCH (:Museum)-[r:MANAGED_BY {ontology_version: 'v2'}]->(:Organization)", "r"),
        ("PART_OF_ORG", "MATCH (:Organization)-[r:PART_OF_ORG {ontology_version: 'v2'}]->(:Organization)", "r"),
        ("Amenity nodes", "MATCH (n:Amenity {ontology_version: 'v2'})", "n"),
        ("HAS_AMENITY", "MATCH (:Museum)-[r:HAS_AMENITY {ontology_version: 'v2'}]->(:Amenity)", "r"),
        ("Theme nodes", "MATCH (n:Theme {ontology_version: 'v2'})", "n"),
        ("Topic nodes", "MATCH (n:Topic {ontology_version: 'v2'})", "n"),
        ("HAS_TOPIC", "MATCH (:Museum)-[r:HAS_TOPIC {ontology_version: 'v2'}]->(:Topic)", "r"),
        ("MENTIONS_TOPIC", "MATCH (:TextSpan)-[r:MENTIONS_TOPIC {ontology_version: 'v2'}]->(:Topic)", "r"),
        ("Museums with facility_type", "MATCH (n:Museum) WHERE n.facility_type IS NOT NULL", "n"),
        ("Museums with closure_parse_status", "MATCH (n:Museum) WHERE n.closure_parse_status IS NOT NULL", "n"),
        ("Museums with activity_types", "MATCH (n:Museum) WHERE n.activity_types IS NOT NULL", "n"),
    ]
    union = "\nUNION ALL\n".join(
        # Aggregate first: a constant next to count() is a grouping key and would
        # return no row at all when nothing matches.
        f"{match} WITH count({var}) AS value "
        f"RETURN {lit(name)} AS check, value, {expected.get(name, 'null')} AS expected"
        for name, match, var in checks
    )
    existing = """
MATCH (m:Museum) WITH count(m) AS museums
MATCH (s:Sido) WITH museums, count(s) AS sidos
MATCH (g:Sigungu) WITH museums, sidos, count(g) AS sigungu
MATCH (d:SourceDocument) WITH museums, sidos, sigungu, count(d) AS sources
MATCH (t:TextSpan)
RETURN museums, sidos, sigungu, sources, count(t) AS spans,
       [738, 20, 199, 1027, 3260] AS expected_unchanged""".strip()
    samples = """
MATCH (m:Museum {name: "박진전쟁기념관"})
OPTIONAL MATCH (m)-[:OPERATED_BY]->(op:Organization)
OPTIONAL MATCH (m)-[:MANAGED_BY]->(mg:Organization)
OPTIONAL MATCH (m)-[ht:HAS_TOPIC]->(tp:Topic)-[:BELONGS_TO]->(th:Theme)
RETURN m.name, m.facility_type, m.closure_weekdays, m.activity_types,
       op.name AS operator, mg.name AS manager,
       collect(DISTINCT [tp.name, th.name, ht.confidence]) AS topics""".strip()
    return [union, existing, samples]


def rollback_statements() -> list[str]:
    museum_props = ", ".join(f"m.{name}" for name in ADDED_MUSEUM_PROPERTIES)
    return [
        "MATCH ()-[r]->() WHERE r.ontology_version = 'v2' DELETE r",
        "MATCH (n) WHERE n.ontology_version = 'v2' AND (n:Organization OR n:Amenity OR n:Theme OR n:Topic) DETACH DELETE n",
        f"MATCH (m:Museum) REMOVE {museum_props}",
        "DROP CONSTRAINT organization_key_unique IF EXISTS",
        "DROP CONSTRAINT amenity_name_unique IF EXISTS",
        "DROP CONSTRAINT theme_name_unique IF EXISTS",
        "DROP CONSTRAINT topic_name_unique IF EXISTS",
        "DROP INDEX museum_facility_type IF EXISTS",
        "DROP INDEX organization_type IF EXISTS",
    ]


# ---------------------------------------------------------------------------
# Review files
# ---------------------------------------------------------------------------


def write_csv(path: Path, header: list[str], rows: Iterable[Iterable[Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def write_review(out: Path, rows: list[dict[str, str]], org: dict, amenity: dict, topic: dict) -> None:
    review = out / "review"
    review.mkdir(parents=True, exist_ok=True)
    museum_names = {row["museum_id"]: row["name"] for row in rows}
    usage: dict[str, Counter[str]] = defaultdict(Counter)
    for link in org["operated"]:
        usage[link["org_key"]]["operated"] += 1
    for link in org["managed"]:
        usage[link["org_key"]]["managed"] += 1
    parents = {edge["child_key"]: edge["parent_key"] for edge in org["part_of"]}
    write_csv(
        review / "organizations.csv",
        ["org_key", "name", "org_type", "level", "sido", "parent_key", "operated", "managed", "raw_names"],
        (
            [node["org_key"], node["name"], node["org_type"], node["level"], node["sido"] or "",
             parents.get(node["org_key"], ""), usage[node["org_key"]]["operated"],
             usage[node["org_key"]]["managed"], " | ".join(node["raw_names"])]
            for node in org["nodes"]
        ),
    )
    write_csv(review / "amenity_unmapped_tokens.csv", ["token", "count"], amenity["unmapped"].most_common())
    write_csv(
        review / "museum_topics.csv",
        ["museum_id", "name", "topic", "theme", "confidence", "hit_count", "name_hit", "matched_terms", "evidence_span_ids"],
        (
            [link["museum_id"], museum_names[link["museum_id"]], link["topic"], TOPICS[link["topic"]][0],
             link["confidence"], link["hit_count"], link["name_hit"], " | ".join(link["matched_terms"]),
             " | ".join(link["evidence_span_ids"])]
            for link in topic["links"]
        ),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build(csv_path: Path, out: Path) -> dict[str, Any]:
    rows = read_rows(csv_path)
    parsed = parse_csv(csv_path)  # same validation and span ids as the original loader
    spans_by_museum: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for span in parsed.spans:
        spans_by_museum[span["museum_id"]].append((span["span_id"], span["properties"]["text"]))

    csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    org = build_organizations(rows)
    amenity = build_amenities(rows)
    topic = build_topics(rows, spans_by_museum)
    facility, facility_counts = facility_statements(rows)
    opening, opening_status = opening_statements(rows)

    out.mkdir(parents=True, exist_ok=True)
    source = f"source: {csv_path.name} (sha256 {csv_sha256[:16]}…), read-only"
    scripts = {
        "00_constraints.cypher": ("Ontology v2 constraints and indexes (idempotent).", CONSTRAINTS),
        "01_facility_type.cypher": (
            "Museum.facility_type from the facility name (property only, no new nodes).", facility),
        "02_organization.cypher": (
            "Organization nodes + OPERATED_BY / MANAGED_BY / PART_OF_ORG.\n"
            "operator_name and manager_name stay separate relationships.\n"
            "MANAGED_BY and PART_OF_ORG are UNVERIFIED name-rule results.",
            organization_statements(org)),
        "03_amenity.cypher": (
            "Amenity controlled vocabulary + HAS_AMENITY from amenities_raw.\n"
            "No HAS_AMENITY edge means 'not recorded', not 'not available'.",
            amenity_statements(amenity)),
        "04_theme_topic.cypher": (
            "Theme / Topic hierarchy, HAS_TOPIC (keyword evidence), TextSpan-[:MENTIONS_TOPIC]->Topic,\n"
            "and derived HAS_THEME (via topic or facility type). All keyword links are UNVERIFIED.",
            topic_statements(topic)),
        "05_activity_types.cypher": (
            "Museum.activity_types (체험/교육/공연/해설) kept apart from Theme, with evidence span ids.",
            activity_statements(topic)),
        "06_opening_rule.cypher": (
            "Museum closure properties parsed from closure_rule_raw (static rules, not real-time status).",
            opening),
    }
    statement_counts = {}
    for filename, (header, statements) in scripts.items():
        statement_counts[filename] = write_script(out / filename, f"{header}\n{source}", statements)

    expected = {
        "Organization nodes": len(org["nodes"]),
        "OPERATED_BY": len(org["operated"]),
        "MANAGED_BY": len(org["managed"]),
        "PART_OF_ORG": len(org["part_of"]),
        "Amenity nodes": len(amenity["nodes"]),
        "HAS_AMENITY": len(amenity["links"]),
        "Theme nodes": len(THEMES),
        "Topic nodes": len(topic["topics"]),
        "HAS_TOPIC": len(topic["links"]),
        "MENTIONS_TOPIC": len({(m["span_id"], m["topic"]) for m in topic["mentions"]}),
        "Museums with facility_type": len(rows),
        "Museums with closure_parse_status": len(rows),
        "Museums with activity_types": len(topic["activities"]),
    }
    write_script(out / "90_verify.cypher", "Read-only checks after 00-06. 'expected' comes from the generator.",
                 verify_statements(expected))
    write_script(out / "99_rollback.cypher",
                 "Removes only what ontology v2 added (ontology_version = 'v2' + listed Museum properties).",
                 rollback_statements())
    write_review(out, rows, org, amenity, topic)

    summary = {
        "csv": str(csv_path),
        "csv_sha256": csv_sha256,
        "expected": expected,
        "statements": statement_counts,
        "facility_type": dict(facility_counts.most_common()),
        "org_type": dict(Counter(node["org_type"] for node in org["nodes"]).most_common()),
        "self_named_operators": sum(link["self_named"] for link in org["operated"]),
        "skipped_org_values": dict(org["skipped"]),
        "museums_with_amenity": len({link["museum_id"] for link in amenity["links"]}),
        "museums_with_topic": len({link["museum_id"] for link in topic["links"]}),
        "topic_confidence": dict(Counter(link["confidence"] for link in topic["links"])),
        "closure_parse_status": dict(opening_status),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    summary = build(args.csv, args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nCypher scripts written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
