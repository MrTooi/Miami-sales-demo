"""Prove the accuracy self-test catches mistakes: plant one bug at a time and count the shops that notice.

Each "mutation" below temporarily breaks MargenX in a realistic way (nothing is saved or changed on
disk). For each one, the first 400 made-up shops from tests/accuracy_shops.py are checked with the
same comparisons as tests/test_accuracy.py. A bug that no shop notices would mean the self-test has
a blind spot. Exits 1 if any planted bug is missed.

Usage: python scripts/accuracy_mutations.py
"""
from __future__ import annotations

import itertools
import sys
from contextlib import ExitStack
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import job_profit as jp  # noqa: E402
import marginx_insights as mi  # noqa: E402
import marginx_ui as ui  # noqa: E402
from tests.test_accuracy import mismatches, screen_mismatches  # noqa: E402

SHOPS = 400
_category, _summarize, _fold = jp.cost_category, mi.summarize, jp._fold


def _shipping_as_materials(cost_type):
    return "materials" if (cost_type or "").strip().lower() == "shipping" else _category(cost_type)


def _fees_left_out(self):
    return sum((v for k, v in self.costs.items() if k != "fees_overhead"), jp.ZERO)


def _credits_left_out(report):
    s = _summarize(report)
    return s.__class__(**{**s.__dict__, "sales": s.sales + sum((-j.sales for j in report.jobs if j.sales < 0), jp.ZERO)})


def _overhead_out_of_left(report):
    s = _summarize(report)
    return s.__class__(**{**s.__dict__, "left_after_job_costs": s.left_after_job_costs - s.overhead_costs})


def _half_even(part, whole):
    if whole <= 0:
        return None
    return int((part * 100 / whole).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


_unique = itertools.count()
MUTATIONS = {
    "Shipping counted as materials (wrong \"Complete\" status)":
        [mock.patch.object(jp, "cost_category", _shipping_as_materials)],
    "Fees recorded on a job left out of its costs":
        [mock.patch.object(jp.JobResult, "total_costs", property(_fees_left_out))],
    "Credits left out of total sales": [mock.patch.object(mi, "summarize", _credits_left_out)],
    "Overhead wrongly taken out of \"left after job costs\"": [mock.patch.object(mi, "summarize", _overhead_out_of_left)],
    "Percentages rounded the wrong way at exact halves":
        [mock.patch.object(mi, "percent", _half_even), mock.patch.object(ui, "percent", _half_even)],
    "Sales with no job number ignored when deciding \"Complete\"":
        [mock.patch.object(jp, "_fold", lambda name: f"{_fold(name)}#{next(_unique)}")],
}


def main() -> int:
    missed = 0
    for name, patches in MUTATIONS.items():
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            caught = sum(1 for seed in range(SHOPS) if mismatches(seed) or screen_mismatches(seed))
        missed += not caught
        print(f"{'CAUGHT' if caught else 'MISSED'}: {name}: {caught} of {SHOPS} shops")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
