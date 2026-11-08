"""MILP load planner. All weights are kg, volumes m3, and arms metres."""
import pulp

from common import parse_bool


def _bump_cost(priority):
    """Penalty for bumping cargo: priority 1 is most important, 5 least.

    This ports the priority scheme from the standalone planner while keeping
    this module's combined-pipeline input and output contract. The weight term
    breaks ties within a priority level by preferring lighter items to bump.
    """
    priority = int(priority)
    if not 1 <= priority <= 5:
        raise ValueError(f"Cargo priority must be between 1 and 5, got {priority}")
    return 10 ** (8 - priority)


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
                      "must_fly": parse_bool(source.get("must_fly", False)),
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
    # Preserve high-priority cargo first (priority 1 is most important). The
    # previous weight-times-rank score could bump a light priority-1 item in
    # preference to a sufficiently heavy priority-5 item.
    cargo_left = pulp.lpSum(
        (_bump_cost(item["priority"]) + item["weight"]) * left[i]
        for i, item in enumerate(items) if item["kind"] == "cargo")
    move_terms = []
    for i, item in enumerate(items):
        h = item["current_hold"]
        if h:
            move_terms.append(1 - x[i, h] if (i, h) in x else 1)
    moves = pulp.lpSum(move_terms)
    stages = [("bags_left", bags_left), ("cargo_left", cargo_left), ("moves", moves),
              ("target_cg_deviation", d_pos + d_neg)]
    if parse_bool(options.get("lightning_mode", False)):
        stages[1], stages[2] = stages[2], stages[1]
    return prob, x, left, W, M, stages


def _hold_specs(aircraft):
    return ({h["hold"]: h for h in aircraft["holds"]}
            if isinstance(aircraft["holds"], list) else aircraft["holds"])


def _starting_situation(items, aircraft, fixed_weight):
    holds = _hold_specs(aircraft)
    load = {h: 0.0 for h in holds}
    volume = {h: 0.0 for h in holds}
    for item in items:
        hold = item["current_hold"]
        if hold in holds:
            load[hold] += item["weight"]
            volume[hold] += item["volume"]
    all_weight = float(fixed_weight) + sum(item["weight"] for item in items)
    return {"load": load, "volume": volume,
            "over_mzfw_kg": all_weight - float(aircraft["max_zero_fuel_weight_kg"])}


def _item_name(item):
    return item["source"].get("description") or f"{item['kind']} {item['id']}"


def _action_line(action, item, instruction, reason):
    return (f"{action} {item['id']} {_item_name(item)} ({item['weight']:.0f} kg): "
            f"{instruction}. Reason: {reason}.")


def _move_reason(item, old, new, situation, holds):
    if old not in holds:
        return _action_line("MOVE", item, f"{old} -> {new}",
                            f"{old} is not a hold on the replacement aircraft")
    spec = holds[old]
    excesses = []
    if situation["load"][old] > float(spec["max_weight_kg"]):
        excesses.append(f"{old} exceeds its weight limit")
    if situation["volume"][old] > float(spec["max_volume_m3"]):
        excesses.append(f"{old} exceeds its volume limit")
    cause = ", ".join(excesses) if excesses else "required to keep the loading plan within aircraft limits"
    return _action_line("MOVE", item, f"{old} -> {new}", cause)


def _bump_reason(item, situation, lightning):
    if situation["over_mzfw_kg"] > 0:
        cause = f"planned load exceeds MZFW by {situation['over_mzfw_kg']:.0f} kg before offloading"
    else:
        cause = "needed to satisfy hold, volume, or balance limits"
    if lightning:
        policy = "lightning mode prioritizes fewer handling actions"
    else:
        policy = f"cargo priority {item['priority']} is selected by the bumping objective"
    verb, instruction = (("OFFLOAD", f"remove from {item['current_hold']}")
                         if item["current_hold"] else ("DO NOT LOAD", "leave on dock"))
    return _action_line(verb, item, instruction, f"{cause}; {policy}")


def _infeasible_reason(items, aircraft, fixed_weight):
    mzfw = float(aircraft["max_zero_fuel_weight_kg"])
    if float(fixed_weight) > mzfw:
        detail = (f"aircraft and passenger load alone exceeds MZFW by "
                  f"{float(fixed_weight) - mzfw:.0f} kg")
    else:
        must_fly = sum(item["weight"] for item in items
                       if item["kind"] == "cargo" and item["must_fly"])
        if must_fly and float(fixed_weight) + must_fly > mzfw:
            detail = (f"must-fly cargo requires {must_fly:.0f} kg, but only "
                      f"{mzfw - float(fixed_weight):.0f} kg remains under MZFW")
        else:
            detail = "no assignment satisfies all hold, weight, volume, and CG limits"
    return f"UNSAFE: do not load. {detail}. Load control must revise the plan."


def solve_load_plan(bags, cargo, aircraft, fixed_weight, fixed_moment, options=None):
    """Solve lexicographic goals and return hold assignments plus actions."""
    options = options or {}
    items = _make_items(bags, cargo, aircraft)
    prob, x, left, W, M, stages = build_model(items, aircraft, fixed_weight, fixed_moment, options)
    time_limit = int(options.get("time_limit_s", 10))
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    objective_values = {}
    plan_status = "OPTIMAL"
    plan_reason = "Optimal plan found within all hard limits"
    try:
        for idx, (name, expr) in enumerate(stages):
            prob.setObjective(expr)
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            solution_status = getattr(prob, "sol_status", None)
            has_incumbent = solution_status in {
                pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible,
            } and all(variable.value() is not None for variable in left.values()) \
                and all(variable.value() is not None for variable in x.values())
            if status == "Infeasible":
                return {"status": "INFEASIBLE",
                        "reason": _infeasible_reason(items, aircraft, fixed_weight),
                        "items": items, "bag_holds": {}, "cargo_holds": {},
                        "bags_left_behind": [], "cargo_bumped": [], "moves": [], "offloads": [],
                        "handling_actions": {"moves": 0, "offloads": 0, "total": 0},
                        "objective_values": objective_values}
            if not has_incumbent:
                return {"status": "ERROR",
                        "reason": f"Solver did not produce a feasible plan at {name}: {status}",
                        "items": items, "bag_holds": {}, "cargo_holds": {},
                        "bags_left_behind": [], "cargo_bumped": [], "moves": [], "offloads": [],
                        "handling_actions": {"moves": 0, "offloads": 0, "total": 0},
                        "objective_values": objective_values}
            best = float(pulp.value(expr) or 0)
            objective_values[name] = round(best, 4)
            if status != "Optimal" or solution_status != pulp.LpSolutionOptimal:
                plan_status = "FEASIBLE"
                plan_reason = f"A feasible plan was found, but optimality was not proven at {name}."
                break
            if idx < len(stages) - 1:
                tol = 1e-5 if name != "target_cg_deviation" else 1e-4
                prob += expr <= best + tol, f"lock_{name}"
    except (pulp.PulpSolverError, AttributeError) as exc:
        return {"status": "ERROR", "reason": f"Optimization solver error: {exc}",
                "items": items, "bag_holds": {}, "cargo_holds": {},
                "bags_left_behind": [], "cargo_bumped": [], "moves": [], "offloads": [],
                "handling_actions": {"moves": 0, "offloads": 0, "total": 0},
                "objective_values": objective_values}

    holds = _hold_specs(aircraft)
    situation = _starting_situation(items, aircraft, fixed_weight)
    lightning = parse_bool(options.get("lightning_mode", False))
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
                           "reason": _bump_reason(item, situation, lightning)})
        if hold and old and hold != old:
            moves.append({"id": item["id"], "kind": item["kind"], "from": old, "to": hold,
                          "reason": _move_reason(item, old, hold, situation, holds)})
        if not hold and old:
            if item["kind"] == "cargo":
                reason = _bump_reason(item, situation, lightning)
            else:
                reason = _action_line("OFFLOAD", item, f"remove from {old}",
                                      "bag cannot fit in any safe hold assignment")
            offloads.append({"id": item["id"], "kind": item["kind"], "from": old,
                             "weight_kg": item["weight"], "reason": reason})
    return {"status": plan_status, "reason": plan_reason,
            "items": items, "bag_holds": bag_holds, "cargo_holds": cargo_holds,
            "bags_left_behind": left_bags, "cargo_bumped": bumped, "moves": moves,
            "offloads": offloads,
            "handling_actions": {"moves": len(moves), "offloads": len(offloads),
                                 "total": len(moves) + len(offloads)},
            "objective_values": objective_values,
            "total_weight_kg": round(float(pulp.value(W)), 1),
            "moment_kg_m": float(pulp.value(M))}
