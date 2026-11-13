"""Declared version 2 (DESIGN-r2.md), added after the results: the fallback rule at every window, the hidden-reference
test, Kaplan-Meier break ages and county money open counted once per payment. Imports the frozen modules and changes
none of them; writes results/results-r2.json.
Usage: python3 -I -B tools/run_r2.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import processor  # noqa: E402
import recon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W0 = 5
SWEEP = [3, 5, 10, 15, 20, 30, 40, 60]
TOL = 100  # cents, the fallback's tolerance as frozen


def usd(c):
    return round(c / 100, 2)


def fallback_sweep(c):
    pay = {m["id"]: m for m in c["mids"]}
    bank = {b["id"]: b for b in c["banks"]}
    out = {}
    for w in SWEEP:
        run = recon.match(c, "R2", w)
        fm = [x for x in recon.false_matches(c, run) if x["join"] == 2]
        fb = [p for p in run["pairs2"] if p[3] == "fallback"]
        fm_pairs = {(x["a"], x["b"]) for x in fm}
        within, beyond, within_type = 0, 0, defaultdict(int)
        for m_id, b_id, D, how in fb:
            b = bank[b_id]
            lag = b["d"] - pay[b["t2"]]["d"]
            if lag <= w:
                within += 1
                within_type[pay[b["t2"]]["type"]] += 1
            else:
                beyond += 1
        out[str(w)] = {"pairs_by_fallback": len(fb),
                       "right_fallback_pairings": sum(1 for m_id, b_id, D, how in fb if (m_id, b_id) not in fm_pairs),
                       "false_matches_bank_join": len(fm),
                       "false_matches_per_1000_bank_lines": round(1000 * len(fm) / len(c["banks"]), 1),
                       "false_matches_usd": usd(sum(x["usd"] for x in fm)),
                       "fallback_bank_line_lag_within_window": within,
                       "fallback_bank_line_lag_within_window_by_type": dict(sorted(within_type.items())),
                       "fallback_bank_line_lag_beyond_window": beyond}
    return out


def hidden_reference(c):
    void_d = {v["k1"]: v["d"] for v in c["voids"]}
    bank_of = {b["t2"]: b for b in c["banks"]}
    pay = {m["id"]: m for m in c["mids"]}
    bucket = defaultdict(list)
    for m in c["mids"]:
        bucket[m["c"] // 100].append(m)
    out = {}
    for w in SWEEP:
        cnt = defaultdict(int)
        for b in c["banks"]:
            D, p = b["d"], b["t2"]
            reach = b["d"] - pay[p]["d"] <= w
            best = None
            for k in (b["c"] // 100 - 1, b["c"] // 100, b["c"] // 100 + 1):
                for x in bucket.get(k, []):
                    if abs(x["c"] - b["c"]) > TOL or not (0 <= D - x["d"] <= w):
                        continue
                    if x["id"] != p:
                        if void_d.get(x["doc"], 10 ** 9) <= D:
                            continue
                        xb = bank_of.get(x["id"])
                        if xb is not None and xb["d"] <= D:
                            continue
                    if best is None or (x["d"], x["id"]) < (best["d"], best["id"]):
                        best = x
            res = "none" if best is None else ("right" if best["id"] == p else "wrong")
            cnt[res] += 1
            if reach:
                cnt["reach"] += 1
                cnt[res + "_reach"] += 1
        n_all = len(c["banks"])
        out[str(w)] = {"debits": n_all, "within_reach": cnt["reach"], "right": cnt["right"], "wrong": cnt["wrong"],
                       "none": cnt["none"], "right_within_reach": cnt["right_reach"], "wrong_within_reach": cnt["wrong_reach"],
                       "none_within_reach": cnt["none_reach"],
                       "wrong_per_1000_within_reach": round(1000 * cnt["wrong_reach"] / cnt["reach"], 1),
                       "wrong_per_1000_debits": round(1000 * cnt["wrong"] / n_all, 1)}
    return out


def km(feeds, run, horizon):
    obs = []
    for join, r, s, e, ca in recon.break_intervals(feeds, run, W0, horizon):
        obs.append((e - s, True) if e <= horizon else (horizon + 1 - s, False))
    times = sorted({t for t, ev in obs if ev})
    by_t = defaultdict(lambda: [0, 0])  # t -> [events, censored]
    for t, ev in obs:
        by_t[t][0 if ev else 1] += 1
    at_risk, surv, med, p90 = len(obs), 1.0, None, None
    for t in sorted(by_t):
        d, cz = by_t[t]
        if d:
            surv *= 1 - d / at_risk
            if med is None and surv <= 0.5:
                med = t
            if p90 is None and surv <= 0.1:
                p90 = t
        at_risk -= d + cz
    return {"breaks": len(obs), "closed": sum(1 for t, ev in obs if ev), "still_open": sum(1 for t, ev in obs if not ev),
            "median": med, "p90": p90, "survival_at_last_event": round(surv, 4), "event_times": len(times)}


def once_per_payment(c, run, lo, hi, horizon):
    pay_usd = {m["id"]: abs(m["usd"]) for m in c["mids"]}
    iv = defaultdict(list)
    n = hi - lo + 1
    both = [0] * (n + 1)
    for join, r, s, e, ca in recon.break_intervals(c, run, W0, horizon):
        pid = r["t1"] if r["kind"] == "line" else (r["id"] if r["kind"] == "payment" else r["t2"])
        iv[pid].append((s, e))
        a, b = max(s, lo), min(e, hi + 1)
        if a < b:
            both[a - lo] += abs(r["usd"])
            both[b - lo] -= abs(r["usd"])
    once = [0] * (n + 1)
    for pid, lst in iv.items():
        lst.sort()
        cs, ce = lst[0]
        merged = []
        for s, e in lst[1:]:
            if s <= ce:
                ce = max(ce, e)
            else:
                merged.append((cs, ce))
                cs, ce = s, e
        merged.append((cs, ce))
        for s, e in merged:
            a, b = max(s, lo), min(e, hi + 1)
            if a < b:
                once[a - lo] += pay_usd[pid]
                once[b - lo] -= pay_usd[pid]

    def mean(arr):
        acc, tot = 0, 0
        for x in arr[:-1]:
            acc += x
            tot += acc
        return tot / n
    return mean(once), mean(both)


def main():
    r1 = json.loads((ROOT / "results" / "results-r1.json").read_text(encoding="utf-8"))
    res = {"version": 2, "added_after_the_results": True, "declared_in": "DESIGN-r2.md and predictions-r2.json",
           "window_business_days_of_version_1": W0}
    c = county.build()
    res["fallback_sweep_county"] = fallback_sweep(c)
    res["hidden_reference_county"] = hidden_reference(c)
    p = processor.build()
    moved_c = sum(m["c"] for m in c["mids"])
    res["break_age_kaplan_meier"] = {"county": {}, "processor": {}}
    res["open_once_per_payment_county"] = {}
    for rule in recon.RULES:
        run = recon.match(c, rule, W0)
        res["break_age_kaplan_meier"]["county"][rule] = km(c, run, county.HORIZON)
        once, both = once_per_payment(c, run, county.FIRST_CLOSE, county.LAST_2024, county.HORIZON)
        frozen = r1["county"]["clean"][rule]["unexplained_mean_usd"]["all"]
        assert abs(usd(both) - frozen) < 0.02, (rule, usd(both), frozen)  # the both-sides figure reproduces
        res["open_once_per_payment_county"][rule] = {
            "mean_usd": usd(once), "share_of_money_in_payments": round(once / moved_c, 4),
            "both_sides_mean_usd_version_1": frozen, "ratio_to_both_sides": round(once / both, 4)}
        runp = recon.match(p, rule, W0)
        res["break_age_kaplan_meier"]["processor"][rule] = km(p, runp, processor.LAST)
    fs, hr = res["fallback_sweep_county"], res["hidden_reference_county"]
    kc, op = res["break_age_kaplan_meier"]["county"], res["open_once_per_payment_county"]
    res["predictions"] = {
        "V1": all(fs[str(w)]["false_matches_per_1000_bank_lines"] >= 1 for w in SWEEP),
        "V2": fs["15"]["false_matches_bank_join"] < fs["5"]["false_matches_bank_join"],
        "V3": hr["5"]["wrong_per_1000_within_reach"] >= 10,
        "V3_opposite": hr["5"]["wrong_per_1000_within_reach"] < 1,
        "V4": hr["15"]["wrong_per_1000_within_reach"] > hr["5"]["wrong_per_1000_within_reach"],
        "V5": kc["R1"]["median"] is None and kc["R2"]["median"] is None and kc["R3"]["median"] is not None
              and 4 <= kc["R3"]["median"] <= 6,
        "V6": 0.4 <= op["R1"]["ratio_to_both_sides"] <= 0.6 and 0.9 <= op["R3"]["ratio_to_both_sides"] <= 1.0,
    }
    out = ROOT / "results" / "results-r2.json"
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    print("PREDICTIONS", json.dumps(res["predictions"]))


if __name__ == "__main__":
    main()
