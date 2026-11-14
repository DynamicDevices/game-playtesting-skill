"""Offline content/package checks; not live compatibility or quality tests."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/app-playtesting"


class ContentTests(unittest.TestCase):
    def test_markdown_links_and_skill_portability(self):
        for document in ROOT.rglob("*.md"):
            if ".git" in document.parts:
                continue
            for target in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                resolved = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.is_relative_to(ROOT))
                self.assertTrue(resolved.exists(), (document, target))
                if document.is_relative_to(SKILL):
                    self.assertTrue(resolved.is_relative_to(SKILL), "Installed skill has an external local dependency")

    def test_metadata_and_license(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertRegex(text.split("---", 2)[1], r"(?m)^name: app-playtesting$")
        self.assertIn("license: MIT", text)
        self.assertIn("Copyright (c) 2026 Dynamic Devices", (ROOT / "LICENSE").read_text())

    def test_safety_and_honest_generalisation(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ["release", "fallback", "hypotheses", "separate approval", "not quality"]:
            self.assertIn(phrase, text)
        status = (ROOT / "docs/validation.md").read_text(encoding="utf-8")
        self.assertIn("has not been exercised live", status)
        self.assertIn("second developer-authorised 2D game", status)
        self.assertIn("conventional app", status)


if __name__ == "__main__":
    unittest.main()
