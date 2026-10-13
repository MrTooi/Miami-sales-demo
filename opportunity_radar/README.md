# Opportunity Radar MVP

Opportunity Radar is an internal decision system for finding and validating B2B software opportunities before the team commits major engineering resources.

## Core rule

The system must not be optimized to prove a favored idea. LEDGER and every other market hypothesis compete under the same scoring rubric.

## MVP layers

1. **Evidence** — traceable facts from interviews, paid behavior, pilots, reviews, communities, reports, and other sources.
2. **Assessment** — a human/agent-generated 0-10 score for ten fixed opportunity dimensions.
3. **Opportunity score** — deterministic weighted score from 0-100.
4. **Confidence score** — deterministic measure of evidence strength, quantity, diversity, and source diversity.
5. **Challenge layer** — bull case, bear case, kill criteria, and next cheapest falsification experiment.

## Fixed opportunity dimensions

- pain severity — 15%
- financial impact — 15%
- willingness to pay — 15%
- frequency — 10%
- software solvability — 10%
- measurable ROI — 10%
- buyer reachability — 8%
- competitive whitespace — 7%
- data feasibility — 5%
- retention potential — 5%

Scores are always 0-10. Missing or unknown dimensions fail closed instead of silently receiving a default.

## Evidence hierarchy

Evidence quality starts strongest with paid customer behavior and weakens through pilots, commitments, explicit willingness to pay, quantified interviews, existing spending/workarounds, software reviews, community signals, industry reports, and finally general speculation.

Contradictory evidence is not discarded. It can increase confidence in our understanding even when it decreases the attractiveness of the opportunity.

## Current confidence formula

The first transparent confidence rubric is:

- 50% average evidence quality
- 25% evidence quantity, saturating at 20 items
- 15% evidence-kind diversity, saturating at 5 kinds
- 10% source-domain diversity, saturating at 5 domains

This is an initial calibration, not a scientific truth. It should only be changed from observed validation outcomes, not to make a favored market rank higher.

## Next build steps

1. persistent evidence store
2. opportunity repository and ranking
3. explicit kill-signal model
4. import/export format for partner research
5. API/service boundary
6. automated evidence ingestion with source preservation
7. bull/bear agent layer
8. internal dashboard
9. interview and pilot evidence ingestion
10. calibration from real conversion/pilot outcomes

## Separation from LEDGER

Opportunity Radar currently lives on an isolated branch while the existing LEDGER prototype remains stable. The systems may later move into separate repositories once the MVP architecture settles.
