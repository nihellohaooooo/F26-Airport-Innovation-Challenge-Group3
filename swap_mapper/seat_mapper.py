
from collections import defaultdict
import re


def _seat_position(seat_id):
    """Extract row number and seat letter."""
    match = re.fullmatch(r"(\d+)([A-Za-z])", seat_id)
    if not match:
        return None

    return int(match.group(1)), match.group(2).upper()


def _find_adjacent_seats(available, cabin, count):
    """
    Find consecutive seat letters in the same row and cabin.

    Prototype assumption:
    Consecutive letters represent adjacent seats.
    Real aircraft layouts require explicit adjacency data.
    """
    rows = defaultdict(list)

    for seat_id, seat in available.items():
        if seat["cabin"] != cabin:
            continue

        position = _seat_position(seat_id)
        if position is not None:
            row, letter = position
            rows[row].append((letter, seat_id))

    for row in sorted(rows):
        seats = sorted(rows[row])

        for start in range(len(seats) - count + 1):
            group = seats[start:start + count]

            letters = [ord(letter) for letter, _ in group]

            if all(
                letters[i + 1] == letters[i] + 1
                for i in range(len(letters) - 1)
            ):
                return [seat_id for _, seat_id in group]

    return None


def map_seats(passengers, new_aircraft_seats):
    """
    Create candidate seat assignments after an aircraft swap.

    Priority:
    1. Preserve original seats when possible.
    2. Keep family groups together when adjacent seats exist.
    3. Reassign remaining passengers within their cabin.
    4. Flag unmapped passengers for DCS review.
    """
    available = {
        seat["seat_id"]: seat
        for seat in new_aircraft_seats
    }

    assignments = []
    unmapped = []
    remaining = []

    # Identify family groups
    families = defaultdict(list)

    for passenger in passengers:
        family_id = passenger.get("family_id")
        if family_id:
            families[family_id].append(passenger)

    family_passenger_ids = {
        passenger["passenger_id"]
        for group in families.values()
        if len(group) > 1
        for passenger in group
    }

    # Pass 1: Keep original seats for individual passengers
    for passenger in passengers:
        if passenger["passenger_id"] in family_passenger_ids:
            remaining.append(passenger)
            continue

        original = passenger["original_seat"]
        cabin = passenger["cabin"]

        if (
            original in available
            and available[original]["cabin"] == cabin
        ):
            assignments.append({
                "passenger_id": passenger["passenger_id"],
                "old_seat": original,
                "new_seat": original,
                "status": "UNCHANGED"
            })
            del available[original]
        else:
            remaining.append(passenger)

    # Pass 2: Assign families to adjacent seats
    assigned_family_ids = set()

    for family_id, group in families.items():
        if len(group) < 2:
            continue

        cabins = {p["cabin"] for p in group}
        if len(cabins) != 1:
            continue

        cabin = group[0]["cabin"]

        # Preserve original family seats if all remain available
        original_seats = [
            p["original_seat"] for p in group
        ]

        original_positions = [
            _seat_position(seat_id)
            for seat_id in original_seats
        ]

        can_preserve = (
            len(set(original_seats)) == len(group)
            and all(
                seat_id in available
                and available[seat_id]["cabin"] == cabin
                for seat_id in original_seats
            )
            and all(pos is not None for pos in original_positions)
            and len({pos[0] for pos in original_positions}) == 1
            and sorted(pos[1] for pos in original_positions)
            == [
                chr(x)
                for x in range(
                    min(ord(pos[1]) for pos in original_positions),
                    min(ord(pos[1]) for pos in original_positions)
                    + len(group)
                )
            ]
        )

        if can_preserve:
            seats = original_seats
        else:
            seats = _find_adjacent_seats(
                available, cabin, len(group)
            )

        if seats is None:
            continue

        for passenger, seat_id in zip(group, seats):
            assignments.append({
                "passenger_id": passenger["passenger_id"],
                "old_seat": passenger["original_seat"],
                "new_seat": seat_id,
                "status": (
                    "UNCHANGED"
                    if passenger["original_seat"] == seat_id
                    else "REASSIGNED"
                )
            })
            del available[seat_id]
            assigned_family_ids.add(
                passenger["passenger_id"]
            )

    # Pass 3: Reassign remaining passengers
    for passenger in remaining:
        if passenger["passenger_id"] in assigned_family_ids:
            continue

        cabin = passenger["cabin"]

        matching_seat = next(
            (
                seat_id
                for seat_id, seat in available.items()
                if seat["cabin"] == cabin
            ),
            None
        )

        if matching_seat is not None:
            assignments.append({
                "passenger_id": passenger["passenger_id"],
                "old_seat": passenger["original_seat"],
                "new_seat": matching_seat,
                "status": (
                    "UNCHANGED"
                    if matching_seat == passenger["original_seat"]
                    else "REASSIGNED"
                )
            })
            del available[matching_seat]
        else:
            unmapped.append({
                "passenger_id": passenger["passenger_id"],
                "old_seat": passenger["original_seat"],
                "reason": "No available seat in the same cabin",
                "status": "NEEDS_DCS_REVIEW"
            })

    return {
        "assignments": assignments,
        "unmapped": unmapped,
        "mapped_count": len(assignments),
        "unmapped_count": len(unmapped)
    }
