"""Write the independent author's bundle (followup/bundle/): what the data stand for, the feeds' fields, the event
grammar and 20 sample rows of each clean feed. Nothing about the matching rules, the planted events or any result.
Usage: python3 -I -B tools/make_bundle.py
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import processor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "followup" / "bundle"


def money(c):
    return f"{c / 100:.2f}"


def write(name, header, rows):
    with (OUT / "samples" / name).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    (OUT / "samples").mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)
    c = county.build()
    cal = c["cal"]
    pays = {p["id"]: p for p in c["mids"]}
    banks = {b["id"]: b for b in c["banks"]}
    lines = {x["id"]: x for x in c["books"]}
    multi = [p for p in c["mids"] if 2 <= len(p["lines"]) <= 4 and p["status"] == "Paid"]
    single = [p for p in c["mids"] if len(p["lines"]) == 1 and p["status"] == "Paid"]
    chosen = rnd.sample(multi, 3) + rnd.sample(single, 9) + rnd.sample([p for p in c["mids"] if p["type"] == "Electronic"], 4) \
        + rnd.sample([p for p in c["mids"] if p["status"] != "Paid"], 4)
    chosen = sorted(chosen, key=lambda p: p["id"])
    ll = [lines[i] for p in chosen for i in p["lines"]][:20]
    write("county_ledger_lines.csv", ["line_id", "payment_doc", "vendor", "invoice", "amount", "date"],
          [[x["id"], x["k1"], x["vendor"], x["invoice"], money(x["c"]), cal.date(x["d"]).isoformat()] for x in ll])
    write("county_payments.csv", ["payment_doc", "check_number", "payment_type", "total", "issue_date", "status"],
          [[p["k1"], p["k2"], p["type"], money(p["c"]), cal.date(p["d"]).isoformat(), p["status"]] for p in chosen])
    bl = [banks[p["t2"]] for p in chosen if p.get("t2") in banks]
    write("county_bank_lines.csv", ["bank_line_id", "reference", "amount", "date"],
          [[b["id"], b["k2"], money(b["c"]), cal.date(b["d"]).isoformat()] for b in bl])
    write("county_voids.csv", ["payment_doc", "date"],
          [[v["k1"], cal.date(v["d"]).isoformat()] for v in sorted(c["voids"], key=lambda v: v["id"])[:20]])
    p = processor.build()
    pc = p["cal"]
    pick = sorted(rnd.sample([m["cid"] for m in p["mids"] if m["kind"] == "charge" and 10 <= m["d"] <= 12], 8))
    extra = [m for m in p["mids"] if m["kind"] in ("refund", "chargeback", "reversal")]
    extra = rnd.sample([m for m in extra if m["kind"] == "refund"], 3) + [m for m in extra if m["kind"] == "chargeback"][:1] \
        + [m for m in extra if m["kind"] == "reversal"][:1]
    rows = [m for m in p["mids"] if m.get("cid") in set(pick)] + extra
    rows = sorted(rows, key=lambda m: (m["d"], m["id"]))[:16]
    batches = sorted({m["grp"] for m in rows})[:4]
    rows += [m for m in p["mids"] if m["kind"] == "payout" and m["grp"] in batches]
    write("processor_settlement_rows.csv", ["row_id", "charge_id", "kind", "currency", "amount", "usd", "batch", "date"],
          [[m["id"], m.get("cid", ""), m["kind"], m.get("cur", "USD"), money(m["c"]), money(m["usd"]), m["grp"],
            pc.date(m["d"]).isoformat()] for m in rows])
    cids = {m.get("cid") for m in rows}
    led = [b for b in p["books"] if b["cid"] in cids]
    led += rnd.sample([b for b in p["books"] if b["cid"] not in cids and b["kind"] != "charge"], 4)
    led += rnd.sample([b for b in p["books"] if b["cid"] not in cids and b["kind"] == "charge"], 20 - len(led))
    led = sorted(led, key=lambda b: (b["d"], b["id"]))[:20]
    write("processor_ledger_items.csv", ["item_id", "charge_id", "kind", "currency", "amount", "date"],
          [[b["id"], b["cid"], b["kind"], b["cur"], money(b["c"]), pc.date(b["d"]).isoformat()] for b in led])
    kb = sorted((b for b in p["banks"] if int(b["k2"]) in set(batches) or b["d"] < 20), key=lambda b: b["d"])[:20]
    write("processor_bank_lines.csv", ["bank_line_id", "remittance", "amount", "date"],
          [[b["id"], b["remittance"], money(b["c"]), pc.date(b["d"]).isoformat()] for b in kb])
    print(f"wrote the bundle samples to {OUT.relative_to(ROOT)}/samples")


if __name__ == "__main__":
    main()
