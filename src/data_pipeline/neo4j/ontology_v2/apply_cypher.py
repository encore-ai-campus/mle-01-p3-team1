#!/usr/bin/env python3
"""Apply, verify or roll back the generated ontology v2 Cypher scripts.

Reads Neo4j settings from .env (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
NEO4J_DATABASE), like load_neo4j.py. Generate the scripts first with
build_cypher.py.

From the repository root:
    uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --dry-run
    uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher
    uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --verify-only
    uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --rollback --yes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .build_cypher import DEFAULT_CSV, DEFAULT_OUT, ROOT

APPLY_FILES = (
    "00_constraints.cypher",
    "01_facility_type.cypher",
    "02_organization.cypher",
    "03_amenity.cypher",
    "04_theme_topic.cypher",
    "05_activity_types.cypher",
    "06_opening_rule.cypher",
)
VERIFY_FILE = "90_verify.cypher"
ROLLBACK_FILE = "99_rollback.cypher"

# The existing graph that ontology v2 builds on; it must not change.
BASE_COUNTS = {"museums": 738, "sidos": 20, "sigungu": 199, "sources": 1027, "spans": 3260}
BASE_COUNT_QUERY = """
MATCH (m:Museum) WITH count(m) AS museums
MATCH (s:Sido) WITH museums, count(s) AS sidos
MATCH (g:Sigungu) WITH museums, sidos, count(g) AS sigungu
MATCH (d:SourceDocument) WITH museums, sidos, sigungu, count(d) AS sources
MATCH (t:TextSpan)
RETURN museums, sidos, sigungu, sources, count(t) AS spans"""
V2_LEFTOVER_QUERY = """
CALL { MATCH (n) WHERE n.ontology_version = 'v2' RETURN count(n) AS nodes }
CALL { MATCH ()-[r]->() WHERE r.ontology_version = 'v2' RETURN count(r) AS rels }
CALL { MATCH (m:Museum) WHERE m.facility_type IS NOT NULL OR m.closure_parse_status IS NOT NULL
          OR m.activity_types IS NOT NULL RETURN count(m) AS museum_props }
RETURN nodes, rels, museum_props"""
SCHEMA_RE = re.compile(r"^(CREATE|DROP)\s+(CONSTRAINT|INDEX)\b", re.IGNORECASE)


class ApplyError(RuntimeError):
    """Preflight or verification failed."""


def read_statements(path: Path) -> list[str]:
    """Split a generated script into statements (comments removed)."""
    body = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("//"))
    statements = []
    for chunk in body.split(";\n\n"):
        chunk = chunk.strip()
        if chunk.endswith(";"):
            chunk = chunk[:-1].rstrip()
        if chunk:
            statements.append(chunk)
    return statements


def kst_now() -> str:
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(message, flush=True)


def check_scripts(script_dir: Path, csv_path: Path, names: list[str]) -> dict[str, Any]:
    """Offline checks: files exist and were generated from the current CSV."""
    missing = [name for name in names if not (script_dir / name).is_file()]
    summary_path = script_dir / "summary.json"
    if missing or not summary_path.is_file():
        raise ApplyError(
            f"생성된 스크립트가 없습니다: {missing or ['summary.json']}. "
            "먼저 build_cypher를 실행하세요."
        )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    current = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if summary.get("csv_sha256") != current:
        raise ApplyError("CSV가 스크립트 생성 이후 바뀌었습니다. build_cypher로 다시 생성하세요.")
    return summary


def connect():
    from dotenv import load_dotenv

    from src.agent.neo4j_tls import load_graph_database

    load_dotenv(ROOT / ".env")
    required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ApplyError(f".env에 Neo4j 설정이 없습니다: {', '.join(missing)}")
    driver = load_graph_database().driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        connection_timeout=15,
        notifications_min_severity="OFF",
    )
    driver.verify_connectivity()
    return driver, os.environ["NEO4J_DATABASE"]


def base_counts(session) -> dict[str, int]:
    return dict(session.run(BASE_COUNT_QUERY).single())


def require_base_unchanged(session, when: str) -> dict[str, int]:
    counts = base_counts(session)
    if counts != BASE_COUNTS:
        raise ApplyError(f"{when}: 기존 그래프 개수가 예상과 다릅니다. 실제 {counts}, 예상 {BASE_COUNTS}")
    return counts


def explain_all(session, script_dir: Path, names: list[str]) -> dict[str, int]:
    compiled = {}
    for name in names:
        count = 0
        for statement in read_statements(script_dir / name):
            if SCHEMA_RE.match(statement):
                continue
            session.run("EXPLAIN " + statement).consume()
            count += 1
        compiled[name] = count
        log(f"  EXPLAIN {name}: {count}개 컴파일")
    return compiled


def run_file(session, path: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    statements = read_statements(path)
    started = time.perf_counter()
    for index, statement in enumerate(statements, 1):
        counters = session.execute_write(lambda tx, q=statement: tx.run(q).consume().counters)
        for key in ("nodes_created", "nodes_deleted", "relationships_created", "relationships_deleted",
                    "properties_set", "constraints_added", "constraints_removed", "indexes_added", "indexes_removed"):
            value = getattr(counters, key, 0)
            if value:
                totals[key] = totals.get(key, 0) + value
        log(f"  {path.name} [{index}/{len(statements)}]")
    log(f"  {path.name} 완료 ({time.perf_counter() - started:.1f}s) {totals}")
    return totals


def verify(session, script_dir: Path) -> dict[str, Any]:
    checks_query = read_statements(script_dir / VERIFY_FILE)[0]
    rows = [dict(record) for record in session.run(checks_query)]
    mismatches = [row for row in rows if row["value"] != row["expected"]]
    width = max(len(row["check"]) for row in rows)
    for row in rows:
        mark = "OK " if row["value"] == row["expected"] else "XX "
        log(f"  {mark}{row['check']:<{width}}  {row['value']:>6} / {row['expected']}")
    base = base_counts(session)
    log(f"  기존 그래프: {base} ({'불변' if base == BASE_COUNTS else '변경됨!'})")
    return {"checks": rows, "mismatches": mismatches, "base_counts": base, "base_unchanged": base == BASE_COUNTS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ontology v2 Cypher scripts to Neo4j.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_OUT, help="build_cypher 출력 폴더")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="쓰기 없이 사전 점검 + EXPLAIN 컴파일만")
    mode.add_argument("--verify-only", action="store_true", help="적재 결과 검증만")
    mode.add_argument("--rollback", action="store_true", help="v2에서 추가한 것만 삭제 (--yes 필요)")
    parser.add_argument("--only", nargs="+", metavar="NN", help="일부 파일만 적용 (예: --only 02 03)")
    parser.add_argument("--yes", action="store_true", help="--rollback 실행 확인")
    args = parser.parse_args(argv)

    names = list(APPLY_FILES)
    if args.only:
        names = [name for name in APPLY_FILES if name[:2] in set(args.only)]
        if not names:
            parser.error(f"--only 값과 맞는 파일이 없습니다: {args.only}")
    if args.rollback and not args.yes:
        parser.error("--rollback은 v2 노드·관계·속성을 삭제합니다. 실행하려면 --yes를 함께 주세요.")

    mode_name = ("dry-run" if args.dry_run else "verify-only" if args.verify_only
                 else "rollback" if args.rollback else "apply")
    result: dict[str, Any] = {"mode": mode_name, "status": "error", "started_at": kst_now(), "files": names}
    try:
        needed = [ROLLBACK_FILE] if args.rollback else [*names, VERIFY_FILE]
        summary = check_scripts(args.dir, args.csv, needed)
        result["csv_sha256"] = summary["csv_sha256"]
        log(f"[{mode_name}] 스크립트: {args.dir}")

        driver, database = connect()
        result["database"] = database
        with driver, driver.session(database=database) as session:
            log(f"  연결: {os.environ['NEO4J_URI']} / {database}")
            if args.dry_run:
                require_base_unchanged(session, "사전 점검")
                result["explain"] = explain_all(session, args.dir, names)
                log("dry-run 완료: 쓰기는 하지 않았습니다.")
            elif args.verify_only:
                result["verify"] = verify(session, args.dir)
                if result["verify"]["mismatches"] or not result["verify"]["base_unchanged"]:
                    raise ApplyError("검증 불일치가 있습니다 (적재 전이라면 정상입니다).")
            elif args.rollback:
                result["counters"] = run_file(session, args.dir / ROLLBACK_FILE)
                leftover = dict(session.run(V2_LEFTOVER_QUERY).single())
                result["leftover"] = leftover
                result["base_counts"] = require_base_unchanged(session, "롤백 후")
                log(f"  남은 v2 항목: {leftover}")
                if any(leftover.values()):
                    raise ApplyError(f"롤백 후에도 v2 항목이 남아 있습니다: {leftover}")
                log("롤백 완료: 기존 그래프는 그대로입니다.")
            else:
                require_base_unchanged(session, "적용 전")
                result["counters"] = {name: run_file(session, args.dir / name) for name in names}
                log("검증:")
                result["verify"] = verify(session, args.dir)
                if not result["verify"]["base_unchanged"]:
                    raise ApplyError("적용 후 기존 그래프 개수가 바뀌었습니다. 99_rollback을 검토하세요.")
                if result["verify"]["mismatches"] and names == list(APPLY_FILES):
                    raise ApplyError(f"검증 불일치: {[row['check'] for row in result['verify']['mismatches']]}")
                log("적용 완료.")
        result["status"] = "ok"
        return_code = 0
    except ApplyError as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        log(f"실패: {exc}")
        return_code = 1
    finally:
        result["finished_at"] = kst_now()
        if args.dir.is_dir():
            (args.dir / f"apply_result_{mode_name}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
    return return_code


if __name__ == "__main__":
    sys.exit(main())
