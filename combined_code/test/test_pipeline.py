"""Integration checks for every bundled aircraft swap scenario."""
import json
import unittest
from pathlib import Path

from pipeline import run_scenario

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"


class PipelineScenarioTests(unittest.TestCase):
    def test_all_scenario_expectations(self):
        for path in sorted(SCENARIOS.glob("*.json")):
            with self.subTest(scenario=path.stem):
                scenario = json.loads(path.read_text(encoding="utf-8"))
                expected = scenario["expected_demo_result"]
                result = run_scenario(scenario)
                self.assertEqual(result["status"], expected["status"])
                if "passengers_mapped" in expected:
                    self.assertEqual(result["passenger_mapping"]["passenger_count_mapped"],
                                     expected["passengers_mapped"])
                if "bags_pulled" in expected:
                    self.assertEqual(result["count_check"]["bags"]["pulled"], expected["bags_pulled"])
                if "bags_at_risk" in expected:
                    self.assertEqual(len(result["bag_actions"]["at_risk"]), expected["bags_at_risk"])
                if "bags_left_behind" in expected:
                    self.assertEqual(result["count_check"]["bags"]["left_behind"],
                                     expected["bags_left_behind"])
                if "moves" in expected:
                    self.assertEqual(len(result["moves"]), expected["moves"])
                if "cargo_bumped" in expected:
                    self.assertEqual(len(result["cargo_bumped"]), expected["cargo_bumped"])
                if "solver_status" in expected:
                    self.assertEqual(result["solver"]["status"], expected["solver_status"])


if __name__ == "__main__":
    unittest.main()
