
import csv
import json
from pathlib import Path

from seat_mapper import map_seats


# Locate the team's data directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_json(filename):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


def load_csv(filename):
    with open(
        DATA_DIR / filename,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        return list(csv.DictReader(file))


def load_aircraft_seats(aircraft_type):
    """
    Generate a candidate seat map using aircraft.json.

    Cabin types and special seat restrictions are not yet
    supplied by the team's data.
    """
    aircraft_data = load_json("aircraft.json")

    if aircraft_type not in aircraft_data:
        raise ValueError(f"Unknown aircraft: {aircraft_type}")

    aircraft = aircraft_data[aircraft_type]

    rows = aircraft["rows"]
    letters = aircraft["seats_per_row"]

    seats = []

    for row in range(1, rows + 1):
        for letter in letters:
            seats.append({
                "seat_id": f"{row}{letter}",
                "cabin": "unspecified",
                "available": True
            })

    return seats


def load_passengers():
    """
    Read passengers.csv and exclude passengers already
    removed by DCS.
    """
    passengers_data = load_csv("passengers.csv")
    dcs_removed_data = load_csv("dcs_removed.csv")

    removed_ids = {
        row["pax_id"]
        for row in dcs_removed_data
    }

    passengers = []
    excluded = []

    for row in passengers_data:
        pax_id = row["pax_id"]

        removed_flag = (
            row["removed_by_dcs"].strip().lower() == "true"
        )

        if removed_flag or pax_id in removed_ids:
            excluded.append(pax_id)
            continue

        passenger = {
            "passenger_id": pax_id,
            "original_seat": row["seat"],
            "cabin": "unspecified"
        }

        # Keep group_id as metadata. It is not necessarily
        # a family relationship.
        if row.get("group_id"):
            passenger["group_id"] = row["group_id"]

        passengers.append(passenger)

    return passengers, excluded


def run_aircraft_swap():
    flight = load_json("flight.json")

    old_aircraft = flight["old_aircraft"]
    new_aircraft = flight["new_aircraft"]

    passengers, excluded = load_passengers()
    new_seats = load_aircraft_seats(new_aircraft)

    result = map_seats(passengers, new_seats)

    expected_count = flight["dcs"]["pax_boarding"]
    actual_count = len(passengers)

    print("=" * 50)
    print("AIRCRAFT SWAP - SEAT MAPPING")
    print("=" * 50)

    print(f"Flight: {flight['flight_no']}")
    print(f"Original aircraft: {old_aircraft}")
    print(f"Replacement aircraft: {new_aircraft}")

    print(f"\nDCS expected passengers: {expected_count}")
    print(f"Active passengers: {actual_count}")
    print(f"DCS removed passengers: {len(excluded)}")

    print(f"\nGenerated seats: {len(new_seats)}")
    print(f"Mapped passengers: {result['mapped_count']}")
    print(f"Unmapped passengers: {result['unmapped_count']}")

    if actual_count != expected_count:
        print("\nWARNING: DCS passenger count mismatch!")

    print("\nSample seat assignments:")

    for assignment in result["assignments"][:10]:
        print(
            f"{assignment['passenger_id']}: "
            f"{assignment['old_seat']} -> "
            f"{assignment['new_seat']} "
            f"({assignment['status']})"
        )

    if result["unmapped"]:
        print("\nPassengers requiring DCS review:")

        for passenger in result["unmapped"]:
            print(passenger["passenger_id"])

    return result


if __name__ == "__main__":
    run_aircraft_swap()
