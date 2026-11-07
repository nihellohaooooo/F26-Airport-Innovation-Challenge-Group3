# Combined aircraft swap re-planner

This folder is a runnable, self-contained copy of the team modules in `../code/`, with the missing planner and orchestration completed. It uses illustrative aircraft weights and balance data for demonstration only; it is not an approved operational load-control system.

## Run it

From the project root:

```bash
python -m pip install -r "combined_code/requirements.txt"
cd "combined code"
python pipeline.py a320_winter_swap
python pipeline.py a220_winter_swap
```

Run a scenario with a passenger-weight buffer or lightning objective:

```bash
python pipeline.py a320_winter_swap --safety-buffer-pct 5
python pipeline.py a320_winter_swap --lightning --safety-buffer-pct 5
python pipeline.py a320_wrong_pax_count
python pipeline.py a320_infeasible_must_fly
python -m unittest discover -s tests -q
```

Add `--json` for the complete structured result. The Python entry point is `run_scenario(scenario, aircraft_profiles=None, options=None, standard_weights=None)` in `pipeline.py`; `scenario` may be a dictionary or a JSON path.

## What the result contains

- Safety status and reasons
- Passenger zone mapping, counts, weights, and passengers that do not fit
- Ordered bag pull list, late inbound bags at risk, and bag counts
- Bag and cargo hold assignments
- Required moves and cargo bumped
- Recalculated final zero-fuel weight and CG
- Independent Safety Gate checks and passenger/bag/cargo reconciliation

## Data layout

- `data/aircraft_profiles.json`: shared A220-300, A320ceo, and A321ceo profiles
- `data/standard_weights.json`: seasonal passenger weights
- `data/scenarios/*.json`: complete flight manifests and DCS counts

Scenarios use kg, m³, and metres. Edit a scenario to change its passenger, bag, cargo, DCS, or option inputs; add an aircraft profile to the profiles file and refer to its key as `flight.new_aircraft`.

The supplied A220-300 profile includes illustrative arms, cabin limits, and CG envelope values. Use qualified, approved aircraft and airline data before any operational use.
