# Supervisor and Hybrid Integration Plan

**Goal:** Keep Supervisor orchestration and the team's hybrid retrieval in distinct, interoperable packages.

**Architecture:** `src.agent.supervisor` owns routing, verification and retries; `src.hybrid` owns BM25, vector fusion and reranking. An explicit retriever adapter translates the actual hybrid response into the Supervisor contract without inventing source provenance. The old BM25 import remains a compatibility alias.

**Constraints:** Preserve the existing graph and injected hybrid-node APIs, local user changes, retrieval diagnostics and the distinction between BM25+vector and Neo4j graph search.

1. Add regression tests for the renamed vector service import and shared BM25 classes; correct the import and consolidate the implementation.
2. Test actual hybrid service output through the Supervisor adapter and graph, including partial results, source provenance and retry behavior; connect the default team retriever while retaining injection.
3. Update the CLI and architecture documentation, then run the complete test suite and review the changes.
