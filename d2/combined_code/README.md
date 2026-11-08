# Combined aircraft swap re-planner

`combined_code/` is the runnable, self-contained application. It contains the pipeline modules, dashboard, aircraft and passenger data, and demo scenarios. The sibling `draft/` directory holds earlier standalone module drafts and source data; the combined application does not load files from it.

The aircraft weights and balance data are illustrative. This is a demonstration project, not an approved operational load-control system.

## Install

From the project root (`d2/`):

```bash
python -m pip install -r combined_code/requirements.txt
```

## Run a scenario

From the project root:

```bash
python combined_code/pipeline.py a320_winter_swap
python combined_code/pipeline.py a220_winter_swap
```

Other included scenarios and options:

```bash
python combined_code/pipeline.py a320_wrong_pax_count
python combined_code/pipeline.py a320_infeasible_must_fly
python combined_code/pipeline.py a320_winter_swap --safety-buffer-pct 5
python combined_code/pipeline.py a320_winter_swap --lightning --safety-buffer-pct 5
```

Add `--json` to print the complete structured result.

## Run the dashboard

From the project root:

```bash
python -m streamlit run combined_code/dashboard.py
```

## Run the tests

From the project root:

```bash
python -m unittest discover -s combined_code/test -v
```

The tests cover passenger mapping, bag tracking, load planning, safety checks, and end-to-end safe, blocked, and infeasible scenarios.

## Python entry point

The pipeline function is `run_scenario(scenario, aircraft_profiles=None, options=None, standard_weights=None)` in `pipeline.py`. `scenario` can be a dictionary or a path to a scenario JSON file. The command-line runner resolves scenario names under `data/scenarios/`.

## Data layout

- `data/aircraft_profiles.json`: A220-300, A320ceo, and A321ceo profiles
- `data/standard_weights.json`: seasonal passenger weights
- `data/scenarios/*.json`: complete flight manifests and DCS counts

Scenarios use kg, m³, and metres. Edit a scenario to change its passenger, bag, cargo, DCS, or option inputs. To add an aircraft profile, add it to the profiles file and set `flight.new_aircraft` to its key.

The supplied aircraft data, including the A220-300 cabin and balance values, is illustrative. Use qualified, approved aircraft and airline data before any operational use.
