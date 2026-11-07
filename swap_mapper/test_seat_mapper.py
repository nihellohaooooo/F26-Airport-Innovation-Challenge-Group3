
import unittest
from seat_mapper import map_seats


class TestSeatMapper(unittest.TestCase):

    def test_keep_original_seat(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(
            result["assignments"][0]["status"],
            "UNCHANGED"
        )

    def test_reassign_seat(self):
        passengers = [
            {
                "passenger_id": "P002",
                "original_seat": "28A",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "15B", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(
            result["assignments"][0]["new_seat"],
            "15B"
        )
        self.assertEqual(
            result["assignments"][0]["status"],
            "REASSIGNED"
        )

    def test_no_available_seat(self):
        passengers = [
            {
                "passenger_id": "P003",
                "original_seat": "28A",
                "cabin": "economy"
            }
        ]

        result = map_seats(passengers, [])

        self.assertEqual(result["mapped_count"], 0)
        self.assertEqual(result["unmapped_count"], 1)
        self.assertEqual(
            result["unmapped"][0]["status"],
            "NEEDS_DCS_REVIEW"
        )

    def test_no_duplicate_seats(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy"
            },
            {
                "passenger_id": "P002",
                "original_seat": "12A",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "12B", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        assigned_seats = [
            item["new_seat"]
            for item in result["assignments"]
        ]

        self.assertEqual(result["mapped_count"], 2)
        self.assertEqual(
            len(assigned_seats),
            len(set(assigned_seats))
        )

    def test_aircraft_swap_with_limited_seats(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "1A",
                "cabin": "business"
            },
            {
                "passenger_id": "P002",
                "original_seat": "12A",
                "cabin": "economy"
            },
            {
                "passenger_id": "P003",
                "original_seat": "12B",
                "cabin": "economy"
            },
            {
                "passenger_id": "P004",
                "original_seat": "28A",
                "cabin": "economy"
            },
            {
                "passenger_id": "P005",
                "original_seat": "28B",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "1A", "cabin": "business"},
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "12B", "cabin": "economy"},
            {"seat_id": "12C", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 4)
        self.assertEqual(result["unmapped_count"], 1)

        assigned_seats = [
            item["new_seat"]
            for item in result["assignments"]
        ]

        self.assertEqual(
            len(assigned_seats),
            len(set(assigned_seats))
        )

    def test_family_seating(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "28A",
                "cabin": "economy",
                "family_id": "F001"
            },
            {
                "passenger_id": "P002",
                "original_seat": "28B",
                "cabin": "economy",
                "family_id": "F001"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "12B", "cabin": "economy"},
            {"seat_id": "15A", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        family_seats = {
            item["new_seat"]
            for item in result["assignments"]
        }

        self.assertEqual(
            family_seats,
            {"12A", "12B"}
        )

    def test_family_seating_unordered_seats(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "28A",
                "cabin": "economy",
                "family_id": "F001"
            },
            {
                "passenger_id": "P002",
                "original_seat": "28B",
                "cabin": "economy",
                "family_id": "F001"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "15A", "cabin": "economy"},
            {"seat_id": "12B", "cabin": "economy"}
        ]

        result = map_seats(passengers, seats)

        family_seats = {
            item["new_seat"]
            for item in result["assignments"]
        }

        self.assertEqual(
            family_seats,
            {"12A", "12B"}
        )

    def test_family_seating_avoids_aisle(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "28A",
                "cabin": "economy",
                "family_id": "F001"
            },
            {
                "passenger_id": "P002",
                "original_seat": "28B",
                "cabin": "economy",
                "family_id": "F001"
            }
        ]

        # 12C and 12D are separated by an aisle.
        # 13A and 13B are physically adjacent.
        seats = [
            {
                "seat_id": "12C",
                "cabin": "economy",
                "seat_block": "LEFT",
                "adjacent_seats": [],
                "available": True
            },
            {
                "seat_id": "12D",
                "cabin": "economy",
                "seat_block": "RIGHT",
                "adjacent_seats": [],
                "available": True
            },
            {
                "seat_id": "13A",
                "cabin": "economy",
                "seat_block": "LEFT",
                "adjacent_seats": ["13B"],
                "available": True
            },
            {
                "seat_id": "13B",
                "cabin": "economy",
                "seat_block": "LEFT",
                "adjacent_seats": ["13A"],
                "available": True
            }
        ]

        result = map_seats(passengers, seats)

        family_seats = {
            item["new_seat"]
            for item in result["assignments"]
        }

        self.assertEqual(result["mapped_count"], 2)
        self.assertEqual(
            family_seats,
            {"13A", "13B"}
        )


    def test_blocked_seat_not_assigned(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy"
            }
        ]

        seats = [
            {
                "seat_id": "12A",
                "cabin": "economy",
                "available": False
            },
            {
                "seat_id": "12B",
                "cabin": "economy",
                "available": True
            }
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(
            result["assignments"][0]["new_seat"],
            "12B"
        )
        self.assertEqual(
            result["assignments"][0]["status"],
            "REASSIGNED"
        )


    def test_exit_row_requires_eligibility(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy",
                "exit_row_eligible": False
            }
        ]

        seats = [
            {
                "seat_id": "12A",
                "cabin": "economy",
                "available": True,
                "exit_row": True
            },
            {
                "seat_id": "13A",
                "cabin": "economy",
                "available": True,
                "exit_row": False
            }
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(
            result["assignments"][0]["new_seat"],
            "13A"
        )
        self.assertEqual(
            result["assignments"][0]["status"],
            "REASSIGNED"
        )

    def test_exit_row_eligible_passenger(self):
        passengers = [
            {
                "passenger_id": "P002",
                "original_seat": "12A",
                "cabin": "economy",
                "exit_row_eligible": True
            }
        ]

        seats = [
            {
                "seat_id": "12A",
                "cabin": "economy",
                "available": True,
                "exit_row": True
            }
        ]

        result = map_seats(passengers, seats)

        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(
            result["assignments"][0]["new_seat"],
            "12A"
        )

    def test_duplicate_passenger_ids_rejected(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy"
            },
            {
                "passenger_id": "P001",
                "original_seat": "12B",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "12B", "cabin": "economy"}
        ]

        with self.assertRaises(ValueError):
            map_seats(passengers, seats)

    def test_duplicate_aircraft_seat_ids_rejected(self):
        passengers = [
            {
                "passenger_id": "P001",
                "original_seat": "12A",
                "cabin": "economy"
            }
        ]

        seats = [
            {"seat_id": "12A", "cabin": "economy"},
            {"seat_id": "12A", "cabin": "economy"}
        ]

        with self.assertRaises(ValueError):
            map_seats(passengers, seats)

if __name__ == "__main__":
    unittest.main()
