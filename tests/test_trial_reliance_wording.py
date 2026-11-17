"""D-010: the trial guide and terms must carry the same reliance wording the results show (the PR #148 manual review,
round 3: "The guide and terms should carry that disclosure before the first real upload")."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quickbooks_figures as qf  # noqa: E402


class RelianceWordingTests(unittest.TestCase):

    def test_the_guide_and_the_terms_quote_the_results_wording_exactly(self):
        for name in ("docs/TRIAL_SHOP_GUIDE.md", "docs/TRIAL_TERMS_DRAFT.md"):
            with self.subTest(name):
                self.assertIn(f"\"{qf.RELIANCE}\"", (ROOT / name).read_text())

    def test_the_guide_and_the_terms_say_nothing_is_complete_before_the_owner_confirms(self):
        for name in ("docs/TRIAL_SHOP_GUIDE.md", "docs/TRIAL_TERMS_DRAFT.md"):
            with self.subTest(name):
                text = (ROOT / name).read_text()
                self.assertIn("Until you answer \"Yes, I checked\", every figure", text)
                self.assertIn("MargenX relies on your confirmation for that file" if name.endswith("TERMS_DRAFT.md")
                              else "No, something is missing", text)

    def test_the_guide_says_yes_confirms_the_whole_business_not_only_that_you_looked(self):
        # The PR #147 confirmation review, blocker: "Yes, I checked" "only if you did" could read as "I looked", even
        # after finding an account missing. A mistaken yes on a file missing Labor can show $4,300 Complete.
        text = (ROOT / "docs/TRIAL_SHOP_GUIDE.md").read_text()
        self.assertIn("Choose **Yes, I checked** only if you checked the list and export settings and can confirm that "
                      "this file includes your whole business's income and costs for those dates, with no filters "
                      "excluding accounts or transactions. If you found something missing, choose **No, something is "
                      "missing**. If you can't tell, choose **Not sure**.", text)
        self.assertNotIn("only if you did", text)


if __name__ == "__main__":
    unittest.main()
