# Chroma 시·도 별칭 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chroma와 Hybrid의 지역 필터 및 표시에서 전북·전남의 기존 표기를 요청한 표준명으로 함께 취급한다.

**Architecture:** 저장된 벡터·문서·CSV는 유지한다. 공용 별칭 정규화, Chroma 필터 별칭, BM25 필터 별칭, UI 결과 표시를 코드에서 맞춘다.

**Tech Stack:** Python, ChromaDB, pandas, existing metadata filters.

**Spec:** `docs/decisions/2026-11-13-chroma-sido-alias-normalization-design.md`

## Global Constraints

- Do not rewrite Chroma collections, embeddings, source CSVs, or saved evaluation outputs.
- Canonical labels are `전북특별자치도` and `전남광주특별자치도`.
- Existing Chroma stored labels include `전라북도` and `전남광주통합특별시`.
- Existing non-target Sido aliases and filter behavior remain intact.

## Review Focus

- Canonical and legacy labels both match the same Chroma metadata rows.
- `전북` and `전남` shorthand still expand to the complete alias groups.
- Multi-Sido filters do not duplicate variants.
- Searches without Sido filters retain their current query and ranking.
- UI and Supervisor evidence expose the canonical labels without mutating stored metadata.

---

### Task 1: Shared and Chroma alias matching

**Files:**
- Add: `src/region_aliases.py`
- Modify: `src/agent/region_normalization.py`
- Modify: `src/service/vector_search_chroma.py`

**Interfaces:**
- Preserve `canonicalize_sido`, `sido_aliases`, and `build_chroma_where` signatures.

- [x] Add `전남광주통합특별시` to the `전남광주특별자치도` alias family.
- [x] Make Chroma filters for either standard name, old full name, or shorthand expand to the stored aliases, de-duplicating variants as today.
- [x] Keep unrelated Sido alias behavior unchanged.
- [x] Share the alias family from a neutral module so Chroma, Supervisor, BM25, and UI cannot drift independently.

### Task 2: Hybrid and UI normalization

**Files:**
- Modify: `src/hybrid/bm25_retriever.py`
- Modify: `src/service/app.py` (make shared `src.*` imports available at UI startup)
- Modify: `src/service/ui/data.py`
- Modify: `src/service/ui/chatbot.py`
- Modify: `src/service/ui/kg.py`

**Interfaces:**
- Preserve the BM25 `search(query, top_k, filters)` and UI retrieval contracts.

- [x] Add the same Jeonbuk/Jeonnam equivalence groups to BM25 filter matching and canonicalize returned metadata copies.
- [x] Map old Jeonbuk/Jeonnam values to the canonical display labels and update Sido option ordering.
- [x] Normalize direct Chroma chatbot hits, CSV keyword fallback, and Neo4j graph evidence for display without mutating stored rows.

### Task 3: Documentation and static verification

**Files:**
- Modify: `docs/evaluation/langgraph-ragas.md` only if region alias behavior is described there.

- [x] Confirm changed Python modules compile with `py_compile`.
- [x] Confirm Chroma collection count and stored metadata remain unchanged; do not run Ragas or mutate Chroma.
- [x] Review the diff to confirm only alias handling, display behavior, and required UI import setup changed.

Static verification completed with `py_compile` and `git diff --check`. No tests or Ragas evaluation were run. A read-only Chroma metadata check showed the collection still has 738 records and the same stored Sido counts; no Chroma write or CSV rewrite was performed.
