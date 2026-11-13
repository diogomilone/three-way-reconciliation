"""Declared version 4 (DESIGN-r4.md), added after the results: the declared run's breaks by kind (count and money) and
the tie-out of the year's money to figures the county publishes. Imports the frozen county and recon modules and
changes neither; writes results/results-r4.json once.
Usage: python3 -I -B tools/run_r4.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import recon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "results-r4.json"
PRED = json.loads((ROOT / "predictions-r4.json").read_text(encoding="utf-8"))
WAITS = PRED["waits_business_days"]
KINDS = list(PRED["kinds"])


def kind_of(join, r):
    """DESIGN-r4 section 2, in order; every break record gets exactly one kind."""
    if join == 2 and r.get("kind") == "payment":
        if r["type"] == "Paper" and r["status"] == "Paid":
            return "K1"
        if r["status"] == "Disbursed":
            return "K2"
        if r["status"] == "Cancelled":
            return "K3"
        if r["type"] == "Electronic":
            return "K4"
    if join == 1 and r.get("kind") != "payment":
        return "K5"
    return "K6"


def usd(cents):
    return round(cents / 100, 2)


def main():
    if OUT.exists():
        sys.exit(f"{OUT} exists; version 4 is written once")
    c = county.build()
    rows = county.load_rows()
    table = {}
    for w in WAITS:
        run = recon.match(c, "R3", w)
        n, money = defaultdict(int), defaultdict(int)
        for join, r, s, e, ca in recon.break_intervals(c, run, w, county.HORIZON):
            k = kind_of(join, r)
            n[k] += 1
            money[k] += abs(r["usd"])
        table[str(w)] = {k: {"breaks": n[k], "usd": usd(money[k])} for k in KINDS}
        table[str(w)]["all"] = {"breaks": sum(n.values()), "usd": usd(sum(money.values()))}
        table[str(w)]["break_age_check"] = recon.break_ages(c, run, w, county.HORIZON)["breaks"]
        assert table[str(w)]["all"]["breaks"] == table[str(w)]["break_age_check"]

    pub = county.published_totals(rows)
    bank_total = sum(b["c"] for b in c["banks"])
    run5 = recon.match(c, "R3", 5)
    fm = recon.false_matches(c, run5)
    pay = {m["id"]: m for m in c["mids"]}
    to_the_cent = all(pay[b["t2"]]["c"] == b["c"] for b in c["banks"])
    fund100 = sum(county.cents(r["amount"]) for r in rows if r["fund"] == "100")
    rep = PRED["report_figures_usd_thousands"]
    gov, gen = rep["governmental_funds_total_expenditures"] * 1000, rep["general_fund_total_expenditures"] * 1000
    tie = {
        "T1_status_totals_usd": {k: usd(v) for k, v in pub.items()},
        "T1_gap_cents": pub["all"] - pub["Paid"] - pub["Disbursed"] - pub["Cancelled"],
        "T2_bank_lines_usd": usd(bank_total),
        "T2_gap_cents": bank_total - pub["Paid"],
        "T2_is_identity": True,
        "T3_bank_lines": len(c["banks"]),
        "T3_wrong_pairings": len(fm),
        "T3_every_pair_to_the_cent": to_the_cent,
        "T4_report": rep["source"],
        "T4_pdf_sha256": rep["pdf_sha256"],
        "T4_vendor_payments_usd": usd(pub["all"]),
        "T4_governmental_funds_expenditures_usd": gov,
        "T4_gap_all_funds_usd": round(gov - usd(pub["all"]), 2),
        "T4_share_all_funds": round(usd(pub["all"]) / gov, 4),
        "T4_fund_100_vendor_payments_usd": usd(fund100),
        "T4_general_fund_expenditures_usd": gen,
        "T4_gap_general_fund_usd": round(gen - usd(fund100), 2),
        "T4_share_general_fund": round(usd(fund100) / gen, 4),
    }
    t5, t15 = table["5"], table["15"]
    pred = {
        "V4-1": all(table[str(w)]["K2"] == {"breaks": 229, "usd": 5861259.68} for w in WAITS),
        "V4-2": all(table[str(w)]["K4"]["breaks"] == 0 for w in WAITS),
        "V4-3": t5["K1"]["breaks"] == 3700 and t15["K1"]["breaks"] == 794,
        "V4-4": t5["K3"]["breaks"] == 24 and t5["K5"]["breaks"] == 0 and t5["all"]["breaks"] == 3953,
        "V4-5": all(table[str(w)]["K1"]["usd"] > table[str(w)]["K2"]["usd"] for w in WAITS),
        "V4-6": t15["K1"]["usd"] < t5["K1"]["usd"] / 4,
        "V4-7": tie["T1_gap_cents"] == 0 and tie["T2_gap_cents"] == 0 and tie["T3_wrong_pairings"] == 0 and to_the_cent,
        "V4-8": tie["T4_share_all_funds"] < 0.5 and tie["T4_share_general_fund"] < 1 / 3,
    }
    out = {"study": "three-way-reconciliation", "version": 4, "added_after_the_results": True,
           "break_table_county_whole_payment": table, "tie_out_county": tie, "predictions": pred}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    tmp.rename(OUT)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
