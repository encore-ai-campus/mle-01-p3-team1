# Supervisor Context Improvement Plan

**Goal:** Give routing and verification truthful backend and source context across question types.

**Architecture:** Preserve separate Hybrid and Graph routes; expose available backends, retry Graph for missing structured facts when appropriate, and attach only matching structured values to a separately labeled derived CSV record. Keep source scope, safety checks and explicit route overrides.

**Tech Stack:** Python, LangGraph, Neo4j, CSV provenance, pytest.

- [x] Add tests for backend availability, structured-fact retry and explicit override.
- [x] Add tests for matching, mismatching and forged metadata provenance.
- [x] Implement route and evidence context; keep original source and safety semantics.
- [x] Verify focused Supervisor tests without live API or database writes.
