import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("outreach", ROOT / "outreach.py")
outreach = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = outreach
assert spec.loader
spec.loader.exec_module(outreach)


class OutreachTests(unittest.TestCase):
    def setUp(self):
        self.target = outreach.Target(
            brand="Example",
            recipient_name="Example Team",
            recipient_email="team@example.com",
            contact_type="PR",
            product_line="ExampleBook",
            appreciation="I appreciate the brand's focus on useful, dependable computing.",
            india_context="The company has a meaningful presence in India.",
            source_url="https://example.com/contact",
            source_checked="2026-09-27",
            approved=False,
            notes="",
        )
        self.config = {
            "profile": {
                "full_name": "Test User",
                "city_country": "Delhi, India",
                "student_or_role": "student",
                "story": "I build software projects for my coursework and portfolio.",
                "use_case": "web development and coursework.",
                "portfolio_url": "",
                "linkedin_url": "",
                "signature": "Test User",
            },
            "ask": {
                "primary_request": "Would you consider supporting me with a laptop?",
                "fallback_request": "A student discount would also help.",
            },
        }

    def test_render(self):
        text = outreach.render("Hello {brand}, I am {full_name}.", self.target, self.config)
        self.assertEqual(text, "Hello Example, I am Test User.")

    def test_target_key_stable(self):
        self.assertEqual(self.target.key, self.target.key)
        self.assertEqual(len(self.target.key), 20)

    def test_validate_target(self):
        self.assertEqual(outreach.validate_targets([self.target]), [])

    def test_placeholder_profile_is_rejected(self):
        cfg = json.loads(json.dumps(self.config))
        cfg["profile"]["full_name"] = "YOUR_FULL_NAME"
        self.assertTrue(outreach.validate_profile(cfg))

    def test_preview_does_not_require_smtp(self):
        # Rendering and preview-generation primitives operate without credentials.
        subject = outreach.render("Request to {brand}", self.target, self.config)
        body = outreach.render("{story}\n{primary_request}", self.target, self.config)
        self.assertIn("Example", subject)
        self.assertIn("supporting me", body)


if __name__ == "__main__":
    unittest.main()
