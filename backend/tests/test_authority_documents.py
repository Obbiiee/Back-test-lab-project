"""Guard the repository's designated authority documents against blob corruption."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AuthorityDocumentTests(unittest.TestCase):
    def read_text(self, relative):
        path = ROOT / relative
        self.assertTrue(path.is_file(), relative)
        raw = path.read_bytes()
        self.assertNotIn(b"\0", raw, relative)
        text = raw.decode("utf-8")
        self.assertTrue(text.strip(), relative)
        return text

    def test_authority_documents_remain_readable_and_have_distinct_roles(self):
        agents = self.read_text("AGENTS.md")
        phase = self.read_text("AI_CONTEXT/04_CURRENT_PHASE.md")
        architecture = self.read_text("docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md")
        register = self.read_text(
            "docs/acceptance/RIKSORA-V1-FREEZE-INTEGRATION-REGISTER-20261108.md")

        self.assertTrue(phase.startswith("# Validation checkpoint —"))
        self.assertIn("# OWNER CHECKPOINT — V1 integration", phase)
        self.assertIn("agent-permission authority", phase)
        self.assertIn("technical authority", phase)
        self.assertIn("implementation-gap register", phase)
        self.assertIn("implementation register, not architectural authority", agents.lower())
        self.assertIn("gap between the **agreed target** and **verified code**", register)
        self.assertIn("architecture", architecture.lower())
        self.assertEqual(len({agents, phase, architecture, register}), 4)


if __name__ == "__main__":
    unittest.main()
