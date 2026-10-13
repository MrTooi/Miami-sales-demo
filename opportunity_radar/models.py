"""Domain models for Opportunity Radar.

These models keep observed facts separate from interpretation and scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class EvidenceKind(str, Enum):
    """Evidence hierarchy from strongest commercial proof to weakest."""

    PAID_CUSTOMER_BEHAVIOR = "paid_customer_behavior"
    PILOT_BEHAVIOR = "pilot_behavior"
    SIGNED_COMMITMENT = "signed_commitment"
    EXPLICIT_WTP = "explicit_willingness_to_pay"
    QUANTIFIED_INTERVIEW = "quantified_customer_interview"
    EXISTING_SPEND = "existing_spend_or_workaround"
    SOFTWARE_REVIEW = "software_review"
    COMMUNITY_SIGNAL = "community_signal"
    INDUSTRY_REPORT = "industry_report"
    GENERAL_SPECULATION = "general_market_speculation"


@dataclass(frozen=True)
class EvidenceItem:
    """One traceable piece of market evidence.

    ``observed_fact`` should describe what the source actually shows.
    ``interpretation`` is deliberately separate so an inference never becomes
    indistinguishable from evidence.
    """

    evidence_id: str
    market: str
    kind: EvidenceKind
    source_url: str
    observed_fact: str
    interpretation: str = ""
    source_name: str = ""
    persona: str = ""
    problem: str = ""
    captured_date: str = ""
    item_confidence: float = 1.0
    supports_opportunity: bool | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("Evidence item requires a nonblank evidence_id")
        if not self.market.strip():
            raise ValueError("Evidence item requires a market")
        if not self.source_url.strip():
            raise ValueError("Evidence item requires a source_url")
        if not self.observed_fact.strip():
            raise ValueError("Evidence item requires an observed_fact")
        if not 0.0 <= self.item_confidence <= 1.0:
            raise ValueError("item_confidence must be between 0 and 1")


@dataclass(frozen=True)
class OpportunityAssessment:
    """Auditable score inputs for one market/problem opportunity.

    Dimension scores are 0-10. The final 0-100 score is calculated in
    :mod:`opportunity_radar.scoring` using a fixed weight table.
    """

    market: str
    niche: str
    buyer: str
    icp: str
    dimension_scores: Mapping[str, float]
    evidence: Sequence[EvidenceItem] = field(default_factory=tuple)
    bull_case: str = ""
    bear_case: str = ""
    kill_criteria: tuple[str, ...] = ()
    next_experiment: str = ""

    def __post_init__(self) -> None:
        if not self.market.strip():
            raise ValueError("Opportunity assessment requires a market")
        if not self.niche.strip():
            raise ValueError("Opportunity assessment requires a niche")
        if not self.buyer.strip():
            raise ValueError("Opportunity assessment requires a buyer")
        for dimension, score in self.dimension_scores.items():
            if not 0.0 <= float(score) <= 10.0:
                raise ValueError(f"{dimension} must be between 0 and 10")
