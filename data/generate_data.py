"""
Generate demo data for the Aircraft Swap Re-planner (YYZ, A321 -> A320, winter evening).

Run:  python generate_data.py          -> writes ./data/*.json and ./data/*.csv
Same seed = same data every run. Aircraft numbers are illustrative, not certified.

Design targets (checked by check_data.py):
  - Full A321 (192 pax). DCS removes rows 28-32 (30 pax) -> 162 fly = full A320.
  - After pulling removed pax bags, A320 FWD hold content is exactly 481 kg over its limit.
    Moving the auto parts (1 item) to AFT fixes it.
  - Zero-fuel weight: winter fits under MZFW by ~300 kg; winter + 5% pax buffer goes over
    -> lowest-priority cargo (e-commerce pallet, loaded in AFT) gets bumped.
    Summer + 5% buffer still fits.
  - Lightning mode (winter + buffer): bumping the not-yet-loaded furniture parts costs
    0 moves, so lightning picks that instead of offloading the pallet.
"""
import csv
import json
import random
from pathlib import Path

SEED = 42
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)
rng = random.Random(SEED)

# ---------------------------------------------------------------- weights
# Transport Canada standard passenger weights, AC 700-022 Appendix A (kg as published).
# I = infant (0-<2 yrs): only added when infants exceed 10% of adults.
STANDARD_WEIGHTS = {
    "units": "kg",
    "source": "Transport Canada AC 700-022, Appendix A",
    "summer": {"M": 93.4, "F": 78.1, "X": 93.4, "C": 34.0, "I": 13.6},
    "winter": {"M": 96.2, "F": 80.7, "X": 96.2, "C": 34.0, "I": 13.6},
    "infant_rule": "Add infant weight only where infants exceed 10% of the number of adults",
}

# ---------------------------------------------------------------- aircraft (DOW of A320 tuned below)
SEATS = ["A", "B", "C", "D", "E", "F"]
AIRCRAFT = {
    "A321ceo": {
        "type": "A321ceo",
        "data_notes": "REAL: specs block + max zero fuel weight 73.8 t (Airbus A321ceo page); hold volumes from A320/A321 ground ops manual (FWD = cmpt 1+2, AFT = cmpt 3+4); hold weight total 11,548 kg. ESTIMATE: FWD/AFT weight split. ILLUSTRATIVE: dry operating weight, arms, CG limits (real ones are %MAC / index in the airline load manual).",
        "specs": {"max_seats": 220, "typical_seats": "170-210", "ld3_45w_underfloor": 10,
                  "max_ramp_weight_kg": 93900, "max_takeoff_weight_kg": 93500, "max_landing_weight_kg": 77800,
                  "max_fuel_l": 30030, "overall_length_m": 44.51, "cabin_length_m": 34.44, "wheelbase_m": 16.90},
        "rows": 32,
        "seats_per_row": SEATS,
        "dry_operating_weight_kg": 48500,
        "dry_operating_arm_m": 19.6,
        "max_zero_fuel_weight_kg": 73800,
        "cg_forward_limit_m": 18.4,
        "cg_aft_limit_m": 20.6,
        "cg_target_m": 19.9,
        "cabin_zones": [
            {"zone": "OA", "row_from": 1, "row_to": 10, "seats": 60, "arm_m": 10.6, "max_weight_kg": 6000},
            {"zone": "OB", "row_from": 11, "row_to": 21, "seats": 66, "arm_m": 18.9, "max_weight_kg": 6600},
            {"zone": "OC", "row_from": 22, "row_to": 32, "seats": 66, "arm_m": 27.5, "max_weight_kg": 6600},
        ],
        "holds": [
            {"hold": "FWD", "arm_m": 12.0, "max_weight_kg": 5515, "max_volume_m3": 22.81, "dg_forbidden_classes": []},
            {"hold": "AFT", "arm_m": 28.0, "max_weight_kg": 4536, "max_volume_m3": 17.93, "dg_forbidden_classes": ["8", "1.4S"]},
            {"hold": "BULK", "arm_m": 32.0, "max_weight_kg": 1497, "max_volume_m3": 5.88, "dg_forbidden_classes": ["8", "1.4S"]},
        ],
    },
    "A320ceo": {
        "type": "A320ceo",
        "data_notes": "REAL: specs block + max zero fuel weight 62.5 t (Airbus A320ceo page); hold weights 3,402 / 4,536 / 1,497 kg and volumes 13.2 / 18.2 / 5.88 m3 (A320-214 ground ops manual). ILLUSTRATIVE: dry operating weight (tuned for the demo), arms, CG limits.",
        "specs": {"max_seats": 180, "typical_seats": "140-170 (2-class)", "ld3_45w_underfloor": 7,
                  "max_ramp_weight_kg": 78400, "max_takeoff_weight_kg": 78000, "max_landing_weight_kg": 66000,
                  "max_fuel_l": 27200, "overall_length_m": 37.57, "cabin_length_m": 27.51, "wheelbase_m": 12.64},
        "rows": 27,
        "seats_per_row": SEATS,
        "dry_operating_weight_kg": None,  # tuned below
        "dry_operating_arm_m": 17.2,
        "max_zero_fuel_weight_kg": 62500,
        "cg_forward_limit_m": 16.4,
        "cg_aft_limit_m": 18.2,
        "cg_target_m": 17.6,
        "cabin_zones": [
            {"zone": "OA", "row_from": 1, "row_to": 9, "seats": 54, "arm_m": 10.2, "max_weight_kg": 5400},
            {"zone": "OB", "row_from": 10, "row_to": 18, "seats": 54, "arm_m": 17.3, "max_weight_kg": 5400},
            {"zone": "OC", "row_from": 19, "row_to": 27, "seats": 54, "arm_m": 24.4, "max_weight_kg": 5400},
        ],
        "holds": [
            {"hold": "FWD", "arm_m": 11.5, "max_weight_kg": 3402, "max_volume_m3": 13.2, "dg_forbidden_classes": []},
            {"hold": "AFT", "arm_m": 23.5, "max_weight_kg": 4536, "max_volume_m3": 18.2, "dg_forbidden_classes": ["8", "1.4S"]},
            {"hold": "BULK", "arm_m": 26.5, "max_weight_kg": 1497, "max_volume_m3": 5.88, "dg_forbidden_classes": ["8", "1.4S"]},
        ],
    },
}

FWD_OVER_KG = 481          # README demo number
WINTER_MARGIN_KG = 300     # MZFW - ZFW in winter, no buffer
BUFFER_PCT = 5

# ---------------------------------------------------------------- passengers (192, full A321)
FIRST = ["Alex", "Priya", "Sam", "Jordan", "Mei", "Omar", "Chloe", "Liam", "Aisha", "Noah", "Sofia",
         "Ethan", "Fatima", "Lucas", "Hannah", "Arjun", "Emma", "Daniel", "Grace", "Mateo", "Nadia",
         "Owen", "Leah", "Ravi", "Zoe", "Marc", "Isabelle", "Kenji", "Amara", "Ben", "Julie", "Tariq",
         "Olivia", "Hugo", "Anika", "Ryan", "Camille", "Wei", "Maya", "Patrick"]
LAST = ["Martin", "Shah", "Lee", "Roy", "Chen", "Tremblay", "Gagnon", "Singh", "Wilson", "Nguyen",
        "Patel", "Bouchard", "Smith", "Brown", "Côté", "Khan", "Taylor", "Pelletier", "Wong", "Kim",
        "Leblanc", "Ali", "Campbell", "Morin", "Fortin", "Anderson", "Lavoie", "Gill", "Thompson", "Ahmed"]

GROUP_ROWS = (24, 26)  # group of 12 in rows 24-26
passengers = []
pid = 0
for row in range(1, 33):
    for seat in SEATS:
        pid += 1
        in_group = GROUP_ROWS[0] <= row <= GROUP_ROWS[1] and seat in "ABCD"  # 3 rows x 4 = 12
        cat = rng.choices(["M", "F", "X", "C"], weights=[47, 45, 1, 7])[0]
        removed = row >= 28
        status = rng.choices(["at_gate", "checked_in", "not_arrived"], weights=[85, 10, 5])[0]
        passengers.append({
            "pax_id": f"P{pid:03d}",
            "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "seat": f"{row}{seat}",
            "row": row,
            "category": cat,
            "removed_by_dcs": str(removed).lower(),
            "checkin_status": status,
            "group_id": "G01" if in_group else "",
        })

removed_ids = [p["pax_id"] for p in passengers if p["removed_by_dcs"] == "true"]
flying_ids = [p["pax_id"] for p in passengers if p["removed_by_dcs"] == "false"]

# ---------------------------------------------------------------- bags (205)
# removed pax: 33 bags = 11 FWD hold, 4 AFT hold, 15 carts, 3 inbound
# flying pax: 172 bags = 100 FWD hold, 20 AFT hold, 48 carts, 4 inbound
def owners(ids, n):
    """Every owner gets >=0 bags; spread n bags with some pax holding 2."""
    out = rng.sample(ids, min(n, len(ids)))
    while len(out) < n:
        out.append(rng.choice(ids))
    rng.shuffle(out)
    return out

def bag_weight():
    return round(rng.triangular(12, 32, 20), 1)

plan = (
    [("removed", "hold_FWD")] * 11 + [("removed", "hold_AFT")] * 4 +
    [("removed", "cart")] * 15 + [("removed", "inbound")] * 3 +
    [("flying", "hold_FWD")] * 100 + [("flying", "hold_AFT")] * 20 +
    [("flying", "cart")] * 48 + [("flying", "inbound")] * 4
)
rem_owners = iter(owners(removed_ids, 33))
fly_owners = iter(owners(flying_ids, 172))

bags = []
for who, loc in plan:
    owner = next(rem_owners) if who == "removed" else next(fly_owners)
    w = bag_weight()
    bags.append({"owner_pax_id": owner, "weight_kg": w, "volume_m3": round(0.03 + w * 0.002, 3),
                 "location": loc, "who": who})
rng.shuffle(bags)

# carts: split into cart_1 / cart_2. Stack position 1 = top.
cart_bags = [b for b in bags if b["location"] == "cart"]
for i, b in enumerate(cart_bags):
    b["location"] = "cart_1" if i % 2 == 0 else "cart_2"
# make sure a removed pax bag is on top of cart_1 (README: "Pull AC100196 first: top of cart 1")
cart1 = [b for b in bags if b["location"] == "cart_1"]
top_removed = next(b for b in cart1 if b["who"] == "removed")
cart1.remove(top_removed)
cart1.insert(0, top_removed)
stacks = {"cart_1": cart1}
for loc in ["cart_2", "hold_FWD", "hold_AFT"]:
    stacks[loc] = [b for b in bags if b["location"] == loc]
for loc, stack in stacks.items():
    for pos, b in enumerate(stack, start=1):  # 1 = top / nearest the door (last loaded)
        b["stack_pos"] = pos

# tags: special tags first
special = {id(top_removed): "AC100196"}
inbound_fly = [b for b in bags if b["location"] == "inbound" and b["who"] == "flying"]
inbound_rem = [b for b in bags if b["location"] == "inbound" and b["who"] == "removed"]
# inbound flying: 2 arrive before cutoff (19:15), 2 after (at risk)
etas_fly = ["18:52", "19:05", "19:27", "19:34"]
flights_fly = ["AC871", "AC1044", "AC871", "AC417"]
for b, eta, fl in zip(inbound_fly, etas_fly, flights_fly):
    b.update(inbound_flight=fl, eta=eta, is_connecting=True)
special[id(inbound_fly[2])] = "AC100150"  # README: "arrives 12 min after cutoff"
for b, eta, fl in zip(inbound_rem, ["18:58", "19:10", "19:22"], ["AC1044", "AC417", "AC871"]):
    b.update(inbound_flight=fl, eta=eta, is_connecting=True)

# 11 more connecting bags that already arrived (on carts / in holds)
already = [b for b in bags if b["location"] != "inbound"]
for b in rng.sample(already, 11):
    b.update(is_connecting=True, inbound_flight=rng.choice(["AC871", "AC1044", "AC417", "AC302"]),
             eta=rng.choice(["17:40", "17:55", "18:10", "18:25"]))

used = set(special.values())
free_tags = (f"AC{n}" for n in range(100001, 100300) if f"AC{n}" not in used)
for b in bags:
    b["tag"] = special.get(id(b)) or next(free_tags)
    b.setdefault("is_connecting", False)
    b.setdefault("inbound_flight", "")
    b.setdefault("eta", "")
    b.setdefault("stack_pos", "")
    b["state"] = {"cart_1": "on_cart", "cart_2": "on_cart", "inbound": "inbound"}.get(b["location"], "loaded")
bags.sort(key=lambda b: b["tag"])

# ---------------------------------------------------------------- cargo (11 items)
cargo = [
    {"cargo_id": "C01", "description": "Canada Post mail", "weight_kg": 400, "volume_m3": 2.0, "priority": 1, "category": "mail", "dg_class": "", "current_hold": "FWD"},
    {"cargo_id": "C02", "description": "Medical supplies (blood products)", "weight_kg": 150, "volume_m3": 0.7, "priority": 1, "category": "medical", "dg_class": "", "current_hold": "FWD"},
    {"cargo_id": "C03", "description": "Fresh salmon", "weight_kg": 300, "volume_m3": 1.4, "priority": 2, "category": "perishable", "dg_class": "", "current_hold": "FWD"},
    {"cargo_id": "C04", "description": "Printed matter", "weight_kg": 200, "volume_m3": 1.0, "priority": 3, "category": "general", "dg_class": "", "current_hold": "FWD"},
    {"cargo_id": "C05", "description": "Auto parts", "weight_kg": None, "volume_m3": 2.4, "priority": 3, "category": "general", "dg_class": "", "current_hold": "FWD"},
    {"cargo_id": "C06", "description": "Lithium batteries", "weight_kg": 80, "volume_m3": 0.4, "priority": 2, "category": "dg", "dg_class": "9", "current_hold": "AFT"},
    {"cargo_id": "C07", "description": "E-commerce pallet", "weight_kg": 540, "volume_m3": 3.0, "priority": 5, "category": "general", "dg_class": "", "current_hold": "AFT"},
    {"cargo_id": "C08", "description": "Furniture parts", "weight_kg": 420, "volume_m3": 2.2, "priority": 4, "category": "general", "dg_class": "", "current_hold": ""},
    {"cargo_id": "C09", "description": "Courier documents", "weight_kg": 60, "volume_m3": 0.3, "priority": 2, "category": "mail", "dg_class": "", "current_hold": ""},
    {"cargo_id": "C10", "description": "Live lobsters", "weight_kg": 120, "volume_m3": 0.6, "priority": 2, "category": "perishable", "dg_class": "", "current_hold": ""},
    {"cargo_id": "C11", "description": "Wet-cell batteries (corrosive)", "weight_kg": 60, "volume_m3": 0.3, "priority": 3, "category": "dg", "dg_class": "8", "current_hold": "FWD"},
]
# current_hold blank = still on the dock (not loaded yet; placing it is not a "move")

# tune auto parts so FWD (flying bags + cargo) = A320 FWD limit + 481
a320 = AIRCRAFT["A320ceo"]
fwd_limit = next(h for h in a320["holds"] if h["hold"] == "FWD")["max_weight_kg"]
fwd_bags = sum(b["weight_kg"] for b in bags if b["location"] == "hold_FWD" and b["who"] == "flying")
fwd_other = sum(c["weight_kg"] for c in cargo if c["current_hold"] == "FWD" and c["weight_kg"])
auto = round(fwd_limit + FWD_OVER_KG - fwd_bags - fwd_other, 1)
assert 550 <= auto <= 900, f"auto parts weight out of range: {auto}"
next(c for c in cargo if c["cargo_id"] == "C05")["weight_kg"] = auto

# ---------------------------------------------------------------- tune A320 DOW
w = STANDARD_WEIGHTS["winter"]
pax_by_id = {p["pax_id"]: p for p in passengers}
pax_winter = sum(w[pax_by_id[i]["category"]] for i in flying_ids)
# bags that will fly = flying pax bags except inbound arriving after cutoff
flying_bags = sum(b["weight_kg"] for b in bags if b["who"] == "flying" and not (b["location"] == "inbound" and b["eta"] > "19:15"))
cargo_total = sum(c["weight_kg"] for c in cargo)
dow = a320["max_zero_fuel_weight_kg"] - WINTER_MARGIN_KG - pax_winter - flying_bags - cargo_total
a320["dry_operating_weight_kg"] = int(round(dow / 10) * 10)

# ---------------------------------------------------------------- flight + scenarios
flight = {
    "flight_no": "AC123",
    "origin": "YYZ",
    "destination": "YVR",
    "date": "2026-11-07",
    "scheduled_departure": "19:30",
    "loading_cutoff": "19:15",
    "season": "winter",
    "old_aircraft": "A321ceo",
    "new_aircraft": "A320ceo",
    "dcs": {"pax_boarding": len(flying_ids), "bags_checked": len(bags)},
    "options": {"lightning_mode": False, "safety_buffer_pct": 0},
}

unsafe_dow = int(a320["max_zero_fuel_weight_kg"] - pax_winter + 150)
scenarios = {
    "base_winter": {
        "description": "Demo flight. A321 -> A320, winter evening, no buffer.",
        "overrides": {},
        "expect": "SAFE. Auto parts moved FWD -> AFT (1 move). No cargo bumped. 2 connecting bags at risk.",
    },
    "summer": {
        "description": "Same flight in summer weights.",
        "overrides": {"season": "summer"},
        "expect": "SAFE. More weight margin than winter.",
    },
    "summer_buffer": {
        "description": "Summer + 5% passenger weight buffer.",
        "overrides": {"season": "summer", "options": {"safety_buffer_pct": BUFFER_PCT}},
        "expect": "SAFE. Still fits under MZFW, nothing bumped.",
    },
    "winter_buffer": {
        "description": "Winter + 5% passenger weight buffer.",
        "overrides": {"options": {"safety_buffer_pct": BUFFER_PCT}},
        "expect": "SAFE. Over MZFW without action -> E-commerce pallet (priority 5) bumped.",
    },
    "lightning": {
        "description": "Winter + 5% buffer + lightning mode (fewest moves ranked above cargo).",
        "overrides": {"options": {"safety_buffer_pct": BUFFER_PCT, "lightning_mode": True}},
        "expect": "SAFE. Furniture parts (on dock, priority 4) bumped instead of offloading the loaded pallet: fewer moves, different cargo trade-off.",
    },
    "wrong_count": {
        "description": "DCS passenger count doesn't match the cabin.",
        "overrides": {"dcs": {"pax_boarding": len(flying_ids) - 1}},
        "expect": f"BLOCKED. DCS says {len(flying_ids) - 1} passengers, cabin has {len(flying_ids)}.",
    },
    "unsafe": {
        "description": "Heavier A320ceo variant (extra galley/equipment). Empty plane + passengers alone exceed MZFW.",
        "overrides": {"aircraft_overrides": {"A320ceo": {"dry_operating_weight_kg": unsafe_dow}}},
        "expect": "UNSAFE. Even with every bag and all cargo offloaded, zero-fuel weight is over the A320 max.",
    },
}

# ---------------------------------------------------------------- write
def write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def write_csv(name, rows, fields):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({k: (str(v).lower() if isinstance(v, bool) else v) for k, v in r.items()})

write_json("aircraft.json", AIRCRAFT)
write_json("standard_weights.json", STANDARD_WEIGHTS)
write_json("flight.json", flight)
write_json("scenarios.json", scenarios)
write_csv("passengers.csv", passengers,
          ["pax_id", "name", "seat", "row", "category", "removed_by_dcs", "checkin_status", "group_id"])
write_csv("bags.csv", bags,
          ["tag", "owner_pax_id", "weight_kg", "volume_m3", "location", "stack_pos", "state",
           "is_connecting", "inbound_flight", "eta"])
write_csv("cargo.csv", cargo,
          ["cargo_id", "description", "weight_kg", "volume_m3", "priority", "category", "dg_class", "current_hold"])
print(f"Wrote data to {OUT}")
