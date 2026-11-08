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
        """Dangerous goods rule: a DG class listed as forbidden for this hold may not go there."""
        dg = item.get("dg_class")
        return not (dg and dg in holds[h].get("dg_forbidden", []))

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


# ---------------------------------------------------------------------------
# Step 4: the four goals, solved in strict order
# ---------------------------------------------------------------------------

def bump_cost(priority):
    """Cost of leaving a cargo item behind. Each priority level costs 10x the next, so one
    priority-4 item always outweighs any realistic number of priority-5 items (1 = most important)."""
    return 10 ** (8 - priority)          # p1 = 10,000,000 ... p5 = 1,000


def make_goals(items, x, left, total_w, total_m, aircraft, lightning=False):
    """Builds the four goals. Returns them in the order to solve, plus the CG link constraint."""
    # Goal 1: bags left behind (count).
    g_bags = pulp.lpSum(left[i] for i, it in enumerate(items) if it["kind"] == "bag")
    # Goal 2: cargo bumped, weighted by priority (+ kg, so the lighter of two equal items goes first).
    g_cargo = pulp.lpSum(left[i] * (bump_cost(it["priority"]) + it["kg"])
                         for i, it in enumerate(items) if it["kind"] == "cargo")
    # Goal 3: handling actions on items already in a hold. Staying in its current hold = 0,
    # moved to another hold or taken off the aircraft = 1.
    g_moves = pulp.lpSum(1 - x[i, it["current_hold"]] for i, it in enumerate(items)
                         if it.get("current_hold") and (i, it["current_hold"]) in x)
    # Goal 4: distance of the CG from the target (absolute value trick from the starter code).
    dev_pos = pulp.LpVariable("cg_dev_pos", lowBound=0)
    dev_neg = pulp.LpVariable("cg_dev_neg", lowBound=0)
    cg_link = total_m - aircraft["cg_target_m"] * total_w == dev_pos - dev_neg
    g_cg = dev_pos + dev_neg

    if lightning:   # after a lightning hold: fewest handling actions matters more than keeping cargo
        order = [("bags left behind", g_bags), ("handling actions", g_moves),
                 ("cargo bumped", g_cargo), ("CG distance from target", g_cg)]
    else:
        order = [("bags left behind", g_bags), ("cargo bumped", g_cargo),
                 ("handling actions", g_moves), ("CG distance from target", g_cg)]
    return order, cg_link


def solve_in_order(prob, order, cg_link, time_limit=10):
    """Solve goal 1, lock its best value in as a rule, then goal 2, and so on.
    Returns 'Optimal' or the solver status that stopped it."""
    prob += cg_link, "cg_link"
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)    # always cap the solve time
    for n, (name, goal) in enumerate(order):
        prob.setObjective(goal)
        status = pulp.LpStatus[prob.solve(solver)]
        if status != "Optimal":
            return status
        prob += goal <= pulp.value(goal) + 1e-6, f"lock_goal_{n}"  # later goals may not make this worse
    return "Optimal"


def read_plan(items, x, left, aircraft, fixed_weight, fixed_moment):
    """Turns solver switches into a plain plan: where everything goes, what moves, what stays behind."""
    holds = aircraft["holds"]
    assignments, moved, offloaded, bumped, bags_left = {}, [], [], [], []
    hold_kg = {h: 0.0 for h in holds}
    for i, it in enumerate(items):
        new = next((h for h in holds if (i, h) in x and x[i, h].value() > 0.5), None)
        assignments[it["id"]] = new
        old = it.get("current_hold")
        if new:
            hold_kg[new] += it["kg"]
        if new is None:
            (bags_left if it["kind"] == "bag" else bumped).append(it)
            if old:
                offloaded.append(it)                       # was in a hold, must come out
        elif old and new != old:
            moved.append({**it, "from": old, "to": new})
    # Recompute weight and CG from the plan itself (don't trust solver rounding).
    w = fixed_weight + sum(hold_kg.values())
    m = fixed_moment + sum(hold_kg[h] * holds[h]["arm_m"] for h in holds)
    return {"assignments": assignments, "moved": moved, "offloaded": offloaded,
            "bumped_cargo": bumped, "bags_left_behind": bags_left,
            "hold_kg": {h: round(v, 1) for h, v in hold_kg.items()},
            "final_weight_kg": round(w, 1), "final_cg_m": round(m / w, 3)}
