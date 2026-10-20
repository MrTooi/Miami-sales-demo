"""Run MargenX's accuracy self-test on many made-up shops with known answers.

Each shop is generated from a seed (tests/accuracy_shops.py works out its right answers in whole
cents without MargenX code), read by MargenX from CSV files like an upload, and every figure and
status is compared, then the results screen is read back and compared too.

Usage: python scripts/accuracy_check.py [NUMBER_OF_SHOPS]   (default 5000)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import accuracy_shops as shops  # noqa: E402
from tests.test_accuracy import mismatches, screen_mismatches  # noqa: E402


def main(argv: list[str]) -> int:
    count = int(argv[1]) if len(argv) > 1 else 5000
    started = time.time()
    problems: list[str] = []
    jobs = customers = 0
    for seed in range(count):
        answer = shops.answer(shops.make_shop(seed))
        jobs += len(answer.jobs)
        customers += len(answer.customers)
        problems += mismatches(seed) + screen_mismatches(seed)
    took = time.time() - started
    print(f"{count} made-up shops, {jobs} jobs, {customers} customers checked in {took:.0f} s.")
    if problems:
        print(f"{len(problems)} differences. First ones:")
        print("\n".join(problems[:20]))
        return 1
    print("Every figure, status and on-screen number matched the known answers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
