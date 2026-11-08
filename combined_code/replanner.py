"""MILP load planner. All weights are kg, volumes m3, and arms metres."""
import pulp


def _make_items(bags, cargo, aircraft):
    holds = {h["hold"]: h for h in aircraft["holds"]} if isinstance(aircraft["holds"], list) else aircraft["holds"]
    items = []
    for source in bags:
        hold = source.get("current_hold")
        if not hold and str(source.get("location", "")).startswith("hold_"):
            hold = str(source["location"])[5:]
        items.append({"id": source["tag"], "kind": "bag", "weight": float(source["weight_kg"]),
                      "volume": float(source.get("volume_m3", 0.07)), "priority": 0,
                      "current_hold": hold, "must_fly": False,
                      "allowed": list(holds), "source": source})
    for source in cargo:
        dg_class = str(source.get("dg_class", ""))
        allowed = [h for h, spec in holds.items()
                   if not dg_class or dg_class not in spec.get("dg_forbidden_classes", [])]
        items.append({"id": source["cargo_id"], "kind": "cargo",
                      "weight": float(source["weight_kg"]),
                      "volume": float(source.get("volume_m3", 0)),
                      "priority": int(source.get("priority", 3)),
                      "current_hold": source.get("current_hold") or None,
                      "must_fly": bool(source.get("must_fly", False)),
                      "allowed": allowed, "source": source})
    return items


def build_model(items, aircraft, fixed_weight, fixed_moment, options=None):
    options = options or {}
    holds = {h["hold"]: h for h in aircraft["holds"]} if isinstance(aircraft["holds"], list) else aircraft["holds"]
    prob = pulp.LpProblem("swap_load_replan", pulp.LpMinimize)
    x = {(i, h): pulp.LpVariable(f"x_{i}_{h}", cat="Binary")
         for i, item in enumerate(items) for h in item["allowed"]}
    left = {i: pulp.LpVariable(f"left_{i}", cat="Binary") for i in range(len(items))}
    d_pos = pulp.LpVariable("target_dev_pos", lowBound=0)
    d_neg = pulp.LpVariable("target_dev_neg", lowBound=0)

    for i, item in enumerate(items):
        prob += pulp.lpSum(x[i, h] for h in item["allowed"] if (i, h) in x) + left[i] == 1, f"one_place_{i}"
        if item["must_fly"]:
            prob += left[i] == 0, f"must_fly_{i}"
    for h, spec in holds.items():
        ids = [i for i, item in enumerate(items) if h in item["allowed"]]
        prob += pulp.lpSum(items[i]["weight"] * x[i, h] for i in ids) <= float(spec["max_weight_kg"]), f"weight_{h}"
        prob += pulp.lpSum(items[i]["volume"] * x[i, h] for i in ids) <= float(spec["max_volume_m3"]), f"volume_{h}"

    W = float(fixed_weight) + pulp.lpSum(items[i]["weight"] * x[i, h] for i, h in x)
    M = float(fixed_moment) + pulp.lpSum(items[i]["weight"] * float(holds[h]["arm_m"]) * x[i, h] for i, h in x)
    prob += W <= float(aircraft["max_zero_fuel_weight_kg"]), "max_zfw"
    prob += M >= float(aircraft["cg_forward_limit_m"]) * W, "cg_forward"
    prob += M <= float(aircraft["cg_aft_limit_m"]) * W, "cg_aft"
    prob += M - float(aircraft["cg_target_m"]) * W == d_pos - d_neg, "target_cg_deviation"

    bags_left = pulp.lpSum(left[i] for i, item in enumerate(items) if item["kind"] == "bag")
    if items:
        max_priority = max([item["priority"] for item in items if item["kind"] == "cargo"] or [1])
    else:
        max_priority = 1
    # Strict priority: each level costs 10x the next (p1 = 10,000,000 ... p5 = 1,000), so a
    # lower-priority item is always bumped first. + weight breaks ties between equal priorities.
    cargo_left = pulp.lpSum(
        (10 ** (8 - item["priority"]) + item["weight"]) * left[i]
        for i, item in enumerate(items) if item["kind"] == "cargo")
    move_terms = []
    for i, item in enumerate(items):
        h = item["current_hold"]
        if h:
            move_terms.append(1 - x[i, h] if (i, h) in x else 1)
    moves = pulp.lpSum(move_terms)
    stages = [("bags_left", bags_left), ("cargo_left", cargo_left), ("moves", moves),
              ("target_cg_deviation", d_pos + d_neg)]
    if options.get("lightning_mode"):
        stages[1], stages[2] = stages[2], stages[1]
    return prob, x, left, W, M, stages



# ---------------------------------------------------------------------------
# Plain-language explanations ("explains why")
# ---------------------------------------------------------------------------

def _holds(aircraft):
    """Hold specs as a dict keyed by hold name, whichever format the profile uses."""
    return {h["hold"]: h for h in aircraft["holds"]} if isinstance(aircraft["holds"], list) else aircraft["holds"]


def _name(item):
    """Readable name: cargo description, or 'bag AC100123'."""
    return item["source"].get("description") or f"{item['kind']} {item['id']}"


def _starting_situation(items, aircraft, fixed_weight):
    """Facts about the position before re-planning, used to explain each decision."""
    holds = _holds(aircraft)
    before = {h: 0.0 for h in holds}
    for item in items:
        if item["current_hold"] in before:
            before[item["current_hold"]] += item["weight"]
    everything = float(fixed_weight) + sum(item["weight"] for item in items)
    return {"type": aircraft["type"], "before_kg": before,
            "over_mzfw_kg": everything - float(aircraft["max_zero_fuel_weight_kg"]),
            "cg_target_m": float(aircraft["cg_target_m"])}


def _move_reason(item, old, new, sit, aircraft, holds):
    cur, cap = sit["before_kg"][old], float(holds[old]["max_weight_kg"])
    if cur > cap:
        why = f"the {old} hold was {cur - cap:.0f} kg over its {sit['type']} limit ({cur:.0f} / {cap:.0f} kg)"
    else:
        why = "needed to keep the aircraft within its weight and balance limits"
    return (f"{_name(item)} moved {old} -> {new}: {why}. {new} was chosen because it keeps the CG "
            f"closest to the {sit['cg_target_m']} m target.")


def _bump_reason(item, sit, lightning):
    if sit["over_mzfw_kg"] > 0:
        cause = (f"with everything loaded the aircraft would be {sit['over_mzfw_kg']:.0f} kg over "
                 f"its max zero-fuel weight")
    else:
        cause = "not everything fits within the hold, weight and balance limits"
    handling = (f"it must be taken out of the {item['current_hold']} hold (1 offload)" if item["current_hold"]
                else "it is still on the dock, so leaving it needs no unloading")
    if lightning:
        rule = "lightning mode keeps handling to a minimum"
    else:
        rule = "lower-priority cargo is removed before higher-priority cargo"
    return f"Priority {item['priority']}: {cause}; {rule}; {handling}."


def solve_load_plan(bags, cargo, aircraft, fixed_weight, fixed_moment, options=None):
    """Solve lexicographic goals and return hold assignments plus actions."""
    options = options or {}
    items = _make_items(bags, cargo, aircraft)
    prob, x, left, W, M, stages = build_model(items, aircraft, fixed_weight, fixed_moment, options)
    time_limit = int(options.get("time_limit_s", 10))
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    objective_values = {}
    try:
        for idx, (name, expr) in enumerate(stages):
            prob.setObjective(expr)
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            if status != "Optimal":
                return {"status": "INFEASIBLE" if status == "Infeasible" else "ERROR",
                        "reason": f"Solver did not find an optimal safe plan at {name}: {status}",
                        "items": items, "bag_holds": {}, "cargo_holds": {},
                        "bags_left_behind": [], "cargo_bumped": [], "moves": [],
                        "objective_values": objective_values}
            best = float(pulp.value(expr) or 0)
            objective_values[name] = round(best, 4)
            if idx < len(stages) - 1:
                tol = 1e-5 if name != "target_cg_deviation" else 1e-4
                prob += expr <= best + tol, f"lock_{name}"
    except (pulp.PulpSolverError, AttributeError) as exc:
        return {"status": "ERROR", "reason": f"Optimization solver error: {exc}",
                "items": items, "bag_holds": {}, "cargo_holds": {},
                "bags_left_behind": [], "cargo_bumped": [], "moves": [],
                "objective_values": objective_values}

    holds = _holds(aircraft)
    sit = _starting_situation(items, aircraft, fixed_weight)
    lightning = bool(options.get("lightning_mode"))
    bag_holds, cargo_holds, left_bags, bumped, moves, offloads = {}, {}, [], [], [], []
    for i, item in enumerate(items):
        hold = next((h for h in item["allowed"] if (x[i, h].value() or 0) > 0.5), None)
        old = item["current_hold"]
        if item["kind"] == "bag":
            if hold:
                bag_holds[item["id"]] = hold
            else:
                left_bags.append(item["id"])
        elif hold:
            cargo_holds[item["id"]] = hold
        else:
            src = item["source"]
            bumped.append({"cargo_id": item["id"], "description": src.get("description", ""),
                           "weight_kg": item["weight"], "priority": item["priority"],
                           "reason": _bump_reason(item, sit, lightning)})
        if hold and old and hold != old:
            moves.append({"id": item["id"], "kind": item["kind"], "from": old, "to": hold,
                          "reason": _move_reason(item, old, hold, sit, aircraft, holds)})
        if not hold and old:   # was already loaded, now has to come back out
            offloads.append({"id": item["id"], "kind": item["kind"], "from": old,
                             "weight_kg": item["weight"],
                             "reason": f"{_name(item)} must be taken out of the {old} hold"})
    return {"status": "OPTIMAL", "reason": "Optimal plan found within all hard limits",
            "items": items, "bag_holds": bag_holds, "cargo_holds": cargo_holds,
            "bags_left_behind": left_bags, "cargo_bumped": bumped, "moves": moves,
            "offloads": offloads,
            "handling_actions": {"moves": len(moves), "offloads": len(offloads),
                                 "total": len(moves) + len(offloads)},
            "objective_values": objective_values,
            "total_weight_kg": round(float(pulp.value(W)), 1),
            "moment_kg_m": float(pulp.value(M))}
