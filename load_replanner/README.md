# 3 · Load Re-planner

Decides which hold each bag and cargo item goes in after an aircraft swap: **safely, with the fewest handling jobs, and with a plain reason for every decision.**

> Not a certified weight-and-balance system. Aircraft data is illustrative. A qualified load controller approves every plan.

**Code:** [`combined_code/replanner.py`](../combined_code/replanner.py) · called by [`combined_code/pipeline.py`](../combined_code/pipeline.py)

## Where it fits

```
1. Swap Mapper  →  2. Bag Offload Tracker  →  3. Load Re-planner  →  4. Safety Gate  →  5. Dashboard
   passenger weight     bags still flying         hold for every         independent        shows plan
   per cabin zone       (pulled bags removed)     bag + cargo item       re-check           + reasons
```

The DCS decides which passengers fly. Removed passengers and their bags are taken out **before** this step, so they never enter the calculation.

## Inputs

| Input | From |
| --- | --- |
| Fixed weight and moment (aircraft + passengers, incl. safety buffer) | Swap Mapper zone weights, via `pipeline.py` |
| Bags still flying, with current hold | Bag Offload Tracker |
| Cargo: weight, volume, priority (1 = most important), DG class, current hold, must-fly flag | Scenario file |
| New aircraft limits: hold weight/volume, DG classes forbidden per hold, MZFW, CG limits, CG target | `aircraft_profiles.json` |
| Options: `lightning_mode`, `time_limit_s` | Dashboard / command line |

## How it decides

**Hard rules (never broken)**
- Each hold's weight and volume limit
- Max zero-fuel weight (MZFW)
- CG between the forward and aft limits (written as `moment ≥ fwd × weight` and `moment ≤ aft × weight`, so it stays linear)
- Dangerous goods only in holds that allow their class
- Must-fly items always fly

**Goals, solved one at a time in strict order.** Each goal's best value is locked in before the next is solved, so a later goal can never make an earlier one worse.

1. Leave no bags behind
2. Bump the least important cargo
3. Fewest handling jobs on items already loaded (moves + offloads)
4. CG as close as possible to the fuel-efficient target

**Lightning mode** swaps goals 2 and 3: after a lightning hold, fewest handling jobs comes before keeping cargo.

**Strict cargo priority.** Leaving an item behind costs `10^(8 − priority) + kg`: each priority level costs 10× the next, so a lower-priority item is always removed first, and weight only breaks ties within the same priority. An earlier version used *weight × priority*, which on the A220 dropped fresh salmon (priority 2) to keep auto parts (priority 3).

The solver is PuLP (CBC) with a 10-second time limit, so it can never freeze the demo. The demo scenarios solve in about 0.2 s.

## Outputs

`solve_load_plan(bags, cargo, aircraft, fixed_weight, fixed_moment, options)` returns:

| Field | Meaning |
| --- | --- |
| `status` | `OPTIMAL`, `INFEASIBLE` or `ERROR` |
| `bag_holds`, `cargo_holds` | Hold for every item that flies |
| `moves` | Loaded items that change hold |
| `offloads` | Loaded items that must come back out |
| `handling_actions` | `moves + offloads`: the extra ramp work caused by re-planning |
| `cargo_bumped` | Cargo not flying, each with its reason |
| `bags_left_behind` | Bags the plan could not place |
| `reason` | Plain explanation when no safe plan exists |
| `objective_values` | Best value of each goal |

## Messages for ground staff and load control

Every instruction uses one format:

```
<ACTION> <ID> <item> (<kg> kg): <what to do>. Reason: <why>.
```

| Action | Meaning |
| --- | --- |
| `MOVE` | Shift a loaded item to another hold |
| `OFFLOAD` | Take a loaded item out of the aircraft |
| `DO NOT LOAD` | Leave an item on the dock or cart |
| `UNSAFE: do not load` | No safe plan exists; a human decision is needed |

Examples:

```
MOVE C05 Auto parts (698 kg): FWD -> BULK. Reason: FWD hold 481 kg over limit; BULK keeps CG closest to target.
OFFLOAD C07 E-commerce pallet (540 kg): remove from AFT. Reason: ZFW 394 kg over MZFW; priority 5, lowest priority removed first.
DO NOT LOAD C08 Furniture parts (420 kg): leave on dock. Reason: ZFW 394 kg over MZFW; lightning mode, fewest handling jobs.
UNSAFE: do not load. Reason: aircraft + passengers 150 kg over MZFW with no bags or cargo. Action: DCS / load control decision required.
```

When no safe plan exists, the re-planner checks the causes in order and names up to two: aircraft + passengers over MZFW; a must-fly item too heavy, too big or not allowed in any hold; must-fly cargo over the available weight; otherwise how far the CG stays outside its limits in the best possible loading. **It never bends a limit to produce a plan.**

Terms: **ZFW** = zero-fuel weight · **MZFW** = maximum zero-fuel weight · **CG** = centre of gravity, in metres from the nose.

## How it behaves in the demo story

A321 → A320 swap on a winter evening. The forward hold was loaded for the bigger aircraft and is now over the A320's limit.

| Situation | What the re-planner does |
| --- | --- |
| Normal re-plan | Moves the one item that fixes the overloaded forward hold; everything else stays where it is |
| Winter + safety buffer | The aircraft would be over MZFW, so the lowest-priority cargo is offloaded |
| Lightning mode | Leaves cargo that is still on the dock instead, so no unloading is needed: fewer handling jobs, but a more important item stays behind |
| No safe plan possible | Reports UNSAFE with the cause and the numbers, and hands the decision to DCS / load control |

## Assumptions and limits

- Units: kg, m³, metres from the nose
- Aircraft arms, CG limits and per-hold DG restrictions are illustrative, not approved airline data
- Passenger weights: Transport Canada standard weights (summer/winter), from the Swap Mapper
- Each bag and cargo item is placed individually (no ULD/container build-up)
- Real dangerous-goods carriage follows the ICAO Technical Instructions / IATA DGR and Transport Canada's TDG Regulations. For example, standalone lithium-ion batteries (UN 3480) are cargo-aircraft-only and may not be carried as cargo on a passenger aircraft at all.

## With more time

- **From-scratch comparison:** a quick test needed about 90 handling jobs when re-planning from scratch, against 1 with this approach
- **Cargo-aircraft-only rule:** never plan such items onto a passenger aircraft
- **What-if margins:** e.g. "+N passengers still fit in zone X"
- **Backup method:** a simple greedy plan if the solver fails
- **Estimated handling time** compared with the time left before the loading cutoff
