"""Invariante 12: `grun` solo importa la biblioteca estándar (y a sí mismo)."""
import ast
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "grun"


def imported_roots(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


class StdlibOnlyTests(unittest.TestCase):
    def test_python_is_new_enough_for_the_stdlib_list(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 10))  # DDD §1: Python >= 3.10

    def test_the_package_has_modules(self):
        self.assertTrue(list(PACKAGE.glob("*.py")))

    def test_every_import_is_stdlib_or_grun(self):
        allowed = set(sys.stdlib_module_names) | {"grun", "__future__"}
        for path in sorted(PACKAGE.rglob("*.py")):
            for root in imported_roots(path):
                with self.subTest(module=path.name, imports=root):
                    self.assertIn(root, allowed, "%s importa %s, que no es de la biblioteca estándar" % (path, root))

    def test_the_checker_catches_a_foreign_import(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "x.py"
            sample.write_text("import json\nimport requests.sessions\nfrom numpy import array\n")
            roots = set(imported_roots(sample))
        self.assertEqual(roots - set(sys.stdlib_module_names), {"requests", "numpy"})


if __name__ == "__main__":
    unittest.main()
