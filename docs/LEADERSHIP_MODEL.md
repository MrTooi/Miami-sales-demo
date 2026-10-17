# Leadership Model

Status: adopted via Issue #88. Governance only; it changes no product, readiness, or scoring behavior. `AGENTS.md` remains the authoritative team charter.

## Roles

| Area | Human owner | Claude Code | ChatGPT |
|---|---|---|---|
| Product direction, pricing, customers, launches | **Decides** | Executes when authorized | Advises / proposes |
| Budgets, purchases, external publication | **Decides** | Never acts alone | Advises |
| Production deployment | **Approves** | Prepares only; never deploys without approval | Reviews |
| Secrets, credentials, permissions | **Owns** | Never accesses/expands | Reviews risk |
| Destructive operations | **Approves** | Never alone | Reviews |
| Architecture and acceptance criteria | Final say | Implements; may propose | **Primary designer / challenger** |
| Day-to-day engineering (branches, PRs, code, tests, CI fixes) | Can override | **Owns**, once authorized | Reviews |
| Technical status and blockers in GitHub | Reads | **Maintains** | Cross-checks |
| Independent review of high-risk work | Final approval; may review | **Never sole reviewer of own work**; `@claude` review-only runs are supplementary, not independent | **Primary independent reviewer** |
| Merging | **Approves every merge** | Never merges without explicit owner approval for that PR | Reports PASS/FAIL |

## Modes

### Pre-readiness (current)

- Product implementation is **PAUSED** until Issue #11 / Issue #69 readiness is satisfied and the human explicitly approves resuming.
- Claude may work only on the D-002 list in `docs/DECISIONS.md`: readiness hardening and readiness-infrastructure repair (including audit remediation), owner observability, demo reliability without product/financial logic changes, governance/docs, and tasks the human explicitly assigns.
- Claude does not choose its own product work from the backlog in this mode.
- Enabling unattended Agent OS scheduling is a separate gate (Issue #35) and is not authorized by this document or by passing #11/#69.

### Post-readiness (only after readiness passes **and** explicit human approval)

- The owner's resume decision (a new entry in `docs/DECISIONS.md`) must name the authorized scope. Within that named scope only, Claude may pick the next safe task, open scoped PRs, run CI, and fix failures without repeated prompting. `docs/ROADMAP.md` "Next after gate" items are candidates, not authorizations.
- All approval gates below still apply. Readiness approval does not authorize deployment, credentials, live financial integrations, or merging high-risk work.

## What Claude may decide autonomously (when work is authorized)

- Branch and commit structure, implementation details within an approved scope.
- Tests to add, and fixing failing tests/CI caused by its own change.
- Documentation updates that make docs match verified reality. This never includes the blind readiness inputs (`AGENTS.md`, `.github/copilot-instructions.md`, `agent_evals/team_profiles.json`) or other `agent_evals/` assets.
- Ordering of tasks inside an already-approved scope.

## What requires owner approval

Production deployment; secrets/credentials; permission expansion; destructive operations; live financial integrations; external publication or purchases; pricing, customer, and launch decisions; major scope changes; resuming paused product work; merging any PR; changes to blind readiness inputs, readiness gates, rubrics, scorer thresholds, or model configuration.

## Autonomy is trigger-based

Claude Code is not an always-on employee. It acts only when a task, event (such as an `@claude` mention or issue/PR event), or schedule triggers a run. "Keeps work moving" means working through authorized tasks during triggered runs and leaving state in GitHub, not running between triggers. Any scheduled or event-driven automation must itself be configured and approved by the human; this document does not create any.

## Disagreements and review findings

1. Reviewers label findings **BLOCKER** (must fix before advancing) or **WARNING** (should be considered), with evidence.
2. Claude responds to each blocker with a fix, or with evidence for why it is not valid, in GitHub.
3. Technical disputes: the evidence (tests, CI, repo state) decides. If still unresolved, or if it touches money/security/privacy/customer trust, escalate to the human owner, who decides.
4. Any reviewer may recommend stopping work; only the human decides to resume.
5. Outcomes of significant disputes are logged in `docs/DECISIONS.md`.
