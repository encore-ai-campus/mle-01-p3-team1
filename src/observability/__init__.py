"""Opt-in Langfuse observability for the museum RAG project.

The package does not initialize the SDK at import time; this matters because the
application loads .env after importing several agent modules.
"""
