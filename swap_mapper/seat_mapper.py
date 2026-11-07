
from collections import defaultdict
import re


def _seat_position(seat_id):
    """Extract row number and seat letter."""
    match = re.fullmatch(r"(\d+)([A-Za-z])", seat_id)

    if match is None:
        return None

    return int(match.group(1)), match.group(2).upper()


def _is_eligible(passenger, seat):
    """Check whether a passenger may use a seat."""

    if seat.get("available", True) is not True:
        return False

    if passenger["cabin"] != seat["cabin"]:
        return False

    # Exit-row seating needs affirmative eligibility.
    if seat.get("exit_row", False):
        if passenger.get("exit_row_eligible") is not True:
            return False

    return True


def _are_adjacent(seat_id_1, seat_id_2, seat_map):
    """
    Determine physical adjacency.

    Explicit adjacent_seats data has priority.
    Legacy test data uses consecutive letters in one row.
    """

    seat_1 = seat_map[seat_id_1]
    seat_2 = seat_map[seat_id_2]

    if (
        "adjacent_seats" in seat_1
        or "adjacent_seats" in seat_2
    ):
        return (
            seat_id_2 in seat_1.get("adjacent_seats", [])
            and seat_id_1 in seat_2.get("adjacent_seats", [])
        )

    if (
        "seat_block" in seat_1
        and "seat_block" in seat_2
        and seat_1["seat_block"] != seat_2["seat_block"]
    ):
        return False

    pos_1 = _seat_position(seat_id_1)
    pos_2 = _seat_position(seat_id_2)

    if pos_1 is None or pos_2 is None:
        return False

    return (
        pos_1[0] == pos_2[0]
        and abs(ord(pos_1[1]) - ord(pos_2[1])) == 1
    )


def _find_family_seats(group, available):
    """
    Find a connected chain of physically adjacent seats.

    Each passenger must be eligible for the assigned seat.
    """

    count = len(group)

    if count == 0:
        return []

    # First try preserving every original seat.
    originals = [
        passenger["original_seat"]
        for passenger in group
    ]

    if (
        len(set(originals)) == count
        and all(
            seat_id in available
            and _is_eligible(passenger, available[seat_id])
            for passenger, seat_id in zip(group, originals)
        )
        and all(
            _are_adjacent(
                originals[i],
                originals[i + 1],
                available
            )
            for i in range(count - 1)
        )
    ):
        return originals

    # Try other available seats, regardless of input order.
    candidates = sorted(
        available,
        key=lambda seat_id: (
            _seat_position(seat_id)
            if _seat_position(seat_id) is not None
            else (999999, seat_id)
        )
    )

    def search(index, selected):
        if index == count:
            return selected.copy()

        passenger = group[index]

        for seat_id in candidates:

            if seat_id in selected:
                continue

            if not _is_eligible(
                passenger,
                available[seat_id]
            ):
                continue

            if selected:
                if not _are_adjacent(
                    selected[-1],
                    seat_id,
                    available
                ):
                    continue

            selected.append(seat_id)

            result = search(index + 1, selected)

            if result is not None:
                return result

            selected.pop()

        return None

    return search(0, [])


def map_seats(passengers, new_aircraft_seats):
    """
    Propose seat mappings after an aircraft swap.

    Priorities:
      1. Preserve individual original seats.
      2. Place multi-passenger family groups together.
      3. Reassign remaining passengers in their cabin.
      4. Send unmapped cases for DCS review.

    This function does not change airline DCS records.
    """

    # Reject duplicate seat definitions.
    seat_ids = [
        seat["seat_id"]
        for seat in new_aircraft_seats
    ]

    if len(seat_ids) != len(set(seat_ids)):
        raise ValueError(
            "Duplicate seat IDs in aircraft layout"
        )

    # Reject duplicate passenger records.
    passenger_ids = [
        passenger["passenger_id"]
        for passenger in passengers
    ]

    if len(passenger_ids) != len(set(passenger_ids)):
        raise ValueError(
            "Duplicate passenger IDs"
        )

    available = {
        seat["seat_id"]: seat
        for seat in new_aircraft_seats
        if seat.get("available", True) is True
    }

    assignments = []
    unmapped = []
    remaining = []

    families = defaultdict(list)

    for passenger in passengers:
        family_id = passenger.get("family_id")

        if family_id:
            families[family_id].append(passenger)

    family_ids = {
        passenger["passenger_id"]
        for group in families.values()
        if len(group) > 1
        for passenger in group
    }

    def assign(passenger, seat_id):
        """Record assignment and reserve the seat."""

        old_seat = passenger["original_seat"]

        assignments.append({
            "passenger_id": passenger["passenger_id"],
            "old_seat": old_seat,
            "new_seat": seat_id,
            "status": (
                "UNCHANGED"
                if old_seat == seat_id
                else "REASSIGNED"
            )
        })

        del available[seat_id]

    # Pass 1: Preserve individual original seats.
    for passenger in passengers:

        if passenger["passenger_id"] in family_ids:
            remaining.append(passenger)
            continue

        original = passenger["original_seat"]

        if (
            original in available
            and _is_eligible(
                passenger,
                available[original]
            )
        ):
            assign(passenger, original)
        else:
            remaining.append(passenger)

    # Pass 2: Find adjacent seats for families.
    assigned_family_ids = set()

    for family_id, group in families.items():

        if len(group) < 2:
            continue

        # Do not mix cabin classes within one seating group.
        cabins = {
            passenger["cabin"]
            for passenger in group
        }

        if len(cabins) != 1:
            continue

        family_seats = _find_family_seats(
            group,
            available
        )

        if family_seats is None:
            continue

        for passenger, seat_id in zip(
            group,
            family_seats
        ):
            assign(passenger, seat_id)

            assigned_family_ids.add(
                passenger["passenger_id"]
            )

    # Pass 3: Seat remaining passengers.
    for passenger in remaining:

        if passenger["passenger_id"] in assigned_family_ids:
            continue

        original = passenger["original_seat"]

        # Preserve original seat if still available.
        if (
            original in available
            and _is_eligible(
                passenger,
                available[original]
            )
        ):
            assign(passenger, original)
            continue

        # Otherwise find another eligible seat.
        matching_seat = next(
            (
                seat_id
                for seat_id, seat in available.items()
                if _is_eligible(passenger, seat)
            ),
            None
        )

        if matching_seat is not None:
            assign(passenger, matching_seat)
        else:
            unmapped.append({
                "passenger_id": passenger["passenger_id"],
                "old_seat": original,
                "reason": (
                    "No eligible seat available "
                    "in the same cabin"
                ),
                "status": "NEEDS_DCS_REVIEW"
            })

    return {
        "assignments": assignments,
        "unmapped": unmapped,
        "mapped_count": len(assignments),
        "unmapped_count": len(unmapped)
    }
