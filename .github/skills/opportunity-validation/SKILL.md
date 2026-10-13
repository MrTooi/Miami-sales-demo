---
name: opportunity-validation
description: Evaluate markets and customer problems using structured evidence, separate opportunity from confidence, preserve contradictory evidence, apply kill criteria, and recommend the cheapest next validation experiment.
---

# Opportunity Validation

Use this skill whenever Opportunity Radar ingests, scores, summarizes, compares, or recommends a market opportunity.

## Core rule

Do not protect LEDGER, commercial printing, or any preferred idea. The goal is to find the strongest business opportunity supported by evidence.

## Separate four things

1. **Observed evidence** — what a source/interview/behavior actually shows.
2. **Interpretation** — what we think it means.
3. **Opportunity score** — attractiveness under the fixed scoring rubric.
4. **Confidence** — how much evidence supports trusting the score.

Never collapse these into one AI opinion.

## Evidence hierarchy

Prefer, roughly from strongest to weakest:

1. Paid customer behavior.
2. Pilot behavior.
3. Signed commitment / deposit / LOI.
4. Explicit willingness-to-pay evidence.
5. Customer interviews with quantified pain.
6. Existing spend/workarounds.
7. Software reviews.
8. Forums/community evidence.
9. Industry reports.
10. General speculation.

Evidence strength depends on relevance, recency, source quality, specificity, independence, and whether the behavior costs the customer real time or money.

## Evidence record requirements

Preserve when available:
- source URL/reference,
- date,
- market/niche,
- buyer/persona,
- problem,
- current workaround,
- frequency,
- quantified time/money impact,
- software named,
- willingness-to-pay signal,
- direct quote/excerpt where permitted,
- whether evidence supports or contradicts the hypothesis,
- confidence/quality metadata.

AI summaries are not source evidence by themselves.

## Opportunity score

The current framework evaluates:
- pain severity,
- financial impact,
- willingness to pay,
- frequency,
- software/AI solvability,
- measurable ROI,
- buyer reachability,
- competitive weakness/whitespace,
- data/integration feasibility,
- retention potential.

Scoring math must remain deterministic and auditable. Do not let an LLM silently adjust weights.

## Confidence

A market can score highly and still be low-confidence.

Confidence should improve with:
- more high-quality evidence,
- evidence diversity,
- independent sources,
- direct buyer evidence,
- quantified pain,
- pilots/paid behavior.

Contradictory evidence must remain visible.

## Bull / bear requirement

For serious opportunities produce both:

### Bull case
Why this could become a strong business.

### Bear case
Why we should not enter it.

The bear case must actively test:
- incumbents already solve it well,
- pain is infrequent or small,
- no clear budget owner,
- low willingness to pay,
- hard/inaccessible data,
- expensive onboarding/support,
- regulatory burden,
- high CAC/low ACV,
- weak retention,
- feature-not-company risk.

## Kill criteria

Downgrade/kill opportunities when evidence shows low urgency, weak economics, inaccessible data, poor reachability, satisfied incumbents, low retention, or pilots that fail to produce measurable value.

## Next-experiment rule

After analysis, recommend the **cheapest experiment with the highest information value**.

Examples:
- 5 targeted interviews,
- ask for anonymized exports,
- manual concierge analysis,
- price test,
- paid pilot,
- narrow landing-page/outbound test.

Do not recommend major engineering investment merely because internet research looks promising.
