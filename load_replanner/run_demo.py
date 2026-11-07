"""Run the Load Re-planner on the demo data and print results."""
from pathlib import Path
import pulp
from replanner import load_input, fixed_load, before_picture, build_model

DATA = Path(__file__).parent / "tests" / "demo_a321_to_a320.json"

data = load_input(DATA)
for season in ["summer", "winter"]:
    w, m = fixed_load(data["aircraft"], data["cabin_zones"], season)
    print(f"{season}: fixed load {w:.0f} kg, CG {m / w:.3f} m")

before = before_picture(data, "winter")
print("\nBefore re-planning (winter):")
for h, v in before["holds"].items():
    flag = f"  <-- {v['over_kg']} kg OVER" if v["over_kg"] else ""
    print(f"  {h:4}: {v['kg']:5} / {v['max_kg']} kg{flag}")
print(f"  Loaded so far: {before['loaded_weight_kg']} kg, CG {before['loaded_cg_m']} m; still on carts: {before['on_carts_kg']} kg")

# --- Step 3 check: does ANY safe arrangement exist? ---
w0, m0 = fixed_load(data["aircraft"], data["cabin_zones"], "winter")
prob, items, x, left, total_w, total_m = build_model(data["bags"], data["cargo"], data["aircraft"], w0, m0)
prob.setObjective(pulp.lpSum(left.values()))          # temporary goal: leave as few items as possible
status = pulp.LpStatus[prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))]
w, m = pulp.value(total_w), pulp.value(total_m)
print(f"\nStep 3 check: status = {status}, items left behind = {int(pulp.value(prob.objective))}")
print(f"  A safe arrangement exists: {w:.0f} kg (limit {data['aircraft']['mzfw_kg']}), CG {m / w:.3f} m (limits 16.4 to 18.0)")