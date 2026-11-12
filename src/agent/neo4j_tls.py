"""Load Neo4j after enabling the operating system's trusted certificate store."""

from importlib import import_module
from typing import Any


def load_graph_database() -> Any:
    """Install system CA roots before importing the Neo4j driver."""
    import truststore

    truststore.inject_into_ssl()
    return import_module("neo4j").GraphDatabase
