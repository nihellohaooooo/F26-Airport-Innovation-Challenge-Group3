"""Adapter: turns the team's shared data (data/ folder + Bag Offload Tracker output) into the
Load Re-planner's input format. Only this file needs to change if teammates rename fields."""
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
sys.path.insert(0, str(REPO / "bag_offload_tracker"))
import bag_offload_tracker as tracker  # noqa: E402  (Task 2, written by a teammate)


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def aircraft_limits(raw):
    """aircraft.json entry -> the limits the solver uses."""
    return {
        "type": raw["type"],
        "oew_kg": raw["dry_operating_weight_kg"],
        "oew_arm_m": raw["dry_operating_arm_m"],
        "mzfw_kg": raw["max_zero_fuel_weight_kg"],
        "cg_fwd_limit_m": raw["cg_forward_limit_m"],
        "cg_aft_limit_m": raw["cg_aft_limit_m"],
        "cg_target_m": raw["cg_target_m"],
        "holds": {h["hold"]: {"arm_m": h["arm_m"], "max_kg": h["max_weight_kg"],
                              "max_m3": h["max_volume_m3"], "dg_forbidden": h["dg_forbidden_classes"]}
                  for h in raw["holds"]},
    }


def cabin_zones_stand_in(raw_aircraft, data_dir):
    """STAND-IN for Swap Mapper (Task 1): passenger weight per cabin zone of the new aircraft.
    Uses Transport Canada standard weights (data/standard_weights.json). Replace with the
    Swap Mapper's output once it is on main."""
    weights = _read_json(data_dir / "standard_weights.json")
    staying = [p for p in _read_csv(data_dir / "passengers.csv") if p["removed_by_dcs"] == "false"]
    zones = []
    for z in raw_aircraft["cabin_zones"]:
        in_zone = [p for p in staying if z["row_from"] <= int(p["row"]) <= z["row_to"]]
        zones.append({"zone": z["zone"], "arm_m": z["arm_m"], "pax": len(in_zone),
                      "kg_summer": sum(weights["summer"][p["category"]] for p in in_zone),
                      "kg_winter": sum(weights["winter"][p["category"]] for p in in_zone)})
    return zones


def bags_still_flying(data_dir, flight):
    """Runs the Bag Offload Tracker (Task 2) and keeps only bags that fly.
    location 'hold_FWD' -> current_hold 'FWD'; carts and inbound -> None (free to place)."""
    inputs = tracker.load_inputs(data_dir)
    removed = tracker.get_removed_passenger_ids(inputs["removed"])
    result = tracker.build_tracker_result(inputs["bags"], removed, flight["loading_cutoff"],
                                          flight["dcs"]["bags_checked"])
    bags = []
    for b in result["bags"]:
        if b["tracker_status"] not in ("ok", "inbound"):
            continue  # to_pull (owner removed) or at_risk (arrives after cutoff): not ours to place
        loc = b["location"]
        bags.append({"tag": b["tag"], "owner": b["owner_pax_id"], "kg": float(b["weight_kg"]),
                     "m3": float(b["volume_m3"]),
                     "current_hold": loc.removeprefix("hold_") if loc.startswith("hold_") else None})
    return bags, removed


def cargo_list(data_dir):
    """cargo.csv -> cargo items. Empty current_hold means still on the cargo dock."""
    return [{"id": c["cargo_id"], "desc": c["description"], "kg": float(c["weight_kg"]),
             "m3": float(c["volume_m3"]), "priority": int(c["priority"]), "category": c["category"],
             "dg_class": c["dg_class"] or None, "current_hold": c["current_hold"] or None}
            for c in _read_csv(data_dir / "cargo.csv")]


def load_scenario(name="base_winter", data_dir=DATA_DIR):
    """Everything the re-planner needs for one scenario from data/scenarios.json."""
    data_dir = Path(data_dir)
    flight = _read_json(data_dir / "flight.json")
    scenario = _read_json(data_dir / "scenarios.json")[name]
    over = scenario["overrides"]
    new_type = flight["new_aircraft"]
    raw = {**_read_json(data_dir / "aircraft.json")[new_type],
           **over.get("aircraft_overrides", {}).get(new_type, {})}
    options = {**flight["options"], **over.get("options", {})}
    bags, removed = bags_still_flying(data_dir, flight)
    return {
        "scenario": name,
        "expect": scenario["expect"],
        "season": over.get("season", flight["season"]),
        "buffer_pct": options["safety_buffer_pct"] / 100,   # team stores 5 for 5%
        "lightning": options["lightning_mode"],
        "aircraft": aircraft_limits(raw),
        "cabin_zones": cabin_zones_stand_in(raw, data_dir),
        "bags": bags,
        "removed_pax_ids": removed,
        "cargo": cargo_list(data_dir),
    }
