"""Small, readable examples for the four pipeline engines."""
import unittest

import bag_offload_tracker
import replanner
import safety_gate
import swap_mapper


def sample_aircraft():
    return {
        "type": "DEMO",
        "specs": {"max_seats": 4},
        "seats_per_row": ["A", "B"],
        "dry_operating_weight_kg": 1000,
        "dry_operating_arm_m": 10,
        "max_zero_fuel_weight_kg": 1450,
        "cg_forward_limit_m": 8,
        "cg_aft_limit_m": 12,
        "cg_target_m": 10,
        "cabin_zones": [
            {"zone": "FRONT", "row_from": 1, "row_to": 1, "seats": 2,
             "arm_m": 10, "max_weight_kg": 200},
            {"zone": "REAR", "row_from": 2, "row_to": 2, "seats": 2,
             "arm_m": 20, "max_weight_kg": 200},
        ],
        "holds": [
            {"hold": "FWD", "arm_m": 8, "max_weight_kg": 600,
             "max_volume_m3": 5, "dg_forbidden_classes": []},
            {"hold": "AFT", "arm_m": 12, "max_weight_kg": 600,
             "max_volume_m3": 5, "dg_forbidden_classes": ["8"]},
        ],
    }


class SwapMapperDemoTests(unittest.TestCase):
    def test_maps_seats_skips_removed_and_flags_row_outside_aircraft(self):
        passengers = [
            {"pax_id": "P1", "seat": "1A", "row": 1, "category": "M"},
            {"pax_id": "P2", "seat": "2B", "row": 2, "category": "I"},
            {"pax_id": "P3", "seat": "3A", "row": 3, "category": "F"},
            {"pax_id": "P4", "seat": "1B", "row": 1, "category": "F",
             "removed_by_dcs": "true"},
        ]
        weights = {"summer": {"M": 80, "F": 70, "C": 30, "I": 10}}

        result = swap_mapper.build_swap_result(passengers, sample_aircraft(), weights, "summer")

        self.assertEqual([p["pax_id"] for p in result["mapped_passengers"]], ["P1", "P2"])
        self.assertEqual([p["pax_id"] for p in result["doesnt_fit"]], ["P3"])
        self.assertEqual(result["zone_weights"]["FRONT"]["weight_kg"], 80)
        self.assertEqual(result["zone_weights"]["REAR"]["weight_kg"], 10)


class BagTrackerDemoTests(unittest.TestCase):
    def test_pull_order_late_bags_and_manifest_reconciliation(self):
        bags = [
            {"tag": "CART", "owner_pax_id": "R1", "location": "cart_1",
             "stack_pos": "1", "weight_kg": "20"},
            {"tag": "HOLD", "owner_pax_id": "R1", "location": "hold_FWD",
             "stack_pos": "1", "weight_kg": "25"},
            {"tag": "LATE_REMOVED", "owner_pax_id": "R1", "location": "inbound",
             "is_connecting": True, "eta": "19:20", "weight_kg": "18"},
            {"tag": "LATE_FLYING", "owner_pax_id": "P2", "location": "inbound",
             "is_connecting": True, "eta": "19:30", "weight_kg": "19"},
            {"tag": "ONTIME", "owner_pax_id": "P2", "location": "inbound",
             "is_connecting": True, "eta": "19:00", "weight_kg": "21"},
        ]

        result = bag_offload_tracker.build_tracker_result(bags, {"R1"}, "19:15", 5)

        self.assertEqual([b["tag"] for b in result["pull_list"]], ["CART", "HOLD"])
        self.assertEqual([b["tag"] for b in result["at_risk"]], ["LATE_REMOVED", "LATE_FLYING"])
        self.assertEqual(result["count_check"]["counts"], {
            "flying": 1, "pulled": 2, "left_behind": 2, "unknown": 0,
        })
        self.assertTrue(result["count_check"]["ok"])


class LoadReplannerDemoTests(unittest.TestCase):
    def _cargo(self, cid, priority, current_hold):
        return {"cargo_id": cid, "description": cid, "weight_kg": 450,
                "volume_m3": 1, "priority": priority, "dg_class": "",
                "current_hold": current_hold}

    def test_keeps_high_priority_cargo_before_low_priority_cargo(self):
        cargo = [self._cargo("LOADED_LOW", 5, "FWD"),
                 self._cargo("DOCK_HIGH", 1, "")]

        plan = replanner.solve_load_plan([], cargo, sample_aircraft(), 1000, 10000)

        self.assertEqual(plan["status"], "OPTIMAL")
        self.assertEqual([c["cargo_id"] for c in plan["cargo_bumped"]], ["LOADED_LOW"])
        self.assertIn("priority 5", plan["cargo_bumped"][0]["reason"])

    def test_lightning_mode_prioritizes_fewer_handling_actions(self):
        cargo = [self._cargo("LOADED_LOW", 5, "FWD"),
                 self._cargo("DOCK_HIGH", 1, "")]

        plan = replanner.solve_load_plan(
            [], cargo, sample_aircraft(), 1000, 10000, {"lightning_mode": True})

        self.assertEqual(plan["status"], "OPTIMAL")
        self.assertEqual([c["cargo_id"] for c in plan["cargo_bumped"]], ["DOCK_HIGH"])
        self.assertEqual(plan["handling_actions"]["total"], 0)

    def test_must_fly_cargo_that_exceeds_mzfw_has_no_plan(self):
        cargo = [{"cargo_id": "REQUIRED", "weight_kg": 600, "volume_m3": 1,
                  "priority": 1, "must_fly": True, "current_hold": ""}]

        plan = replanner.solve_load_plan([], cargo, sample_aircraft(), 1000, 10000)

        self.assertEqual(plan["status"], "INFEASIBLE")
        self.assertIn("must-fly cargo", plan["reason"])


class SafetyGateDemoTests(unittest.TestCase):
    def setUp(self):
        self.aircraft = sample_aircraft()
        self.aircraft["specs"]["max_seats"] = 2
        self.aircraft["cabin_zones"] = [
            {"zone": "CABIN", "row_from": 1, "row_to": 2, "seats": 2,
             "arm_m": 10, "max_weight_kg": 200},
        ]
        self.passengers = [{"pax_id": "P1", "category": "M"}]
        self.bags = [{"tag": "B1", "owner_pax_id": "P1", "weight_kg": 50,
                      "volume_m3": 0.1}]
        self.cargo = [{"cargo_id": "C1", "weight_kg": 50, "volume_m3": 1,
                       "dg_class": ""}]
        self.plan = {
            "passenger_ids": ["P1"],
            "mapped_passengers": [{"pax_id": "P1", "category": "M", "zone": "CABIN"}],
            "bag_holds": {"B1": "FWD"}, "cargo_holds": {"C1": "AFT"},
            "cargo_bumped_ids": [], "bags_offloaded": [], "bags_left_behind": [],
        }
        self.weights = {"summer": {"M": 80, "F": 70, "X": 75, "C": 30, "I": 10}}
        self.dcs = {"pax_boarding": 1, "bags_checked": 1}

    def _evaluate(self, plan=None, aircraft=None, dcs=None):
        return safety_gate.evaluate_plan(
            plan or self.plan, self.passengers, self.bags, self.cargo,
            aircraft or self.aircraft, self.weights, "summer", dcs or self.dcs)

    def test_valid_plan_is_safe(self):
        self.assertEqual(self._evaluate()["status"], "SAFE")

    def test_passenger_count_mismatch_blocks_plan(self):
        result = self._evaluate(dcs={"pax_boarding": 2, "bags_checked": 1})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(c["name"] == "passenger count" and not c["passed"]
                            for c in result["checks"]))

    def test_weight_limit_violation_marks_plan_unsafe(self):
        aircraft = dict(self.aircraft)
        aircraft["max_zero_fuel_weight_kg"] = 1100
        self.assertEqual(self._evaluate(aircraft=aircraft)["status"], "UNSAFE")


if __name__ == "__main__":
    unittest.main()
