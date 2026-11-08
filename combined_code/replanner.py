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


def _line(action, item, todo, reason):
    """One message format for every instruction:
    <ACTION> <ID> <item> (<kg> kg): <what to do>. Reason: <why>."""
    return f"{action} {item['id']} {_name(item)} ({item['weight']:.0f} kg): {todo}. Reason: {reason}."


def _move_reason(item, old, new, sit, aircraft, holds):
    cur, cap = sit["before_kg"][old], float(holds[old]["max_weight_kg"])
    why = f"{old} hold {cur - cap:.0f} kg over limit" if cur > cap else "weight and balance limits"
    return _line("MOVE", item, f"{old} -> {new}", f"{why}; {new} keeps CG closest to target")


def _bump_reason(item, sit, lightning):
    cause = (f"ZFW {sit['over_mzfw_kg']:.0f} kg over MZFW" if sit["over_mzfw_kg"] > 0
             else "not enough hold capacity")
    rule = ("lightning mode, fewest handling jobs" if lightning
            else f"priority {item['priority']}, lowest priority removed first")
    if item["current_hold"]:
        return _line("OFFLOAD", item, f"remove from {item['current_hold']}", f"{cause}; {rule}")
    return _line("DO NOT LOAD", item, "leave on dock", f"{cause}; {rule}")


def _diagnose_infeasible(items, aircraft, fixed_weight, fixed_moment):
    """Explains WHY no safe plan exists, with numbers, so load control knows what to fix.
    Checks the simple causes first; if none applies, measures how far the CG cannot be brought
    back inside its limits. Never suggests breaking a limit: the decision goes back to humans."""
    holds = _holds(aircraft)
    ac_type = aircraft["type"]
    mzfw = float(aircraft["max_zero_fuel_weight_kg"])
    fixed_weight, fixed_moment = float(fixed_weight), float(fixed_moment)
    must = [it for it in items if it.get("must_fly")]
    must_kg = sum(it["weight"] for it in must)
    found = []

    # 1. Aircraft + passengers alone are over the max zero-fuel weight.
    if fixed_weight > mzfw:
        found.append(f"aircraft + passengers {fixed_weight - mzfw:,.0f} kg over MZFW with no bags or cargo")
    # 2. Must-fly items that fit in no hold they are allowed in (grouped, so 10 pallets = 1 line).
    no_hold, too_heavy, too_big = [], [], []
    for it in must:
        allowed = [holds[h] for h in it["allowed"]]
        if not allowed:
            no_hold.append(it)
        elif it["weight"] > max(float(h["max_weight_kg"]) for h in allowed):
            too_heavy.append(it)
        elif it["volume"] > max(float(h["max_volume_m3"]) for h in allowed):
            too_big.append(it)
    if no_hold:
        found.append(f"{len(no_hold)} must-fly item(s) not allowed in any hold (dangerous goods)")
    if too_heavy:
        biggest = max(float(h["max_weight_kg"]) for h in holds.values())
        found.append(f"{len(too_heavy)} must-fly item(s) too heavy for any hold "
                     f"({max(it['weight'] for it in too_heavy):,.0f} kg, hold max {biggest:,.0f} kg)")
    if too_big:
        found.append(f"{len(too_big)} must-fly item(s) too big for any hold")
    # 3. Must-fly items together exceed what the aircraft can carry.
    if must and fixed_weight <= mzfw and fixed_weight + must_kg > mzfw:
        found.append(f"must-fly cargo {must_kg:,.0f} kg, only {mzfw - fixed_weight:,.0f} kg available under MZFW")

    # 4. Nothing obvious: measure how far the CG stays outside its limits in the best arrangement.
    if not found:
        prob = pulp.LpProblem("cg_gap", pulp.LpMinimize)
        x = {(i, h): pulp.LpVariable(f"d_{i}_{h}", cat="Binary") for i, it in enumerate(items) for h in it["allowed"]}
        left = {i: pulp.LpVariable(f"dl_{i}", cat="Binary") for i in range(len(items))}
        gap_fwd = pulp.LpVariable("gap_fwd", lowBound=0)
        gap_aft = pulp.LpVariable("gap_aft", lowBound=0)
        for i, it in enumerate(items):
            prob += pulp.lpSum(x[i, h] for h in it["allowed"]) + left[i] == 1
            if it.get("must_fly"):
                prob += left[i] == 0
        for h, spec in holds.items():
            prob += pulp.lpSum(items[i]["weight"] * x[i, hh] for (i, hh) in x if hh == h) <= float(spec["max_weight_kg"])
            prob += pulp.lpSum(items[i]["volume"] * x[i, hh] for (i, hh) in x if hh == h) <= float(spec["max_volume_m3"])
        W = fixed_weight + pulp.lpSum(items[i]["weight"] * x[i, h] for (i, h) in x)
        M = fixed_moment + pulp.lpSum(items[i]["weight"] * float(holds[h]["arm_m"]) * x[i, h] for (i, h) in x)
        prob += W <= mzfw
        prob += M + gap_fwd >= float(aircraft["cg_forward_limit_m"]) * W
        prob += M - gap_aft <= float(aircraft["cg_aft_limit_m"]) * W
        prob.setObjective(gap_fwd + gap_aft)
        prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))
        if pulp.LpStatus[prob.status] == "Optimal":
            w = float(pulp.value(W))
            fwd_m, aft_m = float(gap_fwd.value() or 0) / w, float(gap_aft.value() or 0) / w
            if fwd_m > 1e-4:
                found.append(f"nose-heavy, CG {fwd_m:.2f} m forward of the forward limit in the best possible loading")
            if aft_m > 1e-4:
                found.append(f"tail-heavy, CG {aft_m:.2f} m aft of the aft limit in the best possible loading")
    if not found:
        found.append("no loading meets all hold, weight and CG limits")
    return "UNSAFE: do not load. Reason: " + "; ".join(found[:2]) + ". Action: DCS / load control decision required."


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
                        "reason": (_diagnose_infeasible(items, aircraft, fixed_weight, fixed_moment)
                                   if status == "Infeasible"
                                   else f"Solver did not find an optimal safe plan at {name}: {status}"),
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
                             "reason": (_bump_reason(item, sit, lightning) if item["kind"] == "cargo"
                                        else _line("OFFLOAD", item, f"remove from {old}", "no safe space in any hold"))})
    return {"status": "OPTIMAL", "reason": "Optimal plan found within all hard limits",
            "items": items, "bag_holds": bag_holds, "cargo_holds": cargo_holds,
            "bags_left_behind": left_bags, "cargo_bumped": bumped, "moves": moves,
            "offloads": offloads,
            "handling_actions": {"moves": len(moves), "offloads": len(offloads),
                                 "total": len(moves) + len(offloads)},
            "objective_values": objective_values,
            "total_weight_kg": round(float(pulp.value(W)), 1),
            "moment_kg_m": float(pulp.value(M))}
