"""Scenario entry point: passenger mapping -> bags -> optimization -> safety gate."""
import argparse
import json
from pathlib import Path

import bag_offload_tracker
import replanner
import safety_gate
import swap_mapper
from common import parse_bool

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def _read_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def _flight(scenario):
    return scenario.get("flight", scenario)


def run_scenario(scenario, aircraft_profiles=None, options=None, standard_weights=None):
    """Run four engines and return one dashboard-ready result.

    `scenario` may be a scenario dictionary or a path to a scenario JSON file.
    `aircraft_profiles` and `standard_weights` may be dictionaries or JSON paths.
    """
    if isinstance(scenario, (str, Path)):
        scenario = _read_json(scenario)
    if aircraft_profiles is None:
        aircraft_profiles = _read_json(DATA_DIR / "aircraft_profiles.json")
    elif isinstance(aircraft_profiles, (str, Path)):
        aircraft_profiles = _read_json(aircraft_profiles)
    if standard_weights is None:
        standard_weights = _read_json(DATA_DIR / "standard_weights.json")
    elif isinstance(standard_weights, (str, Path)):
        standard_weights = _read_json(standard_weights)

    flight = _flight(scenario)
    run_options = {**flight.get("options", {}), **(options or {})}
    season = run_options.get("season", flight.get("season", "winter"))
    ac = swap_mapper.get_new_aircraft(aircraft_profiles, scenario)
    passengers = scenario["passengers"]
    bags = scenario["bags"]
    cargo = scenario["cargo"]
    dcs = flight.get("dcs", scenario.get("dcs_counts", {}))

    # 1. Map retained passengers and calculate fixed cabin loads.
    mapping = swap_mapper.build_swap_result(passengers, ac, standard_weights, season)
    mapped = mapping["mapped_passengers"]
    zone_loads = mapping["zone_weights"]
    passenger_ids = [p["pax_id"] for p in mapped]

    # 2. Classify bags, order pulls, and identify inbound bags that miss cutoff.
    removed_ids = {str(p["pax_id"]).strip() for p in passengers
                   if parse_bool(p.get("removed_by_dcs", False))}
    tracker = bag_offload_tracker.build_tracker_result(
        bags, removed_ids, flight["loading_cutoff"], dcs["bags_checked"])
    pull_ids = [b["tag"] for b in tracker["pull_list"]]
    risk_ids = [b["tag"] for b in tracker["at_risk"]]
    fly_bags = [b for b in tracker["bags"] if b["tracker_status"] in {"ok", "inbound"}]

    # 3. Optimize the remaining bags and cargo around the fixed passenger load.
    pct = float(run_options.get("safety_buffer_pct", 0))
    dow = float(ac["dry_operating_weight_kg"])
    fixed_pax_weight = sum(z["weight_kg"] for z in zone_loads.values()) * (1 + pct / 100)
    fixed_weight = dow + fixed_pax_weight
    fixed_moment = dow * float(ac["dry_operating_arm_m"]) + sum(
        z["weight_kg"] * z["arm_m"] for z in zone_loads.values()) * (1 + pct / 100)
    plan = replanner.solve_load_plan(fly_bags, cargo, ac, fixed_weight, fixed_moment, run_options)

    if plan["status"] not in {"OPTIMAL", "FEASIBLE"}:
        input_pax_ok = (len(mapped) == int(dcs.get("pax_boarding", -1))
                        and not mapping["doesnt_fit"])
        input_bag_check = tracker["count_check"]
        reasons = []
        if not input_pax_ok:
            reasons.append(f"Passenger reconciliation failed: {len(mapped)} mapped, "
                           f"DCS {dcs.get('pax_boarding', '—')}; resolve seat or count issues.")
        if not input_bag_check["ok"]:
            reasons.append(f"Bag reconciliation failed: {input_bag_check['total_known']} classified, "
                           f"DCS {input_bag_check['dcs_bags_checked']} checked; resolve unknown or missing bag data.")
        preflight_block = not input_pax_ok or not input_bag_check["ok"]
        if plan["status"] == "INFEASIBLE":
            status = "UNSAFE"
        else:
            status = "ERROR"
        if preflight_block:
            status = "BLOCKED"
        reasons.append(plan.get("reason", "No feasible plan"))
        return {
            "scenario_id": scenario.get("scenario_id", "unnamed"),
            "scenario_name": scenario.get("name", ""),
            "flight": flight,
            "aircraft": ac["type"], "status": status, "reasons": reasons,
            "passenger_mapping": mapping,
            "bag_actions": {"pull_list": tracker["pull_list"], "at_risk": tracker["at_risk"],
                            "classified_bags": tracker["bags"],
                            "tracker_count_check": input_bag_check,
                            "bags_available_to_load": len(fly_bags), "bags_pulled": len(pull_ids),
                            "bags_left_behind": risk_ids},
            "hold_assignments": {"bags": {}, "cargo": {}}, "moves": [], "cargo_bumped": [],
            "offloads": [], "handling_actions": plan.get("handling_actions"),
            "metrics": None,
            "count_check": {"ok": input_bag_check["ok"] and input_pax_ok,
                            "input_counts_ok": input_bag_check["ok"] and input_pax_ok,
                            "final_plan_verified": False,
                            "passengers": {"planned": len(mapped), "dcs_boarding": dcs.get("pax_boarding")},
                            "bags": input_bag_check["counts"],
                            "dcs_bags_checked": input_bag_check["dcs_bags_checked"]},
            "checks": [],
            "solver": {"status": plan["status"], "reason": plan.get("reason")},
            "safety_gate": {"status": "NOT RUN", "reasons": ["No feasible plan to evaluate"],
                            "metrics": None, "checks": []},
        }

    # 4. Construct the shared plan contract for the independent Safety Gate.
    left_ids = plan["bags_left_behind"]
    bags_left = list(dict.fromkeys([tag for tag in risk_ids if tag not in pull_ids] + left_ids))
    full_plan = {
        "passenger_ids": passenger_ids,
        "mapped_passengers": mapped,
        "bag_holds": plan["bag_holds"], "cargo_holds": plan["cargo_holds"],
        "cargo_bumped_ids": [c["cargo_id"] for c in plan["cargo_bumped"]],
        "bags_offloaded": pull_ids, "bags_left_behind": bags_left,
    }

    # 5. Recalculate all final metrics and counts independently.
    gate = safety_gate.evaluate_plan(
        full_plan, passengers, bags, cargo, ac, standard_weights, season, dcs,
        safety_buffer_pct=pct)
    reasons = list(gate["reasons"])
    if not tracker["count_check"]["ok"]:
        tracker_reason = (f"Bag reconciliation failed: {tracker['count_check']['total_known']} classified, "
                          f"DCS {tracker['count_check']['dcs_bags_checked']} checked; resolve unknown or missing bag data.")
        gate["checks"].append({"name": "input bag reconciliation", "passed": False,
                               "warning": False, "detail": tracker_reason})
        gate["status"] = "BLOCKED"
        gate["ready_for_load_controller"] = False
        gate["reasons"].append(tracker_reason)
        gate["count_check"]["ok"] = False
        reasons.append(tracker_reason)
    if plan["status"] == "FEASIBLE":
        solver_warning = plan.get("reason", "Solver did not prove optimality.")
        gate["checks"].append({"name": "optimizer result", "passed": False,
                               "warning": True, "detail": solver_warning})
        gate["reasons"].append(solver_warning)
        reasons.append(solver_warning)
        if gate["status"] == "SAFE":
            gate["status"] = "NEEDS REVIEW"
            gate["ready_for_load_controller"] = True
    if mapping["doesnt_fit"]:
        reasons.append(f"{len(mapping['doesnt_fit'])} retained passenger(s) have no valid seat; refer to DCS.")
    if plan["cargo_bumped"]:
        reasons.extend(c["reason"] for c in plan["cargo_bumped"])
    if plan["moves"]:
        reasons.extend(m["reason"] for m in plan["moves"])
    reasons = list(dict.fromkeys(reasons))

    return {
        "scenario_id": scenario.get("scenario_id", "unnamed"),
        "scenario_name": scenario.get("name", ""),
        "flight": flight, "aircraft": ac["type"],
        "status": gate["status"], "reasons": reasons,
        "passenger_mapping": mapping,
        "bag_actions": {"pull_list": tracker["pull_list"], "at_risk": tracker["at_risk"],
                        "classified_bags": tracker["bags"],
                        "tracker_count_check": tracker["count_check"],
                        "bags_loaded": len(plan["bag_holds"]), "bags_pulled": len(pull_ids),
                        "bags_left_behind": bags_left},
        "hold_assignments": {"bags": plan["bag_holds"], "cargo": plan["cargo_holds"],
                             "loads": gate["metrics"]["hold_loads"]},
        "moves": plan["moves"], "cargo_bumped": plan["cargo_bumped"],
        "offloads": plan.get("offloads", []),
        "handling_actions": plan.get("handling_actions"),
        "metrics": gate["metrics"],
        "checks": gate["checks"],
        "count_check": {**gate["count_check"], "final_plan_verified": True,
                         "input_counts_ok": tracker["count_check"]["ok"]},
        "solver": {"status": plan["status"], "reason": plan.get("reason"),
                   "objective_values": plan["objective_values"]},
        "safety_gate": gate,
    }


def _print_result(result):
    print(f"\n{result['scenario_id']} · {result['scenario_name']} · {result['aircraft']}")
    print(f"STATUS: {result['status']}")
    for reason in result["reasons"]:
        print(f"  - {reason}")
    mapping = result["passenger_mapping"]
    print(f"\nPASSENGERS: {mapping['passenger_count_mapped']} / {mapping['seat_capacity']} seats")
    for zone, z in mapping["zone_weights"].items():
        print(f"  {zone}: {z['passenger_count']} passengers, {z['weight_kg']:.1f} kg")
    print(f"  Doesn't fit: {len(mapping['doesnt_fit'])}")
    bags = result["bag_actions"]
    print(f"\nBAGS: {bags.get('bags_loaded', 0)} flying · {bags.get('bags_pulled', len(bags.get('pull_list', [])))} pulled · {len(bags.get('bags_left_behind', []))} left behind")
    for i, b in enumerate(bags["pull_list"], 1):
        print(f"  Pull {i}: {b['tag']} at {b.get('location')} (owner {b.get('owner_pax_id', b.get('owner'))})")
    for b in bags.get("at_risk", []):
        print(f"  At risk: {b['tag']} ETA {b.get('eta')}")
    print("\nHOLD ASSIGNMENTS:")
    for hold, totals in result["hold_assignments"].get("loads", {}).items():
        print(f"  {hold}: {totals['weight_kg']:.1f} kg, {totals['volume_m3']:.2f} m³")
    print(f"  Bag assignments: {len(result['hold_assignments'].get('bags', {}))}; cargo assignments: {len(result['hold_assignments'].get('cargo', {}))}")
    print(f"\nMOVES: {len(result['moves'])}")
    for m in result["moves"]:
        print(f"  {m['reason']}")
    actions = result.get("handling_actions")
    if actions:
        print(f"HANDLING ACTIONS: {actions['total']} ({actions['moves']} moves, "
              f"{actions['offloads']} offloads)")
    bag_offloads = [item for item in result.get("offloads", []) if item["kind"] == "bag"]
    if bag_offloads:
        print("BAG OFFLOADS:")
        for item in bag_offloads:
            print(f"  {item['reason']}")
    print(f"CARGO BUMPED: {len(result['cargo_bumped'])}")
    for c in result["cargo_bumped"]:
        print(f"  {c['reason']}")
    if result["metrics"]:
        m = result["metrics"]
        print(f"\nFINAL: {m['total_weight_kg']:.1f} / {m['max_zfw_kg']:.1f} kg ZFW · CG {m['cg_m']:.3f} m "
              f"(limits {m['cg_forward_limit_m']:.2f}–{m['cg_aft_limit_m']:.2f})")
    else:
        print("\nFINAL: unavailable because no feasible loading plan was found")
    print(f"COUNTS: {json.dumps(result['count_check'], ensure_ascii=False)}")


def main():
    parser = argparse.ArgumentParser(description="Run an aircraft swap scenario")
    parser.add_argument("scenario", help="Scenario JSON path or filename under data/scenarios")
    parser.add_argument("--season", choices=["summer", "winter"])
    parser.add_argument("--safety-buffer-pct", type=float)
    parser.add_argument("--lightning", action="store_true", help="Prioritize fewer loaded-item moves")
    parser.add_argument("--json", action="store_true", help="Print the complete result as JSON")
    args = parser.parse_args()
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        scenario_path = DATA_DIR / "scenarios" / args.scenario
    if not scenario_path.exists():
        scenario_path = scenario_path.with_suffix(".json")
    overrides = {}
    if args.season:
        overrides["season"] = args.season
    if args.safety_buffer_pct is not None:
        overrides["safety_buffer_pct"] = args.safety_buffer_pct
    if args.lightning:
        overrides["lightning_mode"] = True
    result = run_scenario(scenario_path, options=overrides)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_result(result)


if __name__ == "__main__":
    main()
