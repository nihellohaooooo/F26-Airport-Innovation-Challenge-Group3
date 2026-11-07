"""Load Re-planner (Task 3): decides which hold each bag and cargo item goes in after an aircraft swap.
Units: kg, m3, metres from the nose. Aircraft values are illustrative, not certified data."""
import json
import pulp



def load_input(path):
    """Read a test/demo input file. Later, real data comes from Swap Mapper and Bag Offload Tracker instead."""
    with open(path) as f:
        return json.load(f)


def fixed_load(aircraft, cabin_zones, season="winter", buffer_pct=0.0):
    """Weight and moment of the parts we cannot move: empty aircraft (with crew) + seated passengers.
    buffer_pct adds a safety margin on passenger weight (0.03 = +3%)."""
    k = 1 + buffer_pct
    pax_kg = sum(z[f"kg_{season}"] for z in cabin_zones) * k
    pax_moment = sum(z[f"kg_{season}"] * z["arm_m"] for z in cabin_zones) * k
    weight = aircraft["oew_kg"] + pax_kg
    moment = aircraft["oew_kg"] * aircraft["oew_arm_m"] + pax_moment
    return weight, moment


def current_hold_loads(bags, cargo, aircraft):
    """kg already sitting in each hold right now (items with current_hold = None are still on carts)."""
    loads = {h: 0 for h in aircraft["holds"]}
    for item in bags + cargo:
        if item.get("current_hold"):
            loads[item["current_hold"]] += item["kg"]
    return loads


def before_picture(data, season="winter", buffer_pct=0.0):
    """The problem we start from: hold loads vs. A320 limits, total weight and CG of what is loaded now."""
    aircraft = data["aircraft"]
    w, m = fixed_load(aircraft, data["cabin_zones"], season, buffer_pct)
    loads = current_hold_loads(data["bags"], data["cargo"], aircraft)
    holds = {}
    for h, spec in aircraft["holds"].items():
        holds[h] = {"kg": loads[h], "max_kg": spec["max_kg"], "over_kg": max(0, loads[h] - spec["max_kg"])}
        w += loads[h]
        m += loads[h] * spec["arm_m"]
    cart_kg = sum(b["kg"] for b in data["bags"] if not b.get("current_hold"))
    return {"holds": holds, "loaded_weight_kg": round(w), "loaded_cg_m": round(m / w, 3), "on_carts_kg": cart_kg}


def check_no_removed_bags(bags, removed_pax_ids):
    """Safety guard: a bag must never fly without its passenger (bag reconciliation)."""
    bad = [b["tag"] for b in bags if b.get("owner") in removed_pax_ids]
    if bad:
        raise ValueError(f"{len(bad)} bag(s) belong to removed passengers and must be pulled first: {bad[:5]}")


def build_model(bags, cargo, aircraft, fixed_weight, fixed_moment):
    """The hard safety rules. Returns the model plus handles to its variables and totals."""
    holds = aircraft["holds"]
    items = [dict(b, kind="bag", id=b["tag"]) for b in bags] + [dict(c, kind="cargo") for c in cargo]

    def allowed(item, h):
        return not (item.get("category") == "dangerous_goods" and not holds[h]["dg_allowed"])

    prob = pulp.LpProblem("load_replan", pulp.LpMinimize)

    # x[i, h] = 1 if item i goes in hold h. No variable at all for forbidden pairs (dangerous goods rule).
    x = {(i, h): pulp.LpVariable(f"x_{i}_{h}", cat="Binary")
         for i, item in enumerate(items) for h in holds if allowed(item, h)}
    # left[i] = 1 if item i does not fly.
    left = {i: pulp.LpVariable(f"left_{i}", cat="Binary") for i in range(len(items))}

    # Rule 1: every item is in exactly one hold, or left behind.
    for i in range(len(items)):
        prob += pulp.lpSum(x[i, h] for h in holds if (i, h) in x) + left[i] == 1, f"one_place_{i}"

    # Rule 2 and 3: hold weight and volume limits.
    for h, spec in holds.items():
        prob += pulp.lpSum(x[i, hh] * items[i]["kg"] for (i, hh) in x if hh == h) <= spec["max_kg"], f"kg_{h}"
        prob += pulp.lpSum(x[i, hh] * items[i]["m3"] for (i, hh) in x if hh == h) <= spec["max_m3"], f"m3_{h}"

    # Totals: fixed part (aircraft + passengers) + whatever the solver puts in the holds.
    total_w = fixed_weight + pulp.lpSum(x[i, h] * items[i]["kg"] for (i, h) in x)
    total_m = fixed_moment + pulp.lpSum(x[i, h] * items[i]["kg"] * holds[h]["arm_m"] for (i, h) in x)

    # Rule 4: max zero-fuel weight.
    prob += total_w <= aircraft["mzfw_kg"], "mzfw"
    # Rule 5: CG between the limits. CG = M / W, so  M >= fwd * W  and  M <= aft * W  (linear).
    prob += total_m >= aircraft["cg_fwd_limit_m"] * total_w, "cg_fwd"
    prob += total_m <= aircraft["cg_aft_limit_m"] * total_w, "cg_aft"

    return prob, items, x, left, total_w, total_m