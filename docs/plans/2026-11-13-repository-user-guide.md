# Repository User Guide and Cleanup Plan

**Goal:** Make the non-Streamlit Supervisor and evaluation paths understandable and runnable from a fresh checkout while preserving the active evaluation.

**Architecture:** Keep canonical retrieval and evaluation code in its existing package paths; document compatibility wrappers instead of moving them during a live run. Consolidate usage instructions through the root README and folder indexes. Keep datasets and generated runs in their existing separate locations.

**Tech Stack:** Python 3.12, uv, LangGraph, Chroma, Neo4j, Ragas, NeMo Guardrails.

- [x] Identify live inputs, compatibility wrappers, ignored assets and existing documentation.
- [x] Write a root installation and CLI guide, with real database and model prerequisites.
- [x] Add folder READMEs and consolidate links to evaluation datasets, evaluators and output locations.
- [x] Update stale setup instructions and ignore generated outputs without moving active files.
- [x] Verify documentation links and read-only CLI help; report any steps that require the current evaluation to finish.
