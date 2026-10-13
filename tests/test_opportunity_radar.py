import unittest

from opportunity_radar.models import EvidenceItem, EvidenceKind, OpportunityAssessment
from opportunity_radar.scoring import (
    DIMENSION_WEIGHTS,
    calculate_confidence,
    calculate_opportunity_score,
    evidence_breakdown,
)


FULL_SCORES = {
    "pain_severity": 10,
    "financial_impact": 10,
    "willingness_to_pay": 10,
    "frequency": 10,
    "software_solvability": 10,
    "measurable_roi": 10,
    "buyer_reachability": 10,
    "competitive_whitespace": 10,
    "data_feasibility": 10,
    "retention_potential": 10,
}


class OpportunityRadarTests(unittest.TestCase):
    def assessment(self, scores=None, evidence=()):
        return OpportunityAssessment(
            market="Commercial printing",
            niche="Independent commercial print shops",
            buyer="Owner / GM",
            icp="10-50 employees",
            dimension_scores=scores or FULL_SCORES,
            evidence=evidence,
        )

    def evidence(self, evidence_id="e1", kind=EvidenceKind.SOFTWARE_REVIEW,
                 url="https://example.com/review", confidence=1.0, supports=True):
        return EvidenceItem(
            evidence_id=evidence_id,
            market="Commercial printing",
            kind=kind,
            source_url=url,
            observed_fact="Owner reports repeated estimating difficulty.",
            interpretation="Possible pricing workflow pain.",
            item_confidence=confidence,
            supports_opportunity=supports,
        )

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(DIMENSION_WEIGHTS.values()), 1.0)

    def test_all_tens_score_one_hundred(self):
        self.assertEqual(calculate_opportunity_score(self.assessment()), 100.0)

    def test_weighted_score_is_deterministic(self):
        scores = dict(FULL_SCORES)
        scores["pain_severity"] = 8
        scores["financial_impact"] = 6
        self.assertEqual(calculate_opportunity_score(self.assessment(scores=scores)), 91.0)

    def test_missing_dimension_fails_closed(self):
        scores = dict(FULL_SCORES)
        del scores["pain_severity"]
        with self.assertRaisesRegex(ValueError, "Missing score dimensions"):
            calculate_opportunity_score(self.assessment(scores=scores))

    def test_unknown_dimension_rejected(self):
        scores = dict(FULL_SCORES)
        scores["hype"] = 10
        with self.assertRaisesRegex(ValueError, "Unknown score dimensions"):
            calculate_opportunity_score(self.assessment(scores=scores))

    def test_score_bounds_are_validated(self):
        scores = dict(FULL_SCORES)
        scores["pain_severity"] = 11
        with self.assertRaisesRegex(ValueError, "between 0 and 10"):
            self.assessment(scores=scores)

    def test_no_evidence_has_zero_confidence(self):
        self.assertEqual(calculate_confidence([]), 0.0)

    def test_stronger_evidence_increases_confidence(self):
        weak = [self.evidence(kind=EvidenceKind.GENERAL_SPECULATION)]
        strong = [self.evidence(kind=EvidenceKind.PAID_CUSTOMER_BEHAVIOR)]
        self.assertGreater(calculate_confidence(strong), calculate_confidence(weak))

    def test_more_diverse_evidence_increases_confidence(self):
        narrow = [
            self.evidence("e1", EvidenceKind.SOFTWARE_REVIEW, "https://same.com/1"),
            self.evidence("e2", EvidenceKind.SOFTWARE_REVIEW, "https://same.com/2"),
        ]
        diverse = [
            self.evidence("e1", EvidenceKind.SOFTWARE_REVIEW, "https://a.com/1"),
            self.evidence("e2", EvidenceKind.QUANTIFIED_INTERVIEW, "https://b.com/2"),
        ]
        self.assertGreater(calculate_confidence(diverse), calculate_confidence(narrow))

    def test_contradicting_evidence_still_counts_toward_confidence(self):
        evidence = [
            self.evidence("e1", supports=True),
            self.evidence("e2", url="https://other.com/review", supports=False),
        ]
        breakdown = evidence_breakdown(evidence)
        self.assertEqual(breakdown["supporting_items"], 1)
        self.assertEqual(breakdown["contradicting_items"], 1)
        self.assertGreater(breakdown["confidence_score"], 0)


if __name__ == "__main__":
    unittest.main()
