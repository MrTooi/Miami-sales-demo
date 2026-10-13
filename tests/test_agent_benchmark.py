import unittest

from agent_evals.benchmark import benchmark_all, benchmark_lineup, best_lineup, load_profiles


class AgentBenchmarkTests(unittest.TestCase):
    def test_candidate_eight_covers_all_benchmark_scenarios(self):
        result = benchmark_lineup("candidate_eight")
        missed = [r for r in result.scenario_results if not r.covered]
        self.assertEqual([], missed)
        self.assertEqual(1.0, result.coverage_rate)

    def test_candidate_eight_has_high_risk_independent_review_coverage(self):
        result = benchmark_lineup("candidate_eight")
        failed = [
            r
            for r in result.scenario_results
            if r.high_risk_review_ready is False
        ]
        self.assertEqual([], failed)
        self.assertEqual(1.0, result.high_risk_review_rate)

    def test_expanded_lineup_improves_over_original_five(self):
        expanded = benchmark_lineup("candidate_eight")
        original = benchmark_lineup("current_five")
        self.assertGreater(expanded.coverage_rate, original.coverage_rate)
        self.assertGreater(expanded.score, original.score)

    def test_expanded_lineup_improves_over_generic_reference_team(self):
        expanded = benchmark_lineup("candidate_eight")
        reference = benchmark_lineup("github_three_reference")
        self.assertGreater(expanded.coverage_rate, reference.coverage_rate)
        self.assertGreater(expanded.score, reference.score)

    def test_candidate_is_best_of_evaluated_lineups(self):
        self.assertEqual("candidate_eight", best_lineup().lineup)

    def test_all_repo_profiles_point_to_agent_files(self):
        data = load_profiles()
        for name, profile in data["agents"].items():
            if profile["source"] != "repo":
                continue
            with self.subTest(agent=name):
                self.assertTrue(profile.get("file"), name)

    def test_benchmarks_are_nonempty_and_bounded(self):
        results = benchmark_all()
        self.assertGreaterEqual(len(results), 3)
        for result in results:
            with self.subTest(lineup=result.lineup):
                self.assertGreater(len(result.scenario_results), 0)
                self.assertGreaterEqual(result.score, 0.0)
                self.assertLessEqual(result.score, 100.0)


if __name__ == "__main__":
    unittest.main()
