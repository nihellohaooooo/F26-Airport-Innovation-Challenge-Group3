"""Bag classification, pull ordering, risk flags, and manifest reconciliation."""


def _minutes(value):
    if not value:
        return None
    h, m = str(value).split(":", 1)
    return int(h) * 60 + int(m)


def _removed_ids(rows):
    return {str(p.get("pax_id", p.get("id", ""))).strip() for p in rows
            if p.get("removed_by_dcs") is True or
            str(p.get("removed_by_dcs", "")).lower() in {"true", "1", "yes"}}


def get_removed_passenger_ids(removed_rows):
    return {str(row.get("pax_id", row.get("id", ""))).strip() for row in removed_rows}


def classify_bags(bags, removed_passenger_ids, cutoff):
    cutoff_min = _minutes(cutoff)
    result = []
    for source in bags:
        bag = dict(source)
        owner_removed = bag.get("owner_pax_id", bag.get("owner")) in removed_passenger_ids
        late = bool(bag.get("is_connecting", bag.get("connecting", False))) and \
            _minutes(bag.get("eta")) is not None and cutoff_min is not None and \
            _minutes(bag.get("eta")) > cutoff_min
        # An inbound bag arriving after cutoff cannot be physically intercepted
        # in time, even when its owner was removed. Count it as left behind,
        # rather than claiming it was pulled.
        if late and bag.get("location") == "inbound":
            bag["tracker_status"] = "at_risk"
            bag["pull_reason"] = "connecting bag arrives after loading cutoff"
            bag["at_risk"] = True
        elif owner_removed:
            bag["tracker_status"] = "to_pull"
            bag["pull_reason"] = "owner removed by DCS"
            bag["at_risk"] = False
        elif late:
            bag["tracker_status"] = "at_risk"
            bag["pull_reason"] = "connecting bag arrives after loading cutoff"
            bag["at_risk"] = True
        elif bag.get("location") == "inbound":
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
