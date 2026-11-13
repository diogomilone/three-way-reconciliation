"""The synthetic card processor's three feeds (DESIGN-r1.md section 2b). Every rule here is an assumption of the study.

Books: the platform ledger (charges, refunds, chargebacks, reversals in presentment currency). Settlement report: one
row per settled charge, refund, chargeback, reversal and fee, plus one payout row per batch, shaped by a published
settlement report's journal types. Bank: one credit per payout, shaped by an ISO 20022 camt.053 entry.
"""
import datetime as dt
import math
import random
from collections import defaultdict

from recon import Calendar

SEED = 20261111
CAL = Calendar(dt.date(2025, 1, 1), dt.date(2025, 6, 30))
N = len(CAL.days)
FIRST_MEASURED = CAL.bday(dt.date(2025, 1, 15))
LAST = N - 1
PRICES = [900, 1900, 2900, 4900, 9900, 19900]
PRICE_P = [0.15, 0.25, 0.25, 0.2, 0.1, 0.05]


def rate(i):
    return round(0.72 * (1 + 0.02 * math.sin(2 * math.pi * i / 60)), 6)


def to_usd(cents, cur, i):
    return cents if cur == "USD" else int(round(cents * rate(i)))


def fee_cents(usd, pct=0.029, fixed=30):
    return int(round(usd * pct)) + fixed


def generate(seed=SEED):
    rnd = random.Random(seed)
    charges = []
    lag_of_day = {}
    for i in range(N):
        lag_of_day[i] = rnd.choices([1, 2, 3], [0.7, 0.25, 0.05])[0]
        for _ in range(rnd.randint(120, 180)):
            if rnd.random() < 0.8:
                amt = rnd.choices(PRICES, PRICE_P)[0]
            else:
                amt = rnd.randint(500, 50000)
            cur = "USD" if rnd.random() < 0.8 else "CAD"
            charges.append({"cid": f"ch{len(charges):06d}", "day": i, "cur": cur, "amt": amt})
    events = []  # (kind, charge, ledger day, batch day)
    for ch in charges:
        events.append(("charge", ch, ch["day"], ch["day"] + lag_of_day[ch["day"]]))
        u = rnd.random()
        if u < 0.03:
            rd = ch["day"] + rnd.randint(1, 20)
            events.append(("refund", ch, rd, rd + 1))
        elif rnd.random() < 0.003:
            dd = ch["day"] + rnd.randint(10, 40)
            events.append(("chargeback", ch, dd + 1, dd + 1))
            if rnd.random() < 0.4:
                vd = dd + 1 + rnd.randint(15, 30)
                events.append(("reversal", ch, vd, vd))
    return charges, events


def build(seed=SEED):
    charges, events = generate(seed)
    books, mids, banks = [], [], []
    sign = {"charge": 1, "refund": -1, "chargeback": -1, "reversal": 1}
    batch_rows = defaultdict(list)
    for kind, ch, lday, bday in events:
        if bday > LAST:
            continue  # settles after the period: not in the report
        usd = to_usd(ch["amt"], ch["cur"], bday)
        rid = f"S{kind[:2]}{ch['cid'][2:]}"
        row = {"id": rid, "kind": kind, "k1": f"{ch['cid']}|{kind}", "c": ch["amt"], "cur": ch["cur"],
               "usd": sign[kind] * usd, "d": bday, "grp": bday, "t1": None, "cid": ch["cid"]}
        mids.append(row)
        batch_rows[bday].append(row)
        if kind == "charge":
            f = {"id": f"Sfe{ch['cid'][2:]}", "kind": "fee", "k1": None, "c": fee_cents(usd), "cur": "USD",
                 "usd": -fee_cents(usd), "d": bday, "grp": bday, "t1": None, "cid": ch["cid"]}
            mids.append(f)
            batch_rows[bday].append(f)
        if lday <= LAST:
            led = {"id": f"L{kind[:2]}{ch['cid'][2:]}", "kind": kind, "k1": f"{ch['cid']}|{kind}", "c": ch["amt"],
                   "cur": ch["cur"], "usd": sign[kind] * to_usd(ch["amt"], ch["cur"], lday), "d": lday, "t1": rid,
                   "cid": ch["cid"]}
            row["t1"] = led["id"]
            books.append(led)
    # ledger items whose row settles after the period keep t1 None
    row_ids = {m["id"] for m in mids}
    for b in books:
        if b["t1"] not in row_ids:
            b["t1"] = None
    carry, carried = [], 0
    for bday in sorted(batch_rows):
        rows = carry + batch_rows[bday]
        net = sum(r["usd"] for r in rows)
        if net <= 0:  # carried into the next batch (design section 2b)
            carry, carried = rows, carried + 1
            continue
        carry = []
        for r in rows:
            r["grp"] = bday
        po = {"id": f"PO{bday}", "kind": "payout", "k1": None, "k2": str(bday), "c": net, "usd": net, "d": bday,
              "grp": bday, "t2": None}
        mids.append(po)
        if bday + 1 <= LAST:
            bl = {"id": f"K{bday}", "kind": "bankline", "k2": str(bday), "c": net, "usd": net, "d": bday + 1,
                  "t2": po["id"], "remittance": f"batch {bday}"}
            po["t2"] = bl["id"]
            banks.append(bl)
    return {"kind": "processor", "books": books, "mids": mids, "banks": banks, "voids": [], "cal": CAL,
            "charges": len(charges), "carried_batches": carried}


def camt_rows(feeds):
    """the bank feed as camt.053-shaped entries, for the download"""
    out = []
    for b in feeds["banks"]:
        d = CAL.date(b["d"]).isoformat()
        out.append({"NtryRef": b["id"], "BookgDt": d, "ValDt": d, "Amt": f"{b['c'] / 100:.2f}", "Ccy": "USD",
                    "CdtDbtInd": "CRDT", "AcctSvcrRef": f"AS{b['id'][1:]:0>8}", "Ustrd": b["remittance"]})
    return out
