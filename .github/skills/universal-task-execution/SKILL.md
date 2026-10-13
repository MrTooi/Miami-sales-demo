---
name: universal-task-execution
description: 'General execution protocol for unfamiliar, cross-cutting, or high-uncertainty tasks. Helps agents classify work, discover context, plan, execute, verify, self-critique, and escalate when tools or evidence are insufficient.'
---

# Universal Task Execution

Use this skill for any non-trivial task that is unfamiliar, cross-cutting, ambiguous, or not fully covered by a narrower domain skill.

## Goal

Complete the requested outcome safely and verifiably without pretending to know unavailable facts, tools, or system behavior.

## Workflow

1. **Restate the outcome**
   - Define what must be observably true when the task is done.
   - Separate requested outcome from implementation guesses.

2. **Classify the task**
   - Product/research
   - General engineering/UI
   - Backend/data/financial
   - Integration/provider
   - QA/debugging
   - Security/data integrity
   - Release/operations
   - Cross-cutting

3. **Inspect context before acting**
   - Read repository instructions and active issue/PR.
   - Inspect relevant code, tests, docs, and current state.
   - Do not assume a framework, API, file, branch, or feature exists.

4. **Identify unknowns and risk**
   - Mark unknown facts, unavailable tools, destructive operations, customer-data exposure, security implications, financial semantics, and external side effects.
   - If an unknown can materially change correctness, resolve it from authoritative evidence or escalate.

5. **Choose the smallest capable owner/toolset**
   - Prefer one primary owner plus independent review over many agents touching the same files.
   - Delegate independent research/review in parallel only when workstreams do not share mutable state.
   - Never pretend a tool ran if it is not available.

6. **Plan the smallest complete change**
   - Define acceptance criteria.
   - Define explicit exclusions.
   - Define tests/checks before implementation where practical.
   - Identify rollback/recovery for risky changes.

7. **Execute incrementally**
   - Reuse existing patterns.
   - Avoid unrelated refactors.
   - Preserve unknown work.
   - Prefer reversible changes.

8. **Verify with the strongest available evidence**
   - Run focused tests/checks first, then broader relevant checks.
   - For research, verify sources and preserve provenance.
   - For UI, verify actual user-visible states when possible.
   - For integrations, verify against current provider docs/fixtures/sandbox behavior.
   - For releases, verify CI/runtime state.

9. **Adversarial self-check**
   Ask:
   - What assumption could make this wrong?
   - What edge case did I not test?
   - What claim am I making without evidence?
   - What security/data/customer-trust boundary changed?
   - Did I accidentally broaden scope or permissions?

10. **Handoff clearly**
    Report:
    - outcome,
    - changes/evidence,
    - checks actually performed,
    - failures/limitations,
    - unresolved uncertainty,
    - required reviewer/human approval,
    - next action.

## Unfamiliar-task rule

When the team has never done the task before:

- do not reject it merely because it is unfamiliar;
- do not bluff expertise;
- discover the actual environment and authoritative documentation;
- use the Product Engineer as the engineering fallback, Research & Product Analyst as the evidence/product fallback, and Orchestrator for routing;
- create a reusable skill only after the workflow proves repeatable enough to justify one.

## Tool-limit rule

If the requested task requires a tool/capability that is unavailable:

1. state the exact missing capability;
2. check for a supported alternative;
3. complete all safe independent work that does not require the missing capability;
4. stop before fabricating execution or results;
5. request the smallest necessary human action or connection.

## Completion rule

Code written is not completion. A plausible answer is not verification. A passing unit test is not production readiness.

Only claim the level of completion directly supported by evidence.