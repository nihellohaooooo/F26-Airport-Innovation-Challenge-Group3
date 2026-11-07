"""
Sanity-check the demo data before building the optimiser.
Run:  python check_data.py
Prints the key numbers and fails loudly if a demo moment wouldn't work.
"""
import csv
import json
from pathlib import Path

D = Path(__file__).parent / "data"
aircraft = json.loads((D / "aircraft.json").read_text())
weights = json.loads((D / "standard_weights.json").read_text())
flight = json.loads((D / "flight.json").read_text())
scenarios = json.loads((D / "scenarios.json").read_text())
pax = list(csv.DictReader(open(D / "passengers.csv", encoding="utf-8")))
bags = list(csv.DictReader(open(D / "bags.csv", encoding="utf-8")))
cargo = list(csv.DictReader(open(D / "cargo.csv", encoding="utf-8")))

ok = True
def check(cond, msg):
    global ok
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    ok &= bool(cond)

old, new = aircraft[flight["old_aircraft"]], aircraft[flight["new_aircraft"]]
holds = {h["hold"]: h for h in new["holds"]}
cutoff = flight["loading_cutoff"]
pax_by_id = {p["pax_id"]: p for p in pax}
removed = {p["pax_id"] for p in pax if p["removed_by_dcs"] == "true"}
flying = [p for p in pax if p["removed_by_dcs"] == "false"]

print("\n== Aircraft specs")
for ac in (old, new):
    sp = ac["specs"]
    seats = ac["rows"] * len(ac["seats_per_row"])
    check(seats <= sp["max_seats"], f"{ac['type']}: {seats} seats <= max {sp['max_seats']}")
    arms = [z["arm_m"] for z in ac["cabin_zones"]] + [h["arm_m"] for h in ac["holds"]]
    check(0 < min(arms) and max(arms) < sp["overall_length_m"], f"{ac['type']}: all arms inside {sp['overall_length_m']} m fuselage")
    check(ac["max_zero_fuel_weight_kg"] < sp["max_landing_weight_kg"] < sp["max_takeoff_weight_kg"], f"{ac['type']}: MZFW < MLW < MTOW")

print("\n== Counts & integrity")
check(len(pax) == old["rows"] * len(old["seats_per_row"]), f"{len(pax)} passengers = full {old['type']}")
check(len(removed) == 30 and all(int(pax_by_id[i]["row"]) >= 28 for i in removed), f"{len(removed)} removed, all in rows 28-32")
check(len(flying) == new["rows"] * len(new["seats_per_row"]), f"{len(flying)} flying = full {new['type']}")
check(all(b["owner_pax_id"] in pax_by_id for b in bags), f"all {len(bags)} bags have a valid owner")
check(len({b['tag'] for b in bags}) == len(bags), "bag tags unique")
check(all(c["current_hold"] in ("", *holds) for c in cargo), f"{len(cargo)} cargo items, holds valid")
check(all(c["dg_class"] not in holds[c["current_hold"]]["dg_forbidden_classes"] for c in cargo if c["category"] == "dg" and c["current_hold"]), "DG cargo in allowed hold")
check(flight["dcs"]["bags_checked"] == len(bags), f"DCS bags_checked = {len(bags)}")

def zone_of(row, ac):
    for z in ac["cabin_zones"]:
        if z["row_from"] <= row <= z["row_to"]:
            return z
    return None

def pax_load(season, buffer_pct=0):
    w = weights[season]
    zones = {}
    for p in flying:
        z = zone_of(int(p["row"]), new)
        zones.setdefault(z["zone"], [0, z["arm_m"]])
        zones[z["zone"]][0] += w[p["category"]] * (1 + buffer_pct / 100)
    return zones

# bags/cargo that will fly
fly_bags = [b for b in bags if b["owner_pax_id"] not in removed]
at_risk = [b for b in fly_bags if b["location"] == "inbound" and b["eta"] > cutoff]
fly_bags = [b for b in fly_bags if b not in at_risk]

print("\n== Forward hold overload (after pulling removed-pax bags)")
fwd_bags = sum(float(b["weight_kg"]) for b in fly_bags if b["location"] == "hold_FWD")
fwd_cargo = sum(float(c["weight_kg"]) for c in cargo if c["current_hold"] == "FWD")
fwd = fwd_bags + fwd_cargo
over = fwd - holds["FWD"]["max_weight_kg"]
print(f"  FWD content {fwd:.0f} kg vs A320 limit {holds['FWD']['max_weight_kg']} -> over by {over:.0f} kg")
check(abs(over - 481) < 1, "FWD over by 481 kg (README demo number)")
auto = next(c for c in cargo if c["description"] == "Auto parts")
check(float(auto["weight_kg"]) >= over, f"moving auto parts ({auto['weight_kg']} kg) alone fixes FWD weight")
fwd_vol = sum(float(b["volume_m3"]) for b in fly_bags if b["location"] == "hold_FWD") + sum(float(c["volume_m3"]) for c in cargo if c["current_hold"] == "FWD")
vlim = holds["FWD"]["max_volume_m3"]
print(f"  FWD volume {fwd_vol:.2f} m3 vs A320 limit {vlim} -> over by {fwd_vol - vlim:.2f} m3")
check(fwd_vol - float(auto["volume_m3"]) <= vlim, "moving auto parts also fixes FWD volume")
old_fwd_lim = next(h for h in old["holds"] if h["hold"] == "FWD")["max_weight_kg"]
fwd_before = fwd + sum(float(b["weight_kg"]) for b in bags if b["location"] == "hold_FWD" and b["owner_pax_id"] in removed)
check(fwd_before <= old_fwd_lim, f"FWD was legal on the A321 ({fwd_before:.0f} <= {old_fwd_lim})")

print("\n== Zero-fuel weight vs MZFW")
bag_w = sum(float(b["weight_kg"]) for b in fly_bags)
cargo_w = sum(float(c["weight_kg"]) for c in cargo)
mzfw = new["max_zero_fuel_weight_kg"]
def zfw(season, buf):
    return new["dry_operating_weight_kg"] + sum(v[0] for v in pax_load(season, buf).values()) + bag_w + cargo_w
for season, buf in [("summer", 0), ("summer", 5), ("winter", 0), ("winter", 5)]:
    z = zfw(season, buf)
    print(f"  {season:6} buffer {buf}%: ZFW {z:,.0f}  margin {mzfw - z:+,.0f} kg")
check(zfw("summer", 5) <= mzfw, "summer + buffer fits")
check(zfw("winter", 0) <= mzfw, "winter (no buffer) fits")
need = zfw("winter", 5) - mzfw
check(need > 0, f"winter + buffer is over by {need:.0f} kg -> cargo must be bumped")
pallet = next(c for c in cargo if c["description"] == "E-commerce pallet")
furn = next(c for c in cargo if c["description"] == "Furniture parts")
check(float(pallet["weight_kg"]) >= need and int(pallet["priority"]) == max(int(c["priority"]) for c in cargo),
      "lowest-priority pallet alone covers it (normal mode)")
check(float(furn["weight_kg"]) >= need and furn["current_hold"] == "",
      "unloaded furniture parts alone covers it (lightning mode, 0 moves)")

print("\n== CG of a simple valid plan (winter, auto parts -> AFT, unloaded items -> AFT)")
items = []
for zname, (wt, arm) in pax_load("winter").items():
    items.append((wt, arm))
items.append((new["dry_operating_weight_kg"], new["dry_operating_arm_m"]))
load = {"FWD": 0.0, "AFT": 0.0, "BULK": 0.0}
for b in fly_bags:
    h = b["location"].replace("hold_", "") if b["location"].startswith("hold_") else "AFT"
    load[h] += float(b["weight_kg"])
for c in cargo:
    h = c["current_hold"] or "AFT"
    if c is auto:
        h = "AFT"
    load[h] += float(c["weight_kg"])
for h, wt in load.items():
    items.append((wt, holds[h]["arm_m"]))
    check(wt <= holds[h]["max_weight_kg"], f"{h} {wt:.0f} / {holds[h]['max_weight_kg']} kg")
vol = {"FWD": 0.0, "AFT": 0.0, "BULK": 0.0}
for b in fly_bags:
    vol[b["location"].replace("hold_", "") if b["location"].startswith("hold_") else "AFT"] += float(b["volume_m3"])
for c in cargo:
    vol["AFT" if (c is auto or not c["current_hold"]) else c["current_hold"]] += float(c["volume_m3"])
for h, v in vol.items():
    check(v <= holds[h]["max_volume_m3"], f"{h} {v:.2f} / {holds[h]['max_volume_m3']} m3")
tw = sum(w for w, _ in items)
cg = sum(w * a for w, a in items) / tw
print(f"  CG {cg:.2f} m  (limits {new['cg_forward_limit_m']}-{new['cg_aft_limit_m']}, target {new['cg_target_m']})")
check(new["cg_forward_limit_m"] <= cg <= new["cg_aft_limit_m"], "CG inside limits")

print("\n== Bags")
pull = [b for b in bags if b["owner_pax_id"] in removed]
print(f"  pull list: {len(pull)} bags  (carts {sum(b['location'].startswith('cart') for b in pull)}, "
      f"holds {sum(b['location'].startswith('hold') for b in pull)}, inbound {sum(b['location']=='inbound' for b in pull)})")
top1 = next(b for b in bags if b["location"] == "cart_1" and b["stack_pos"] == "1")
check(top1["tag"] == "AC100196" and top1["owner_pax_id"] in removed, "AC100196 is top of cart 1 and must be pulled")
print(f"  at risk (flying, arrive after {cutoff}): {[(b['tag'], b['eta']) for b in at_risk]}")
check(any(b["tag"] == "AC100150" for b in at_risk), "AC100150 at risk (12 min after cutoff)")

print("\n== Scenarios")
check(scenarios["wrong_count"]["overrides"]["dcs"]["pax_boarding"] != len(flying), "wrong_count mismatches cabin")
u = scenarios["unsafe"]["overrides"]["aircraft_overrides"][new["type"]]["dry_operating_weight_kg"]
check(u + sum(v[0] for v in pax_load("winter").values()) > mzfw, "unsafe: empty plane + passengers alone exceed MZFW")

grp = [p for p in pax if p["group_id"]]
print(f"\n  group G01: {len(grp)} pax in rows {min(int(p['row']) for p in grp)}-{max(int(p['row']) for p in grp)}")
print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
raise SystemExit(0 if ok else 1)
