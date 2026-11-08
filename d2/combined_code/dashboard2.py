"""Dash version of the aircraft swap dashboard for UI comparison."""
import json
from html import escape

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html

from pipeline import DATA_DIR, run_scenario


SCENARIO_DIR = DATA_DIR / "scenarios"
DEMO_CASES = {
    "Clear to fly · SAFE": ("a320_winter_swap", "Clear-to-fly demonstration"),
    "DCS count mismatch · BLOCKED": ("a320_wrong_pax_count", "Passenger-count mismatch demonstration"),
    "Must-fly cargo · UNSAFE": ("a320_infeasible_must_fly", "Infeasible must-fly cargo demonstration"),
}
BLUE, MID_BLUE, DEEP_BLUE = "#2a78d6", "#3479ad", "#153d5d"
PALE_BLUE, PAGE_BLUE, PANEL_BLUE = "#e7f3fc", "#dceefa", "#edf7fe"
INK, GRID = "#101c28", "#b6d5eb"
STATUS_COLORS = {
    "SAFE": "#1c5d91", "NEEDS REVIEW": "#3479ad",
    "BLOCKED": "#24567e", "UNSAFE": "#153d5d",
}


def _load_demo_case(label):
    stem, title = DEMO_CASES[label]
    path = SCENARIO_DIR / f"{stem}.json"
    scenario = json.loads(path.read_text(encoding="utf-8"))
    note = ""
    if stem == "a320_winter_swap":
        cutoff = scenario["flight"]["loading_cutoff"]
        for bag in scenario["bags"]:
            if bag.get("location") == "inbound" and bag.get("eta") and bag["eta"] > cutoff:
                bag["eta"] = "19:10"
        note = "Demo setup: inbound bags arrive before the 19:15 cutoff."
    return scenario, title, note


def _card(label, value, note="", shade=BLUE):
    return html.Div([
        html.Div(label, className="card-label"),
        html.Div(str(value), className="card-value"),
        html.Div(note, className="card-note") if note else None,
    ], className="card", style={"borderTopColor": shade})


def _cards(items):
    return html.Div([_card(*item) for item in items], className="card-grid")


def _table(rows, columns=None):
    rows = list(rows or [])
    if not rows:
        return html.Div("No items to show.", className="empty-note")
    columns = columns or list(rows[0].keys())
    return html.Div(html.Table([
        html.Thead(html.Tr([html.Th(str(col)) for col in columns])),
        html.Tbody([
            html.Tr([html.Td("—" if row.get(col) is None else str(row.get(col, ""))) for col in columns])
            for row in rows
        ]),
    ], className="data-table"), className="table-wrap")


def _panel(title, body, caption=None):
    return html.Section([
        html.H3(title),
        html.P(caption, className="panel-caption") if caption else None,
        body,
    ], className="panel")


def _count(result, field):
    return len(result.get(field, []))


def _action_strip(result):
    bags = result.get("bag_actions", {})
    summary = [
        ("pulls", len(bags.get("pull_list", []))),
        ("moves", _count(result, "moves")),
        ("offloads", _count(result, "offloads")),
        ("at risk", len(bags.get("at_risk", []))),
        ("cargo bumped", _count(result, "cargo_bumped")),
    ]
    return html.Div([html.Span(f"{n} {label}", className="action-pill") for label, n in summary],
                    className="action-strip")


def _cg_chart(metrics):
    fwd = metrics["cg_forward_limit_m"]
    aft = metrics["cg_aft_limit_m"]
    target = metrics["cg_target_m"]
    cg = metrics["cg_m"]
    pad = (aft - fwd) * 0.25 or 0.1
    lo, hi = min(fwd, cg) - pad, max(aft, cg) + pad
    fig = go.Figure()
    fig.add_vrect(x0=lo, x1=fwd, fillcolor="rgba(77,145,198,.10)", line_width=0)
    fig.add_vrect(x0=fwd, x1=aft, fillcolor="rgba(42,120,214,.14)", line_width=0)
    fig.add_vrect(x0=aft, x1=hi, fillcolor="rgba(77,145,198,.10)", line_width=0)
    fig.add_vline(x=fwd, line_color=MID_BLUE, line_dash="dot")
    fig.add_vline(x=aft, line_color=MID_BLUE, line_dash="dot")
    fig.add_vline(x=target, line_color=DEEP_BLUE, line_dash="dash")
    fig.add_trace(go.Scatter(
        x=[cg], y=[0], mode="markers+text", text=[f"{cg:.3f} m"], textposition="top center",
        marker={"symbol": "diamond", "size": 17, "color": BLUE},
        hovertemplate=f"CG {cg:.3f} m<br>Target {target:.3f} m<extra></extra>",
    ))
    fig.update_layout(height=225, margin={"l": 10, "r": 10, "t": 38, "b": 8},
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"color": INK}, showlegend=False)
    fig.update_xaxes(range=[lo, hi], title="Centre of gravity (m)", gridcolor=GRID, zeroline=False)
    fig.update_yaxes(visible=False, fixedrange=True)
    return fig


def _hold_chart(result):
    loads = result.get("hold_assignments", {}).get("loads", {})
    limits = (result.get("safety_gate", {}).get("metrics") or {}).get("hold_limits", {})
    names, weights, labels, colors, hover = [], [], [], [], []
    for hold, load in loads.items():
        weight = float(load.get("weight_kg") or 0)
        limit = limits.get(hold, {}).get("max_weight_kg")
        names.append(hold)
        weights.append(weight)
        if limit is None or float(limit) <= 0:
            labels.append(f"{weight:,.0f} kg · limit unavailable")
            colors.append(MID_BLUE)
            hover.append("Limit unavailable")
        else:
            frac = weight / float(limit)
            labels.append(f"{frac:.0%} · {weight:,.0f}/{float(limit):,.0f} kg")
            colors.append(DEEP_BLUE if frac >= 0.9 else BLUE)
            hover.append(f"{frac:.0%} of {float(limit):,.0f} kg limit")
    fig = go.Figure(go.Bar(
        y=names, x=weights, orientation="h", marker_color=colors,
        text=labels, textposition="outside", cliponaxis=False,
        customdata=hover,
        hovertemplate="<b>%{y}</b><br>%{x:,.1f} kg<br>%{customdata}<extra></extra>",
    ))
    fig.update_layout(height=max(200, 70 * len(names)), margin={"l": 10, "r": 210, "t": 10, "b": 20},
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"color": INK}, showlegend=False)
    fig.update_xaxes(visible=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def _overview(result, scenario):
    if result["status"] in {"BLOCKED", "UNSAFE"}:
        return html.Div("Plan statistics are hidden for blocked or unsafe results. Resolve the findings and re-plan.",
                        className="notice")
    metrics = result.get("metrics")
    if not metrics:
        return html.Div("Final weight and CG are unavailable because the optimizer found no feasible plan.",
                        className="notice")
    mapping = result["passenger_mapping"]
    mapped, capacity = mapping["passenger_count_mapped"], mapping["seat_capacity"]
    actions = len(result.get("bag_actions", {}).get("pull_list", [])) + _count(result, "moves") + _count(result, "offloads")
    cards = _cards([
        ("Actions required", actions, "Pulls, moves, and offloads", BLUE),
        ("Passengers mapped", f"{mapped} / {capacity}", "Passengers assigned to seats", MID_BLUE),
        ("Zero-fuel weight", f"{metrics['total_weight_kg']:,.1f} kg", f"Margin {metrics['zfw_margin_kg']:,.1f} kg", BLUE),
        ("Centre of gravity", f"{metrics['cg_m']:.3f} m", "Final calculated position", DEEP_BLUE),
    ])
    return html.Div([
        cards,
        html.Div([
            _panel("CG envelope", dcc.Graph(figure=_cg_chart(metrics), config={"displayModeBar": False}),
                   "Final CG against forward and aft limits"),
            _panel("Hold loading", dcc.Graph(figure=_hold_chart(result), config={"displayModeBar": False}),
                   "Load and structural limit by hold"),
        ], className="two-col"),
        html.P(f"Loading cutoff: {scenario.get('flight', {}).get('loading_cutoff', '—')}", className="footnote"),
    ])


def _swap_stage(scenario, result):
    mapping = result["passenger_mapping"]
    fit = len(mapping["doesnt_fit"])
    cards = _cards([
        ("Input passengers", len(scenario.get("passengers", [])), "Source manifest", BLUE),
        ("Mapped", mapping["passenger_count_mapped"], "Assigned to cabin zones", MID_BLUE),
        ("Do not fit", fit, "Needs a seat decision" if fit else "All retained passengers fit", DEEP_BLUE if fit else BLUE),
    ])
    zones = [{"Zone": zone, "Passengers": info["passenger_count"],
              "Weight (kg)": f"{info['weight_kg']:,.1f}", "Arm (m)": f"{info['arm_m']:.2f}"}
             for zone, info in mapping["zone_weights"].items()]
    seats = [{"Passenger": p.get("pax_id"), "Seat": p.get("seat"), "Zone": p.get("zone"),
              "Category": p.get("category")} for p in mapping["mapped_passengers"][:12]]
    parts = [cards, html.P("Removed passengers are skipped; valid seats map to zones with seasonal weights.", className="logic-note"),
             html.Div([_panel("Cabin-zone load", _table(zones)),
                       _panel("Seat mapping sample", _table(seats))], className="two-col")]
    if fit:
        invalid = [{"Passenger": p.get("pax_id"), "Seat": p.get("seat"), "Reason": p.get("doesnt_fit_reason")}
                   for p in mapping["doesnt_fit"]]
        parts.append(_panel("Seat decision needed", _table(invalid)))
    return html.Div(parts)


def _bag_stage(result, scenario):
    bags = result["bag_actions"]
    check = bags["tracker_count_check"]
    counts = check.get("counts", {})
    total = int(check.get("total_known", sum(counts.values()) if counts else 0))
    cards = _cards([
        ("Flying", counts.get("flying", 0), "Eligible for this flight", BLUE),
        ("Pulled", counts.get("pulled", 0), "Removed-owner bags", MID_BLUE),
        ("At risk", len(bags.get("at_risk", [])), f"After {scenario.get('flight', {}).get('loading_cutoff', 'cutoff')}", DEEP_BLUE),
        ("DCS checked", check.get("dcs_bags_checked", "—"), f"{total} bags classified", BLUE),
    ])
    pulls = [{"Step": i, "Tag": b.get("tag"), "Owner": b.get("owner_pax_id", b.get("owner")),
              "Location": b.get("location"), "Why": b.get("pull_reason")}
             for i, b in enumerate(bags.get("pull_list", []), 1)]
    at_risk = [{"Tag": b.get("tag"), "Owner": b.get("owner_pax_id", b.get("owner")),
                "Inbound flight": b.get("inbound_flight", ""), "ETA": b.get("eta"),
                "Why": b.get("pull_reason")} for b in bags.get("at_risk", [])]
    note = (f"All {total} bags reconcile with DCS." if check.get("ok") else
            f"Tracker and DCS counts differ by {abs(int(check.get('difference', 0)))} bag(s).")
    return html.Div([
        cards,
        html.P(f"{note} Removed-owner bags are pulled; inbound bags after cutoff are at risk.", className="logic-note"),
        html.Div([_panel("Ordered pull list", _table(pulls)), _panel("At-risk bags", _table(at_risk))], className="two-col"),
    ])


def _replanner_stage(result, settings):
    assignments = result.get("hold_assignments", {})
    actions = result.get("handling_actions") or {}
    solver = result.get("solver", {})
    moves = result.get("moves", [])
    offloads = result.get("offloads", [])
    bumped = result.get("cargo_bumped", [])
    cards = _cards([
        ("Solver", solver.get("status", "—"), "Feasible plan" if solver.get("status") == "OPTIMAL" else "Review result",
         BLUE if solver.get("status") == "OPTIMAL" else DEEP_BLUE),
        ("Moves", actions.get("moves", len(moves)), "Handling changes", MID_BLUE),
        ("Offloads", actions.get("offloads", len(offloads)), "Already-loaded items", BLUE),
        ("Cargo bumped", len(bumped), "Not assigned to a hold", DEEP_BLUE if bumped else BLUE),
    ])
    rows = ([{"Type": "Bag", "Item": item, "Hold": hold} for item, hold in assignments.get("bags", {}).items()] +
            [{"Type": "Cargo", "Item": item, "Hold": hold} for item, hold in assignments.get("cargo", {}).items()])
    action_rows = moves + offloads
    priority = "bags left behind → fewest moves → cargo retained → CG target" if settings.get("lightning_mode") else \
               "bags left behind → cargo priority → fewest moves → CG target"
    content = [cards, html.P(f"Limits: hold weight/volume, dangerous goods, ZFW, and CG. Priority: {priority}.", className="logic-note")]
    objectives = solver.get("objective_values", {})
    if objectives:
        obj_rows = [{"Goal": name.replace("_", " ").title(), "Result": value} for name, value in objectives.items()]
        content.append(_panel("Planner priorities", _table(obj_rows)))
    content.extend([
        html.Div([_panel("Hold assignments", _table(rows)), _panel("Moves and offloads", _table(action_rows))], className="two-col"),
        _panel("Cargo not loaded", _table(bumped)),
    ])
    if solver.get("reason") and solver.get("status") != "OPTIMAL":
        content.insert(1, html.Div(solver["reason"], className="notice"))
    return html.Div(content)


def _safety_stage(result):
    gate = result.get("safety_gate", {})
    metrics = result.get("metrics") or gate.get("metrics")
    status = result.get("status", gate.get("status", "—"))
    ready = bool(gate.get("ready_for_load_controller"))
    cards = [
        ("Final decision", status, STATUS_COLORS.get(status, BLUE), "Safety Gate result"),
        ("Load-controller review", "Ready" if ready else "Not ready", BLUE if ready else DEEP_BLUE,
         "Qualified review required" if ready else "Resolve the findings"),
    ]
    parts = [_cards(cards)]
    if gate.get("status") == "NOT RUN":
        parts.append(html.Div("The planner found no feasible assignment, so the Safety Gate did not run.", className="notice"))
        return html.Div(parts)
    if metrics:
        margin = metrics["zfw_margin_kg"]
        parts.append(_cards([
            ("Zero-fuel weight", f"{metrics['total_weight_kg']:,.1f} kg", BLUE, f"Limit {metrics['max_zfw_kg']:,.0f} kg"),
            ("Centre of gravity", f"{metrics['cg_m']:.3f} m", MID_BLUE, "Final calculated position"),
            ("Weight margin", f"{margin:,.1f} kg", BLUE if margin >= 0 else DEEP_BLUE,
             "Below limit" if margin >= 0 else "Over limit"),
        ]))
    if gate.get("reasons"):
        parts.append(_panel("Decision reasons", html.Ul([html.Li(reason) for reason in gate["reasons"]])))
    checks = result.get("checks", gate.get("checks", []))
    check_rows = []
    for check in sorted(checks, key=lambda item: (bool(item.get("passed")), bool(item.get("warning")))):
        state = "Review" if check.get("warning") else ("Pass" if check.get("passed") else "Fail")
        check_rows.append({"Check": check.get("name"), "Result": state, "Detail": check.get("detail")})
    if check_rows:
        parts.append(_panel("Safety checks", _table(check_rows), "Passed, review, and failed checks"))
    count = result.get("count_check", {})
    reconciliation = [{"Check": "Passengers", "Planned": count.get("passengers", {}).get("planned", "—"),
                       "DCS": count.get("passengers", {}).get("dcs_boarding", "—")},
                      {"Check": "Bags", "Planned": count.get("bags", {}).get("loaded", "—"),
                       "DCS": count.get("dcs_bags_checked", "—")}]
    parts.append(_panel("Count reconciliation", _table(reconciliation)))
    return html.Div(parts)


def _engine_content(stage, scenario, result, settings):
    if stage == "swap":
        return _swap_stage(scenario, result)
    if stage == "bags":
        return _bag_stage(result, scenario)
    if stage == "replanner":
        return _replanner_stage(result, settings)
    return _safety_stage(result)


app = Dash(__name__, title="Aircraft Swap Re-planner · Dash")
app.index_string = """<!DOCTYPE html>
<html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
:root{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#101c28;background:#dceefa}
body{margin:0;background:#dceefa;color:#101c28}*{box-sizing:border-box}
.app-shell{max-width:1440px;margin:auto;padding:22px 28px 40px}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #a8cce6;padding:10px 0 16px}
h1{font-size:26px;margin:0;color:#102a40}.subhead,.muted,.panel-caption,.footnote{color:#40586b;font-size:13px;margin:5px 0 0}
.controlbar{display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:14px;align-items:end;padding:16px;background:#cde5f6;border:1px solid #a8cce6;border-radius:14px;margin:18px 0}
.control label,.control-title{font-size:12px;font-weight:700;display:block;margin-bottom:7px;color:#183c58}
.control select,.control input{font:inherit;color:#101c28;background:#f5faff;border:1px solid #9dbfda;border-radius:8px;padding:9px;width:100%}
.radio-row{display:flex;gap:12px;align-items:center;min-height:38px}.radio-row label{display:flex;gap:5px;align-items:center;font-size:13px}
.run-button{border:0;border-radius:8px;background:#1e659b;color:white;font-weight:700;padding:11px 18px;cursor:pointer}
.status{border:1px solid #9dbfda;border-left:6px solid;border-radius:12px;padding:13px 16px;background:#e7f3fc;margin:12px 0}.status-title{font-size:17px;font-weight:800}.status-reasons{margin:8px 0 0;padding-left:22px}
.action-strip{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 18px}.action-pill{background:#c6e1f4;border:1px solid #a8cce6;color:#173b58;padding:6px 10px;border-radius:99px;font-size:12px;font-weight:700}
.tabs{margin:12px 0}.tab{padding:11px 16px!important;background:#cde5f6!important;border-radius:9px 9px 0 0!important;color:#173b58!important}.tab--selected{background:#edf7fe!important;border-color:#a8cce6!important;border-bottom-color:#edf7fe!important}
.tab-content{background:#edf7fe;border:1px solid #a8cce6;border-radius:0 12px 12px 12px;padding:18px;min-height:300px}
.card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0 18px}.card{background:#f0f8fe;border:1px solid #b6d5eb;border-top:4px solid;border-radius:11px;padding:12px 14px;min-height:90px}.card-label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:#40586b;font-weight:700}.card-value{font-size:22px;font-weight:800;margin-top:4px;color:#102a40}.card-note{font-size:12px;color:#40586b;margin-top:3px}
.two-col{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.panel{background:#f0f8fe;border:1px solid #b6d5eb;border-radius:12px;padding:14px 16px;margin:12px 0}.panel h3{margin:0 0 8px;font-size:16px;color:#173b58}.panel-caption{margin:0 0 8px}.logic-note{background:#dceefa;border-left:4px solid #4b8ab8;border-radius:6px;padding:10px 12px;color:#183c58;font-size:13px}
.table-wrap{overflow-x:auto}.data-table{border-collapse:collapse;width:100%;font-size:13px}.data-table th{text-align:left;background:#d5eafb;color:#173b58;font-weight:700}.data-table th,.data-table td{padding:8px 10px;border-bottom:1px solid #d1e2ef;vertical-align:top}.data-table tr:last-child td{border-bottom:0}.empty-note,.notice{padding:12px;background:#dceefa;border-radius:8px;color:#183c58}.notice{border-left:4px solid #3479ad;margin:12px 0}.footnote{margin-top:12px}
@media(max-width:900px){.controlbar{grid-template-columns:repeat(2,minmax(0,1fr))}.card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.two-col{grid-template-columns:1fr}}
</style></head><body><div id="react-entry-point"><div class="app-shell">{%app_entry%}</div></div><footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""


app.layout = html.Div([
    html.Div([
        html.Div([html.H1("✈️ Aircraft Swap Re-planner"),
                  html.Div("Flight status, next actions, and engine walkthrough", className="subhead")]),
        html.Div(id="header-details", className="muted"),
    ], className="topbar"),
    html.Div([
        html.Div([html.Label("Demo case"), dcc.Dropdown(
            id="demo-case", options=[{"label": label, "value": label} for label in DEMO_CASES],
            value="Clear to fly · SAFE", clearable=False)], className="control"),
        html.Div([html.Label("Passenger season"), dcc.RadioItems(
            id="season", options=[{"label": "Summer", "value": "summer"}, {"label": "Winter", "value": "winter"}],
            value="summer", inline=True, className="radio-row")], className="control"),
        html.Div([html.Label("Weight buffer"), dcc.RadioItems(
            id="buffer", options=[{"label": "0%", "value": 0}, {"label": "5%", "value": 5}],
            value=0, inline=True, className="radio-row")], className="control"),
        html.Div([html.Label("Planner mode"), dcc.Checklist(
            id="lightning", options=[{"label": "Lightning", "value": "on"}], value=[], className="radio-row")], className="control"),
        html.Button("Re-plan", id="run", n_clicks=0, className="run-button"),
    ], className="controlbar"),
    html.Div(id="status-banner"),
    html.Div(id="action-strip"),
    dcc.Tabs(id="main-tab", value="overview", className="tabs", children=[
        dcc.Tab(label="Overview", value="overview", children=html.Div(id="overview-content", className="tab-content")),
        dcc.Tab(label="Engine walkthrough", value="engines", children=html.Div([
            dcc.Tabs(id="engine-stage", value="swap", children=[
                dcc.Tab(label="1 · Swap Mapper", value="swap"),
                dcc.Tab(label="2 · Bag Tracker", value="bags"),
                dcc.Tab(label="3 · Load Re-planner", value="replanner"),
                dcc.Tab(label="4 · Safety Gate", value="safety"),
            ]),
            html.Div(id="engine-content", style={"paddingTop": "12px"}),
        ], className="tab-content")),
    ]),
    dcc.Store(id="result-store"),
])


@app.callback(
    Output("status-banner", "children"),
    Output("action-strip", "children"),
    Output("overview-content", "children"),
    Output("engine-content", "children"),
    Output("header-details", "children"),
    Input("run", "n_clicks"),
    Input("engine-stage", "value"),
    State("demo-case", "value"),
    State("season", "value"),
    State("buffer", "value"),
    State("lightning", "value"),
)
def update_dashboard(_clicks, stage, case, season, buffer_pct, lightning):
    scenario, scenario_title, note = _load_demo_case(case or "Clear to fly · SAFE")
    settings = {"season": season or "summer", "safety_buffer_pct": buffer_pct or 0,
                "lightning_mode": "on" in (lightning or [])}
    result = run_scenario(scenario, options=settings)
    status = result.get("status", "—")
    status_color = STATUS_COLORS.get(status, BLUE)
    reasons = result.get("reasons", [])
    banner = html.Div([
        html.Div([html.Span("● ", style={"color": status_color}),
                  html.Span(status, className="status-title"),
                  html.Span(" · " + {"SAFE": "Plan cleared by Safety Gate",
                                     "NEEDS REVIEW": "Load controller review required",
                                     "BLOCKED": "Plan blocked — cannot proceed",
                                     "UNSAFE": "Plan unsafe — do not dispatch"}.get(status, ""), className="muted")]),
        html.Ul([html.Li(str(reason)) for reason in reasons], className="status-reasons") if reasons else None,
    ], className="status", style={"borderLeftColor": status_color})
    cutoff = scenario.get("flight", {}).get("loading_cutoff", "—")
    aircraft = result.get("aircraft", "—")
    header = f"{scenario_title} · Replacement aircraft {aircraft} · Loading cutoff {cutoff} · {settings['season'].title()} weights"
    if settings["lightning_mode"]:
        header += " · Lightning mode"
    if note:
        header += f" · {note}"
    return banner, _action_strip(result), _overview(result, scenario), _engine_content(stage, scenario, result, settings), header


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
