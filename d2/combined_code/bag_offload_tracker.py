"""Bag classification, pull ordering, risk flags, and manifest reconciliation."""
import re

from common import parse_bool


def _minutes(value):
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*", str(value))
    if not match:
        return None
    hour, minute, second = (int(part or 0) for part in match.groups())
    if hour > 23 or minute > 59 or second > 59:
        return None
    return hour * 60 + minute + second / 60


def _after_cutoff(eta, cutoff):
    if eta is None or cutoff is None:
        return False
    # The manifests store clock times without dates. Treat an early-morning ETA
    # as next-day only when the cutoff is late evening; e.g. 00:10 after 23:50.
    if cutoff >= 22 * 60 and eta <= 2 * 60:
        eta += 24 * 60
    return eta > cutoff


def _known_location(location):
    value = str(location or "").strip().lower()
    return (value == "inbound" or value == "cart" or value.startswith("cart_")
            or value == "hold" or value.startswith("hold_"))


def classify_bags(bags, removed_passenger_ids, cutoff):
    cutoff_min = _minutes(cutoff)
    removed_ids = {str(pid).strip() for pid in removed_passenger_ids}
    result = []
    for source in bags:
        bag = dict(source)
        owner = str(bag.get("owner_pax_id", bag.get("owner", ""))).strip()
        owner_removed = owner in removed_ids
        location = str(bag.get("location", "")).strip().lower()
        eta_min = _minutes(bag.get("eta"))
        location_known = _known_location(location)
        is_connecting = parse_bool(bag.get("is_connecting", bag.get("connecting", False)))
        late = _after_cutoff(eta_min, cutoff_min) and (location == "inbound" or is_connecting)

        if not location_known:
            bag["tracker_status"] = "unknown"
            bag["pull_reason"] = "bag location unknown; hold off flight pending confirmation"
            bag["at_risk"] = True
        elif location == "inbound" and (eta_min is None or cutoff_min is None):
            bag["tracker_status"] = "at_risk"
            bag["pull_reason"] = "inbound arrival time or loading cutoff unknown"
            bag["at_risk"] = True
        # An inbound bag arriving after cutoff cannot be physically intercepted
        # in time, even when its owner was removed.
        elif late and location == "inbound":
            bag["tracker_status"] = "at_risk"
            bag["pull_reason"] = "inbound bag arrives after loading cutoff"
            bag["at_risk"] = True
        elif owner_removed:
            bag["tracker_status"] = "to_pull"
            bag["pull_reason"] = "owner removed by DCS"
            bag["at_risk"] = False
        elif late:
            bag["tracker_status"] = "at_risk"
            bag["pull_reason"] = "connecting bag arrives after loading cutoff"
            bag["at_risk"] = True
        elif location == "inbound":
            bag["tracker_status"] = "inbound"
            bag["pull_reason"] = "arrives before loading cutoff"
        else:
            bag["tracker_status"] = "ok"
            bag["pull_reason"] = ""
            bag["at_risk"] = False
        result.append(bag)
    return result


def build_ordered_pull_list(classified_bags):
    group_order = {"cart": 0, "hold": 1, "inbound": 2}
    def key(b):
        loc = str(b.get("location", ""))
        group = loc.split("_", 1)[0]
        return (group_order.get(group, 3), loc, int(b.get("stack_pos") or 0), str(b.get("tag", "")))
    return sorted((b for b in classified_bags if b["tracker_status"] == "to_pull"), key=key)


def find_connecting_bags_at_risk(classified_bags):
    return sorted((b for b in classified_bags if b.get("at_risk") or b["tracker_status"] == "at_risk"),
                  key=lambda b: (_minutes(b.get("eta")) or 0, str(b.get("tag", ""))))


def check_bag_counts(classified_bags, bags_checked):
    counts = {"flying": 0, "pulled": 0, "left_behind": 0, "unknown": 0}
    for bag in classified_bags:
        status = bag.get("tracker_status")
        if status in {"ok", "inbound"}:
            counts["flying"] += 1
        elif status == "to_pull":
            counts["pulled"] += 1
        elif status == "at_risk":
            counts["left_behind"] += 1
        else:
            counts["unknown"] += 1
    total = sum(counts.values())
    return {"ok": total == len(classified_bags) == int(bags_checked) and counts["unknown"] == 0,
            "counts": counts, "total_known": total, "dcs_bags_checked": int(bags_checked),
            "difference": total - int(bags_checked)}


def build_tracker_result(bags, removed_passenger_ids, cutoff, bags_checked):
    classified = classify_bags(bags, removed_passenger_ids, cutoff)
    pulls = build_ordered_pull_list(classified)
    at_risk = find_connecting_bags_at_risk(classified)
    counts = check_bag_counts(classified, bags_checked)
    return {"cutoff": cutoff, "bags": classified, "pull_list": pulls, "at_risk": at_risk,
            "count_check": counts,
            "summary": {"total_bags": len(classified), "to_pull": len(pulls),
                        "at_risk": len(at_risk), "counts_ok": counts["ok"]}}
