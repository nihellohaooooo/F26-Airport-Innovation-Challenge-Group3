"""Three compact end-to-end cases for a short project demo."""
import json
import unittest
from pathlib import Path

from pipeline import run_scenario


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"


def read_scenario(name):
    return json.loads((SCENARIOS / name).read_text(encoding="utf-8"))


def clear_to_fly_scenario():
    """Summer demo with every inbound bag arriving before the loading cutoff."""
    scenario = read_scenario("a320_winter_swap.json")
    cutoff = scenario["flight"]["loading_cutoff"]
    for bag in scenario["bags"]:
        if bag.get("location") == "inbound" and bag.get("eta") and bag["eta"] > cutoff:
            bag["eta"] = "19:10"
    return scenario


class PipelineDemoTests(unittest.TestCase):
    def test_clear_to_fly_demo_is_safe(self):
        result = run_scenario(clear_to_fly_scenario(), options={"season": "summer"})

        self.assertEqual(result["status"], "SAFE")
        self.assertTrue(result["safety_gate"]["ready_for_load_controller"])
        self.assertEqual(result["bag_actions"]["bags_left_behind"], [])
        self.assertTrue(result["count_check"]["ok"])

    def test_wrong_dcs_passenger_count_is_blocked(self):
        result = run_scenario(read_scenario("a320_wrong_pax_count.json"))

        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("passenger count" in reason.lower()
                            for reason in result["reasons"]))

    def test_infeasible_must_fly_cargo_is_unsafe(self):
        result = run_scenario(read_scenario("a320_infeasible_must_fly.json"))

        self.assertEqual(result["status"], "UNSAFE")
        self.assertEqual(result["solver"]["status"], "INFEASIBLE")
        self.assertIn("must-fly cargo", result["solver"]["reason"])


if __name__ == "__main__":
    unittest.main()
