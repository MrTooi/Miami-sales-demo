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
                "details", "summary", "i", "img"}
ALLOWED_ATTRIBUTES = {"name", "content", "class", "style",  # meta, classes, inline styles
                      "src", "alt"}  # the embedded logo, checked below
# The only image allowed: the MargenX logo embedded as PNG data, so it loads nothing from outside.
LOGO_DATA = "data:image/png;base64,"


class _Inventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attributes = set(), set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self.attributes.update(name for name, _ in attrs)
        self.image_sources = getattr(self, "image_sources", []) + [v for n, v in attrs if n == "src"]


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
        self.assertIn("It isn't accounting, tax or financial advice.", self.page)  # the how-to-read note

    def test_header_shows_the_real_margenx_logo(self):
        import base64
        logo = base64.b64encode((ROOT / "assets" / "margenx-logo.png").read_bytes()).decode("ascii")
        self.assertIn(f'<img class="mx-logo" src="{LOGO_DATA}{logo}" alt="MargenX logo">', self.page)
        self.assertNotIn("<svg", self.page)  # the old placeholder mark is gone

    def test_logo_file_is_a_valid_png_of_the_expected_size(self):
        from PIL import Image
        with Image.open(ROOT / "assets" / "margenx-logo.png") as image:
            image.verify()  # raises if the file is corrupt or not really a PNG
        with Image.open(ROOT / "assets" / "margenx-logo.png") as image:
            self.assertEqual(("PNG", (108, 120)), (image.format, image.size))
            self.assertIn(image.mode, {"P", "RGBA"})  # has transparency for the mint background

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
        self.assertEqual(1, len(found.image_sources))  # just the logo
        self.assertTrue(all(src.startswith(LOGO_DATA) for src in found.image_sources))
        # Checked with the logo's embedded data left out, so its random-looking letters can't hide or fake a match.
        lowered = re.sub(re.escape(LOGO_DATA) + r"[A-Za-z0-9+/=]+", "", self.page).lower()
        # Nothing that loads or sends anything from CSS or text: no url(), @import, protocol or
        # protocol-relative address, and no data: or javascript: scheme.
        for forbidden in ("url(", "@import", "javascript:", "data:", "upload"):
            self.assertNotIn(forbidden, lowered, forbidden)
        self.assertEqual([], re.findall(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]", lowered))

    def test_clicking_a_job_or_customer_still_opens_its_breakdown(self):
        # Every job and every customer in the engine's report has its own details element whose hidden
        # breakdown matches the engine: the job's "Sold for" line, the customer's own jobs.
        report = build.demo_report()
        blocks = re.findall(r"<details class=\"mx-d\">(.*?)</details>", self.page)
        self.assertEqual(len(report.jobs) + len(report.customers), len(blocks))
        for job in report.jobs:
            block = next(b for b in blocks if f"· {job.job_id}</small>" in b)
            self.assertIn(f'<td>Sold for</td><td class="r">{mi.money(job.sales)}</td>', block)
        for customer in report.customers:
            block = next(b for b in blocks if f'<div class="n">{customer.customer}<' in b)
            for job_id in customer.jobs:
                self.assertIn(f"· {job_id}</td>", block)

    def test_script_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo.html"
            self.assertEqual(0, build.main(["build_demo_page.py", str(out)]))
            self.assertEqual(self.page, out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
