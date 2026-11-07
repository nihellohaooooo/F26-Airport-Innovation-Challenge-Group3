
import unittest
from unittest.mock import patch

from app import app


class TestSafetyAPI(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

        self.aircraft_params = {
            "oew": 1000,
            "oew_arm": 100,
            "max_zfw": 2000,
            "cg_min": 90,
            "cg_max": 110,
            "zones": {
                "FWD_CABIN": {
                    "type": "passenger",
                    "arm": 100,
                    "max_weight": 500,
                    "max_seats": 30
                }
            }
        }

        self.valid_plan = {
            "status": "Optimal",
            "assignments": {
                "FWD_CABIN": [
                    {
                        "id": "PAX-001",
                        "type": "passenger",
                        "count": 20,
                        "weight": 300
                    }
                ]
            },
            "unassigned": [],
            "metrics": {
                "total_weight": 1300,
                "final_cg": 100.0,
                "target_cg": 100.0,
                "deviation_inches": 0.0
            }
        }

    def send_request(self, solver_result, params=None):
        with patch(
            "app.solve_loading_plan",
            return_value=solver_result
        ):
            response = self.client.post(
                "/api/optimize",
                json={
                    "manifest": [],
                    "aircraft_params": (
                        params
                        if params is not None
                        else self.aircraft_params
                    )
                }
            )

        self.assertEqual(response.status_code, 200)
        return response.get_json()

    # Test 1: Valid loading plan
    def test_api_pass(self):
        result = self.send_request(self.valid_plan)

        self.assertEqual(result["status"], "Optimal")
        self.assertEqual(result["safety"]["status"], "PASS")
        self.assertTrue(result["safety"]["passed"])
        self.assertTrue(result["safety"]["weight"]["passed"])
        self.assertTrue(result["safety"]["cg"]["passed"])
        self.assertTrue(result["safety"]["seats"]["passed"])
        self.assertEqual(result["safety"]["reasons"], [])

    # Test 2: CG outside allowed range
    def test_api_unsafe_cg(self):
        params = self.aircraft_params.copy()
        params["cg_max"] = 99

        result = self.send_request(
            self.valid_plan,
            params=params
        )

        self.assertEqual(result["safety"]["status"], "UNSAFE")
        self.assertFalse(result["safety"]["passed"])
        self.assertFalse(result["safety"]["cg"]["passed"])
        self.assertTrue(
            any(
                "CG too far aft" in reason
                for reason in result["safety"]["reasons"]
            )
        )

    # Test 3: Unassigned payload
    def test_api_unsafe_unassigned(self):
        plan = {
            **self.valid_plan,
            "unassigned": [
                {
                    "id": "PAX-002",
                    "type": "passenger",
                    "count": 10,
                    "weight": 150
                }
            ]
        }

        result = self.send_request(plan)

        self.assertEqual(result["safety"]["status"], "UNSAFE")
        self.assertFalse(result["safety"]["passed"])
        self.assertFalse(result["safety"]["all_assigned"])
        self.assertEqual(
            result["safety"]["unassigned_count"], 1
        )
        self.assertTrue(
            any(
                "remain unassigned" in reason
                for reason in result["safety"]["reasons"]
            )
        )

    # Test 4: Solver cannot produce optimal plan
    def test_api_blocked(self):
        plan = {
            "status": "Infeasible"
        }

        result = self.send_request(plan)

        self.assertEqual(result["safety"]["status"], "BLOCKED")
        self.assertFalse(result["safety"]["passed"])
        self.assertTrue(result["safety"]["reasons"])


if __name__ == "__main__":
    unittest.main()
