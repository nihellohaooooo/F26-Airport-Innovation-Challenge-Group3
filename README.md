
# Module 4 — Safety Gate

## Overview

This module is part of the Aircraft Swap Re-planner project for the Fall 2026 Airport Innovation Challenge.

It extends the University of Waterloo's original Flask + PuLP aircraft weight-and-balance optimizer.

The original optimizer calculates how passengers and cargo should be distributed across aircraft compartments.

Our Safety Gate adds an independent validation layer to check the resulting loading plan.

**Key idea: Optimal does not necessarily mean safe or operationally complete.**

## What We Built

The current prototype performs four checks:

### 1. Weight Validation
- Recalculates total zero-fuel weight.
- Checks the aircraft's maximum zero-fuel weight.
- Checks individual cabin and cargo-hold weight limits.

### 2. Center of Gravity Validation
- Independently recalculates the aircraft CG.
- Checks forward and aft CG limits.
- Reports specific violations.

### 3. Seat Capacity Validation
- Counts passengers assigned to each cabin.
- Checks whether passenger counts exceed available seats.

### 4. Unassigned Payload Validation
- Detects passenger or cargo groups left unassigned.
- Prevents a plan with unresolved unassigned payload from receiving PASS.

## Safety Gate Status

The current prototype returns:

| Status | Meaning |
|---|---|
| PASS | All four implemented checks pass |
| UNSAFE | One or more checks fail |
| BLOCKED | The solver did not return an optimal solution |

The API also returns a list of reasons explaining failed checks.

**Integration note:** The team specification uses SAFE, UNSAFE, BLOCKED, and NEEDS REVIEW. Our prototype currently uses PASS instead of SAFE. Status definitions and unassigned-payload handling must be aligned during integration.

PASS does not constitute certified aircraft safety approval.

## Architecture

```text
Aircraft Parameters + Manifest
              |
              v
      Flask API (app.py)
              |
              v
      PuLP MILP Optimizer
              |
              v
         Safety Gate
        /    |    \
    Weight  CG   Seats
              |
       Unassigned Check
              |
              v
     PASS / UNSAFE / BLOCKED
              |
              v
      Dashboard + Reasons
```

## Project Files

```text
safety_gate/
├── app.py
├── safety.py
├── requirements.txt
├── test_safety.py
├── test_safety_api.py
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

- `app.py`: Flask API, PuLP optimizer, and Safety Gate integration.
- `safety.py`: Independent weight, CG, and seat-capacity checks.
- `test_safety.py`: Seven unit tests.
- `test_safety_api.py`: Four API integration tests using mocked solver results.
- `templates/index.html`: Dashboard layout and warning panel.
- `static/js/app.js`: API requests and Safety Gate result display.

## Installation

Requirements: Python 3 and pip.

From the safety_gate directory:

```bash
python -m pip install -r requirements.txt
```

## Run the Application

```bash
python app.py
```

Open:

http://127.0.0.1:5000

Click **Run Server MILP Engine** to generate and validate a loading plan.

## Run Automated Tests

From the safety_gate directory:

```bash
python -m unittest discover -p "test_safety*.py" -v
```

Latest local test result:

```text
Ran 11 tests in 0.108s

OK
```

The tests cover:

- CG too far forward
- CG too far aft
- Empty loading plan
- Maximum zero-fuel weight exceeded
- Cabin seat capacity exceeded
- Individual zone overweight
- Valid loading plan
- API PASS
- API UNSAFE due to CG
- API UNSAFE due to unassigned payload
- API BLOCKED due to solver failure

## Demonstration

### Scenario A: Normal Loading

Using the original demonstration configuration:

- Maximum ZFW: 355,000 lbs
- Calculated total weight: 352,750 lbs
- Calculated CG: 1028.18 inches
- Unassigned payload groups: 0

Expected result: PASS

### Scenario B: Unassigned Payload

Change Maximum ZFW to 260,000 lbs.

The optimizer may still return Optimal because leaving payload unassigned is allowed by its mathematical model.

However, the Safety Gate detects the unresolved items.

Observed result:

- 12 unassigned payload groups
- Safety Gate: UNSAFE
- Warning: 12 payload groups remain unassigned.

This demonstrates why mathematical optimization and independent validation are different.

## Current Limitations

This is a competition prototype, not a certified aviation load-control system.

- CG limits are illustrative, not certified aircraft-specific envelopes.
- Current application calculations use pounds and inches.
- The wider team specification uses kilograms and metres; conversion and consistent aircraft parameters are required.
- Passenger and checked-baggage reconciliation is not yet implemented.
- Approved cargo offloading must be distinguished from unresolved unassigned payload.
- DCS passenger counts are not yet cross-checked.
- NEEDS REVIEW and human approval workflows are not implemented.
- BLOCKED exists in the API but needs further dashboard integration.
- The four API tests mock solver results; additional real-solver end-to-end tests are needed.

## Integration With Other Modules

The Safety Gate is intended to receive the final loading plan from Module 3 (Load Re-planner) and provide validation results to Module 5 (Control Dashboard).

The team needs to agree on:

1. A shared loading-plan JSON format.
2. Consistent aircraft weight and CG units.
3. Aircraft-specific limits.
4. Passenger and baggage count reconciliation.
5. Shared SAFE / UNSAFE / BLOCKED / NEEDS REVIEW definitions.
6. Handling of approved cargo offloading and passenger removals.

## Original Project

University of Waterloo, Fall 2026 Airport Innovation Challenge:

https://github.com/IdeasClinicUWaterloo/F26-Airport-Innovation-Challenge

## Current Progress

- Independent validation functions implemented.
- Flask API integration completed.
- Dashboard PASS and UNSAFE display tested.
- Eleven automated tests passed.
- Local prototype committed to Git.

The next goal is to integrate this prototype with the team's shared aircraft-swap data structures and operational workflow.
