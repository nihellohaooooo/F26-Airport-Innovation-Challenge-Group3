"""Streamlit visual dashboard for the combined aircraft swap pipeline."""
import json
from html import escape

import plotly.graph_objects as go
import streamlit as st

from pipeline import DATA_DIR, run_scenario


SCENARIO_DIR = DATA_DIR / "scenarios"
RESULT_VIEW_REVISION = 2

# ── Design tokens ───────────────────────────────────────────────────────────
# Status colours are reserved for state (always paired with an icon + label);
# the accent/series colours carry identity only.
STATUS = {
    "SAFE":         {"icon": "✅", "color": "#0ca30c", "tint": "rgba(12,163,12,0.10)",  "label": "Plan cleared by Safety Gate"},
    "NEEDS REVIEW": {"icon": "🟠", "color": "#ec835a", "tint": "rgba(236,131,90,0.12)", "label": "Load controller review required"},
    "BLOCKED":      {"icon": "⛔", "color": "#d03b3b", "tint": "rgba(208,59,59,0.10)",  "label": "Plan blocked — cannot proceed"},
    "UNSAFE":       {"icon": "🚫", "color": "#d03b3b", "tint": "rgba(208,59,59,0.10)",  "label": "Plan unsafe — do not dispatch"},
}
STATUS_DEFAULT = {"icon": "ℹ️", "color": "#2a78d6", "tint": "rgba(42,120,214,0.10)", "label": ""}
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
ACCENT = "#2a78d6"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
MUTED = "rgba(128,128,128,0.55)"
GRID = "rgba(128,128,128,0.18)"
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}

CSS = """
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px;}
h1, h2, h3 {letter-spacing: -0.01em;}
div[data-testid="stSidebar"] h2 {font-size: 1.05rem;}

.hero {display:flex; align-items:center; justify-content:space-between; gap:1rem;
       padding: 1.1rem 1.4rem; border-radius: 14px; margin-bottom: 1rem;
       background: linear-gradient(120deg, #0f2a47 0%, #1a4a7a 55%, #2a78d6 100%); color: #fff;}
.hero h1 {color:#fff; margin:0; font-size:1.6rem; line-height:1.2; padding:0;}
.hero .sub {opacity:.82; font-size:.86rem; margin-top:.25rem;}
.hero .chip {background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25);
             padding:.35rem .75rem; border-radius:999px; font-size:.82rem; white-space:nowrap;}

.status {border-radius: 12px; padding: .9rem 1.2rem; margin: .2rem 0 1.1rem;
         border: 1px solid; border-left-width: 6px;}
.status .head {display:flex; align-items:baseline; gap:.6rem; flex-wrap:wrap;}
.status .title {font-weight:750; font-size:1.15rem; letter-spacing:.02em;}
.status .label {opacity:.75; font-size:.9rem;}
.status ul {margin:.45rem 0 0 1.1rem; padding:0; font-size:.9rem;}
.status li {margin:.1rem 0;}

.kpi-grid {display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:.8rem; margin-bottom:.4rem;}
@media (max-width: 900px) {.kpi-grid {grid-template-columns: repeat(2, minmax(0,1fr));}}
.kpi {border:1px solid rgba(128,128,128,.22); border-radius:12px; padding:.85rem 1rem;
      background: rgba(128,128,128,.04);}
.kpi .k-label {font-size:.74rem; text-transform:uppercase; letter-spacing:.07em; opacity:.65; font-weight:600;}
.kpi .k-value {font-size:1.55rem; font-weight:700; margin-top:.15rem; line-height:1.25;
               font-variant-numeric: tabular-nums;}
.kpi .k-unit {font-size:.85rem; font-weight:500; opacity:.6; margin-left:.2rem;}
.kpi .k-foot {font-size:.8rem; opacity:.75; margin-top:.2rem;}
.kpi .bar {height:6px; border-radius:4px; background:rgba(128,128,128,.18); margin-top:.5rem; overflow:hidden;}
.kpi .bar > span {display:block; height:100%; border-radius:4px;}

.section-title {font-size:1.05rem; font-weight:700; margin:.2rem 0 .1rem;}
.section-cap {font-size:.82rem; opacity:.65; margin-bottom:.3rem;}

.pill {display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.78rem; font-weight:600;
       border:1px solid; margin-right:.3rem;}
.tracker-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.8rem 0;}
@media (max-width: 800px) {.tracker-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
.tracker-card {border:1px solid rgba(128,128,128,.2);border-top:4px solid;border-radius:10px;
               padding:.75rem .9rem;background:rgba(128,128,128,.035);}
.tracker-card .label {font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;opacity:.68;font-weight:650;}
.tracker-card .value {font-size:1.6rem;font-weight:750;line-height:1.25;margin-top:.12rem;font-variant-numeric:tabular-nums;}
.tracker-card .note {font-size:.76rem;opacity:.72;margin-top:.12rem;}
.tracker-bar {height:18px;display:flex;overflow:hidden;border-radius:9px;background:rgba(128,128,128,.12);margin:.7rem 0 .35rem;}
.tracker-bar span {height:100%;min-width:0;}
.tracker-legend {display:flex;gap:1rem;flex-wrap:wrap;font-size:.78rem;opacity:.78;}
</style>
"""


# ── Helpers ─────────────────────────────────────────────────────────────────
def _scenario_files():
    return sorted(SCENARIO_DIR.glob("*.json"))


def _scenario_name(path):
    try:
        return json.loads(path.read_text()).get("name", path.stem)
    except (OSError, json.JSONDecodeError):
        return path.stem


def _fmt(value, spec=",.1f", default="—"):
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return default


def _section(title, caption=None):
    st.markdown(f'<div class="section-title">{escape(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="section-cap">{escape(caption)}</div>', unsafe_allow_html=True)


def _base_layout(fig, height, **kwargs):
    kwargs.setdefault("margin", dict(l=8, r=8, t=8, b=8))
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
        showlegend=False,
        hoverlabel=dict(font_size=12),
        bargap=0.35,
        **kwargs,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def _plot(fig):
    st.plotly_chart(fig, config=PLOT_CONFIG, theme="streamlit", width="stretch")


def _util_color(fraction):
    if fraction > 1.0:
        return CRIT
    if fraction >= 0.9:
        return WARN
    return GOOD


# ── Header & status ─────────────────────────────────────────────────────────
def _hero(scenario_label, settings):
    chips = f"{settings['season'].title()} weights · +{settings['safety_buffer_pct']}% buffer"
    if settings["lightning_mode"]:
        chips += " · ⚡ Lightning"
    st.markdown(
        f"""<div class="hero"><div>
        <h1>✈️ Aircraft Swap Re-planner</h1>
        <div class="sub">{escape(scenario_label)} · illustrative aircraft profiles ·
        qualified load-controller review required</div></div>
        <div class="chip">{escape(chips)}</div></div>""",
        unsafe_allow_html=True,
    )


def _status_banner(result):
    status = result["status"]
    style = STATUS.get(status, STATUS_DEFAULT)
    reasons = result.get("reasons", [])
    items = "".join(f"<li>{escape(str(r))}</li>" for r in reasons)
    st.markdown(
        f"""<div class="status" style="background:{style['tint']};border-color:{style['color']}">
        <div class="head"><span class="title" style="color:{style['color']}">{style['icon']} {escape(status)}</span>
        <span class="label">{escape(style['label'])}</span></div>
        {f'<ul>{items}</ul>' if items else ''}</div>""",
        unsafe_allow_html=True,
    )


def _kpi(label, value, unit="", foot="", bar=None):
    bar_html = ""
    if bar is not None:
        frac, color = bar
        bar_html = f'<div class="bar"><span style="width:{min(1.0, max(0.0, frac))*100:.1f}%;background:{color}"></span></div>'
    unit_html = f'<span class="k-unit">{escape(unit)}</span>' if unit else ""
    return (f'<div class="kpi"><div class="k-label">{escape(label)}</div>'
            f'<div class="k-value">{escape(str(value))}{unit_html}</div>{bar_html}'
            f'<div class="k-foot">{foot}</div></div>')


def _kpi_row(result, metrics):
    mapping = result["passenger_mapping"]
    mapped, capacity = mapping["passenger_count_mapped"], mapping["seat_capacity"]
    dnf = len(mapping["doesnt_fit"])
    pax_frac = mapped / capacity if capacity else 0
    pax_foot = f"{dnf} don't fit" if dnf else "All passengers seated"

    zfw, max_zfw, margin = metrics["total_weight_kg"], metrics["max_zfw_kg"], metrics["zfw_margin_kg"]
    zfw_frac = zfw / max_zfw if max_zfw else 0
    margin_color = GOOD if margin >= 0 else CRIT
    zfw_foot = (f'<span style="color:{margin_color};font-weight:600">'
                f'{"▲" if margin >= 0 else "▼"} {_fmt(abs(margin))} kg</span> '
                f'{"under" if margin >= 0 else "over"} {_fmt(max_zfw, ",.0f")} kg limit')

    cg, fwd, aft, target = metrics["cg_m"], metrics["cg_forward_limit_m"], metrics["cg_aft_limit_m"], metrics["cg_target_m"]
    in_env = fwd <= cg <= aft
    cg_foot = (f'<span style="color:{GOOD if in_env else CRIT};font-weight:600">'
               f'{"✓ Within envelope" if in_env else "✗ Outside envelope"}</span> · '
               f'{cg - target:+.3f} m vs target')

    st.markdown(
        '<div class="kpi-grid">'
        + _kpi("Replacement aircraft", result["aircraft"], foot="Swap target")
        + _kpi("Passengers mapped", f"{mapped} / {capacity}", foot=pax_foot,
               bar=(pax_frac, ACCENT))
        + _kpi("Zero-fuel weight", _fmt(zfw), "kg", zfw_foot, bar=(zfw_frac, _util_color(zfw_frac)))
        + _kpi("Centre of gravity", f"{cg:.3f}", "m", cg_foot)
        + "</div>",
        unsafe_allow_html=True,
    )


# ── Charts ──────────────────────────────────────────────────────────────────
def _cg_chart(metrics):
    fwd, aft = metrics["cg_forward_limit_m"], metrics["cg_aft_limit_m"]
    target, cg = metrics["cg_target_m"], metrics["cg_m"]
    span = aft - fwd
    pad = span * 0.25 if span else 1.0
    lo, hi = min(fwd, cg) - pad, max(aft, cg) + pad
    in_env = fwd <= cg <= aft

    fig = go.Figure()
    # Out-of-envelope zones, then the allowed envelope band.
    fig.add_shape(type="rect", x0=lo, x1=fwd, y0=0.3, y1=0.7, line_width=0,
                  fillcolor="rgba(208,59,59,0.10)", layer="below")
    fig.add_shape(type="rect", x0=aft, x1=hi, y0=0.3, y1=0.7, line_width=0,
                  fillcolor="rgba(208,59,59,0.10)", layer="below")
    fig.add_shape(type="rect", x0=fwd, x1=aft, y0=0.3, y1=0.7, line_width=0,
                  fillcolor="rgba(12,163,12,0.16)", layer="below")
    for x, name in ((fwd, "Fwd limit"), (aft, "Aft limit")):
        fig.add_shape(type="line", x0=x, x1=x, y0=0.22, y1=0.78, line=dict(color=MUTED, width=2))
        fig.add_annotation(x=x, y=0.16, text=f"{name}<br><b>{x:.2f} m</b>", showarrow=False,
                           yanchor="top", font=dict(size=11))
    fig.add_shape(type="line", x0=target, x1=target, y0=0.18, y1=0.82,
                  line=dict(color=MUTED, width=2, dash="dash"))
    fig.add_annotation(x=target, y=0.86, text=f"Target {target:.2f} m", showarrow=False,
                       yanchor="bottom", font=dict(size=11))
    fig.add_trace(go.Scatter(
        x=[cg], y=[0.5], mode="markers",
        marker=dict(symbol="diamond", size=22, color=ACCENT if in_env else CRIT,
                    line=dict(color="white", width=2)),
        hovertemplate=(f"Plan CG: <b>{cg:.3f} m</b><br>Δ target: {cg - target:+.3f} m"
                       f"<br>Fwd margin: {cg - fwd:+.3f} m<br>Aft margin: {aft - cg:+.3f} m<extra></extra>"),
    ))
    fig.add_annotation(x=cg, y=0.5, text=f"<b>{cg:.3f} m</b>", showarrow=True, arrowhead=0,
                       ax=0, ay=-34, font=dict(size=13))
    _base_layout(fig, 200)
    fig.update_xaxes(range=[lo, hi], showgrid=False, ticksuffix=" m", title=None)
    fig.update_yaxes(range=[-0.2, 1.05], visible=False, fixedrange=True)
    return fig


def _payload_chart(metrics, mapping):
    pax_kg = sum(float(z.get("weight_kg") or 0) for z in mapping["zone_weights"].values())
    rows = [("Passengers", pax_kg), ("Bags", float(metrics.get("bag_weight_kg") or 0)),
            ("Cargo", float(metrics.get("cargo_weight_kg") or 0))]
    total = sum(v for _, v in rows) or 1
    fig = go.Figure(go.Bar(
        y=[r[0] for r in rows][::-1], x=[r[1] for r in rows][::-1], orientation="h",
        marker=dict(color=ACCENT, cornerradius=4),
        text=[f"{v:,.0f} kg · {v/total:.0%}" for _, v in rows][::-1], textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}: <b>%{x:,.1f} kg</b><extra></extra>",
    ))
    _base_layout(fig, 170, margin=dict(l=8, r=90, t=4, b=8))
    fig.update_xaxes(showgrid=True, ticksuffix=" kg", rangemode="tozero")
    fig.update_yaxes(showgrid=False)
    return fig


def _zone_chart(mapping):
    zones = sorted(mapping["zone_weights"].items(), key=lambda kv: kv[1].get("arm_m", 0))
    names = [n for n, _ in zones]
    fig = go.Figure(go.Bar(
        x=names, y=[z["weight_kg"] for _, z in zones],
        marker=dict(color=ACCENT, cornerradius=4),
        customdata=[[z["passenger_count"], z["arm_m"]] for _, z in zones],
        text=[f"{z['passenger_count']} pax" for _, z in zones], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{customdata[0]} passengers<br>%{y:,.1f} kg"
                      "<br>Arm %{customdata[1]:.2f} m<extra></extra>",
    ))
    _base_layout(fig, 280, margin=dict(l=8, r=8, t=24, b=8))
    fig.update_yaxes(ticksuffix=" kg", rangemode="tozero")
    fig.update_xaxes(showgrid=False, title=dict(text="Cabin zone (forward → aft)", font=dict(size=12)))
    return fig


def _hold_chart(result):
    loads = result["hold_assignments"].get("loads", {})
    limits = result["safety_gate"]["metrics"].get("hold_limits", {})
    holds, weights, caps, vols = [], [], [], []
    for hold, load in loads.items():
        limit = limits.get(hold, {}).get("max_weight_kg") or load["weight_kg"] or 1
        holds.append(hold)
        weights.append(float(load["weight_kg"]))
        caps.append(float(limit))
        vols.append(float(load.get("volume_m3") or 0))
    fracs = [w / c for w, c in zip(weights, caps)]

    fig = go.Figure()
    fig.add_trace(go.Bar(  # capacity track
        y=holds, x=caps, orientation="h", marker=dict(color="rgba(128,128,128,0.16)", cornerradius=4),
        width=0.62, hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(  # actual load
        y=holds, x=weights, orientation="h", width=0.62,
        marker=dict(color=[_util_color(f) for f in fracs], cornerradius=4),
        customdata=[[c, f, v] for c, f, v in zip(caps, fracs, vols)],
        hovertemplate="<b>%{y}</b><br>%{x:,.1f} / %{customdata[0]:,.1f} kg"
                      "<br>%{customdata[1]:.0%} of limit<br>%{customdata[2]:.2f} m³<extra></extra>",
    ))
    for h, w, c, f, v in zip(holds, weights, caps, fracs, vols):
        fig.add_annotation(x=max(w, c), y=h, xanchor="left", xshift=8, showarrow=False,
                           text=f"<b>{f:.0%}</b> · {w:,.0f}/{c:,.0f} kg · {v:.2f} m³", font=dict(size=12))
    _base_layout(fig, 90 + 56 * len(holds), barmode="overlay", margin=dict(l=8, r=210, t=4, b=8))
    fig.update_xaxes(ticksuffix=" kg", rangemode="tozero")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


# ── Sections ────────────────────────────────────────────────────────────────
def _render_overview(result, metrics):
    _kpi_row(result, metrics)
    st.write("")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            _section("CG envelope", "Plan centre of gravity against forward/aft limits")
            _plot(_cg_chart(metrics))
    with right:
        with st.container(border=True):
            _section("Payload breakdown",
                     f"Bags {_fmt(metrics['bag_weight_kg'])} kg · Cargo {_fmt(metrics['cargo_weight_kg'])} kg")
            _plot(_payload_chart(metrics, result["passenger_mapping"]))


def _render_count_check(check):
    passengers = check.get("passengers", {})
    bags = check.get("bags", {})
    if check.get("final_plan_verified"):
        if check.get("ok"):
            pill = f'<span class="pill" style="color:{GOOD};border-color:{GOOD}">✓ Counts reconcile</span>'
        else:
            pill = f'<span class="pill" style="color:{CRIT};border-color:{CRIT}">✗ Count mismatch — see Safety Gate</span>'
    else:
        pill = '<span class="pill" style="opacity:.75">ℹ Pre-plan manifest counts</span>'
    planned, dcs = passengers.get("planned", "—"), passengers.get("dcs_boarding", "—")
    st.markdown(
        '<div class="kpi-grid">'
        + _kpi("Passengers (plan / DCS)", f"{planned} / {dcs}")
        + _kpi("Bags loaded", bags.get("loaded", "—"))
        + _kpi("Bags pulled", bags.get("pulled", "—"))
        + _kpi("Left behind", bags.get("left_behind", "—"))
        + "</div>" + pill,
        unsafe_allow_html=True,
    )


def _render_tracker_count(check):
    """Render the pre-plan tracker reconciliation as an operator summary."""
    counts = check.get("counts", {})
    flying = int(counts.get("flying", 0))
    pulled = int(counts.get("pulled", 0))
    left = int(counts.get("left_behind", 0))
    unknown = int(counts.get("unknown", 0))
    total = int(check.get("total_known", flying + pulled + left + unknown))
    dcs = int(check.get("dcs_bags_checked", 0))
    if check.get("ok"):
        st.success(f"All {total} bags are accounted for and match the DCS checked-bag count.")
    else:
        st.error(f"Tracker and DCS counts differ by {int(check.get('difference', total-dcs))} bag(s). Resolve the mismatch before release.")

    entries = [
        ("Flying", flying, "Eligible for this flight", ACCENT),
        ("Pulled", pulled, "Owner removed by DCS", "#eb6834"),
        ("Left behind", left, "At risk after cutoff", CRIT),
        ("DCS checked", dcs, "Source manifest total", "#6f7785"),
    ]
    cards = "".join(
        f'<div class="tracker-card" style="border-top-color:{color}">'
        f'<div class="label">{escape(label)}</div><div class="value">{value}</div>'
        f'<div class="note">{escape(note)}</div></div>'
        for label, value, note, color in entries
    )
    st.markdown(f'<div class="tracker-grid">{cards}</div>', unsafe_allow_html=True)

    stacked = [("Flying", flying, ACCENT), ("Pulled", pulled, "#eb6834"),
               ("Left behind", left, CRIT), ("Unknown", unknown, "#8a8f98")]
    pieces = "".join(
        f'<span title="{escape(label)}: {value}" style="width:{(value/total*100 if total else 0):.3f}%;background:{color}"></span>'
        for label, value, color in stacked if value
    )
    legend = "".join(
        f'<span><b style="color:{color}">●</b> {escape(label)} {value}</span>'
        for label, value, color in stacked if value
    )
    st.markdown(f'<div class="tracker-bar">{pieces}</div><div class="tracker-legend">{legend}</div>',
                unsafe_allow_html=True)
    st.caption(f"Reconciliation: {flying} flying + {pulled} pulled + {left} left behind + {unknown} unknown = {total}; DCS checked {dcs}.")


def _render_plan(result):
    mapping = result["passenger_mapping"]
    bags = result["bag_actions"]
    loads = result["hold_assignments"].get("loads", {})

    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            _section("Passenger distribution",
                     f"{mapping['passenger_count_mapped']} mapped / {mapping['seat_capacity']} seats · "
                     f"{len(mapping['doesnt_fit'])} don't fit")
            if mapping["zone_weights"]:
                _plot(_zone_chart(mapping))
            if mapping["doesnt_fit"]:
                with st.expander(f"⚠️ {len(mapping['doesnt_fit'])} passengers don't fit", expanded=True):
                    st.dataframe([{"Passenger": p.get("pax_id"), "Seat": p.get("seat"),
                                   "Reason": p.get("doesnt_fit_reason")} for p in mapping["doesnt_fit"]],
                                 hide_index=True, width="stretch")
    with right:
        with st.container(border=True):
            _section("Hold loading", "Weight vs structural limit · green < 90% · amber ≥ 90% · red > 100%")
            if loads:
                _plot(_hold_chart(result))
            else:
                st.info("No assignments: the optimizer did not find a feasible plan.")

    st.write("")
    with st.container(border=True):
        _section("Count checks")
        _render_count_check(result["count_check"])

    st.write("")
    _section("Operational detail")
    checks = result.get("checks", [])
    tabs = st.tabs([
        f"🧳 Pull list ({len(bags['pull_list'])})",
        f"⏱️ At risk ({len(bags['at_risk'])})",
        f"🔁 Moves ({len(result['moves'])})",
        f"📦 Cargo bumped ({len(result['cargo_bumped'])})",
        "🗂️ Hold assignments",
        f"🛡️ Safety Gate ({len(checks)})",
        "🔢 Tracker count",
    ])
    with tabs[0]:
        if bags["pull_list"]:
            st.dataframe([{"Step": i, "Tag": b["tag"], "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Location": b.get("location"), "Stack": b.get("stack_pos"),
                           "Action": b.get("pull_reason")} for i, b in enumerate(bags["pull_list"], 1)],
                         hide_index=True, width="stretch",
                         column_config={"Step": st.column_config.NumberColumn(width="small")})
        else:
            st.success("No bags to pull.")
    with tabs[1]:
        if bags["at_risk"]:
            st.dataframe([{"Tag": b["tag"], "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Inbound flight": b.get("inbound_flight", ""), "ETA": b.get("eta"),
                           "Action": b.get("pull_reason")} for b in bags["at_risk"]],
                         hide_index=True, width="stretch")
        else:
            st.success("No connecting bags at risk.")
    with tabs[2]:
        if result["moves"]:
            st.dataframe(result["moves"], hide_index=True, width="stretch")
        else:
            st.success("No moves required.")
    with tabs[3]:
        if result["cargo_bumped"]:
            st.dataframe(result["cargo_bumped"], hide_index=True, width="stretch")
        else:
            st.success("No cargo bumped.")
    with tabs[4]:
        if loads:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Bags**")
                st.dataframe([{"Bag": t, "Hold": h} for t, h in result["hold_assignments"]["bags"].items()],
                             hide_index=True, width="stretch")
            with c2:
                st.markdown("**Cargo**")
                st.dataframe([{"Cargo": t, "Hold": h} for t, h in result["hold_assignments"]["cargo"].items()],
                             hide_index=True, width="stretch")
        else:
            st.info("No assignments: the optimizer did not find a feasible plan.")
    with tabs[5]:
        if checks:
            st.dataframe(checks, hide_index=True, width="stretch")
        else:
            st.info("No Safety Gate checks reported.")
    with tabs[6]:
        _render_tracker_count(bags["tracker_count_check"])


def _render_no_plan(result):
    """Avoid presenting candidate or pre-plan figures as a valid final plan."""
    st.info("Final plan statistics are hidden for BLOCKED and UNSAFE results. Resolve the issue above, then re-plan.")
    if result["status"] == "UNSAFE":
        solver_reason = result.get("solver", {}).get("reason")
        if solver_reason:
            with st.container(border=True):
                _section("Planner result")
                st.write(solver_reason)


# ── App ─────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Aircraft Swap Re-planner", page_icon="✈️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    scenarios = _scenario_files()
    if not scenarios:
        st.error(f"No scenario JSON files found in {SCENARIO_DIR}")
        return
    lookup = {p.stem: p for p in scenarios}
    labels = {n: _scenario_name(p) for n, p in lookup.items()}
    names = list(lookup)
    default = names.index("a320_winter_swap") if "a320_winter_swap" in names else 0

    with st.sidebar:
        st.header("✈️ Re-plan controls")
        selected = st.selectbox("Scenario", names, index=default, format_func=labels.get)
        st.divider()
        season = st.segmented_control("Passenger season", ["winter", "summer"], default="winter",
                                      format_func=lambda s: {"winter": "❄️ Winter", "summer": "☀️ Summer"}[s])
        buffer_pct = st.segmented_control("Passenger weight buffer", [0, 5], default=0,
                                          format_func=lambda v: f"{v}%")
        lightning = st.toggle("⚡ Lightning mode")
        st.divider()
        run = st.button("Re-plan", type="primary", width="stretch", icon="🔄")
        st.caption("Results refresh automatically when a control changes.")

    # segmented_control returns None if the user deselects; fall back to defaults.
    settings = {"season": season or "winter", "safety_buffer_pct": buffer_pct if buffer_pct is not None else 0,
                "lightning_mode": lightning}
    scenario_stamp = lookup[selected].stat().st_mtime_ns
    profiles_stamp = (DATA_DIR / "aircraft_profiles.json").stat().st_mtime_ns
    weights_stamp = (DATA_DIR / "standard_weights.json").stat().st_mtime_ns
    cache_key = (RESULT_VIEW_REVISION, selected, scenario_stamp, profiles_stamp,
                 weights_stamp, tuple(sorted(settings.items())))
    if run or st.session_state.get("result_key") != cache_key:
        # Clear first so an exception cannot leave the previous scenario visible.
        st.session_state.pop("result", None)
        st.session_state.pop("result_key", None)
        with st.spinner("Solving the selected scenario…"):
            try:
                st.session_state["result"] = run_scenario(lookup[selected], options=settings)
            except Exception as exc:
                st.error(f"Could not run the selected scenario: {exc}")
                st.stop()
            st.session_state["result_key"] = cache_key
    result = st.session_state["result"]

    _hero(labels[selected], settings)
    _status_banner(result)

    if result["status"] in {"BLOCKED", "UNSAFE"}:
        _render_no_plan(result)
        return

    metrics = result.get("metrics")
    if metrics:
        _render_overview(result, metrics)
    else:
        st.info("Final weight and CG are unavailable because the optimizer found no feasible plan.")
    st.write("")
    _render_plan(result)


if __name__ == "__main__":
    main()
