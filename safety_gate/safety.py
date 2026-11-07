
def check_weight_limits(aircraft_params, load_plan):
    """
    Independently verify aircraft and zone weight limits.
    Uses the official optimizer's input/output structure.
    """
    oew = float(aircraft_params["oew"])
    max_zfw = float(aircraft_params["max_zfw"])
    zones = aircraft_params["zones"]
    assignments = load_plan["assignments"]

    total_payload = 0
    violations = []

    for zone_id, items in assignments.items():
        zone_weight = sum(float(item["weight"]) for item in items)
        total_payload += zone_weight

        zone_limit = float(zones[zone_id]["max_weight"])

        if zone_weight > zone_limit:
            violations.append(
                f"{zone_id} overweight: "
                f"{zone_weight} lbs > {zone_limit} lbs"
            )

    total_weight = oew + total_payload

    if total_weight > max_zfw:
        violations.append(
            f"Maximum zero fuel weight exceeded: "
            f"{total_weight} lbs > {max_zfw} lbs"
        )

    return {
        "passed": len(violations) == 0,
        "total_weight": total_weight,
        "violations": violations
    }



def check_center_of_gravity(aircraft_params, load_plan):
    """
    Independently recalculate center of gravity (CG).
    All weights are in lbs and arms are in inches.
    """
    oew = float(aircraft_params["oew"])
    oew_arm = float(aircraft_params["oew_arm"])
    zones = aircraft_params["zones"]
    assignments = load_plan["assignments"]

    total_weight = oew
    total_moment = oew * oew_arm

    for zone_id, items in assignments.items():
        arm = float(zones[zone_id]["arm"])

        for item in items:
            weight = float(item["weight"])
            total_weight += weight
            total_moment += weight * arm

    cg = total_moment / total_weight

    cg_min = float(aircraft_params["cg_min"])
    cg_max = float(aircraft_params["cg_max"])

    violations = []

    if cg < cg_min:
        violations.append(
            f"CG too far forward: {cg:.2f} < {cg_min:.2f} inches"
        )

    if cg > cg_max:
        violations.append(
            f"CG too far aft: {cg:.2f} > {cg_max:.2f} inches"
        )

    return {
        "passed": len(violations) == 0,
        "calculated_cg": round(cg, 2),
        "violations": violations
    }
     # Calculate the aircraft's operating empty weight moment.

     
def check_seat_capacity(aircraft_params, load_plan):
    zones = aircraft_params["zones"]
    assignments = load_plan["assignments"]
    violations = []

    for zone_id, zone in zones.items():
        if zone["type"] != "passenger":
            continue

        max_seats = int(zone["max_seats"])
        assigned_passengers = sum(
            int(item["count"])
            for item in assignments.get(zone_id, [])
        )

        if assigned_passengers > max_seats:
            violations.append(
                f"{zone_id} seat capacity exceeded: "
                f"{assigned_passengers} passengers > {max_seats} seats"
            )

    return {
        "passed": len(violations) == 0,
        "violations": violations
    }
