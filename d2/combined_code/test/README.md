# Demo test suite

These tests are intentionally small enough to explain during a project demo.

From `combined_code/`, run:

```bash
python -m unittest discover -s test -v
```

The engine tests demonstrate:

- **Swap Mapper:** valid seats map to cabin zones, removed passengers are skipped, invalid rows are flagged, and passenger weights use the selected season.
- **Bag Offload Tracker:** cart bags come before hold bags, late inbound bags are left at risk instead of being reported as pulled, and every bag reconciles to the DCS count.
- **Load Re-planner:** higher-priority cargo is retained, lightning mode chooses fewer handling actions, and impossible must-fly cargo is reported infeasible.
- **Safety Gate:** a valid plan is `SAFE`, a passenger count mismatch is `BLOCKED`, and a weight limit violation is `UNSAFE`.

The three pipeline tests then show an end-to-end **SAFE** clear-to-fly plan, a **BLOCKED** DCS count mismatch, and an **UNSAFE** must-fly cargo case. The clear-to-fly demo uses summer weights and makes the sample inbound bags arrive before cutoff, so the normal result demonstrates a plan that can proceed to load-controller approval.
