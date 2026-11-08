# Original code and combined-code changes

The source files in the project’s `code/` directory were left unchanged. Their copies are in this folder, edited to share one data format and run as one pipeline. The `engine/` draft supplied the staged optimization approach; it was not copied as a second application.

| Combined file | Source | What was retained | What was edited or added |
|---|---|---|---|
| `swap_mapper.py` | `../code/swap_mapper.py` | Passenger-to-zone mapping, seat/row checks, seasonal zone weights | Removed hard-coded file loading; takes scenario and profile data; accepts boolean or CSV-style removal flags; includes the infant weight rule; returns a dashboard-ready mapping result. |
| `bag_offload_tracker.py` | `../code/bag_offload_tracker.py` | Bag classifications, cart/hold/inbound pull order, cutoff risk, manifest counts | Removed fixed data-file assumptions; accepts scenario records directly; parses ETA seconds and explicit boolean flags; treats unknown or untimed inbound bags as unresolved and inbound arrivals after cutoff as at risk; returns structured pull, risk, and count results. |
| `replanner.py` | `../code/replanner.py` | Binary item-to-hold variables and weight, volume, ZFW, CG, and dangerous-goods constraints | Completed the planner: added sequential objectives for bags, cargo priority, moves, and target CG; lightning mode; must-fly cargo constraints; explicit solver error, infeasible, optimal, and incumbent-only statuses; assignments, moves, and bumped-cargo reasons. |
| `safety_gate.py` | `../code/safety_gate.py` | Independent recalculation and aircraft/count validation | Removed global data reads; accepts profiles and weights as inputs; validates passenger IDs, seat uniqueness/capacity, category integrity, bags, and cargo; checks holds, cabin zones, DG, ZFW, CG, and counts; returns `SAFE`, `UNSAFE`, `BLOCKED`, or `NEEDS REVIEW` with checks and reasons. |
| `pipeline.py` | New | — | New single entry point. Loads scenarios and profiles, calls the other four modules, combines their outputs, and provides both a CLI and `run_scenario()` API. |

## Added data and documentation

- `data/aircraft_profiles.json` and `data/standard_weights.json` are copies of the project data used by the combined pipeline.
- `data/scenarios/a320_winter_swap.json` contains the 162-passenger A320 demo based on the team CSV data.
- `data/scenarios/a220_winter_swap.json` contains a 160-passenger A220 case. Retained passengers are assigned seats in the A220’s 2-3 layout; the DCS removal list is expanded to match its seat capacity.
- `data/scenarios/a320_wrong_pax_count.json` deliberately mismatches the passenger count to demonstrate `BLOCKED`.
- `data/scenarios/a320_infeasible_must_fly.json` adds must-fly cargo beyond the aircraft’s feasible capacity to demonstrate a graceful unsafe/infeasible result.
- `README.md` documents installation, commands, outputs, and the data layout.
- `test/test_pipeline.py` runs all included scenarios through the combined pipeline and checks their expected outcomes.

`seat_mapper.py` was not copied into this pipeline. It has four engine modules plus the `pipeline.py` orchestrator. The combined path maps each passenger’s scenario seat to a cabin zone. The A220 fixture already represents the post-swap seat assignments; a live seat reassignment step can be added if the demo needs it.

The scenario inputs and aircraft profiles are illustrative. In particular, the A220 arms and CG limits are not an approved load-control profile.
