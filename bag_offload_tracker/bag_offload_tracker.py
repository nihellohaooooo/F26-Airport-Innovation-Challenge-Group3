"""Part 2: Bag Offload Tracker
Run python3 bag_offload_tracker.py

To do
- Confirm with your group that lower stack_pos means closer to the top of the stack.
- Decide how to handle a removed passenger’s inbound bag that arrives after cutoff: include it on the pull list, or mark it at risk and left behind. The current code marks it at risk and excludes it from pulls.
- Track bag state transitions (on cart → in hold → loaded, inbound → arrived, to pull → pulled) if you need to demonstrate the full states.
- Add hold-space reservation for likely late bags, if you’re doing that stronger feature.
- Add a simulated scan feed, if you’re doing that stronger feature.
"""



import csv
import json
from pathlib import Path


# Project data lives in ./data relative to this file.
DATA_DIR = Path(__file__).parent / "data"

def to_minutes(hhmm):
    """Convert 'HH:MM' to minutes since midnight, e.g. '19:27' -> 19*60 + 27 =1167"""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)

def load_csv(path):
    """Read a CSV file and return its rows as dictionaries."""
    # open with UTF-8 and return list(csv.DictReader(...))
    with open(path, mode='r', encoding='utf-8') as file:
        return list(csv.DictReader(file))

def load_json(path):
    """Read a JSON file and return its contents."""
    # read and parse JSON
    with open(path, mode='r', encoding='utf-8') as file:
        return json.load(file)

def load_inputs(data_dir=DATA_DIR):
    """Load bags, removed passengers, and flight settings."""
    # read bags.csv, dcs_removed.csv, and flight.json
    # Return a dict, for example: {"bags": ..., "removed": ..., "flight": ...}
    data_dir = Path(data_dir)
    return {
        "bags": load_csv(data_dir / "bags.csv"),
        "removed": load_csv(data_dir / "dcs_removed.csv"),
        "flight": load_json(data_dir / "flight.json"),
    }


def get_removed_passenger_ids(removed_rows):
    """Return a set of passenger IDs removed by the DCS."""
    # build a set using the pax_id column
    return {row["pax_id"].strip() for row in removed_rows}


def classify_bags(bags, removed_passenger_ids, cutoff):
    """Copy/classify every bag and mark bags owned by removed passengers."""
    # don't mutate the original CSV row dictionaries
    # Add fields such as tracker_status and pull_reason to each copied bag.
    # Bags whose owner was removed should be marked "to_pull".
    # Consider connecting inbound bags with ETA after cutoff as "at_risk".
    classified = []

    for bag in bags:
        b = dict(bag)

        # An inbound bag that arrives after cutoff cannot be intercepted in time,
        # even if its owner was removed. Count it as left behind instead of a
        # physical pull task.
        if (
            b["location"] == "inbound"
            and b["eta"]
            and to_minutes(b["eta"]) > to_minutes(cutoff)
        ):
            b["tracker_status"] = "at_risk"
            b["pull_reason"] = "arrives after loading cutoff"
        elif b["owner_pax_id"] in removed_passenger_ids:
            b["tracker_status"] = "to_pull"
            b["pull_reason"] = "owner removed by DCS"
        elif b["location"] == "inbound":
            b["tracker_status"] = "inbound" # arriving on time so wont pull
            b["pull_reason"] = ""
        else:
            b["tracker_status"] = "ok" #no pull the bag is flying
            b["pull_reason"] = ""

        classified.append(b)

    return classified


def build_ordered_pull_list(classified_bags):
    """Return bags to pull in the required order.

    Ordering rules: carts first, then loaded holds, then inbound; within each
    cart/hold, top of stack first. Confirm whether smaller or larger stack_pos
    means closer to the top in your team's data assumptions.
    """
    # filter to_pull bags and sort by location group and stack position
    group_order = {"cart": 0, "hold": 1, "inbound": 2}

    def sort_key(bag):
        location = bag["location"]  # cart_1, hold_FWD, or inbound
        group = group_order[location.split("_")[0]]
        pos = int(bag["stack_pos"]) if bag["stack_pos"] else 0
        return (group, location, pos, bag["eta"], bag["tag"])

    to_pull = [b for b in classified_bags if b["tracker_status"] == "to_pull"]
    return sorted(to_pull, key=sort_key)



def find_connecting_bags_at_risk(classified_bags, cutoff):
    """Return connecting bags that will arrive after the loading cutoff."""
    # compare ETA with cutoff (times are HH:MM strings in flight data)
    return sorted(
        [
            b for b in classified_bags
            if b["is_connecting"] == "true"
            and b["eta"]
            and to_minutes(b["eta"]) > to_minutes(cutoff)
            and b["tracker_status"] == "at_risk"
        ],
        key=lambda b: to_minutes(b["eta"]),
    )

def check_bag_counts(classified_bags, bags_checked):
    """Check all known bags are accounted for and compare with DCS count."""
    # count loaded, pulled, and left-behind bags without double-counting
    # Return a summary and a boolean (or a dict containing both).
    counts = {"flying": 0, "pulled": 0, "left_behind": 0, "unknown": 0}

    for b in classified_bags:
        status = b["tracker_status"]
        if status in ("ok", "inbound"):
            counts["flying"] += 1        # loaded/on cart, or arriving before cutoff
        elif status == "to_pull":
            counts["pulled"] += 1        # owner removed by DCS
        elif status == "at_risk":
            counts["left_behind"] += 1   # arrives after cutoff, will miss the flight
        else:
            counts["unknown"] += 1       # a status we didn't expect

    total = counts["flying"] + counts["pulled"] + counts["left_behind"] + counts["unknown"]
    ok = (total == len(classified_bags)
          and total == bags_checked
          and counts["unknown"] == 0)

    return {
        "ok": ok,
        "counts": counts,
        "total_known": total,
        "dcs_bags_checked": bags_checked,
        "difference": total - bags_checked,
    }

def build_tracker_result(bags, removed_passenger_ids, cutoff, bags_checked):
    """Run tracker steps and package the results for a UI or report."""
    # call classify_bags, build_ordered_pull_list,
    # find_connecting_bags_at_risk, and check_bag_counts.
    # Return a dict with all bag statuses, pull list, risks, and count check.
    classified = classify_bags(bags, removed_passenger_ids, cutoff)
    pull_list = build_ordered_pull_list(classified)
    at_risk = find_connecting_bags_at_risk(classified, cutoff)
    count_check = check_bag_counts(classified, bags_checked)

    return {
        "cutoff": cutoff,
        "bags": classified,          # every bag, with tracker_status + pull_reason
        "pull_list": pull_list,      # to_pull bags, in pull order
        "at_risk": at_risk,          # late connecting bags
        "count_check": count_check,  # totals vs DCS
        "summary": {                 # quick numbers for a header/dashboard
            "total_bags": len(classified),
            "to_pull": len(pull_list),
            "at_risk": len(at_risk),
            "counts_ok": count_check["ok"],
        },
    }

def main():
    """Load demo inputs and print a small tracker summary."""
    # load inputs, get removed IDs, call build_tracker_result, and print
    # useful results (pull tags/order, at-risk bags, and count check).
    inputs = load_inputs()
    flight = inputs["flight"]
    cutoff = flight["loading_cutoff"]

    removed_ids = get_removed_passenger_ids(inputs["removed"])
    result = build_tracker_result(
        inputs["bags"], removed_ids, cutoff, flight["dcs"]["bags_checked"]
    )

    # Header
    print(f"=== Bag Offload Tracker: {flight['flight_no']} "
          f"{flight['origin']}->{flight['destination']} "
          f"({flight['old_aircraft']} -> {flight['new_aircraft']})")
    print(f"Loading cutoff: {cutoff}   Removed passengers: {len(removed_ids)}")

    # Pull list, in order
    print(f"\n--- Pull list ({len(result['pull_list'])} bags, in order) ---")
    for i, b in enumerate(result["pull_list"], start=1):
        where = b["location"]
        if b["stack_pos"]:
            where += f" #{b['stack_pos']}"
        elif b["eta"]:
            where += f" ETA {b['eta']}"
        print(f"{i:>3}. {b['tag']}  {where:<18} owner {b['owner_pax_id']}  {b['weight_kg']} kg")

    # At-risk connecting bags
    print(f"\n--- Connecting bags at risk ({len(result['at_risk'])}) ---")
    if not result["at_risk"]:
        print("  none")
    for b in result["at_risk"]:
        late = to_minutes(b["eta"]) - to_minutes(cutoff)
        print(f"  {b['tag']}  owner {b['owner_pax_id']}  on {b['inbound_flight']}  "
              f"ETA {b['eta']} ({late} min after cutoff)")

    # Count check
    check = result["count_check"]
    c = check["counts"]
    print("\n--- Bag count check ---")
    print(f"  flying {c['flying']} + pulled {c['pulled']} + left behind {c['left_behind']}"
          f" = {check['total_known']}   (DCS = {check['dcs_bags_checked']})")
    if check["ok"]:
        print("  OK: all bags accounted for")
    else:
        print(f"  MISMATCH: off by {check['difference']:+d}"
              + (f", {c['unknown']} bags with unknown status" if c["unknown"] else ""))


if __name__ == "__main__":
    main()
