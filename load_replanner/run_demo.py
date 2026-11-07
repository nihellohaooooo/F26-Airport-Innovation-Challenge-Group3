"""Run the Load Re-planner on the team's shared data and print results.
Usage:  python run_demo.py                 (base_winter)
        python run_demo.py winter_buffer   (any scenario name from data/scenarios.json)"""
import sys
import pulp
from replanner import fixed_load, before_picture, build_model, check_no_removed_bags
from team_data import load_scenario

name = sys.argv[1] if len(sys.argv) > 1 else "base_winter"
data = load_scenario(name)
season, buffer_pct = data["season"], data["buffer_pct"]
print(f"Scenario: {name}  ({season}, buffer {buffer_pct:.0%}, lightning {data['lightning']})")
print(f"Team expects: {data['expect']}\n")

check_no_removed_bags(data["bags"], data["removed_pax_ids"])
pax = sum(z["pax"] for z in data["cabin_zones"])
w0, m0 = fixed_load(data["aircraft"], data["cabin_zones"], season, buffer_pct)
print(f"{pax} passengers, {len(data['bags'])} bags flying, {len(data['cargo'])} cargo items")
print(f"Fixed load (aircraft + passengers): {w0:.0f} kg, CG {m0 / w0:.3f} m")

before = before_picture(data, season, buffer_pct)
print(f"\nBefore re-planning ({data['aircraft']['type']}):")
for h, v in before["holds"].items():
    flag = f"  <-- {v['over_kg']:.0f} kg OVER" if v["over_kg"] else ""
    print(f"  {h:4}: {v['kg']:7.1f} / {v['max_kg']} kg{flag}")
print(f"  Loaded so far: {before['loaded_weight_kg']} kg, CG {before['loaded_cg_m']} m; bags not in a hold yet: {before['on_carts_kg']:.0f} kg")

# --- Step 3 check: does ANY safe arrangement exist? ---
prob, items, x, left, total_w, total_m = build_model(data["bags"], data["cargo"], data["aircraft"], w0, m0)
prob.setObjective(pulp.lpSum(left.values()))          # temporary goal: leave as few items as possible
status = pulp.LpStatus[prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))]
print(f"\nStep 3 check: status = {status}")
if status == "Optimal":
    w, m = pulp.value(total_w), pulp.value(total_m)
    print(f"  items left behind = {int(pulp.value(prob.objective))}")
    print(f"  A safe arrangement exists: {w:.0f} kg (limit {data['aircraft']['mzfw_kg']}), "
          f"CG {m / w:.3f} m (limits {data['aircraft']['cg_fwd_limit_m']} to {data['aircraft']['cg_aft_limit_m']})")
else:
    print(f"  No safe arrangement: fixed load alone is {w0:.0f} kg vs max zero-fuel weight {data['aircraft']['mzfw_kg']}")
