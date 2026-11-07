
import csv
import json
from pathlib import Path

from seat_mapper import map_seats


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_json(filename):
    """Load JSON data from the team's data directory."""
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


def load_csv(filename):
    """Load CSV data from the team's data directory."""
    with open(
        DATA_DIR / filename,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        return list(csv.DictReader(file))


def get_cabin_for_row(row_number, cabin_sections):
    """
    Determine a passenger's cabin from the aircraft layout.
    """
    matches = [
        section["cabin"]
        for section in cabin_sections
        if section["row_from"] <= row_number <= section["row_to"]
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected one cabin for row {row_number}, "
            f"found {len(matches)}"
        )

    return matches[0]


def load_aircraft_seats(aircraft_type):
    """
    Generate replacement-aircraft seats.

    aircraft.json:
        Aircraft type, number of rows, seat letters.

    seat_layouts.json:
        Cabin sections, aisle blocks, blocked seats,
        exit rows and adjacency.

    This is a configurable demonstration layout,
    not an airline-certified seating plan.
    """

    aircraft_data = load_json("aircraft.json")
    layouts = load_json("seat_layouts.json")

    if aircraft_type not in aircraft_data:
        raise ValueError(
            f"Unknown aircraft: {aircraft_type}"
        )

    if aircraft_type not in layouts:
        raise ValueError(
            f"No seat layout defined for: {aircraft_type}"
        )

    aircraft = aircraft_data[aircraft_type]
    layout = layouts[aircraft_type]

    rows = aircraft["rows"]
    valid_letters = aircraft["seats_per_row"]

    seat_blocks = layout["default_layout"]["seat_blocks"]
    cabin_sections = layout["cabin_sections"]

    blocked = set(layout.get("blocked_seats", []))
    exit_rows = set(layout.get("exit_rows", []))

    # Validate that configured seat letters match aircraft data
    configured_letters = [
        letter
        for block in seat_blocks
        for letter in block
    ]

    if (
        len(configured_letters) != len(set(configured_letters))
        or set(configured_letters) != set(valid_letters)
    ):
        raise ValueError(
            "Seat layout does not match aircraft seat letters"
        )

    seats = []

    for row_number in range(1, rows + 1):

        cabin = get_cabin_for_row(
            row_number,
            cabin_sections
        )

        for block_index, block in enumerate(seat_blocks):

            for position, letter in enumerate(block):

                seat_id = f"{row_number}{letter}"

                adjacent = []

                if position > 0:
                    adjacent.append(
                        f"{row_number}{block[position - 1]}"
                    )

                if position < len(block) - 1:
                    adjacent.append(
                        f"{row_number}{block[position + 1]}"
                    )

                seats.append({
                    "seat_id": seat_id,
                    "cabin": cabin,
                    "seat_block": block_index,
                    "adjacent_seats": adjacent,
                    "available": seat_id not in blocked,
                    "exit_row": row_number in exit_rows
                })

    return seats


def load_passengers():
    """
    Load the team's passenger manifest.

    - Exclude passengers already removed by DCS.
    - Convert pax_id to passenger_id.
    - Convert seat to original_seat.
    - Determine cabin using the ORIGINAL aircraft layout.
    - Preserve group_id without assuming it means family.
    """

    flight = load_json("flight.json")
    layouts = load_json("seat_layouts.json")

    old_aircraft = flight["old_aircraft"]

    if old_aircraft not in layouts:
        raise ValueError(
            f"No original-aircraft layout: {old_aircraft}"
        )

    cabin_sections = layouts[old_aircraft]["cabin_sections"]

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

        # Never reassign passengers already removed by DCS
        if removed_flag or pax_id in removed_ids:
            excluded.append(pax_id)
            continue

        seat_row = int(row["row"])

        # Determine cabin from the original aircraft layout
        cabin = get_cabin_for_row(
            seat_row,
            cabin_sections
        )

        passenger = {
            "passenger_id": pax_id,
            "original_seat": row["seat"],
            "cabin": cabin
        }

        # Keep team group metadata.
        # group_id may represent a travel group, not a family.
        group_id = row.get("group_id", "").strip()

        if group_id:
            passenger["group_id"] = group_id

        passengers.append(passenger)

    return passengers, excluded


def run_aircraft_swap():
    """Run seat mapping using the team's flight and aircraft data."""

    flight = load_json("flight.json")

    old_aircraft = flight["old_aircraft"]
    new_aircraft = flight["new_aircraft"]

    passengers, excluded = load_passengers()

    new_seats = load_aircraft_seats(new_aircraft)

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

    # Avoid producing a proposed seating plan when
    # the manifest contradicts the DCS boarding count.
    if actual_count != expected_count:
        print("\nBLOCKED: DCS passenger count mismatch!")
        return {
            "status": "BLOCKED",
            "reason": "DCS passenger count mismatch",
            "expected_count": expected_count,
            "actual_count": actual_count
        }

    result = map_seats(passengers, new_seats)

    print(f"Mapped passengers: {result['mapped_count']}")
    print(f"Unmapped passengers: {result['unmapped_count']}")

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
            print(
                f"{passenger['passenger_id']}: "
                f"{passenger['reason']}"
            )

    result["status"] = (
        "NEEDS_REVIEW"
        if result["unmapped_count"] > 0
        else "MAPPED"
    )

    return result


if __name__ == "__main__":
    run_aircraft_swap()
