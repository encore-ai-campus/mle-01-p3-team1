import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.agent.neo4j_tls import load_graph_database


class Neo4jTlsTests(unittest.TestCase):
    def test_installs_system_trust_before_loading_neo4j_driver(self):
        events = []
        graph_database = object()

        def load_module(name):
            events.append(f"import:{name}")
            return SimpleNamespace(GraphDatabase=graph_database)

        with patch("truststore.inject_into_ssl", side_effect=lambda: events.append("trust")):
            with patch("src.agent.neo4j_tls.import_module", side_effect=load_module):
                loaded = load_graph_database()

        self.assertIs(loaded, graph_database)
        self.assertEqual(events, ["trust", "import:neo4j"])


if __name__ == "__main__":
    unittest.main()
