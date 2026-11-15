import io
import unittest

from src.agent.neo4j_demo import _configure_output_stream


class Neo4jDemoOutputTests(unittest.TestCase):
    def test_console_output_escapes_characters_not_supported_by_windows_code_page(self):
        encoded_output = io.BytesIO()
        stream = io.TextIOWrapper(encoded_output, encoding="cp949")
        try:
            _configure_output_stream(stream)
            stream.write("서울 —")
            stream.flush()
            output = encoded_output.getvalue().decode("cp949")
        finally:
            stream.detach()

        self.assertEqual(output, r"서울 \u2014")


if __name__ == "__main__":
    unittest.main()
