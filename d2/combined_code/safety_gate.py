"""Independent final-plan checks. Recomputes metrics from input manifests."""
from common import parse_bool


def evaluate_plan(plan, passengers, bags, cargo, aircraft, standard_weights,
                  season, dcs_counts, safety_buffer_pct=0):
    zones_by_name = {z["zone"]: z for z in aircraft["cabin_zones"]}
    holds_by_name = ({h["hold"]: h for h in aircraft["holds"]}
                     if isinstance(aircraft["holds"], list) else aircraft["holds"])
    pax_by_id = {str(p["pax_id"]): p for p in passengers}
    bag_by_id = {str(b["tag"]): b for b in bags}
    cargo_by_id = {str(c["cargo_id"]): c for c in cargo}
    boarded_list = [str(pid) for pid in plan.get("passenger_ids", [])]
    boarded = set(boarded_list)
    removed = {pid for pid, p in pax_by_id.items() if parse_bool(p.get("removed_by_dcs", False))}
    active_ids = set(pax_by_id) - removed
    f = 1 + float(safety_buffer_pct) / 100.0

    zone_loads = {z: {"passenger_count": 0, "seats_used": 0, "weight_kg": 0.0, "arm_m": float(spec["arm_m"])}
                  for z, spec in zones_by_name.items()}
    weights = standard_weights[season]
    adults = sum(pax_by_id[pid].get("category") in {"M", "F", "X"} for pid in boarded if pid in pax_by_id)
    infants = sum(pax_by_id[pid].get("category") == "I" for pid in boarded if pid in pax_by_id)
    count_infants = infants > 0.10 * adults
    problems = [f"Unknown passenger ID {pid}" for pid in boarded if pid not in pax_by_id]
    problems.extend(f"DCS-removed passenger {pid} is included in the plan" for pid in boarded & removed)
    if len(boarded_list) != len(boarded):
        problems.append("Passenger IDs are duplicated in the plan")
    unmapped_active = active_ids - boarded
    if unmapped_active:
        problems.append(f"Retained passengers are missing from the plan: {', '.join(sorted(unmapped_active))}")

    mapped_ids = [str(p.get("pax_id", "")) for p in plan.get("mapped_passengers", [])]
    mapped_counts = {pid: mapped_ids.count(pid) for pid in set(mapped_ids)}
    if any(count > 1 for count in mapped_counts.values()):
        problems.append("Passenger mapping contains duplicate passenger IDs")
    if set(mapped_ids) != boarded:
        problems.append("Mapped passenger records do not match the passenger IDs in the plan")
    seat_owners = {}
    duplicate_seats = []
    invalid_seat_assignments = []
    for p in plan.get("mapped_passengers", []):
        pid, zone = str(p.get("pax_id", "")), p.get("zone")
        if pid not in boarded:
            continue
        passenger = pax_by_id.get(pid)
        if passenger and parse_bool(passenger.get("removed_by_dcs", False)):
            problems.append(f"DCS-removed passenger {pid} is mapped onto the aircraft")
        if zone not in zone_loads:
            problems.append(f"Passenger {pid} references unknown cabin zone {zone}")
            continue
        category = passenger.get("category") if passenger else p.get("category")
        if passenger and p.get("category") != category:
            problems.append(f"Passenger {pid} category does not match the manifest")
        if category not in weights:
            problems.append(f"Passenger {pid} has unknown category {category!r}")
            weight = 0.0
        else:
            weight = float(weights[category])
        if category == "I" and not count_infants:
            weight = 0
        zone_loads[zone]["passenger_count"] += 1
        seat_occupied = parse_bool(p.get("seat_occupied", True))
        if seat_occupied:
            seat = str(p.get("seat") or "").strip().upper()
            if seat:
                if seat in seat_owners:
                    duplicate_seats.append(seat)
                seat_owners[seat] = pid
            else:
                invalid_seat_assignments.append(pid)
                problems.append(f"Passenger {pid} has no assigned seat")
            zone_loads[zone]["seats_used"] += 1
        elif category != "I":
            problems.append(f"Non-infant passenger {pid} is marked as not occupying a seat")
        else:
            parent_id = p.get("parent_pax_id", p.get("guardian_pax_id", p.get("adult_pax_id")))
            parent_id = str(parent_id) if parent_id is not None else ""
            if not parent_id or parent_id not in boarded or parent_id not in seat_owners.values():
                problems.append(f"Lap infant {pid} has no mapped parent/guardian seat")
        zone_loads[zone]["weight_kg"] += weight * f

    hold_loads = {h: {"weight_kg": 0.0, "volume_m3": 0.0} for h in holds_by_name}
    bag_holds = plan.get("bag_holds", {})
    cargo_holds = plan.get("cargo_holds", {})
    cargo_bumped_ids = list(plan.get("cargo_bumped_ids", []))
    for tag, hold in bag_holds.items():
        item = bag_by_id.get(tag)
        if item is None or hold not in hold_loads:
            problems.append(f"Unknown bag or hold assignment: {tag} -> {hold}")
            continue
        hold_loads[hold]["weight_kg"] += float(item["weight_kg"])
        hold_loads[hold]["volume_m3"] += float(item.get("volume_m3", 0.07))
        owner = str(item.get("owner_pax_id", item.get("owner", ""))).strip()
        if owner not in boarded:
            problems.append(f"Bag {tag} is loaded without its owner {owner} on board")
    for cid, hold in cargo_holds.items():
        item = cargo_by_id.get(cid)
        if item is None or hold not in hold_loads:
            problems.append(f"Unknown cargo or hold assignment: {cid} -> {hold}")
            continue
        hold_loads[hold]["weight_kg"] += float(item["weight_kg"])
        hold_loads[hold]["volume_m3"] += float(item.get("volume_m3", 0))
        dg = str(item.get("dg_class", ""))
        if dg and dg in holds_by_name[hold].get("dg_forbidden_classes", []):
            problems.append(f"Dangerous goods cargo {cid} is prohibited in {hold}")

    dow = float(aircraft["dry_operating_weight_kg"])
    pax_weight = sum(z["weight_kg"] for z in zone_loads.values())
    bag_weight = sum(float(bag_by_id[tag]["weight_kg"]) for tag in bag_holds if tag in bag_by_id)
    cargo_weight = sum(float(cargo_by_id[cid]["weight_kg"]) for cid in cargo_holds if cid in cargo_by_id)
    zfw = dow + pax_weight + bag_weight + cargo_weight
    moment = dow * float(aircraft["dry_operating_arm_m"])
    moment += sum(z["weight_kg"] * z["arm_m"] for z in zone_loads.values())
    moment += sum(load["weight_kg"] * float(holds_by_name[h]["arm_m"]) for h, load in hold_loads.items())
    cg = moment / zfw if zfw else 0.0
    mzfw = float(aircraft["max_zero_fuel_weight_kg"])
    fwd, aft = float(aircraft["cg_forward_limit_m"]), float(aircraft["cg_aft_limit_m"])
    seats = min(int(aircraft["specs"]["max_seats"]), sum(int(z.get("seats", 0)) for z in aircraft["cabin_zones"]))
    seats_used = sum(load["seats_used"] for load in zone_loads.values())

    checks = []
    def check(name, passed, detail, warning=False):
        checks.append({"name": name, "passed": bool(passed), "warning": bool(warning), "detail": detail})
    for h, load in hold_loads.items():
        spec = holds_by_name[h]
        check(f"{h} weight", load["weight_kg"] <= float(spec["max_weight_kg"]) + 1e-4,
              f"{load['weight_kg']:.1f} / {spec['max_weight_kg']} kg")
        check(f"{h} volume", load["volume_m3"] <= float(spec["max_volume_m3"]) + 1e-5,
              f"{load['volume_m3']:.2f} / {spec['max_volume_m3']} m³")
    for z, load in zone_loads.items():
        spec = zones_by_name[z]
        check(f"{z} seats", load["seats_used"] <= int(spec.get("seats", 10**9)),
              f"{load['seats_used']} / {spec.get('seats', 'no seat limit')} seats")
        check(f"{z} weight", load["weight_kg"] <= float(spec.get("max_weight_kg", float("inf"))),
              f"{load['weight_kg']:.1f} / {spec.get('max_weight_kg', 'no limit')} kg")
    check("passenger count", len(boarded) == int(dcs_counts["pax_boarding"]),
          f"plan {len(boarded)}, DCS {dcs_counts['pax_boarding']}")
    passenger_accounted = (not unmapped_active and not (boarded & removed)
                           and len(boarded_list) == len(boarded)
                           and set(mapped_ids) == boarded
                           and all(count == 1 for count in mapped_counts.values()))
    check("passenger accounting", passenger_accounted,
          "all retained passengers are mapped once and removed passengers are excluded"
          if passenger_accounted else "; ".join(problems))
    seat_assignment_ok = not duplicate_seats and not invalid_seat_assignments
    seat_detail = []
    if duplicate_seats:
        seat_detail.append(f"duplicate seat(s): {', '.join(sorted(set(duplicate_seats)))}")
    if invalid_seat_assignments:
        seat_detail.append(f"missing seat(s): {', '.join(sorted(set(invalid_seat_assignments)))}")
    check("seat assignments", seat_assignment_ok,
          "; ".join(seat_detail) if seat_detail else "seat assignments are unique and complete")
    check("aircraft seat capacity", seats_used <= seats,
          f"{seats_used} seats used / {seats} available")
    all_bag_tags = list(bag_holds) + list(plan.get("bags_offloaded", [])) + list(plan.get("bags_left_behind", []))
    bag_count_ok = (len(all_bag_tags) == len(bags) == int(dcs_counts["bags_checked"])
                    and len(set(all_bag_tags)) == len(all_bag_tags)
                    and set(all_bag_tags) == set(bag_by_id))
    check("bag count and accounting", bag_count_ok,
          f"loaded {len(bag_holds)} + pulled {len(plan.get('bags_offloaded', []))} + "
          f"left behind {len(plan.get('bags_left_behind', []))} = {len(all_bag_tags)}; "
          f"DCS {dcs_counts['bags_checked']}")
    cargo_accounted = list(cargo_holds) + cargo_bumped_ids
    cargo_count_ok = (len(cargo_accounted) == len(cargo) and
                      len(set(cargo_accounted)) == len(cargo_accounted) and
                      set(cargo_accounted) == set(cargo_by_id))
    check("cargo accounting", cargo_count_ok,
          f"loaded {len(cargo_holds)} + bumped {len(cargo_bumped_ids)} = {len(cargo_accounted)}; "
          f"manifest {len(cargo)}")
    for cid, item in cargo_by_id.items():
        if parse_bool(item.get("must_fly", False)) and cid not in cargo_holds:
            problems.append(f"Must-fly cargo {cid} was not assigned")
    check("plan integrity", not problems, "; ".join(problems) if problems else "All assignments are valid")
    check("cargo bumped", not cargo_bumped_ids,
          f"{len(cargo_bumped_ids)} cargo item(s) not loaded",
          warning=bool(cargo_bumped_ids))
    zfw_ok = zfw <= mzfw
    check("zero-fuel weight", zfw_ok, f"{zfw:.1f} / {mzfw:.1f} kg (margin {mzfw-zfw:.1f} kg)")
    cg_ok = fwd <= cg <= aft
    check("centre of gravity", cg_ok, f"{cg:.3f} m (limits {fwd:.2f}–{aft:.2f} m)")
    check("CG margin", True, f"nearest limit margin {min(cg-fwd,aft-cg):.3f} m",
          warning=cg_ok and min(cg-fwd, aft-cg) < 0.2)
    check("ZFW margin", True, f"{(mzfw-zfw)/mzfw*100:.2f}% of MZFW remaining",
          warning=zfw_ok and (mzfw-zfw) < 0.01*mzfw)
    left_count = len(plan.get("bags_left_behind", []))
    check("bags left behind", left_count == 0, f"{left_count} bag(s) left behind", warning=left_count > 0)
    count_fail = any(c["name"] in {"passenger count", "passenger accounting", "seat assignments",
                                   "aircraft seat capacity", "bag count and accounting"} and not c["passed"]
                     for c in checks)
    hard_fail = any(not c["passed"] and not c["warning"] for c in checks)
    warnings = [c for c in checks if c["warning"]]
    if count_fail:
        status = "BLOCKED"
    elif hard_fail:
        status = "UNSAFE"
    elif warnings:
        status = "NEEDS REVIEW"
    else:
        status = "SAFE"
    reasons = [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"] or c["warning"]]
    if problems and "plan integrity: " + "; ".join(problems) not in reasons:
        reasons.append("Plan integrity: " + "; ".join(problems))
    if not reasons:
        reasons = ["All counts and aircraft limits pass."]
    metrics = {"dry_operating_weight_kg": dow, "passenger_weight_kg": round(pax_weight, 1),
               "bag_weight_kg": round(bag_weight, 1), "cargo_weight_kg": round(cargo_weight, 1),
               "total_weight_kg": round(zfw, 1), "max_zfw_kg": mzfw,
               "zfw_margin_kg": round(mzfw-zfw, 1), "cg_m": round(cg, 3),
               "cg_forward_limit_m": fwd, "cg_aft_limit_m": aft,
               "cg_target_m": float(aircraft["cg_target_m"]), "seats_available": seats,
               "passengers_seated": seats_used, "zone_loads": zone_loads,
               "hold_limits": {h: {"max_weight_kg": float(spec["max_weight_kg"]),
                                   "max_volume_m3": float(spec["max_volume_m3"])}
                               for h, spec in holds_by_name.items()},
               "hold_loads": hold_loads, "problems": problems}
    return {"status": status, "ready_for_load_controller": status in {"SAFE", "NEEDS REVIEW"},
            "reasons": reasons, "checks": checks, "metrics": metrics,
            "count_check": {"ok": bag_count_ok and passenger_accounted and len(boarded) == int(dcs_counts["pax_boarding"]),
                            "bags": {"loaded": len(bag_holds), "pulled": len(plan.get("bags_offloaded", [])),
                                     "left_behind": len(plan.get("bags_left_behind", [])),
                                     "checked": len(bags), "dcs_checked": int(dcs_counts["bags_checked"])},
                            "passengers": {"planned": len(boarded), "dcs_boarding": int(dcs_counts["pax_boarding"])}}}
