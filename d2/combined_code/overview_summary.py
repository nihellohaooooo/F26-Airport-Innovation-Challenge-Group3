"""Combined overview for first-time users: is it safe, what was wrong before,
what has to happen, and what it looks like after. Used by dashboard.py.
Exact numbers stay in the Details and Engine walkthrough tabs."""
import json
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

STATUS = {
    "SAFE":         ("✅", "#1f8a4c", "#e8f5ec", "Safe to load",
                     "All limits and counts check out. Ready for the load controller to approve."),
    "NEEDS REVIEW": ("⚠️", "#b7791f", "#fdf4e3", "Safe, but check before approving",
                     "The plan meets every limit. A person should look at the points below first."),
    "BLOCKED":      ("⛔", "#c53030", "#fdecec", "Blocked: numbers don't match",
                     "Two systems disagree. Fix the mismatch before anything is loaded."),
    "UNSAFE":       ("🚫", "#c53030", "#fdecec", "Unsafe: no safe way to load",
                     "No arrangement meets the aircraft limits. People must decide what to change."),
}

GREEN, AMBER, RED, GREY, BLUE = "#2f9e5b", "#d69e2e", "#d64545", "#a0aec0", "#3b7dd8"

CSS = """
<style>
.ov-status {border-radius: 14px; padding: 1.1rem 1.4rem; margin: .4rem 0 1.2rem 0; border: 2px solid;}
.ov-status h2 {margin: 0; font-size: 1.7rem;}
.ov-status p {margin: .3rem 0 0 0; font-size: 1.05rem;}
.ov-step {font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: #718096; font-weight: 700; margin-top: 1.4rem;}
.ov-card {border: 1px solid #e2e8f0; border-radius: 12px; padding: .8rem 1rem; height: 100%;}
.ov-card .k {font-size: .78rem; color: #718096; text-transform: uppercase; letter-spacing: .06em; font-weight: 600;}
.ov-card .v {font-size: 1.45rem; font-weight: 700; margin-top: .15rem;}
.ov-card .f {font-size: .9rem; margin-top: .15rem;}
.ov-action {border-left: 5px solid; border-radius: 8px; padding: .55rem .9rem; margin: .45rem 0; background: #f7fafc;}
.ov-action b {font-size: 1.02rem;}
.ov-action span {color: #4a5568; font-size: .93rem;}
</style>
"""


# ── data helpers ────────────────────────────────────────────────────────────

def kg(value):
    return f"{value:,.0f} kg"


def before_picture(scenario, result, profile, buffer_pct):
    """The situation before re-planning: what is in each hold right now (only items that will fly),
    and what the aircraft would weigh if every flying item were loaded."""
    holds = {h["hold"]: h for h in profile["holds"]}
    flying_tags = {b["tag"] for b in result["bag_actions"]["classified_bags"]
                   if b.get("tracker_status") in {"ok", "inbound"}}
    loaded = {h: 0.0 for h in holds}
    to_load = 0.0
    for b in scenario["bags"]:
        if b["tag"] not in flying_tags:
            continue
        loc = b.get("location", "")
        if loc.startswith("hold_") and loc[5:] in loaded:
            loaded[loc[5:]] += b["weight_kg"]
        else:
            to_load += b["weight_kg"]
    for c in scenario["cargo"]:
        if c.get("current_hold") in loaded:
            loaded[c["current_hold"]] += c["weight_kg"]
        else:
            to_load += c["weight_kg"]
    k = 1 + buffer_pct / 100
    zones = result["passenger_mapping"]["zone_weights"].values()
    pax_kg = sum(z["weight_kg"] for z in zones) * k
    pax_moment = sum(z["weight_kg"] * z["arm_m"] for z in zones) * k
    dow, dow_arm = profile["dry_operating_weight_kg"], profile["dry_operating_arm_m"]
    fixed = dow + pax_kg
    now_w = fixed + sum(loaded.values())
    now_m = dow * dow_arm + pax_moment + sum(loaded[h] * holds[h]["arm_m"] for h in holds)
    return {
        "holds": holds, "loaded": loaded, "to_load_kg": to_load,
        "fixed_kg": fixed, "all_in_kg": now_w + to_load,
        "cg_now": now_m / now_w, "mzfw": profile["max_zero_fuel_weight_kg"],
    }


def names(scenario):
    return {c["cargo_id"]: c["description"] for c in scenario["cargo"]}


def actions(result, scenario, before):
    """Short, plain to-do list built from the structured results (not the long reason strings)."""
    desc = names(scenario)
    weight = {c["cargo_id"]: c["weight_kg"] for c in scenario["cargo"]}
    over_mzfw = before["all_in_kg"] - before["mzfw"]
    todo = []
    for m in result["moves"]:
        cap = before["holds"][m["from"]]["max_weight_kg"]
        over = before["loaded"][m["from"]] - cap
        why = f"{m['from']} hold is {kg(over)} over its limit" if over > 0 else "keeps the aircraft in balance"
        name = desc.get(m["id"], f"bag {m['id']}")
        todo.append((BLUE, f"Move {name} ({kg(weight.get(m['id'], 0))}) from {m['from']} to {m['to']}", why))
    for c in result["cargo_bumped"]:
        loaded_in = next((o["from"] for o in result.get("offloads", []) if o["id"] == c["cargo_id"]), None)
        why = f"flight would be {kg(over_mzfw)} too heavy" if over_mzfw > 0 else "not enough room in the holds"
        why += f" · priority {c['priority']} of 5, least important goes first"
        if loaded_in:
            todo.append((RED, f"Take {c['description']} ({kg(c['weight_kg'])}) out of {loaded_in}", why))
        else:
            todo.append((AMBER, f"Don't load {c['description']} ({kg(c['weight_kg'])}), leave it on the dock", why))
    bag_offloads = [o for o in result.get("offloads", []) if o["kind"] == "bag"]
    if bag_offloads:
        todo.append((RED, f"Take {len(bag_offloads)} bag(s) out of the holds", "no safe space left for them"))
    pulled = result["bag_actions"]["bags_pulled"]
    if pulled:
        todo.append((GREY, f"Pull {pulled} bags of passengers removed by the DCS",
                     "a bag never flies without its passenger · order in Details"))
    late = result["bag_actions"]["at_risk"]
    if late:
        todo.append((GREY, f"{len(late)} connecting bag(s) arrive after the {result['flight']['loading_cutoff']} cutoff",
                     "they follow on a later flight · tags in Details"))
    return todo


# ── charts ──────────────────────────────────────────────────────────────────

def hold_chart(before, after_loads):
    holds = list(before["holds"])
    caps = [before["holds"][h]["max_weight_kg"] for h in holds]
    b_vals = [before["loaded"][h] for h in holds]
    over = [v > c for v, c in zip(b_vals, caps)]
    fig = go.Figure()
    fig.add_bar(name="Before", x=holds, y=b_vals, showlegend=False,
                marker_color=[RED if o else GREY for o in over],
                text=[kg(v) for v in b_vals], textposition="outside")
    for label, color in [("Before", GREY), ("Before: over the limit", RED)]:   # legend entries only
        fig.add_scatter(name=label, x=[None], y=[None], mode="markers",
                        marker=dict(symbol="square", size=12, color=color))
    if after_loads:
        a_vals = [after_loads[h]["weight_kg"] for h in holds]
        fig.add_bar(name="After re-plan", x=holds, y=a_vals, marker_color=GREEN,
                    text=[kg(v) for v in a_vals], textposition="outside")
    fig.add_scatter(name="Hold limit", x=holds, y=caps, mode="markers",
                    marker=dict(symbol="line-ew", size=90, line=dict(width=3, color="#1a202c")),
                    hovertemplate="%{x} limit: %{y:,.0f} kg<extra></extra>")
    fig.update_layout(barmode="group", height=340, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=1.18), yaxis_title="kg",
                      yaxis_range=[0, max(caps + b_vals) * 1.22])
    return fig


def cg_chart(fwd, aft, target, before_cg, after_cg):
    lo, hi = fwd - 1.2, aft + 1.2
    fig = go.Figure()
    for x0, x1, color in [(lo, fwd, "#fde2e2"), (fwd, aft, "#e3f4e9"), (aft, hi, "#fde2e2")]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=0, y1=1, fillcolor=color, line_width=0, layer="below")
    fig.add_shape(type="line", x0=target, x1=target, y0=0, y1=1, line=dict(color="#4a5568", dash="dash"), layer="below")
    fig.add_annotation(x=target, y=1.0, text=f"ideal {target} m", showarrow=False, yanchor="bottom", font=dict(size=12))
    fig.add_annotation(x=lo + .1, y=.5, text="nose-heavy", showarrow=False, xanchor="left", font=dict(size=12, color=RED))
    fig.add_annotation(x=hi - .1, y=.5, text="tail-heavy", showarrow=False, xanchor="right", font=dict(size=12, color=RED))
    fig.add_annotation(x=fwd, y=0, text=f"limit {fwd} m", showarrow=False, yanchor="top", font=dict(size=11))
    fig.add_annotation(x=aft, y=0, text=f"limit {aft} m", showarrow=False, yanchor="top", font=dict(size=11))
    fig.add_scatter(x=[before_cg], y=[.72], mode="markers+text", marker=dict(size=18, color="#718096", symbol="diamond"),
                    text=[f"before {before_cg:.2f} m"], textposition="middle right" if before_cg > target else "middle left",
                    textfont=dict(size=13), name="before")
    if after_cg is not None:
        fig.add_scatter(x=[after_cg], y=[.3], mode="markers+text", marker=dict(size=20, color=GREEN, symbol="diamond"),
                        text=[f"after {after_cg:.2f} m"], textposition="middle right" if after_cg > target else "middle left",
                        textfont=dict(size=13, color=GREEN), name="after")
    fig.update_layout(height=200, showlegend=False, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis=dict(range=[lo, hi], title="Balance point (CG), metres from the nose", showgrid=False),
                      yaxis=dict(visible=False, range=[-.25, 1.15]), plot_bgcolor="white")
    return fig


def compare_chart(rows):
    """Simple 'needed vs available' bars for UNSAFE explanations."""
    fig = go.Figure()
    fig.add_bar(y=[r[0] for r in rows], x=[r[1] for r in rows], orientation="h",
                marker_color=[r[2] for r in rows], text=[kg(r[1]) for r in rows], textposition="outside")
    fig.update_layout(height=80 + 55 * len(rows), margin=dict(l=10, r=40, t=10, b=10),
                      xaxis=dict(range=[0, max(r[1] for r in rows) * 1.25], title="kg"))
    return fig


# ── page sections ───────────────────────────────────────────────────────────

def card(col, label, value, foot, color="#1a202c"):
    col.markdown(f'<div class="ov-card"><div class="k">{label}</div><div class="v" style="color:{color}">{value}</div>'
                 f'<div class="f">{foot}</div></div>', unsafe_allow_html=True)


def status_box(result):
    icon, color, tint, title, line = STATUS.get(result["status"], ("ℹ️", BLUE, "#ebf4ff", result["status"], ""))
    st.markdown(f'<div class="ov-status" style="border-color:{color};background:{tint}">'
                f'<h2 style="color:{color}">{icon} {title}</h2><p>{line}</p></div>', unsafe_allow_html=True)


def review_points(result):
    """Plain versions of the Safety Gate's warnings (same rules, so the page never disagrees with it)."""
    pts = []
    m = result.get("metrics") or {}
    for c in result.get("checks", []):
        if c["name"] == "ZFW margin" and c.get("warning") and m:
            pts.append(f"Weight margin is thin: only {kg(m['zfw_margin_kg'])} left under the maximum "
                       f"({m['zfw_margin_kg'] / m['max_zfw_kg'] * 100:.1f}%; review below 1%).")
        elif c["name"] == "CG margin" and c.get("warning") and m:
            gap = min(m["cg_m"] - m["cg_forward_limit_m"], m["cg_aft_limit_m"] - m["cg_m"])
            pts.append(f"Balance is close to a limit: {gap:.2f} m away (review below 0.2 m).")
        elif c["name"] == "bags left behind" and c.get("warning"):
            pts.append(f"{len(result['bag_actions']['at_risk'])} connecting bag(s) arrive after loading closes "
                       f"and will miss this flight.")
        elif not c["passed"] and c["name"] not in {"passenger count", "bag count and accounting"}:
            pts.append(f"Failed check: {c['name']} ({c['detail']}).")
    return pts


def unsafe_explainer(scenario, before):
    must = [c for c in scenario["cargo"] if c.get("must_fly")]
    room = before["mzfw"] - before["fixed_kg"]
    st.markdown('<div class="ov-step">Why there is no safe plan</div>', unsafe_allow_html=True)
    if before["fixed_kg"] > before["mzfw"]:
        st.markdown(f"**The aircraft with its passengers is already too heavy**, before any bag or cargo: "
                    f"{kg(before['fixed_kg'] - before['mzfw'])} over the maximum.")
        st.plotly_chart(compare_chart([("Aircraft + passengers", before["fixed_kg"], RED),
                                       ("Maximum allowed", before["mzfw"], GREEN)]), width="stretch")
    elif must:
        total = sum(c["weight_kg"] for c in must)
        biggest = max(h["max_weight_kg"] for h in before["holds"].values())
        heaviest = max(c["weight_kg"] for c in must)
        st.markdown(f"**{len(must)} items are marked must-fly** (they may not be left behind). "
                    f"Together they weigh **{total / 1000:,.0f} tonnes**, but the aircraft has room for only "
                    f"**{room / 1000:,.1f} tonnes** more. One item alone ({kg(heaviest)}) is also heavier than "
                    f"the biggest hold allows ({kg(biggest)}).")
        st.plotly_chart(compare_chart([("Must-fly cargo", total, RED),
                                       ("Room left on the aircraft", max(room, 0), GREEN)]), width="stretch")
    st.info("**What happens next:** the system will not bend a safety limit, so nothing is loaded yet.\n"
            "1. Load control escalates to operations / cargo, who decide: split the shipment, send it on a freighter, "
            "or remove the must-fly flag.\n"
            "2. The updated cargo or passenger list comes back (from the cargo system or the DCS).\n"
            "3. Re-plan with the new list, and the plan goes to the load controller as usual.")


def blocked_explainer(result):
    cc = result["count_check"]
    st.markdown('<div class="ov-step">Why it is blocked</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    p = cc["passengers"]
    card(c1, "Passengers in our plan", p["planned"], "from the seat map")
    card(c2, "Passengers per DCS", p["dcs_boarding"], "from the airline system",
         RED if p["planned"] != p["dcs_boarding"] else "#1a202c")
    card(c3, "Difference", abs(p["planned"] - p["dcs_boarding"]), "must be 0 before loading",
         RED if p["planned"] != p["dcs_boarding"] else GREEN)
    st.info("**What happens next:** check the passenger list with the gate / DCS, fix the count, then re-plan. "
            "The loading plan below is shown for reference only.")


def flight_glance(scenario, result, before):
    """Who and what is on this flight, before any re-planning."""
    f = result["flight"]
    pax = scenario.get("passengers", [])
    removed = sum(str(p.get("removed_by_dcs")).lower() == "true" for p in pax)
    seats = result["passenger_mapping"].get("seat_capacity")
    tc = result["bag_actions"]["tracker_count_check"]          # always present, even with no plan
    counts = tc["counts"]
    cargo = scenario.get("cargo", [])
    st.markdown('<div class="ov-step">The flight at a glance</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    card(c1, "Aircraft swap", f"{f['old_aircraft'].replace('ceo', '')} → {f['new_aircraft'].replace('ceo', '')}",
         f"{f['flight_no']} {f['origin']} → {f['destination']} · departs {f['scheduled_departure']}")
    card(c2, "Passengers", f"{len(pax) - removed} flying",
         f"{len(pax)} booked · {removed} removed by DCS · {seats} seats")
    card(c3, "Checked bags", f"{counts['flying']} flying",
         f"{tc['total_known']} checked · {counts['pulled']} pulled · {counts['left_behind']} miss the flight")
    card(c4, "Cargo", f"{len(cargo)} items", f"{kg(sum(c['weight_kg'] for c in cargo))} in total")
    st.caption("Passenger weights use Transport Canada standard weights, which already include clothing and carry-on bags. "
               f"Loading closes {f['loading_cutoff']}.")


def aircraft_check(result, profile):
    """Guards against the classic swap error: a plan calculated for the wrong aircraft type."""
    f = result["flight"]
    planned_for = result.get("aircraft")
    assigned = f["new_aircraft"]
    per_row = profile.get("seats_per_row", 0)
    seats_profile = profile.get("rows", 0) * (len(per_row) if isinstance(per_row, (list, tuple)) else per_row)
    seats_map = result["passenger_mapping"].get("seat_capacity")
    problems = []
    if planned_for != assigned:
        problems.append(f"plan was calculated for {planned_for}, but {f['flight_no']} is assigned {assigned}")
    if profile.get("type") != assigned:
        problems.append(f"aircraft data loaded is {profile.get('type')}, not {assigned}")
    if seats_profile and seats_map and seats_profile != seats_map:
        problems.append(f"seat map has {seats_map} seats, {assigned} data says {seats_profile}")
    if problems:
        st.error("✈️ **Aircraft check failed:** " + "; ".join(problems) + ". Do not use this plan.")
    else:
        st.success(f"✈️ **Aircraft check:** plan calculated for **{planned_for}**, the aircraft now assigned to "
                   f"{f['flight_no']} (was {f['old_aircraft']}). Limits, holds and {seats_map} seats all come from "
                   f"the {assigned} data.")
    return not problems


def ramp_instructions(scenario, result):
    """Loading instructions in the shape a ramp crew works from: per hold, then the pull list and late bags."""
    if not result["hold_assignments"]["cargo"] and not result["hold_assignments"]["bags"]:
        return
    desc = names(scenario)
    cargo = {c["cargo_id"]: c for c in scenario["cargo"]}
    bag_w = {b["tag"]: b["weight_kg"] for b in scenario["bags"]}
    bag_from = {b["tag"]: b.get("location", "") for b in scenario["bags"]}
    moved = {m["id"]: m["from"] for m in result["moves"]}
    with st.expander("📋 Loading instructions for the ramp (per hold, pull list, late bags)"):
        holds = list((result.get("metrics") or {}).get("hold_loads", {})) or \
            sorted(set(result["hold_assignments"]["cargo"].values()) | set(result["hold_assignments"]["bags"].values()))
        rows = []
        for h in holds:
            for cid, hold in result["hold_assignments"]["cargo"].items():
                if hold == h:
                    action = (f"MOVE IN from {moved[cid]}" if cid in moved
                              else "stays" if cargo[cid].get("current_hold") == h else "load")
                    rows.append({"Hold": h, "Item": f"{cid} {desc.get(cid, '')}", "kg": round(cargo[cid]["weight_kg"]),
                                 "Action": action})
            tags = [t for t, hold in result["hold_assignments"]["bags"].items() if hold == h]
            already = sum(1 for t in tags if bag_from.get(t) == f"hold_{h}")
            rows.append({"Hold": h, "Item": f"{len(tags)} bags", "kg": round(sum(bag_w.get(t, 0) for t in tags)),
                         "Action": f"{already} already in, {len(tags) - already} to load"})
        for o in result.get("offloads", []):
            rows.append({"Hold": o["from"], "Item": f"{o['id']} {desc.get(o['id'], 'bag')}", "kg": round(o["weight_kg"]),
                         "Action": "TAKE OUT"})
        st.markdown("**Where everything goes** (changes in capitals)")
        st.dataframe(rows, hide_index=True, width="stretch", height=36 * (len(rows) + 1) + 4)
        ab = result["bag_actions"]
        left, right = st.columns([3, 2])
        left.markdown(f"**Pull list: {len(ab['pull_list'])} bags, in this order**")
        left.dataframe([{"Step": i, "Bag tag": b["tag"], "Where": b["location"].replace("_", " "), "Owner": b.get("owner")}
                        for i, b in enumerate(ab["pull_list"], 1)], hide_index=True, width="stretch", height=250)
        right.markdown(f"**Arriving after loading closes: {len(ab['at_risk'])}**")
        if ab["at_risk"]:
            right.dataframe([{"Bag tag": b["tag"], "Arrives": b.get("eta"), "On flight": b.get("inbound_flight")}
                             for b in ab["at_risk"]], hide_index=True, width="stretch")
        else:
            right.write("None. All connecting bags arrive in time.")


def _plan_key(result):
    """Identifies this exact plan, so an approval never carries over to a different one."""
    m = result.get("metrics") or {}
    return (result["scenario_id"], result["status"], m.get("total_weight_kg"), m.get("cg_m"),
            tuple(sorted(result["hold_assignments"]["cargo"].items())), len(result["hold_assignments"]["bags"]))


def sign_off(result, step="4"):
    """Load controller approval. Kept for this browser session as a simple audit log."""
    st.markdown(f'<div class="ov-step">{step} · Load controller sign-off</div>', unsafe_allow_html=True)
    log = st.session_state.setdefault("approval_log", [])
    key = _plan_key(result)
    done = next((a for a in log if a["key"] == key), None)
    if result["status"] in {"BLOCKED", "UNSAFE"}:
        st.warning("This plan cannot be approved while it is " + result["status"] + ". Fix the issue above and re-plan.")
    elif done:
        st.success(f"✅ Approved by **{done['by']}** at {done['at']}. Any change to the plan needs a new approval.")
    else:
        with st.form("approve_form", border=True):
            name = st.text_input("Load controller name")
            checked = True
            if result["status"] == "NEEDS REVIEW":
                checked = st.checkbox("I have checked the points marked “Check before approving”.")
            submit = st.form_submit_button("Approve plan", type="primary")
        if submit:
            if not name.strip():
                st.error("Enter your name to approve.")
            elif not checked:
                st.error("Tick the box to confirm you checked the review points.")
            else:
                log.append({"key": key, "by": name.strip(), "at": datetime.now().strftime("%H:%M:%S"),
                            "flight": result["flight"]["flight_no"], "status": result["status"],
                            "weight": (result.get("metrics") or {}).get("total_weight_kg"),
                            "cg": (result.get("metrics") or {}).get("cg_m")})
                st.rerun()
    if log:
        with st.expander(f"Approval log ({len(log)})"):
            st.dataframe([{"Time": a["at"], "Load controller": a["by"], "Flight": a["flight"], "Status": a["status"],
                           "ZFW (kg)": a["weight"], "CG (m)": a["cg"]} for a in log], hide_index=True, width="stretch")
            st.caption("Kept for this session only. A real system would store it permanently.")


def summary_tab(scenario, result, profile, buffer_pct):
    status_box(result)
    aircraft_check(result, profile)
    before = before_picture(scenario, result, profile, buffer_pct)
    metrics = result.get("metrics")
    pts = review_points(result)
    if result["status"] == "NEEDS REVIEW" and pts:
        st.markdown("**Check before approving:**\n" + "\n".join(f"- {p}" for p in pts))
    flight_glance(scenario, result, before)
    if result["status"] == "UNSAFE":
        unsafe_explainer(scenario, before)
    if result["status"] == "BLOCKED":
        blocked_explainer(result)

    # 1. Before
    st.markdown('<div class="ov-step">1 · The problem (before re-planning)</div>', unsafe_allow_html=True)
    over_holds = {h: v - before["holds"][h]["max_weight_kg"] for h, v in before["loaded"].items()
                  if v > before["holds"][h]["max_weight_kg"]}
    c1, c2, c3 = st.columns(3)
    if over_holds:
        h, o = max(over_holds.items(), key=lambda x: x[1])
        card(c1, "Holds", f"{h} {kg(o)} over", "loaded for the bigger aircraft", RED)
    else:
        card(c1, "Holds", "Within limits", "for what is loaded so far", GREEN)
    over = before["all_in_kg"] - before["mzfw"]
    card(c2, "Weight if everything is loaded", kg(before["all_in_kg"]),
         (f"{kg(over)} over the {kg(before['mzfw'])} maximum" if over > 0 else f"under the {kg(before['mzfw'])} maximum"),
         RED if over > 0 else GREEN)
    inside = profile["cg_forward_limit_m"] <= before["cg_now"] <= profile["cg_aft_limit_m"]
    card(c3, "Balance (CG) right now", f"{before['cg_now']:.2f} m",
         "inside the safe range" if inside else "outside the safe range", GREEN if inside else RED)

    # 2. What to do
    st.markdown('<div class="ov-step">2 · What has to happen</div>', unsafe_allow_html=True)
    if result["status"] == "UNSAFE":
        st.markdown("Nothing should be loaded until a person has decided what to change.")
    else:
        todo = actions(result, scenario, before)
        jobs = result.get("handling_actions") or {}
        if jobs:
            st.caption(f"Extra handling jobs caused by the re-plan: **{jobs.get('total', 0)}** "
                       f"({jobs.get('moves', 0)} moved, {jobs.get('offloads', 0)} taken out). Everything else stays where it is.")
        for color, what, why in todo:
            st.markdown(f'<div class="ov-action" style="border-color:{color}"><b>{what}</b><br><span>{why}</span></div>',
                        unsafe_allow_html=True)

    # 3. After
    if result["status"] == "UNSAFE":
        sign_off(result, step="3")
        glossary()
        return
    st.markdown('<div class="ov-step">3 · Before and after</div>', unsafe_allow_html=True)
    after_loads = metrics["hold_loads"] if metrics else None
    st.plotly_chart(hold_chart(before, after_loads), width="stretch")
    st.plotly_chart(cg_chart(profile["cg_forward_limit_m"], profile["cg_aft_limit_m"], profile["cg_target_m"],
                             before["cg_now"], metrics["cg_m"] if metrics else None), width="stretch")
    if metrics:
        c1, c2, c3 = st.columns(3)
        pct = metrics["zfw_margin_kg"] / metrics["max_zfw_kg"] * 100
        card(c1, "Final weight", kg(metrics["total_weight_kg"]),
             f"margin {kg(metrics['zfw_margin_kg'])} ({pct:.1f}%) under the {kg(metrics['max_zfw_kg'])} maximum",
             RED if metrics["zfw_margin_kg"] < 0 else (AMBER if pct < 1 else GREEN))
        ok_cg = metrics["cg_forward_limit_m"] <= metrics["cg_m"] <= metrics["cg_aft_limit_m"]
        gap = min(metrics["cg_m"] - metrics["cg_forward_limit_m"], metrics["cg_aft_limit_m"] - metrics["cg_m"])
        card(c2, "Final balance (CG)", f"{metrics['cg_m']:.2f} m",
             f"inside the safe range · {gap:.2f} m from the nearest limit" if ok_cg else "outside the safe range",
             RED if not ok_cg else (AMBER if gap < 0.2 else GREEN))
        ab = result["bag_actions"]
        card(c3, "Bags", f"{ab['bags_loaded']} flying",
             f"{ab['bags_pulled']} pulled · {len(ab['bags_left_behind'])} miss the flight")
    st.write("")
    ramp_instructions(scenario, result)
    sign_off(result)
    glossary()


def glossary():
    with st.expander("What do these words mean?"):
        st.markdown("- **Hold:** cargo compartment under the cabin floor: FWD (front), AFT (rear), BULK (very back).\n"
                    "- **Weight limit (MZFW):** the most the aircraft may weigh without fuel. "
                    "**Margin** is how much is left; under 1% is flagged for review.\n"
                    "- **Balance (CG, centre of gravity):** the balance point, in metres from the nose. "
                    "It must stay inside the safe range (flagged if within 0.2 m of a limit); the ideal point saves fuel.\n"
                    "- **Passenger weight:** Transport Canada standard weights (summer/winter), "
                    "including clothing and carry-on bags.\n"
                    "- **Pulled bag:** taken off because its passenger was removed by the DCS.\n"
                    "- **DCS:** the airline's departure control system, which decides who flies.")


def render_overview(scenario, result, settings):
    """Entry point called by dashboard.py."""
    st.markdown(CSS, unsafe_allow_html=True)
    profiles = json.loads((DATA_DIR / "aircraft_profiles.json").read_text(encoding="utf-8"))
    profile = profiles[result["flight"]["new_aircraft"]]
    summary_tab(scenario, result, profile, settings.get("safety_buffer_pct", 0) or 0)
