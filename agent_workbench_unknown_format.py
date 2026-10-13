"""Synthetic evaluation task. Intentionally incorrect; not product code.

Synthetic ORADAR1 text format:
- first non-empty, non-comment line must be exactly ORADAR1
- subsequent non-comment lines are: evidence_id|market|kind|observed_fact
- observed_fact may itself contain additional `|` characters
- evidence_id, market, kind, and observed_fact must be nonblank
- duplicate evidence_id values are invalid
- malformed input must fail explicitly rather than being silently dropped
"""


def parse_oradar1(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line == "ORADAR1":
            continue
        parts = line.split(",")
        if len(parts) != 4:
            continue
        rows.append(
            {
                "evidence_id": parts[0],
                "market": parts[1],
                "kind": parts[2],
                "observed_fact": parts[3],
            }
        )
    return rows
