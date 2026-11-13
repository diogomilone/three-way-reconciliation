"""Build the county's three feeds from the published FY2024 extract (DESIGN-r1.md section 2a).

Books: one ledger line per published row. Register: one payment per document whose lines net to more than zero.
Bank: one debit per Paid payment on its clearance date. Voids: one per Cancelled payment on its cancel date.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
from collections import defaultdict
from pathlib import Path

from recon import Calendar

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "county-fy2024.csv.gz"
SHA256 = "897aaea38ed2a1281f9eaa2b21211970166842fb764d97a211fcceebd10f9791"
CAL = Calendar(dt.date(2023, 12, 1), dt.date(2026, 3, 31))
FIRST_CLOSE = CAL.bday(dt.date(2024, 1, 2))
LAST_2024 = CAL.bday(dt.date(2024, 12, 31))
HORIZON = CAL.bday(dt.date(2026, 2, 6))


def day(s):
    return dt.date.fromisoformat(s[:10])


def cents(s):
    return int(round(float(s) * 100))


def load_rows():
    raw = gzip.open(DATA).read()
    assert hashlib.sha256(raw).hexdigest() == SHA256, "the county extract does not match its pinned sha256"
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def build(rows=None):
    rows = load_rows() if rows is None else rows
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["dis_doc_id"], rows[i]["vendor_invoice_no"],
                                                    cents(rows[i]["amount"]), i))
    books, by_doc = [], defaultdict(list)
    for n, i in enumerate(order):
        r = rows[i]
        rec = {"id": f"L{n:05d}", "kind": "line", "k1": r["dis_doc_id"], "c": cents(r["amount"]), "usd": cents(r["amount"]),
               "d": CAL.bday(day(r["disb_date"])), "date": r["disb_date"][:10], "vendor": r["vendor_code"],
               "invoice": r["vendor_invoice_no"], "doc": r["dis_doc_id"], "t1": None}
        books.append(rec)
        by_doc[r["dis_doc_id"]].append((rec, r))
    mids, banks, voids, anomalies = [], [], [], {"several_dates": [], "net_zero_or_less": [], "never_cleared": []}
    for doc in sorted(by_doc):
        recs = by_doc[doc]
        r0 = recs[0][1]
        total = sum(x["c"] for x, _ in recs)
        if len({x["date"] for x, _ in recs}) > 1:
            anomalies["several_dates"].append(doc)
        if total <= 0:  # Amendment 1: all are exactly zero (voids carrying their reversing lines); out of every feed
            anomalies["net_zero_or_less"].append(doc)
            for x, _ in recs:
                x["excluded"] = True
            continue
        pid = f"P{doc}"
        issue = max(day(r["disb_date"]) for _, r in recs)
        pay = {"id": pid, "kind": "payment", "k1": doc, "k2": r0["check_no"], "doc": doc, "c": total, "usd": total,
               "d": CAL.bday(issue), "date": issue.isoformat(), "type": r0["payment_type"], "status": r0["check_status"],
               "vendor": r0["vendor_code"], "t2": None, "lines": [x["id"] for x, _ in recs]}
        for x, _ in recs:
            x["t1"] = pid
        mids.append(pay)
        cc = r0["check_clearance_or_cancel_date"]
        if r0["check_status"] == "Paid":
            b = {"id": f"B{doc}", "kind": "bankline", "k2": r0["check_no"], "c": total, "usd": total,
                 "d": CAL.bday(day(cc)), "date": cc[:10], "t2": pid}
            pay["t2"] = b["id"]
            banks.append(b)
        elif r0["check_status"] == "Cancelled":
            voids.append({"id": f"V{doc}", "kind": "void", "k1": doc, "d": CAL.bday(day(cc)), "date": cc[:10]})
        else:
            anomalies["never_cleared"].append(doc)
    excluded = [x for x in books if x.get("excluded")]
    books = [x for x in books if not x.get("excluded")]
    return {"kind": "county", "books": books, "excluded_lines": excluded, "mids": mids, "banks": banks, "voids": voids, "anomalies": anomalies,
            "cal": CAL}


def published_totals(rows=None):
    rows = load_rows() if rows is None else rows
    t = defaultdict(int)
    for r in rows:
        t[r["check_status"]] += cents(r["amount"])
    return {"all": sum(t.values()), **dict(t)}
