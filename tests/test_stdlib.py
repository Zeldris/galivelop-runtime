import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class StdlibOnlyTests(unittest.TestCase):
    def test_the_package_imports_only_stdlib_and_itself(self):
        # Invariant 12: every import of grun is stdlib or grun itself.
        stdlib = set(sys.stdlib_module_names)
        found = []
        for py in sorted((ROOT / "grun").glob("*.py")):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"), py.name)):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                found += [(py.name, n) for n in names if n not in stdlib and n != "grun"]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
