"""Run the declared study (DESIGN-r1.md sections 6 and 7) and write results/results-r1.json.
Usage: python3 -I -B tools/run_study.py
"""
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import plant  # noqa: E402
import processor  # noqa: E402
import recon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W = 5
SWEEP = [3, 5, 10, 15, 20, 30, 40, 60]


def usd(c):
    return round(c / 100, 2)


def clean_measures(f, rule, lo, hi, horizon, moved):
    run = recon.match(f, rule, W)
    m = recon.money_by_close(f, run, W, lo, hi, horizon)
    n = len(m["all"])
    ends = f["cal"].month_ends(lo, hi)
    fm = recon.false_matches(f, run)
    j2_b = len(run["j2"][1])
    return run, {
        "pairs_books_to_intermediary": len(run["pairs1"]),
        "pairs_intermediary_to_bank": len(run["pairs2"]),
        "pairs_by_fallback": sum(1 for p in run["pairs2"] if p[3] == "fallback"),
        "bank_lines": j2_b,
        "false_matches": len(fm),
        "false_matches_usd": usd(sum(x["usd"] for x in fm)),
        "false_matches_per_1000_bank_lines": round(1000 * sum(1 for x in fm if x["join"] == 2) / j2_b, 1),
        "unexplained_mean_usd": {k: usd(sum(v) / n) for k, v in m.items()},
        "unexplained_mean_share_of_money_moved": round(sum(m["all"]) / n / moved, 4),
        "unexplained_month_end_usd": {f["cal"].date(e).isoformat(): usd(m["all"][e - lo]) for e in ends},
        "unexplained_last_close_usd": {k: usd(v[-1]) for k, v in m.items()},
        "break_age_business_days": recon.break_ages(f, run, W, horizon),
    }


def planted_measures(make, clean, types, rule):
    out = {}
    for t in types:
        f, inst = make(clean, t)
        run = recon.match(f, rule, W)
        fm = recon.false_matches(f, run)
        fm_ids = {x["a"] for x in fm} | {x["b"] for x in fm}
        flags, right, hidden_by_false_match = [], 0, 0
        c2 = Counter()
        for i in inst:
            first, _ = recon.flagged(f, run, W, i["touched"], i["first_d"], i["last_d"])
            fl = first is not None
            flags.append(fl)
            right += (fl if plant.CORRECT[t] == "flag" else not fl)
            if not fl and fm_ids & set(i["touched"]):
                hidden_by_false_match += 1
            if t == "C2":
                bank_id = [x for x in i["touched"] if x.startswith("B")][0]
                p = [x for x in run["pairs2"] if x[1] == bank_id]
                c2["left open" if not p else ("right payment" if p[0][0] == i["note"] else "wrong payment")] += 1
        out[t] = {"instances": len(inst), "correct_call": plant.CORRECT[t], "flagged": sum(flags), "right_calls": right,
                  "not_flagged_through_a_false_match": hidden_by_false_match, "false_matches_in_run": len(fm)}
        if t == "C2":
            out[t]["outcomes"] = dict(c2)
    return out


def sweep(clean):
    res = {}
    f8, inst8 = plant.plant_county(clean, "C8")
    for w in SWEEP:
        run = recon.match(clean, "R3", w)
        brk = {r["id"] for j, r, s, e, ca in recon.break_intervals(clean, run, w, county.HORIZON) if j == 2}
        by = {}
        for typ in ("Paper", "Electronic"):
            cleared = [p for p in clean["mids"] if p["type"] == typ and p["status"] == "Paid"]
            by[typ] = {"cleared_payments": len(cleared), "break_before_clearing": sum(p["id"] in brk for p in cleared)}
            by[typ]["share"] = round(by[typ]["break_before_clearing"] / len(cleared), 4)
        run8 = recon.match(f8, "R3", w)
        delays = []
        for i in inst8:
            first, _ = recon.flagged(f8, run8, w, i["touched"], i["first_d"], i["last_d"], horizon_bd=max(20, w + 5))
            delays.append(None if first is None else first - i["first_d"])
        got = [d for d in delays if d is not None]
        res[str(w)] = {"by_type": by, "never_cleared_flagged": len(got), "never_cleared_delay_median": statistics.median(got) if got else None}
    return res


def tie(clean):
    """books issued less voids less bank debits equals what is still open, payment by payment (a bookkeeping identity
    on clean data, because the bank side is built from the same table)"""
    cal = clean["cal"]
    out = {}
    void_d = {v["k1"]: v["d"] for v in clean["voids"]}
    bank_d = {b["t2"]: b for b in clean["banks"]}
    for e in cal.month_ends(county.FIRST_CLOSE, county.LAST_2024):
        issued = sum(p["c"] for p in clean["mids"] if p["d"] <= e)
        voided = sum(p["c"] for p in clean["mids"] if p["d"] <= e and void_d.get(p["doc"], 10 ** 9) <= e)
        cleared = sum(b["c"] for b in clean["banks"] if b["d"] <= e)
        open_ = sum(p["c"] for p in clean["mids"] if p["d"] <= e and void_d.get(p["doc"], 10 ** 9) > e
                    and (p["id"] not in bank_d or bank_d[p["id"]]["d"] > e))
        out[cal.date(e).isoformat()] = {"issued_less_voids_less_cleared_usd": usd(issued - voided - cleared),
                                        "open_payments_usd": usd(open_), "gap_cents": issued - voided - cleared - open_}
    return out


def main():
    res = {"window_business_days": W}
    # ---------------- county
    c = county.build()
    rows = county.load_rows()
    moved_c = sum(p["c"] for p in c["mids"])
    res["county"] = {
        "feeds": {"ledger_lines": len(c["books"]), "excluded_zero_net_lines": len(c["excluded_lines"]),
                  "register_payments": len(c["mids"]), "bank_lines": len(c["banks"]), "voids": len(c["voids"]),
                  "payments_by_type_status": {f"{k[0]} {k[1]}": v for k, v in
                                              sorted(Counter((p["type"], p["status"]) for p in c["mids"]).items())},
                  "multi_line_payments": sum(1 for p in c["mids"] if len(p["lines"]) > 1),
                  "multi_line_money_usd": usd(sum(p["c"] for p in c["mids"] if len(p["lines"]) > 1)),
                  "money_in_payments_usd": usd(moved_c)},
        "anomalies": {"several_disbursement_dates": len(c["anomalies"]["several_dates"]),
                      "zero_net_documents": len(c["anomalies"]["net_zero_or_less"]),
                      "never_cleared_payments": len(c["anomalies"]["never_cleared"]),
                      "never_cleared_usd": usd(sum(p["c"] for p in c["mids"] if p["doc"] in set(c["anomalies"]["never_cleared"])))},
        "published_totals_usd": {k: usd(v) for k, v in county.published_totals(rows).items()},
        "tie_month_ends": tie(c),
        "clean": {}, "planted": {},
    }
    for rule in recon.RULES:
        _, m = clean_measures(c, rule, county.FIRST_CLOSE, county.LAST_2024, county.HORIZON, moved_c)
        res["county"]["clean"][rule] = m
        res["county"]["planted"][rule] = planted_measures(plant.plant_county, c, plant.COUNTY_TYPES, rule)
    res["county"]["window_sweep_R3"] = sweep(c)
    # ---------------- processor
    p = processor.build()
    moved_p = sum(b["c"] for b in p["banks"])
    res["processor"] = {
        "feeds": {"charges": p["charges"], "ledger_items": len(p["books"]),
                  "settlement_rows": Counter(m["kind"] for m in p["mids"]), "bank_lines": len(p["banks"]),
                  "carried_batches": p["carried_batches"], "money_paid_out_usd": usd(moved_p),
                  "fees_usd": usd(-sum(m["usd"] for m in p["mids"] if m["kind"] == "fee"))},
        "clean": {}, "planted": {}}
    for rule in recon.RULES:
        _, m = clean_measures(p, rule, processor.FIRST_MEASURED, processor.LAST, processor.LAST, moved_p)
        res["processor"]["clean"][rule] = m
        res["processor"]["planted"][rule] = planted_measures(plant.plant_processor, p, plant.PROC_TYPES, rule)
    out = ROOT / "results" / "results-r1.json"
    out.write_text(json.dumps(res, indent=1, sort_keys=False, default=dict) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
