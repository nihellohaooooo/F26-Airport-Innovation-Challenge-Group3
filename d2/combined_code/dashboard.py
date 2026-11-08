"""Streamlit visual dashboard for the combined aircraft swap pipeline."""
import json
from html import escape

import plotly.graph_objects as go
import streamlit as st

from pipeline import DATA_DIR, run_scenario


SCENARIO_DIR = DATA_DIR / "scenarios"
RESULT_VIEW_REVISION = 3

# ── Design tokens ───────────────────────────────────────────────────────────
# Status colours are reserved for state (always paired with an icon + label);
# the accent/series colours carry identity only.
STATUS = {
    "SAFE":         {"icon": "●", "color": "#1c5d91", "tint": "#e7f3fc", "label": "Plan cleared by Safety Gate"},
    "NEEDS REVIEW": {"icon": "◆", "color": "#3479ad", "tint": "#e1f0fb", "label": "Load controller review required"},
    "BLOCKED":      {"icon": "■", "color": "#24567e", "tint": "#d7eafa", "label": "Plan blocked — cannot proceed"},
    "UNSAFE":       {"icon": "⬟", "color": "#153d5d", "tint": "#c9e1f4", "label": "Plan unsafe — do not dispatch"},
}
STATUS_DEFAULT = {"icon": "ℹ️", "color": "#2a78d6", "tint": "#e5f2fc", "label": ""}
GOOD, WARN, CRIT = "#1c5d91", "#3479ad", "#153d5d"
ACCENT = "#2a78d6"
MUTED = "rgba(27,65,99,0.52)"
GRID = "rgba(42,120,214,0.18)"
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}

CSS = """
<style>
.stApp, [data-testid="stAppViewContainer"] {background:#dceefa;color:#101c28;}
[data-testid="stSidebar"] > div {background:#c9e2f5;}
[data-testid="stHeader"] {background:rgba(220,238,250,.96);}
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px;}
h1, h2, h3 {letter-spacing: -0.01em;}
h1, h2, h3, p, label, [data-testid="stCaptionContainer"] {color:#101c28;}
div[data-testid="stSidebar"] h2 {font-size: 1.05rem;}
button[kind="primary"] {background:#1e659b;border-color:#1e659b;color:#fff;}
[data-testid="stVerticalBlockBorderWrapper"] {background:#e9f5fd;border-color:#a8cce6;border-radius:12px;}
[data-testid="stExpander"] {background:#e5f2fb;border-color:#a8cce6;}
[data-testid="stTab"] {color:#173b58;}
[role="tab"][aria-selected="true"] {border-bottom-color:#2a78d6;color:#102a40;}
input, textarea, [data-baseweb="select"] > div {background:#f2f9fe;color:#101c28;}

.hero {display:flex; align-items:center; justify-content:space-between; gap:1rem;
       padding: .55rem 0; border-bottom:1px solid rgba(42,120,214,.24); margin-bottom:.7rem;}
.hero h1 {margin:0; font-size:1.35rem; line-height:1.2; padding:0;}
.hero .sub {opacity:.72; font-size:.82rem; margin-top:.18rem;}
.hero .chip {font-size:.8rem; opacity:.75; white-space:nowrap;}

.status {border-radius: 12px; padding: .9rem 1.2rem; margin: .2rem 0 1.1rem;
         border: 1px solid; border-left-width: 6px;}
.status .head {display:flex; align-items:baseline; gap:.6rem; flex-wrap:wrap;}
.status .title {font-weight:750; font-size:1.15rem; letter-spacing:.02em;}
.status .label {opacity:.75; font-size:.9rem;}
.status ul {margin:.45rem 0 0 1.1rem; padding:0; font-size:.9rem;}
.status li {margin:.1rem 0;}

.kpi-grid {display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:.8rem; margin-bottom:.4rem;}
@media (max-width: 900px) {.kpi-grid {grid-template-columns: repeat(2, minmax(0,1fr));}}
.kpi {border:1px solid #b6d5eb; border-radius:12px; padding:.85rem 1rem;
      background:#edf7fe;color:#101c28;}
.kpi .k-label {font-size:.74rem; text-transform:uppercase; letter-spacing:.07em; opacity:.65; font-weight:600;}
.kpi .k-value {font-size:1.55rem; font-weight:700; margin-top:.15rem; line-height:1.25;
               font-variant-numeric: tabular-nums;}
.kpi .k-unit {font-size:.85rem; font-weight:500; opacity:.6; margin-left:.2rem;}
.kpi .k-foot {font-size:.8rem; opacity:.75; margin-top:.2rem;}
.kpi .bar {height:6px; border-radius:4px; background:rgba(42,120,214,.14); margin-top:.5rem; overflow:hidden;}
.kpi .bar > span {display:block; height:100%; border-radius:4px;}

.section-title {font-size:1.05rem; font-weight:700; margin:.2rem 0 .1rem;}
.section-cap {font-size:.82rem; opacity:.65; margin-bottom:.3rem;}

.pill {display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.78rem; font-weight:600;
       border:1px solid; margin-right:.3rem;}
.tracker-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.8rem 0;}
@media (max-width: 800px) {.tracker-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
.tracker-card {border:1px solid #b6d5eb;border-top:4px solid;border-radius:10px;
               padding:.75rem .9rem;background:#edf7fe;color:#101c28;}
.tracker-card .label {font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;opacity:.68;font-weight:650;}
.tracker-card .value {font-size:1.6rem;font-weight:750;line-height:1.25;margin-top:.12rem;font-variant-numeric:tabular-nums;}
.tracker-card .note {font-size:.76rem;opacity:.72;margin-top:.12rem;}
.tracker-bar {height:18px;display:flex;overflow:hidden;border-radius:9px;background:rgba(42,120,214,.12);margin:.7rem 0 .35rem;}
.tracker-bar span {height:100%;min-width:0;}
.tracker-legend {display:flex;gap:1rem;flex-wrap:wrap;font-size:.78rem;opacity:.78;}
.action-strip {display:flex;gap:.45rem;flex-wrap:wrap;margin:-.45rem 0 1rem;}
.action-strip span {padding:.28rem .6rem;border-radius:999px;background:rgba(42,120,214,.09);
                    font-size:.8rem;font-weight:600;font-variant-numeric:tabular-nums;}
.engine-cards {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.75rem 0 1rem;}
@media (max-width: 900px) {.engine-cards {grid-template-columns:repeat(2,minmax(0,1fr));}}
.engine-card {border:1px solid #b6d5eb;border-left:4px solid;border-radius:10px;
              padding:.7rem .85rem;background:#edf7fe;color:#101c28;}
.engine-card .label {font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;opacity:.68;font-weight:650;}
.engine-card .value {font-size:1.25rem;font-weight:750;line-height:1.25;margin-top:.1rem;font-variant-numeric:tabular-nums;}
.engine-card .note {font-size:.76rem;opacity:.72;margin-top:.12rem;}
div[data-testid="stAlert"] {background:#e7f3fc;border-color:#a8cce6;color:#101c28;}
div[data-testid="stAlert"] svg {color:#1e659b;fill:#1e659b;}
</style>
"""


# ── Helpers ─────────────────────────────────────────────────────────────────
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
        font=dict(size=13, color="#101c28"),
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
def _hero(scenario_label, settings, loading_cutoff):
    chips = f"{settings['season'].title()} weights · +{settings['safety_buffer_pct']}% buffer"
    if settings["lightning_mode"]:
        chips += " · ⚡ Lightning"
    st.markdown(
        f"""<div class="hero"><div>
        <h1>✈️ Aircraft Swap Re-planner</h1>
        <div class="sub">{escape(scenario_label)} · illustrative aircraft profiles ·
        qualified load-controller review required · Loading cutoff {escape(str(loading_cutoff or '—'))}</div></div>
        <div class="chip">Replacement aircraft: {escape(str(settings.get('aircraft', '')))} · {escape(chips)}</div></div>""",
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
        + _kpi("Actions required", _action_count(result), foot=_action_breakdown(result))
        + _kpi("Passengers mapped", f"{mapped} / {capacity}", foot=pax_foot,
               bar=(pax_frac, ACCENT))
        + _kpi("Zero-fuel weight", _fmt(zfw), "kg", zfw_foot, bar=(zfw_frac, _util_color(zfw_frac)))
        + _kpi("Centre of gravity", f"{cg:.3f}", "m", cg_foot)
        + "</div>",
        unsafe_allow_html=True,
    )


def _action_count(result):
    bags = result.get("bag_actions", {})
    return (len(bags.get("pull_list", [])) + len(result.get("moves", []))
            + len(result.get("offloads", [])))


def _action_breakdown(result):
    bags = result.get("bag_actions", {})
    return (f"{len(bags.get('pull_list', []))} pulls · {len(result.get('moves', []))} moves · "
            f"{len(result.get('offloads', []))} offloads")


def _action_strip(result):
    bags = result.get("bag_actions", {})
    values = [
        (f"{len(bags.get('pull_list', []))} pulls", "pulls"),
        (f"{len(result.get('moves', []))} moves", "moves"),
        (f"{len(result.get('offloads', []))} offloads", "offloads"),
        (f"{len(bags.get('at_risk', []))} at risk", "at-risk bags"),
        (f"{len(result.get('cargo_bumped', []))} cargo bumped", "bumped cargo items"),
    ]
    items = "".join(f'<span title="{escape(label)}">{escape(value)}</span>' for value, label in values)
    st.markdown(f'<div class="action-strip">{items}</div>', unsafe_allow_html=True)


def _engine_cards(items):
    cards = "".join(
        f'<div class="engine-card" style="border-left-color:{color}">'
        f'<div class="label">{escape(str(label))}</div>'
        f'<div class="value">{escape(str(value))}</div>'
        f'<div class="note">{escape(str(note))}</div></div>'
        for label, value, note, color in items
    )
    st.markdown(f'<div class="engine-cards">{cards}</div>', unsafe_allow_html=True)


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
                  fillcolor="rgba(77,145,198,0.10)", layer="below")
    fig.add_shape(type="rect", x0=aft, x1=hi, y0=0.3, y1=0.7, line_width=0,
                  fillcolor="rgba(77,145,198,0.10)", layer="below")
    fig.add_shape(type="rect", x0=fwd, x1=aft, y0=0.3, y1=0.7, line_width=0,
                  fillcolor="rgba(23,105,170,0.16)", layer="below")
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


def _zone_chart(mapping):
    zones = sorted(mapping["zone_weights"].items(), key=lambda kv: kv[1].get("arm_m", 0))
    names = [n for n, _ in zones]
    fig = go.Figure(go.Bar(
        x=names, y=[z["weight_kg"] for _, z in zones],
        marker=dict(color=ACCENT, cornerradius=4),
        customdata=[[z["passenger_count"], z["arm_m"]] for _, z in zones],
        text=[f"{z['weight_kg']:,.0f} kg" for _, z in zones], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{customdata[0]} passengers<br>%{y:,.1f} kg"
                      "<br>Arm %{customdata[1]:.2f} m<extra></extra>",
    ))
    _base_layout(fig, 280, margin=dict(l=8, r=8, t=24, b=8))
    fig.update_yaxes(visible=False, showgrid=False, rangemode="tozero", fixedrange=True)
    fig.update_xaxes(showgrid=False, title=dict(text="Cabin zone (forward → aft)", font=dict(size=12)))
    return fig


def _hold_chart(result):
    loads = result["hold_assignments"].get("loads", {})
    limits = result["safety_gate"]["metrics"].get("hold_limits", {})
    holds, weights, caps, vols, known = [], [], [], [], []
    for hold, load in loads.items():
        limit = limits.get(hold, {}).get("max_weight_kg")
        holds.append(hold)
        weights.append(float(load["weight_kg"]))
        caps.append(float(limit) if limit is not None else 0.0)
        known.append(limit is not None and float(limit) > 0)
        vols.append(float(load.get("volume_m3") or 0))
    fracs = [w / c if k else None for w, c, k in zip(weights, caps, known)]

    fig = go.Figure()
    fig.add_trace(go.Bar(  # capacity track
        y=[h for h, k in zip(holds, known) if k],
        x=[c for c, k in zip(caps, known) if k], orientation="h",
        marker=dict(color="rgba(42,120,214,0.16)", cornerradius=4), width=0.62, hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(  # actual load
        y=holds, x=weights, orientation="h", width=0.62,
        marker=dict(color=[_util_color(f) if f is not None else MUTED for f in fracs], cornerradius=4),
        customdata=[[c, f, v, (f"{f:.0%} of {c:,.0f} kg limit" if k else "Limit unavailable")]
                    for c, f, v, k in zip(caps, fracs, vols, known)],
        hovertemplate="<b>%{y}</b><br>%{x:,.1f} kg · %{customdata[2]:.2f} m³"
                      "<br>%{customdata[3]}<extra></extra>",
    ))
    for h, w, c, f, v in zip(holds, weights, caps, fracs, vols):
        label = f"<b>{f:.0%}</b> · {w:,.0f}/{c:,.0f} kg · {v:.2f} m³" if f is not None else f"{w:,.0f} kg · limit unavailable"
        fig.add_annotation(x=max(w, c), y=h, xanchor="left", xshift=8, showarrow=False,
                           text=label, font=dict(size=12))
    _base_layout(fig, 90 + 56 * len(holds), barmode="overlay", margin=dict(l=8, r=210, t=4, b=8))
    fig.update_xaxes(visible=False, showgrid=False, zeroline=False, fixedrange=True)
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
            _section("Hold loading", "Weight use by hold · limit status shown where available")
            if result.get("hold_assignments", {}).get("loads"):
                _plot(_hold_chart(result))
            else:
                st.info("No hold assignments are available.")


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
        st.error(f"Tracker and DCS counts differ by {abs(int(check.get('difference', total-dcs)))} bag(s). Resolve the mismatch before release.")

    entries = [
        ("Flying", flying, "Eligible for this flight", ACCENT),
        ("Pulled", pulled, "Owner removed by DCS", "#6d94b5"),
        ("Left behind", left, "At risk after cutoff", CRIT),
        ("DCS checked", dcs, "Source manifest total", "#6d94b5"),
    ]
    cards = "".join(
        f'<div class="tracker-card" style="border-top-color:{color}">'
        f'<div class="label">{escape(label)}</div><div class="value">{value}</div>'
        f'<div class="note">{escape(note)}</div></div>'
        for label, value, note, color in entries
    )
    st.markdown(f'<div class="tracker-grid">{cards}</div>', unsafe_allow_html=True)

    stacked = [("Flying", flying, ACCENT), ("Pulled", pulled, "#6d94b5"),
               ("Left behind", left, CRIT), ("Unknown", unknown, "#9bb7cf")]
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


def _render_no_plan(result):
    """Avoid presenting candidate or pre-plan figures as a valid final plan."""
    st.info("Plan statistics are hidden for blocked or unsafe results. Resolve the findings and re-plan.")
    if result["status"] == "UNSAFE":
        solver_reason = result.get("solver", {}).get("reason")
        if solver_reason:
            with st.container(border=True):
                _section("Planner result")
                st.write(solver_reason)


def _style_checks(checks):
    import pandas as pd

    frame = pd.DataFrame(checks)
    status_column = next((name for name in ("passed", "ok", "status") if name in frame.columns), None)
    if status_column is None:
        return frame

    def color_row(row):
        value = row[status_column]
        passed = value is True or str(value).upper() in {"PASS", "PASSED", "TRUE", "SAFE"}
        color = "#c9e1f4" if row.get("warning") else ("#e9f3fb" if passed else "#a9cce7")
        return [f"background-color: {color}"] * len(row)

    return frame.style.apply(color_row, axis=1)


def _render_swap_stage(scenario, result):
    mapping = result["passenger_mapping"]
    passengers = scenario.get("passengers", [])
    fit_count = len(mapping["doesnt_fit"])
    removed_count = sum(
    str(p.get("removed_by_dcs", "")).lower() in {"true", "1", "yes"}
    for p in passengers)
    retained_count = len(passengers) - removed_count

    st.info(
        f"**When the aircraft changes, DCS sends the list of removed passengers.** "
        f"{removed_count} of {len(passengers)} passengers are on that list and are skipped here. "
        f"The other {retained_count} are checked against the new aircraft and mapped to cabin zones with seasonal weights."
    )

    _engine_cards([
    ("Input passengers", len(passengers), "Source manifest", ACCENT),
    ("Removed by DCS", removed_count, "Skipped before seat mapping", "#6f7785"),
    ("Mapped", mapping["passenger_count_mapped"], "Assigned to cabin zones",  "#b586f2"),
    ("Do not fit", fit_count, "Needs a DCS seat decision" if fit_count else "All retained passengers fit", CRIT if fit_count else GOOD),
    ])

    left, right = st.columns([1, 1.4], gap="large")
    with left:
        with st.container(border=True):
            _section("Cabin-zone output")
            rows = [{"Zone": zone, "Passengers": info["passenger_count"],
                     "Weight (kg)": info["weight_kg"], "Arm (m)": info["arm_m"]}
                    for zone, info in mapping["zone_weights"].items()]
            st.dataframe(rows, hide_index=True, width="stretch")
    with right:
        with st.container(border=True):
            _section("Seat mapping decisions")
            rows = [{"Passenger": p.get("pax_id"), "Seat": p.get("seat"), "Row": p.get("row"),
                     "Zone": p.get("zone"), "Category": p.get("category")}
                    for p in mapping["mapped_passengers"]]
            st.dataframe(rows, hide_index=True, width="stretch")
    if mapping["doesnt_fit"]:
        with st.container(border=True):
            st.warning("Passengers without a valid seat need a DCS decision.")
            st.dataframe([{"Passenger": p.get("pax_id"), "Seat": p.get("seat"),
                           "Reason": p.get("doesnt_fit_reason")} for p in mapping["doesnt_fit"]],
                         hide_index=True, width="stretch")
    else:
        st.success("Every retained passenger maps to a valid cabin zone.")


def _render_bag_stage(result, scenario):
    bags = result["bag_actions"]
    check = bags["tracker_count_check"]
    counts = check.get("counts", {})
    st.caption("Classifies bags to fly, pull, or leave behind at the loading cutoff.")
    st.caption(f"Cutoff: {scenario.get('flight', {}).get('loading_cutoff', '—')} · "
               f"DCS checked bags: {check.get('dcs_bags_checked', '—')}")
    _render_tracker_count(check)
    st.info("Removed-owner bags are pulled; inbound bags after cutoff are marked at risk.")
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            _section("Ordered pull list", f"{len(bags['pull_list'])} bags to physically remove")
            st.dataframe([{"Step": i, "Tag": b.get("tag"), "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Location": b.get("location"), "Stack": b.get("stack_pos"),
                           "Why": b.get("pull_reason")} for i, b in enumerate(bags["pull_list"], 1)],
                         hide_index=True, width="stretch")
    with right:
        with st.container(border=True):
            _section("At-risk bags", f"{len(bags['at_risk'])} bags arrive after cutoff")
            st.dataframe([{"Tag": b.get("tag"), "Owner": b.get("owner_pax_id", b.get("owner")),
                           "Inbound flight": b.get("inbound_flight", ""), "ETA": b.get("eta"),
                           "Status": b.get("tracker_status"), "Why": b.get("pull_reason")}
                          for b in bags["at_risk"]], hide_index=True, width="stretch")
    with st.expander("Show every classified bag"):
        st.dataframe([{"Tag": b.get("tag"), "Owner": b.get("owner_pax_id", b.get("owner")),
                       "Location": b.get("location"), "Status": b.get("tracker_status"),
                       "ETA": b.get("eta", ""), "Reason": b.get("pull_reason", "")}
                      for b in bags.get("classified_bags", [])], hide_index=True, width="stretch")


def _render_replanner_stage(result, settings):
    assignments = result["hold_assignments"]
    solver = result.get("solver", {})
    actions = result.get("handling_actions") or {}
    st.caption("Assigns bags and cargo to holds within aircraft limits.")
    solver_status = solver.get("status", "—")
    move_count = actions.get("moves", len(result.get("moves", [])))
    offload_count = actions.get("offloads", len(result.get("offloads", [])))
    _engine_cards([
        ("Solver", solver_status, "Feasible plan found" if solver_status == "OPTIMAL" else "Review planner result",
         GOOD if solver_status == "OPTIMAL" else CRIT),
        ("Moves", move_count, "Handling changes" if move_count else "No moves required", WARN if move_count else GOOD),
        ("Offloads", offload_count, "Already-loaded items" if offload_count else "No offloads required", WARN if offload_count else GOOD),
        ("Cargo bumped", len(result.get("cargo_bumped", [])), "Priority items not loaded", WARN if result.get("cargo_bumped") else GOOD),
    ])
    if settings["lightning_mode"]:
        order = "bags left behind → fewest moves → cargo retained → CG target"
    else:
        order = "bags left behind → cargo priority → fewest moves → CG target"
    st.info(f"Limits: hold weight/volume, dangerous goods, ZFW, and CG. Priority: {order}.")
    objectives = solver.get("objective_values", {})
    if objectives:
        metrics = result.get("metrics") or {}
        objective_rows = []
        labels = {"bags_left": "Bags left behind", "cargo_left": "Cargo bump score",
                  "moves": "Handling moves"}
        for name, value in objectives.items():
            if name == "target_cg_deviation" and metrics:
                value_text = f"{abs(metrics['cg_m'] - metrics['cg_target_m']):.3f} m from target"
                label = "Final CG deviation"
            else:
                label = labels.get(name, name.replace("_", " ").title())
                value_text = str(value)
            objective_rows.append({"Goal": label, "Result": value_text})
        with st.container(border=True):
            _section("Planner priorities", "Results returned by the optimizer")
            st.dataframe(objective_rows, hide_index=True, width="stretch")
    if solver.get("reason") and solver.get("status") != "OPTIMAL":
        st.error(solver["reason"])
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            _section("Hold assignments")
            rows = ([{"Type": "Bag", "Item": item, "Hold": hold}
                     for item, hold in assignments.get("bags", {}).items()] +
                    [{"Type": "Cargo", "Item": item, "Hold": hold}
                     for item, hold in assignments.get("cargo", {}).items()])
            st.dataframe(rows, hide_index=True, width="stretch")
    with right:
        with st.container(border=True):
            _section("Moves and offloads")
            actions_rows = result.get("moves", []) + result.get("offloads", [])
            if actions_rows:
                st.dataframe(actions_rows, hide_index=True, width="stretch")
            else:
                st.success("No already-loaded items need to move or come off.")
    with st.container(border=True):
        _section("Cargo not loaded", "Each row explains the selected bump decision")
        if result.get("cargo_bumped"):
            st.dataframe(result["cargo_bumped"], hide_index=True, width="stretch")
        else:
            st.success("All cargo was assigned to a hold.")


def _render_safety_stage(result):
    gate = result.get("safety_gate", {})
    metrics = result.get("metrics") or gate.get("metrics")
    st.caption("Independently checks the final load and its release status.")
    status = result.get("status", gate.get("status", "—"))
    decision_style = STATUS.get(status, STATUS_DEFAULT)
    ready = bool(gate.get("ready_for_load_controller"))
    _engine_cards([
        ("Final decision", status, decision_style["label"], decision_style["color"]),
        ("Load-controller review", "Ready" if ready else "Not ready",
         "Qualified review required before dispatch" if ready else "Resolve the listed findings first",
         GOOD if ready else CRIT),
    ])
    if gate.get("status") == "NOT RUN":
        st.warning("The load planner found no feasible assignment, so the independent Safety Gate did not run.")
        return
    st.info("Checks counts, load accounting, aircraft limits, dangerous goods, and CG.")
    if metrics:
        margin = metrics["zfw_margin_kg"]
        _engine_cards([
            ("Zero-fuel weight", f"{metrics['total_weight_kg']:,.1f} kg",
             f"Limit {metrics['max_zfw_kg']:,.0f} kg", ACCENT),
            ("Centre of gravity", f"{metrics['cg_m']:.3f} m", "Final calculated position", "#4d91c6"),
            ("Weight margin", f"{margin:,.1f} kg", "Below limit" if margin >= 0 else "Over limit",
             GOOD if margin >= 0 else CRIT),
        ])
    if gate.get("reasons"):
        _section("Decision reasons")
        for reason in gate["reasons"]:
            st.write(f"• {reason}")
    checks = result.get("checks", gate.get("checks", []))
    if checks:
        _section("Individual gate checks", "Blue shades distinguish passed, review, and failed checks")
        checks = sorted(checks, key=lambda row: (bool(row.get("passed", row.get("ok", False))),
                                                   bool(row.get("warning", False))))
        with st.container(border=True):
            st.dataframe(_style_checks(checks), hide_index=True, width="stretch")
    with st.container(border=True):
        _section("Count reconciliation")
        _render_count_check(result.get("count_check", {}))


def _load_demo_case(label):
    cases = {
        "Clear to fly · SAFE": ("a320_winter_swap", "Clear-to-fly demonstration"),
        "DCS count mismatch · BLOCKED": ("a320_wrong_pax_count", "Passenger-count mismatch demonstration"),
        "Must-fly cargo · UNSAFE": ("a320_infeasible_must_fly", "Infeasible must-fly cargo demonstration"),
    }
    stem, title = cases[label]
    path = SCENARIO_DIR / f"{stem}.json"
    scenario = json.loads(path.read_text(encoding="utf-8"))
    note = ""
    if stem == "a320_winter_swap":
        cutoff = scenario["flight"]["loading_cutoff"]
        for bag in scenario["bags"]:
            if bag.get("location") == "inbound" and bag.get("eta") and bag["eta"] > cutoff:
                bag["eta"] = "19:10"
        note = "Demo setup: inbound bags arrive before the 19:15 cutoff; use summer weights for the clear-to-fly result."
    return path, scenario, title, note


# ── App ─────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Aircraft Swap Re-planner", page_icon="✈️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.header("✈️ Demo controls")
        selected = st.selectbox("Demo case", [
            "Clear to fly · SAFE",
            "DCS count mismatch · BLOCKED",
            "Must-fly cargo · UNSAFE",
        ], index=0)
        st.divider()
        season = st.radio("Passenger season", ["summer", "winter"], index=0, horizontal=True,
                          format_func=lambda s: {"winter": "❄️ Winter", "summer": "☀️ Summer"}[s])
        buffer_pct = st.segmented_control("Passenger weight buffer", [0, 5], default=0,
                                          format_func=lambda v: f"{v}%")
        lightning = st.toggle("⚡ Lightning mode")
        st.divider()
        run = st.button("Re-plan", type="primary", width="stretch", icon="🔄")
        st.caption("Change a setting or demo case to rerun the pipeline.")

    settings = {"season": season, "safety_buffer_pct": buffer_pct if buffer_pct is not None else 0,
                "lightning_mode": lightning}
    scenario_path, scenario, scenario_label, demo_note = _load_demo_case(selected)
    scenario_stamp = scenario_path.stat().st_mtime_ns
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
                st.session_state["result"] = run_scenario(scenario, options=settings)
            except Exception as exc:
                st.error(f"Could not run the selected scenario: {exc}")
                st.stop()
            st.session_state["result_key"] = cache_key
    result = st.session_state["result"]

    settings["aircraft"] = result["aircraft"]
    _hero(scenario_label, settings, scenario.get("flight", {}).get("loading_cutoff", "—"))
    if demo_note:
        st.caption(demo_note)
    _status_banner(result)
    _action_strip(result)
    overview, engines = st.tabs(["🌐 Combined overview", "🧩 Engine walkthrough"])

    with overview:
        st.markdown("**One flight, four engines:** map passengers → track bags → re-plan holds → independently verify the load.")
        metrics = result.get("metrics")
        if result["status"] in {"BLOCKED", "UNSAFE"}:
            _render_no_plan(result)
        elif metrics:
            _render_overview(result, metrics)
        else:
            st.info("Final weight and CG are unavailable because the optimizer found no feasible plan.")

    with engines:
        stage = st.selectbox("Choose a pipeline stage", [
            "1 · Swap Mapper", "2 · Bag Offload Tracker",
            "3 · Load Re-planner", "4 · Safety Gate",
        ], key="engine_stage")
        st.divider()
        if stage.startswith("1"):
            _render_swap_stage(scenario, result)
        elif stage.startswith("2"):
            _render_bag_stage(result, scenario)
        elif stage.startswith("3"):
            _render_replanner_stage(result, settings)
        else:
            _render_safety_stage(result)


if __name__ == "__main__":
    main()
