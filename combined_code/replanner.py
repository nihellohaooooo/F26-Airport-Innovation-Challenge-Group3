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

    bag_holds, cargo_holds, left_bags, bumped, moves = {}, {}, [], [], []
    for i, item in enumerate(items):
        hold = next((h for h in item["allowed"] if (x[i, h].value() or 0) > 0.5), None)
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
                           "reason": "Offloaded to satisfy aircraft limits while retaining higher-priority cargo where feasible"})
        old = item["current_hold"]
        if hold and old and hold != old:
            moves.append({"id": item["id"], "kind": item["kind"], "from": old, "to": hold,
                          "reason": f"Move {item['id']} from {old} to {hold} to meet hold and balance limits"})
    return {"status": "OPTIMAL", "reason": "Optimal plan found within all hard limits",
            "items": items, "bag_holds": bag_holds, "cargo_holds": cargo_holds,
            "bags_left_behind": left_bags, "cargo_bumped": bumped, "moves": moves,
            "objective_values": objective_values,
            "total_weight_kg": round(float(pulp.value(W)), 1),
            "moment_kg_m": float(pulp.value(M))}
