# Museum Neo4j Load Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Load the 738-museum CSV into Neo4j with source and text-span provenance, verify the result, and publish a load report.

**Architecture:** Parse and validate the complete CSV before writing. Use stable IDs and parameterized Cypher `MERGE` operations in batches. Keep museum text and its cited spans available as later vector anchors; vector generation belongs to the separate vector DB work and needs a specified model and dimension.

**Tech Stack:** Python 3.12, official Neo4j Python driver, python-dotenv, stdlib unittest.

**Spec:** The user's instructions in this conversation and `src/for_build/museum_final_738.csv`.

## Global constraints

- Keep code under `src/for_build/build_neo4j` except dependency declarations.
- Keep all Cypher in `graph_db.py` and use parameters for data.
- Load `.env`, handle failures, and document the run command.
- Do not claim a successful load without read-back counts from Neo4j.

## Tasks

1. **Parsing:** Test missing or malformed IDs, JSON, hashes, spans, and duplicate IDs. Implement typed CSV parsing and preflight statistics in `parsing.py`.
2. **Graph DB:** Test parameter payload contracts. Implement constraints, batched node and relationship `MERGE`, and read-back verification in `graph_db.py`.
3. **Command and report:** Implement `load_neo4j.py` with `.env` loading and a `--dry-run` option; add usage instructions and dependency declarations. Run dry-run and live load, then write a report with observed counts and limitations.

## Review focus

- Empty source fields must not become invented values.
- Re-running must preserve stable node counts.
- Bad span references must fail before any database write.
- A failed batch must stop the load and produce no success report.
- The report must distinguish CSV validation from confirmed database state.
