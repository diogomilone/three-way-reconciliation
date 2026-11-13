"""Planted events (DESIGN-r1.md section 5 and amendment 2). Each function takes clean feeds, returns a changed copy and
the instances: the records each touched (created, changed, their true counterparts, and the counterparts of removed
records), its first and last record dates, and the correct call."""
import copy
import random

import county
import processor

N_INST = 20
COUNTY_SEED = 41101
PROC_SEED = 41201
CORRECT = {"C1": "flag", "C2": "explain", "C3": "flag", "C4": "flag", "C5": "flag", "C6": "flag", "C7": "explain",
           "C8": "flag", "X1": "explain", "X2": "flag", "X3": "flag", "X4": "flag", "X5": "flag", "X6": "explain",
           "X7": "flag"}


def _inst(touched, ds, note=""):
    return {"touched": sorted(set(t for t in touched if t)), "first_d": min(ds), "last_d": max(ds), "note": note}


# ---------------------------------------------------------------- county
def _county_index(f):
    pay = {p["id"]: p for p in f["mids"]}
    bank = {b["id"]: b for b in f["banks"]}
    return pay, bank


def _max_check(f):
    nums = [int(p["k2"]) for p in f["mids"] if str(p["k2"]).isdigit()]
    return max(nums)


def plant_county(clean, t):
    f = copy.deepcopy({k: v for k, v in clean.items() if k != "cal"})
    f["cal"] = clean["cal"]
    rnd = random.Random(COUNTY_SEED + int(t[1:]))
    pay, bank = _county_index(f)
    paid = sorted((p for p in f["mids"] if p["status"] == "Paid" and p["t2"] in bank), key=lambda p: p["id"])
    out = []
    if t == "C1":
        for p in rnd.sample(paid, N_INST):
            b = bank[p["t2"]]
            n = dict(b, id=b["id"] + "dup", d=b["d"] + rnd.randint(1, 3), t2=None)
            f["banks"].append(n)
            out.append(_inst([n["id"]], [n["d"]]))
    elif t == "C2":
        for p in rnd.sample([p for p in paid if len(str(p["k2"])) >= 2], N_INST):
            b = bank[p["t2"]]
            k = str(b["k2"])
            nk = k[:-2] + k[-1] + k[-2]
            if nk == k:
                nk = k[:-1] + str((int(k[-1]) + 1) % 10)
            b["k2"] = nk
            out.append(_inst([b["id"], p["id"]], [p["d"], b["d"]], note=p["id"]))
    elif t == "C3":
        for p in rnd.sample([p for p in paid if p["c"] >= 1000], N_INST):
            b = bank[p["t2"]]
            dollars, cts = divmod(b["c"], 100)
            s = str(dollars)
            if s[-1] != s[-2]:
                nd = int(s[:-2] + s[-1] + s[-2])
                b["c"] = nd * 100 + cts
            else:
                b["c"] += 900
            b["usd"] = b["c"]
            out.append(_inst([b["id"], p["id"]], [p["d"], b["d"]]))
    elif t == "C4":
        top = _max_check(f)
        lines = {x["id"]: x for x in f["books"]}
        for i, p in enumerate(rnd.sample(paid, N_INST)):
            ln = max((lines[x] for x in p["lines"] if lines[x]["c"] > 0), key=lambda x: (x["c"], x["id"]))
            doc = "DUP" + p["doc"]
            d2 = p["d"] + rnd.randint(5, 20)
            chk = str(top + 5000 + i)
            nl = dict(ln, id=ln["id"] + "dup", k1=doc, doc=doc, d=d2, t1="P" + doc)
            np_ = dict(p, id="P" + doc, k1=doc, k2=chk, doc=doc, c=ln["c"], usd=ln["c"], d=d2, t2="B" + doc,
                       lines=[nl["id"]])
            nb = {"id": "B" + doc, "kind": "bankline", "k2": chk, "c": ln["c"], "usd": ln["c"], "d": d2 + 3, "t2": np_["id"]}
            f["books"].append(nl)
            f["mids"].append(np_)
            f["banks"].append(nb)
            out.append(_inst([nl["id"], np_["id"], nb["id"]], [d2, d2 + 3]))
    elif t == "C5":
        for p in rnd.sample([p for p in paid if bank[p["t2"]]["d"] - p["d"] >= 3], N_INST):
            b = bank[p["t2"]]
            f["voids"].append({"id": "V" + p["doc"] + "planted", "kind": "void", "k1": p["doc"], "d": p["d"] + 2})
            out.append(_inst([b["id"], p["id"]], [p["d"], b["d"]]))
    elif t == "C6":
        top = _max_check(f)
        lo, hi = county.FIRST_CLOSE, county.LAST_2024
        for i in range(N_INST):
            other = rnd.choice(paid)
            n = {"id": f"BX{i:02d}", "kind": "bankline", "k2": str(top + 1000 + i), "c": other["c"], "usd": other["c"],
                 "d": rnd.randint(lo, hi), "t2": None}
            f["banks"].append(n)
            out.append(_inst([n["id"]], [n["d"]]))
    elif t == "C7":
        cal = f["cal"]
        ends = set(cal.month_ends(county.FIRST_CLOSE, county.LAST_2024))
        last3 = {e - k for e in ends for k in range(3)}
        elig = [p for p in paid if p["type"] == "Electronic" and p["d"] in last3]
        for p in rnd.sample(elig, N_INST):
            b = bank[p["t2"]]
            b["d"] = p["d"] + 8
            out.append(_inst([b["id"], p["id"]], [p["d"], b["d"]]))
    elif t == "C8":
        for p in rnd.sample(paid, N_INST):
            b = bank.pop(p["t2"])
            f["banks"].remove(b)
            p["t2"] = None
            out.append(_inst([p["id"]], [p["d"], b["d"]]))
    else:
        raise ValueError(t)
    return f, out


# ---------------------------------------------------------------- processor
def rebuild_payouts(f):
    """recompute payout rows and bank lines from the settlement rows as they now stand (the processor's report stays
    internally consistent, and the bank receives what the processor paid out)"""
    keep_bank = {b["id"]: b for b in f["banks"]}
    rows = [m for m in f["mids"] if m["kind"] != "payout"]
    by = {}
    for m in rows:
        by.setdefault(m["d"], []).append(m)
    payouts, banks, carry = [], [], []
    for d in sorted(by):
        rs = carry + by[d]
        net = sum(r["usd"] for r in rs)
        if net <= 0:
            carry = rs
            continue
        carry = []
        for r in rs:
            r["grp"] = d
        po = {"id": f"PO{d}", "kind": "payout", "k1": None, "k2": str(d), "c": net, "usd": net, "d": d, "grp": d, "t2": None}
        payouts.append(po)
        if d + 1 <= processor.LAST:
            old = keep_bank.get(f"K{d}", {})
            bl = {"id": f"K{d}", "kind": "bankline", "k2": str(d), "c": net, "usd": net, "d": d + 1, "t2": po["id"],
                  "remittance": old.get("remittance", f"batch {d}")}
            po["t2"] = bl["id"]
            banks.append(bl)
    f["mids"] = rows + payouts
    f["banks"] = banks


def _pcopy(clean):
    f = copy.deepcopy({k: v for k, v in clean.items() if k != "cal"})
    f["cal"] = clean["cal"]
    return f


def plant_processor(clean, t):
    f = _pcopy(clean)
    rnd = random.Random(PROC_SEED + int(t[1:]))
    lo, hi = processor.FIRST_MEASURED, processor.CAL.bday(__import__("datetime").date(2025, 6, 15))
    rows = {m["id"]: m for m in f["mids"]}
    books = {b["id"]: b for b in f["books"]}
    out = []

    def in_range(m):
        return lo <= m["d"] <= hi

    if t == "X1":
        ends = set(processor.CAL.month_ends(lo, hi))
        last2 = {e - k for e in ends for k in range(2)}
        elig = sorted((m for m in f["mids"] if m["kind"] == "charge" and m["t1"] in books and books[m["t1"]]["d"] in last2
                       and books[m["t1"]]["d"] + 6 <= processor.LAST - 1), key=lambda m: m["id"])
        picks = rnd.sample(elig, N_INST)
        for m in picks:
            led = books[m["t1"]]
            nd = led["d"] + 6
            fee = rows["Sfe" + m["id"][3:]]
            m["d"] = fee["d"] = nd
            usd = processor.to_usd(m["c"], m["cur"], nd)
            m["usd"] = usd
            fee["usd"] = -processor.fee_cents(usd)
            fee["c"] = processor.fee_cents(usd)
        rebuild_payouts(f)
        for m in picks:
            out.append(_inst([m["id"], "Sfe" + m["id"][3:], m["t1"]], [books[m["t1"]]["d"], m["d"]]))
    elif t == "X2":
        elig = sorted((m for m in f["mids"] if m["kind"] == "charge" and in_range(m)), key=lambda m: m["id"])
        picks = rnd.sample(elig, N_INST)
        for m in picks:
            fee = rows["Sfe" + m["id"][3:]]
            f["mids"].append(dict(m, id=m["id"] + "dup", t1=None))
            f["mids"].append(dict(fee, id=fee["id"] + "dup"))
        rebuild_payouts(f)
        for m in picks:
            out.append(_inst([m["id"] + "dup", "Sfe" + m["id"][3:] + "dup"], [m["d"]]))
    elif t == "X3":
        elig = sorted((m for m in f["mids"] if m["kind"] == "refund" and in_range(m) and m["t1"] in books), key=lambda m: m["id"])
        picks = rnd.sample(elig, N_INST)
        for m in picks:
            m["c"] = m["c"] // 2
            m["usd"] = -processor.to_usd(m["c"], m["cur"], m["d"])
        rebuild_payouts(f)
        for m in picks:
            out.append(_inst([m["id"], m["t1"]], [books[m["t1"]]["d"], m["d"]]))
    elif t == "X4":
        have_rev = {m["cid"] for m in f["mids"] if m["kind"] == "reversal"}
        elig = sorted((m for m in f["mids"] if m["kind"] == "chargeback" and m["cid"] not in have_rev
                       and lo <= m["d"] and m["d"] + 15 <= processor.LAST - 1), key=lambda m: m["id"])
        picks = rnd.sample(elig, min(N_INST, len(elig)))
        for m in picks:
            rv = {"id": "Sre" + m["cid"][2:] + "planted", "kind": "reversal", "k1": f"{m['cid']}|reversal", "c": m["c"],
                  "cur": m["cur"], "usd": processor.to_usd(m["c"], m["cur"], m["d"] + 15), "d": m["d"] + 15,
                  "grp": m["d"] + 15, "t1": None, "cid": m["cid"]}
            f["mids"].append(rv)
        rebuild_payouts(f)
        for m in picks:
            out.append(_inst(["Sre" + m["cid"][2:] + "planted"], [m["d"] + 15]))
    elif t == "X5":
        days = sorted({m["d"] for m in f["mids"] if m["kind"] == "payout" and in_range(m) and m["t2"]})
        picks = rnd.sample(days, N_INST)
        touched = {}
        for d in picks:
            ids = []
            for m in f["mids"]:
                if m["kind"] == "fee" and m["d"] == d:
                    ch = rows["Sch" + m["id"][3:]]
                    m["c"] = processor.fee_cents(ch["usd"], pct=0.039)
                    m["usd"] = -m["c"]
                    ids.append(m["id"])
            touched[d] = ids
        rebuild_payouts(f)
        for d in picks:
            out.append(_inst(touched[d] + [f"PO{d}", f"G{d}", f"K{d}"], [d, d + 1]))
    elif t == "X6":
        elig = sorted((b for b in f["banks"] if lo <= b["d"] <= hi), key=lambda b: b["id"])
        for b in rnd.sample(elig, N_INST):
            delta = rnd.choice([-3, -2, -1, 1, 2, 3])
            b["c"] += delta
            b["usd"] = b["c"]
            g = b["k2"]
            out.append(_inst([b["id"], f"PO{g}", f"G{g}"], [b["d"] - 1, b["d"]]))
    elif t == "X7":
        elig = sorted((b for b in f["banks"] if lo <= b["d"] <= hi), key=lambda b: b["id"])
        for b in rnd.sample(elig, N_INST):
            f["banks"].remove(b)
            g = b["k2"]
            for m in f["mids"]:
                if m["id"] == f"PO{g}":
                    m["t2"] = None
            out.append(_inst([f"PO{g}", f"G{g}"], [b["d"] - 1, b["d"]]))
    else:
        raise ValueError(t)
    return f, out


COUNTY_TYPES = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
PROC_TYPES = ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]
