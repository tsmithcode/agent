import tempfile
import unittest
from pathlib import Path

from cg.runtime.ask_engine import ask_workspace_file_count


class AskDeterministicTests(unittest.TestCase):
    def test_count_files_by_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "a").mkdir()
            (ws / "b").mkdir()
            (ws / "a" / "metrics-summary.csv").write_text("x", encoding="utf-8")
            (ws / "b" / "metrics-summary.csv").write_text("x", encoding="utf-8")
            matched, answer = ask_workspace_file_count("how many metrics-summary.csv files?", ws)
            self.assertTrue(matched)
            self.assertIn("Found 2 file(s)", answer)


if __name__ == "__main__":
    unittest.main()
