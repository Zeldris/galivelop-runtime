"""Placeholder check for the design phase: the DDD exists and keeps its numbered sections.

Replaced by the real invariant tests (DDD §5) once `grun` has code (milestone R1).
"""

import re
import unittest
from pathlib import Path

DDD = Path(__file__).resolve().parent.parent / "docs" / "design" / "ddd.md"
SECTIONS = ["Propósito", "Lenguaje", "Contextos acotados", "Modelo", "Invariantes", "Alcance",
            "Escalera de hitos", "Preguntas abiertas"]


class DddTest(unittest.TestCase):
    def test_ddd_has_numbered_sections_in_order(self):
        text = DDD.read_text(encoding="utf-8")
        found = re.findall(r"^## (\d+)\. (.+)$", text, flags=re.MULTILINE)
        self.assertEqual([title for _, title in found], SECTIONS)
        self.assertEqual([int(n) for n, _ in found], list(range(1, len(SECTIONS) + 1)))

    def test_ddd_has_decisions_section(self):
        text = DDD.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^## Decisiones$")


if __name__ == "__main__":
    unittest.main()
