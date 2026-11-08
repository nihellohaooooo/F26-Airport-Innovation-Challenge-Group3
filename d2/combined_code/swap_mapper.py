"""Passenger mapping for the combined scenario runner (kg, metres)."""


def _truth(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def get_new_aircraft(aircraft_profiles, scenario):
    """Resolve the replacement aircraft profile named by a scenario."""
    flight = scenario.get("flight", scenario)
    name = flight.get("new_aircraft") or scenario.get("new_aircraft")
    if name not in aircraft_profiles:
        raise KeyError(f"Replacement aircraft {name!r} not found in aircraft_profiles.json")
    return aircraft_profiles[name]


def map_passengers_to_zones(passengers, aircraft):
    """Map retained passenger seats to zones; return mapped and invalid records."""
    mapped, doesnt_fit = [], []
    valid_letters = set(aircraft.get("seats_per_row", []))
    check_letters = aircraft.get("validate_seat_letters", True)
    zones = aircraft.get("cabin_zones", [])
    for raw in passengers:
        p = dict(raw)
        if _truth(p.get("removed_by_dcs", False)):
            continue
        try:
            row = int(p.get("row") or str(p.get("seat", ""))[:-1])
        except (TypeError, ValueError):
            p["doesnt_fit_reason"] = "missing or invalid row"
            doesnt_fit.append(p)
            continue
        zone = next((z for z in zones if int(z["row_from"]) <= row <= int(z["row_to"])), None)
        seat = str(p.get("seat", ""))
        seat_row, letter = seat[:-1], seat[-1:].upper()
        reason = None
        if zone is None:
            reason = f"row {row} does not exist on {aircraft['type']}"
        elif seat and (seat_row != str(row) or (check_letters and letter not in valid_letters)):
            reason = f"seat {seat!r} is invalid on {aircraft['type']}"
        if reason:
            p["doesnt_fit_reason"] = reason
            doesnt_fit.append(p)
            continue
        p["row"] = row
        p["zone"] = zone["zone"]
        p["zone_arm_m"] = float(zone["arm_m"])
        mapped.append(p)
    return mapped, doesnt_fit


def calculate_zone_weights(mapped, standard_weights, season):
    if season not in standard_weights:
        raise ValueError(f"Unknown season {season!r}; expected summer or winter")
    weights = standard_weights[season]
    result = {}
    adults = sum(p.get("category") in {"M", "F", "X"} for p in mapped)
    infants = sum(p.get("category") == "I" for p in mapped)
    count_infants = infants > 0.10 * adults
    for p in mapped:
        category = p.get("category")
        if category not in weights:
            raise ValueError(f"Unknown passenger category {category!r} for {p.get('pax_id')}")
        z = result.setdefault(p["zone"], {
            "passenger_count": 0, "weight_kg": 0.0,
            "arm_m": p["zone_arm_m"], "passenger_ids": [],
        })
        z["passenger_count"] += 1
        passenger_weight = float(weights[category])
        if category == "I" and not count_infants:
            passenger_weight = 0.0
        z["weight_kg"] += passenger_weight
        z["passenger_ids"].append(p["pax_id"])
    for z in result.values():
        z["weight_kg"] = round(z["weight_kg"], 1)
    return result


def build_swap_result(passengers, aircraft, standard_weights, season):
    mapped, doesnt_fit = map_passengers_to_zones(passengers, aircraft)
    zones = calculate_zone_weights(mapped, standard_weights, season)
    seats_by_profile = sum(int(z.get("seats", 0)) for z in aircraft["cabin_zones"])
    seat_capacity = min(int(aircraft["specs"]["max_seats"]), seats_by_profile)
    return {
        "aircraft_type": aircraft["type"], "season": season,
        "mapped_passengers": mapped, "doesnt_fit": doesnt_fit,
        "zone_weights": zones, "passenger_count_mapped": len(mapped),
        "seat_capacity": seat_capacity,
        "capacity_shortfall": max(0, len(mapped) - seat_capacity),
    }
