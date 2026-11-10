
import unittest

from safety import (
    check_seat_capacity,
    check_center_of_gravity,
    check_weight_limits
)


class TestSafetyGate(unittest.TestCase):

    def test_seat_capacity_exceeded(self):
        aircraft_params = {
            "zones": {
                "FWD_CABIN": {
                    "type": "passenger",
                    "max_seats": 30
                }
            }
        }

        load_plan = {
            "assignments": {
                "FWD_CABIN": [
                    {"count": 45}
                ]
            }
        }

        result = check_seat_capacity(
            aircraft_params, load_plan
        )

        self.assertFalse(result["passed"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn(
            "seat capacity exceeded",
            result["violations"][0]
        )

    def test_cg_out_of_range(self):
        aircraft_params = {
            "oew": 1000,
            "oew_arm": 100,
            "cg_min": 90,
            "cg_max": 110,
            "zones": {
                "AFT_HOLD": {
                    "arm": 200
                }
            }
        }

        load_plan = {
            "assignments": {
                "AFT_HOLD": [
                    {"weight": 500}
                ]
            }
        }

        result = check_center_of_gravity(
            aircraft_params, load_plan
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["calculated_cg"], 133.33)
        self.assertIn(
            "CG too far aft",
            result["violations"][0]
        )

    def test_max_zero_fuel_weight_exceeded(self):
        aircraft_params = {
            "oew": 1000,
            "max_zfw": 1200,
            "zones": {
                "FWD_HOLD": {
                    "max_weight": 500
                }
            }
        }

        load_plan = {
            "assignments": {
                "FWD_HOLD": [
                    {"weight": 300}
                ]
            }
        }

        result = check_weight_limits(
            aircraft_params, load_plan
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["total_weight"], 1300)
        self.assertIn(
            "Maximum zero fuel weight exceeded",
            result["violations"][0]
        )

    def test_zone_weight_limit_exceeded(self):
        aircraft_params = {
            "oew": 1000,
            "max_zfw": 2000,
            "zones": {
                "FWD_HOLD": {
                    "max_weight": 200
                }
            }
        }

        load_plan = {
            "assignments": {
                "FWD_HOLD": [
                    {"weight": 300}
                ]
            }
        }

        result = check_weight_limits(
            aircraft_params, load_plan
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["total_weight"], 1300)
        self.assertIn(
            "FWD_HOLD overweight",
            result["violations"][0]
        )


    def test_valid_loading_plan(self):
        aircraft_params = {
            "oew": 1000,
            "oew_arm": 100,
            "max_zfw": 2000,
            "cg_min": 90,
            "cg_max": 110,
            "zones": {
                "FWD_CABIN": {
                    "type": "passenger",
                    "max_seats": 30,
                    "max_weight": 500,
                    "arm": 100
                }
            }
        }

        load_plan = {
            "assignments": {
                "FWD_CABIN": [
                    {
                        "type": "passenger",
                        "count": 20,
                        "weight": 300
                    }
                ]
            }
        }

        weight_result = check_weight_limits(
            aircraft_params, load_plan
        )
        cg_result = check_center_of_gravity(
            aircraft_params, load_plan
        )
        seat_result = check_seat_capacity(
            aircraft_params, load_plan
        )

        self.assertTrue(weight_result["passed"])
        self.assertTrue(cg_result["passed"])
        self.assertTrue(seat_result["passed"])
        self.assertEqual(weight_result["total_weight"], 1300)
        self.assertEqual(cg_result["calculated_cg"], 100.0)

        
    def test_cg_too_far_forward(self):
        aircraft_params = {
            "oew": 1000,
            "oew_arm": 100,
            "cg_min": 90,
            "cg_max": 110,
            "zones": {
                "FWD_HOLD": {
                    "arm": 50
                }
            }
        }

        load_plan = {
            "assignments": {
                "FWD_HOLD": [
                    {"weight": 500}
                ]
            }
        }

        result = check_center_of_gravity(
            aircraft_params, load_plan
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["calculated_cg"], 83.33)
        self.assertIn(
            "CG too far forward",
            result["violations"][0]
        )


    def test_empty_loading_plan(self):
        aircraft_params = {
            "oew": 1000,
            "oew_arm": 100,
            "cg_min": 90,
            "cg_max": 110,
            "zones": {}
        }

        load_plan = {
            "assignments": {}
        }

        result = check_center_of_gravity(
            aircraft_params, load_plan
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["calculated_cg"], 100.0)
        self.assertEqual(result["violations"], [])

if __name__ == "__main__":
    unittest.main()
