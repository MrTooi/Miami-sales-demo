"""Opportunity Radar core domain package.

The package is intentionally deterministic: AI may gather or summarize evidence,
but scoring and confidence calculations are plain Python and auditable.
"""

from .models import EvidenceItem, EvidenceKind, OpportunityAssessment
from .scoring import calculate_confidence, calculate_opportunity_score

__all__ = [
    "EvidenceItem",
    "EvidenceKind",
    "OpportunityAssessment",
    "calculate_confidence",
    "calculate_opportunity_score",
]
