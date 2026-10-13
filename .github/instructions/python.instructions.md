---
applyTo: "**/*.py"
description: "Python engineering rules for LEDGER and Opportunity Radar"
---

# Python engineering rules

- Follow the existing module structure and standard-library-first style unless a dependency is clearly justified.
- Prefer explicit, readable domain code over deep abstraction.
- Validate inputs at trust boundaries; do not allow malformed external data to become canonical internal state.
- Keep pure calculations separate from I/O where practical so behavior remains easy to test.
- Financial calculations use `Decimal`; do not introduce binary floating-point money logic.
- Keep Opportunity Radar scoring deterministic and auditable.
- Preserve source provenance rather than replacing source facts with AI summaries.
- Use descriptive exceptions/messages without leaking secrets or confidential data.
- New public behavior requires tests; bug fixes should add regression coverage when practical.
- Avoid broad refactors during scoped feature work unless required for correctness.
