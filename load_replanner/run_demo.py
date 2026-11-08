"""Run the Load Re-planner on the team's shared data and print results.
Usage:  python run_demo.py                 (base_winter)
        python run_demo.py winter_buffer   (any scenario name from data/scenarios.json)"""
import sys
import time
from replanner import (fixed_load, before_picture, build_model, check_no_removed_bags,
                       make_goals, solve_in_order, read_plan)
from team_data import load_scenario

name = sys.argv[1] if len(sys.argv) > 1 else "base_winter"
data = load_scenario(name)
season, buffer_pct, lightning = data["season"], data["buffer_pct"], data["lightning"]
aircraft = data["aircraft"]
print(f"Scenario: {name}  ({season}, buffer {buffer_pct:.0%}, lightning {lightning})")
print(f"Team expects: {data['expect']}\n")

check_no_removed_bags(data["bags"], data["removed_pax_ids"])
pax = sum(z["pax"] for z in data["cabin_zones"])
w0, m0 = fixed_load(aircraft, data["cabin_zones"], season, buffer_pct)
print(f"{pax} passengers, {len(data['bags'])} bags flying, {len(data['cargo'])} cargo items")
print(f"Fixed load (aircraft + passengers): {w0:.0f} kg, CG {m0 / w0:.3f} m")

before = before_picture(data, season, buffer_pct)
print(f"\nBefore re-planning ({aircraft['type']}):")
for h, v in before["holds"].items():
    flag = f"  <-- {v['over_kg']:.0f} kg OVER" if v["over_kg"] else ""
    print(f"  {h:4}: {v['kg']:7.1f} / {v['max_kg']} kg{flag}")

# --- Step 4: hard rules + four goals in order ---
start = time.time()
prob, items, x, left, total_w, total_m = build_model(data["bags"], data["cargo"], aircraft, w0, m0)
order, cg_link = make_goals(items, x, left, total_w, total_m, aircraft, lightning)
status = solve_in_order(prob, order, cg_link)
print(f"\nRe-plan: {status} in {time.time() - start:.1f} s   (goal order: {', '.join(n for n, _ in order)})")
if status != "Optimal":
    print(f"  No safe plan. Fixed load alone is {w0:.0f} kg vs max zero-fuel weight {aircraft['mzfw_kg']} kg.")
    sys.exit()

plan = read_plan(items, x, left, aircraft, w0, m0)
print("\nAfter re-planning:")
for h, kg in plan["hold_kg"].items():
    print(f"  {h:4}: {kg:7.1f} / {aircraft['holds'][h]['max_kg']} kg")
print(f"  Total {plan['final_weight_kg']:.0f} kg (max {aircraft['mzfw_kg']}), CG {plan['final_cg_m']} m "
      f"(limits {aircraft['cg_fwd_limit_m']} to {aircraft['cg_aft_limit_m']}, target {aircraft['cg_target_m']})")
print(f"\nMoved ({len(plan['moved'])}):")
for it in plan["moved"]:
    print(f"  {it['id']:9} {it.get('desc', 'bag'):28} {it['kg']:6.1f} kg  {it['from']} -> {it['to']}")
print(f"Offloaded from a hold ({len(plan['offloaded'])}):")
for it in plan["offloaded"]:
    print(f"  {it['id']:9} {it.get('desc', 'bag'):28} {it['kg']:6.1f} kg  out of {it['current_hold']}")
print(f"Cargo not flying ({len(plan['bumped_cargo'])}):")
for it in plan["bumped_cargo"]:
    print(f"  {it['id']:9} {it['desc']:28} {it['kg']:6.1f} kg  priority {it['priority']}")
print(f"Bags left behind: {len(plan['bags_left_behind'])}")
