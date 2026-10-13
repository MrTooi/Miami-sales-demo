"""Deterministic scoring for Opportunity Radar."""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from .models import EvidenceItem, EvidenceKind, OpportunityAssessment


DIMENSION_WEIGHTS = {
    "pain_severity": 0.15,
    "financial_impact": 0.15,
    "willingness_to_pay": 0.15,
    "frequency": 0.10,
    "software_solvability": 0.10,
    "measurable_roi": 0.10,
    "buyer_reachability": 0.08,
    "competitive_whitespace": 0.07,
    "data_feasibility": 0.05,
    "retention_potential": 0.05,
}


EVIDENCE_QUALITY = {
    EvidenceKind.PAID_CUSTOMER_BEHAVIOR: 1.00,
    EvidenceKind.PILOT_BEHAVIOR: 0.95,
    EvidenceKind.SIGNED_COMMITMENT: 0.90,
    EvidenceKind.EXPLICIT_WTP: 0.85,
    EvidenceKind.QUANTIFIED_INTERVIEW: 0.80,
    EvidenceKind.EXISTING_SPEND: 0.70,
    EvidenceKind.SOFTWARE_REVIEW: 0.55,
    EvidenceKind.COMMUNITY_SIGNAL: 0.45,
    EvidenceKind.INDUSTRY_REPORT: 0.40,
    EvidenceKind.GENERAL_SPECULATION: 0.15,
}


if abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) > 1e-9:
    raise RuntimeError("Opportunity dimension weights must sum to 1.0")


def calculate_opportunity_score(assessment: OpportunityAssessment) -> float:
    """Return the fixed weighted opportunity score from 0 to 100.

    Every required scoring dimension must be present. This intentionally fails
    closed rather than silently treating unknown dimensions as zero.
    """

    missing = set(DIMENSION_WEIGHTS) - set(assessment.dimension_scores)
    extra = set(assessment.dimension_scores) - set(DIMENSION_WEIGHTS)
    if missing:
        raise ValueError("Missing score dimensions: " + ", ".join(sorted(missing)))
    if extra:
        raise ValueError("Unknown score dimensions: " + ", ".join(sorted(extra)))

    weighted_0_to_10 = sum(
        float(assessment.dimension_scores[name]) * weight
        for name, weight in DIMENSION_WEIGHTS.items()
    )
    return round(weighted_0_to_10 * 10.0, 1)


def _domain(source_url: str) -> str:
    host = (urlparse(source_url).hostname or "").lower()
    return host.removeprefix("www.")


def calculate_confidence(evidence: list[EvidenceItem] | tuple[EvidenceItem, ...]) -> float:
    """Return evidence confidence from 0 to 100.

    Confidence measures how much evidence supports the *assessment process*, not
    whether the market is attractive. Contradictory evidence can increase
    confidence because it improves our understanding.

    Initial transparent formula:
      50% average evidence quality
      25% evidence quantity (saturates at 20 items)
      15% evidence-kind diversity (saturates at 5 kinds)
      10% source-domain diversity (saturates at 5 domains)

    The rubric is intentionally explicit and should be calibrated later with
    real validation outcomes rather than changed ad hoc for a favored market.
    """

    if not evidence:
        return 0.0

    adjusted_quality = [
        EVIDENCE_QUALITY[item.kind] * item.item_confidence for item in evidence
    ]
    quality = sum(adjusted_quality) / len(adjusted_quality)
    quantity = min(len(evidence) / 20.0, 1.0)
    kind_diversity = min(len({item.kind for item in evidence}) / 5.0, 1.0)
    domains = {_domain(item.source_url) for item in evidence if _domain(item.source_url)}
    domain_diversity = min(len(domains) / 5.0, 1.0)

    confidence = (
        0.50 * quality
        + 0.25 * quantity
        + 0.15 * kind_diversity
        + 0.10 * domain_diversity
    )
    return round(confidence * 100.0, 1)


def evidence_breakdown(evidence: list[EvidenceItem] | tuple[EvidenceItem, ...]) -> dict:
    """Return a human-readable audit breakdown for an opportunity."""

    return {
        "evidence_count": len(evidence),
        "evidence_kinds": dict(Counter(item.kind.value for item in evidence)),
        "source_domains": sorted({_domain(item.source_url) for item in evidence if _domain(item.source_url)}),
        "supporting_items": sum(item.supports_opportunity is True for item in evidence),
        "contradicting_items": sum(item.supports_opportunity is False for item in evidence),
        "neutral_or_unclassified_items": sum(item.supports_opportunity is None for item in evidence),
        "confidence_score": calculate_confidence(evidence),
    }
