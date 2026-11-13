"""Breakdown of the hidden-reference test's wrong payments at 5 business days (DESIGN-r2.md, measure b), computed after
version 2 ran: was the payment taken the same amount to the cent, the same supplier, the same issue day? Same pick
rule as tools/run_r2.py; writes results/results-r2-breakdown.json.
Usage: python3 -I -B tools/r2_breakdown.py
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W, TOL = 5, 100


def main():
    c = county.build()
    void_d = {v["k1"]: v["d"] for v in c["voids"]}
    bank_of = {b["t2"]: b for b in c["banks"]}
    pay = {m["id"]: m for m in c["mids"]}
    bucket = defaultdict(list)
    for m in c["mids"]:
        bucket[m["c"] // 100].append(m)
    kinds = Counter()
    for b in c["banks"]:
        D, p = b["d"], b["t2"]
        if D - pay[p]["d"] > W:
            continue
        best = None
        for k in (b["c"] // 100 - 1, b["c"] // 100, b["c"] // 100 + 1):
            for x in bucket.get(k, []):
                if abs(x["c"] - b["c"]) > TOL or not (0 <= D - x["d"] <= W):
                    continue
                if x["id"] != p:
                    if void_d.get(x["doc"], 10 ** 9) <= D:
                        continue
                    xb = bank_of.get(x["id"])
                    if xb is not None and xb["d"] <= D:
                        continue
                if best is None or (x["d"], x["id"]) < (best["d"], best["id"]):
                    best = x
        if best["id"] == p:
            continue
        kinds["wrong"] += 1
        kinds["same_cents" if best["c"] == b["c"] else "within_us1_not_same_cents"] += 1
        kinds["same_issue_day" if best["d"] == pay[p]["d"] else "older_issue_day"] += 1
        kinds["same_supplier" if best["vendor"] == pay[p]["vendor"] else "other_supplier"] += 1
        if best["c"] == b["c"] and best["d"] == pay[p]["d"]:
            kinds["same_cents_and_same_issue_day"] += 1
    out = {"added_after_the_results": True, "computed_after_version_2_ran": True, "window_business_days": W,
           "debits_within_reach_paired_wrong": dict(sorted(kinds.items()))}
    dest = ROOT / "results" / "results-r2-breakdown.json"
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}", json.dumps(out["debits_within_reach_paired_wrong"]))


if __name__ == "__main__":
    main()
