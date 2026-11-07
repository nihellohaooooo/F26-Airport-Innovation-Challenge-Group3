"""Streamlit visual dashboard for the combined aircraft swap pipeline."""
import json
from pathlib import Path

import streamlit as st

from pipeline import DATA_DIR, run_scenario


SCENARIO_DIR = DATA_DIR / "scenarios"
STATUS_EMOJI = {"SAFE": "✅", "NEEDS REVIEW": "🟠", "BLOCKED": "⛔", "UNSAFE": "🚫"}


def _scenario_files():
    return sorted(SCENARIO_DIR.glob("*.json"))


def _status_banner(result):
    status = result["status"]
    title = f"{STATUS_EMOJI.get(status, 'ℹ️')} {status}"
    reasons = result.get("reasons", [])
    if status == "SAFE":
        st.success(title)
    elif status == "NEEDS REVIEW":
        st.warning(title)
    else:
        st.error(title)
    if reasons:
        for reason in reasons:
            st.markdown(f"- {reason}")


def _cg_gauge(metrics):
    fwd = metrics["cg_forward_limit_m"]
    aft = metrics["cg_aft_limit_m"]
    target = metrics["cg_target_m"]
    cg = metrics["cg_m"]
    fraction = min(1.0, max(0.0, (cg - fwd) / (aft - fwd)))
    target_fraction = min(1.0, max(0.0, (target - fwd) / (aft - fwd)))
    st.markdown(
        f"""<div style="position:relative;margin:22px 4px 8px;height:18px;background:#e6edf4;
        border-radius:10px;border:1px solid #b7c4d1">
        <div style="position:absolute;left:{target_fraction*100:.2f}%;top:-8px;height:32px;border-left:2px dashed #34495e"></div>
        <div style="position:absolute;left:calc({fraction*100:.2f}% - 8px);top:-5px;width:16px;height:26px;
        background:#1769aa;border:2px solid white;border-radius:8px;box-shadow:0 1px 4px #566"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#556575">
        <span>Forward {fwd:.2f} m</span><span>Target {target:.2f} m</span><span>Aft {aft:.2f} m</span></div>
        <div style="text-align:center;font-weight:650;margin-top:4px">Plan CG: {cg:.3f} m</div>""",
        unsafe_allow_html=True,
    )


def _render_count_check(check):
    st.subheader("Count checks")
    passengers = check.get("passengers", {})
    bags = check.get("bags", {})
    cols = st.columns(4)
    cols[0].metric("Passengers", f"{passengers.get('planned', '—')} / {passengers.get('dcs_boarding', '—')}")
    cols[1].metric("Bags loaded", bags.get("loaded", "—"))
    cols[2].metric("Bags pulled", bags.get("pulled", "—"))
    cols[3].metric("Left behind", bags.get("left_behind", "—"))
    if check.get("final_plan_verified"):
        if check.get("ok"):
            st.success("Final passenger and bag counts reconcile.")
        else:
            st.error("Final count mismatch; review the Safety Gate checks.")
    else:
        st.info("No final load plan was available; these are the pre-plan manifest counts.")


def _render_plan(result):
    mapping = result["passenger_mapping"]
    bags = result["bag_actions"]
    st.subheader("Passenger mapping")
    st.caption(f"{mapping['passenger_count_mapped']} mapped / {mapping['seat_capacity']} available seats · {len(mapping['doesnt_fit'])} don't fit")
    zone_rows = [{"Zone": name, "Passengers": item["passenger_count"],
                  "Weight (kg)": item["weight_kg"], "Arm (m)": item["arm_m"]}
                 for name, item in mapping["zone_weights"].items()]
    st.dataframe(zone_rows, hide_index=True, width="stretch")
    if mapping["doesnt_fit"]:
        st.dataframe([{"Passenger": p.get("pax_id"), "Seat": p.get("seat"),
                       "Reason": p.get("doesnt_fit_reason")} for p in mapping["doesnt_fit"]],
                     hide_index=True, width="stretch")

    st.subheader("Bag actions")
    pull_tab, risk_tab, bag_count_tab = st.tabs([f"Pull list ({len(bags['pull_list'])})",
                                               f"At risk ({len(bags['at_risk'])})", "Tracker count check"])
    with pull_tab:
        if bags["pull_list"]:
            st.dataframe([{"Step": i, "Tag": b["tag"], "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Location": b.get("location"), "Stack": b.get("stack_pos"),
                           "Action": b.get("pull_reason")} for i, b in enumerate(bags["pull_list"], 1)],
                         hide_index=True, width="stretch")
        else:
            st.write("No bags to pull.")
    with risk_tab:
        if bags["at_risk"]:
            st.dataframe([{"Tag": b["tag"], "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Inbound flight": b.get("inbound_flight", ""), "ETA": b.get("eta"),
                           "Action": b.get("pull_reason")} for b in bags["at_risk"]],
                         hide_index=True, width="stretch")
        else:
            st.write("No connecting bags at risk.")
    with bag_count_tab:
        st.json(bags["tracker_count_check"])

    st.subheader("Hold loading")
    loads = result["hold_assignments"].get("loads", {})
    if loads:
        for hold, load in loads.items():
            limit = result["safety_gate"]["metrics"].get("hold_limits", {}).get(hold, {}).get("max_weight_kg")
            if not limit:
                limit = load["weight_kg"] or 1
            pct = min(1.0, load["weight_kg"] / float(limit))
            st.markdown(f"**{hold}** · {load['weight_kg']:.1f} / {float(limit):.1f} kg · {load['volume_m3']:.2f} m³")
            st.progress(pct)
        with st.expander("Item-to-hold assignments"):
            st.markdown("**Bags**")
            st.dataframe([{"Bag": tag, "Hold": hold} for tag, hold in result["hold_assignments"]["bags"].items()],
                         hide_index=True, width="stretch")
            st.markdown("**Cargo**")
            st.dataframe([{"Cargo": tag, "Hold": hold} for tag, hold in result["hold_assignments"]["cargo"].items()],
                         hide_index=True, width="stretch")
    else:
        st.info("No assignments: the optimizer did not find a feasible plan.")

    left, right = st.columns(2)
    with left:
        st.subheader(f"Moves ({len(result['moves'])})")
        st.dataframe(result["moves"], hide_index=True, width="stretch")
    with right:
        st.subheader(f"Cargo bumped ({len(result['cargo_bumped'])})")
        st.dataframe(result["cargo_bumped"], hide_index=True, width="stretch")

    _render_count_check(result["count_check"])
    with st.expander("Safety Gate checks"):
        st.dataframe(result.get("checks", []), hide_index=True, width="stretch")


def main():
    st.set_page_config(page_title="Aircraft Swap Re-planner", page_icon="✈️", layout="wide")
    st.title("Aircraft Swap Re-planner")
    st.caption("Scenario-based planning demo · illustrative aircraft profiles · qualified load-controller review required")
    scenarios = _scenario_files()
    if not scenarios:
        st.error(f"No scenario JSON files found in {SCENARIO_DIR}")
        return
    lookup = {p.stem: p for p in scenarios}
    names = list(lookup)
    default = names.index("a320_winter_swap") if "a320_winter_swap" in names else 0
    with st.sidebar:
        st.header("Re-plan controls")
        selected = st.selectbox("Scenario", names, index=default,
                                format_func=lambda n: json.loads(lookup[n].read_text()).get("name", n))
        season = st.selectbox("Passenger season", ["winter", "summer"], index=0)
        buffer_pct = st.selectbox("Passenger weight buffer", [0, 5], index=0,
                                  format_func=lambda v: f"{v}%")
        lightning = st.checkbox("Lightning mode")
        run = st.button("Re-plan", type="primary", width="stretch")
    settings = {"season": season, "safety_buffer_pct": buffer_pct, "lightning_mode": lightning}
    cache_key = (selected, tuple(sorted(settings.items())))
    if run or st.session_state.get("result_key") != cache_key:
        with st.spinner("Solving the selected scenario…"):
            st.session_state["result"] = run_scenario(lookup[selected], options=settings)
            st.session_state["result_key"] = cache_key
    result = st.session_state["result"]
    _status_banner(result)
    metrics = result.get("metrics")
    if metrics:
        cols = st.columns(4)
        cols[0].metric("Replacement aircraft", result["aircraft"])
        cols[1].metric("Passengers mapped", f"{result['passenger_mapping']['passenger_count_mapped']} / {result['passenger_mapping']['seat_capacity']}")
        cols[2].metric("Zero-fuel weight", f"{metrics['total_weight_kg']:,.1f} kg",
                       delta=f"{metrics['zfw_margin_kg']:,.1f} kg margin", delta_color="normal")
        cols[3].metric("Centre of gravity", f"{metrics['cg_m']:.3f} m")
        cg_col, detail_col = st.columns([1, 1])
        with cg_col:
            st.subheader("CG envelope")
            _cg_gauge(metrics)
        with detail_col:
            st.subheader("Final load summary")
            st.write(f"ZFW limit: **{metrics['max_zfw_kg']:,.1f} kg**")
            st.write(f"CG target: **{metrics['cg_target_m']:.2f} m**")
            st.write(f"Bag weight: **{metrics['bag_weight_kg']:,.1f} kg** · Cargo weight: **{metrics['cargo_weight_kg']:,.1f} kg**")
    else:
        st.info("Final weight and CG are unavailable because the optimizer found no feasible plan.")
    st.divider()
    _render_plan(result)


if __name__ == "__main__":
    main()
