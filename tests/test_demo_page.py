"""The static demo page (D-006): the made-up demo shop, built from the real MargenX code, with no
way to send anything anywhere."""
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

import marginx_insights as mi

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_demo_page", ROOT / "scripts" / "build_demo_page.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


# Display-only HTML: text, layout, a table, an inline drawing and the details/summary breakdowns.
ALLOWED_TAGS = {"title", "meta", "style", "main", "div", "span", "b", "small", "h3", "table", "tr", "td",
                "details", "summary", "i", "svg", "path"}
ALLOWED_ATTRIBUTES = {"name", "content", "class", "style",  # meta, classes, inline styles
                      "width", "height", "viewbox", "fill", "aria-hidden", "d", "stroke", "stroke-width",
                      "stroke-linejoin"}  # the brand mark's inline SVG


class _Inventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attributes = set(), set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self.attributes.update(name for name, _ in attrs)


class DemoPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = build.build_page()

    def test_page_shows_the_demo_shop_from_the_real_engine(self):
        summary = mi.summarize(build.demo_report())
        self.assertIn(f">{mi.money(summary.sales)}<", self.page)  # $11,000
        self.assertIn(f">{mi.money(summary.left_after_job_costs)}<", self.page)  # $3,640
        self.assertIn("Here's where your money was made", self.page)
        self.assertIn("Rush banner (next-day) · J-105 lost $140", self.page)
        self.assertIn("Sales dated Oct 2 to Oct 23, 2026", self.page)
        self.assertIn("<title>MargenX Demo Shop</title>", self.page)

    def test_page_says_the_data_is_made_up(self):
        self.assertIn("Every name and number here is invented.", self.page)
        self.assertIn("Example data only", self.page)

    def test_page_has_no_way_to_send_anything(self):
        # Every tag and attribute must come from a short allowlist of display-only HTML. A script, form,
        # input, button, frame, media, link, event handler or URL-bearing attribute fails the test.
        found = _Inventory()
        found.feed(self.page)
        self.assertEqual(set(), found.tags - ALLOWED_TAGS, "unexpected tags")
        self.assertEqual(set(), found.attributes - ALLOWED_ATTRIBUTES, "unexpected attributes")
        self.assertFalse(any(a.startswith("on") for a in found.attributes))
        lowered = self.page.lower()
        # Nothing that loads or sends anything from CSS or text: no url(), @import, protocol or
        # protocol-relative address, and no data: or javascript: scheme.
        for forbidden in ("url(", "@import", "javascript:", "data:", "upload"):
            self.assertNotIn(forbidden, lowered, forbidden)
        self.assertEqual([], re.findall(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]", lowered))

    def test_clicking_a_job_or_customer_still_opens_its_breakdown(self):
        self.assertGreaterEqual(self.page.count("<details"), 12)  # 8 jobs + 4 customers in the demo shop

    def test_script_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo.html"
            self.assertEqual(0, build.main(["build_demo_page.py", str(out)]))
            self.assertEqual(self.page, out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
