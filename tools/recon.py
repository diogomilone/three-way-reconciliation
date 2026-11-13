"""The three matching rules, the daily close and the measures (DESIGN-r1.md sections 3 to 6).

A feed set is a dict:
  books  - records of the books (county ledger lines; processor ledger items)
  mids   - records of the intermediary (county register payments; processor settlement rows, payout rows)
  banks  - bank lines
  voids  - county voids (closing a payment and its open lines)
Each record: id, d (business-day index of its date), c (cents, signed; the amount compared), usd (US$ cents, for money
measures), k1 (key in the books-to-intermediary join), k2 (key in the intermediary-to-bank join), grp (the group a
record nets into), kind, and its truth: t1 (true counterpart id in the first join), t2 (true counterpart id in the second).
"""
import datetime as dt
from collections import defaultdict

RULES = ("R1", "R2", "R3")


class Calendar:
    """Business days Monday to Friday, no holidays. A weekend date is seen at the next business day's close."""

    def __init__(self, start, end):
        self.days, d = [], start
        while d <= end:
            if d.weekday() < 5:
                self.days.append(d)
            d += dt.timedelta(1)
        self.index = {d: i for i, d in enumerate(self.days)}

    def bday(self, d):
        while d.weekday() >= 5:
            d += dt.timedelta(1)
        return self.index[d]

    def date(self, i):
        return self.days[i]

    def month_ends(self, lo, hi):
        """indices of the last business day of each month with lo <= index <= hi"""
        out = []
        for i in range(lo, hi + 1):
            if i == len(self.days) - 1 or self.days[i + 1].month != self.days[i].month:
                out.append(i)
        return out


def _j1_records(feeds, rule):
    """(books side, intermediary side) of the first join under a rule"""
    books = feeds["books"]
    if feeds["kind"] == "county":
        return books, [m for m in feeds["mids"] if m["kind"] == "payment"]
    rows = [m for m in feeds["mids"] if m["kind"] in ("charge", "refund", "chargeback", "reversal")]
    if rule in ("R1", "R2"):
        rows = rows + [m for m in feeds["mids"] if m["kind"] == "fee"]  # fees have no books record; they stay open
    return books, rows


def _batch_groups(feeds):
    """R3 on the processor: one record per batch, the net of every row as the processor reports it"""
    g = {}
    for m in feeds["mids"]:
        if m["kind"] in ("charge", "refund", "chargeback", "reversal", "fee"):
            b = m["grp"]
            if b not in g:
                g[b] = {"id": f"G{b}", "kind": "batch", "k2": str(b), "d": m["d"], "c": 0, "usd": 0, "grp": b,
                        "t2": None, "rows": []}
            r = g[b]
            r["c"] += m["usd"]
            r["usd"] += m["usd"]
            r["d"] = max(r["d"], m["d"])
            r["rows"].append(m["id"])
    for m in feeds["mids"]:
        if m["kind"] == "payout" and m["grp"] in g:
            g[m["grp"]]["t2"] = m.get("t2")
    return list(g.values())


def _j2_records(feeds, rule):
    if feeds["kind"] == "county":
        return [m for m in feeds["mids"] if m["kind"] == "payment"], feeds["banks"]
    if rule in ("R1", "R2"):
        return [m for m in feeds["mids"] if m["kind"] == "payout"], feeds["banks"]
    return _batch_groups(feeds), feeds["banks"]


def match(feeds, rule, W, tol=100):
    """Run every close in order. Returns the pairings and, per record and join, the close at which it was resolved
    (paired or voided), or None."""
    assert rule in RULES
    tol_c = tol if rule == "R2" else 0
    b1, m1 = _j1_records(feeds, rule)
    m2, k2 = _j2_records(feeds, rule)
    res1, res2 = {}, {}  # record id -> close index when resolved in that join
    pairs1, pairs2 = [], []  # (a id, b id, close, how)
    by_close = defaultdict(lambda: {"b1": [], "m1": [], "m2": [], "k2": [], "v": []})
    for r in b1:
        by_close[r["d"]]["b1"].append(r)
    for r in m1:
        by_close[r["d"]]["m1"].append(r)
    for r in m2:
        by_close[r["d"]]["m2"].append(r)
    for r in k2:
        by_close[r["d"]]["k2"].append(r)
    for r in feeds.get("voids", []):
        by_close[r["d"]]["v"].append(r)
    open_b1 = defaultdict(list)  # k1 -> open books records
    open_m1 = defaultdict(list)  # k1 -> open intermediary records
    grp_lines = defaultdict(list)  # R3 county: doc -> open lines
    open_m2 = defaultdict(list)  # k2 -> open intermediary records (join 2)
    open_k2 = defaultdict(list)  # k2 -> open bank lines
    amt_m2 = defaultdict(list)  # R2 fallback: amount bucket (dollars) -> open intermediary records (join 2)
    voided = set()
    j1_by_id = {}

    def ok_pair(a, b):
        if abs(a["c"] - b["c"]) > tol_c:
            return False
        if rule == "R2" and abs(a["d"] - b["d"]) > W:
            return False
        return True

    def take(lst, pred):
        best = None
        for x in lst:
            if pred(x) and (best is None or (x["d"], x["id"]) < (best["d"], best["id"])):
                best = x
        if best is not None:
            lst.remove(best)
        return best

    def drop_amt(m):
        lst = amt_m2.get(m["c"] // 100)
        if lst and m in lst:
            lst.remove(m)

    for D in sorted(by_close):
        arr = by_close[D]
        # ---- join 1: books to intermediary
        if feeds["kind"] == "county" and rule == "R3":
            touched = set()
            for r in arr["b1"]:
                grp_lines[r["k1"]].append(r)
                touched.add(r["k1"])
            for m in arr["m1"]:
                open_m1[m["k1"]].append(m)
                touched.add(m["k1"])
            for k in sorted(touched):
                lines, pays = grp_lines.get(k, []), open_m1.get(k, [])
                if lines and len(pays) == 1 and sum(x["c"] for x in lines) == pays[0]["c"]:
                    p = pays.pop()
                    res1[p["id"]] = D
                    for x in lines:
                        res1[x["id"]] = D
                        pairs1.append((x["id"], p["id"], D, "group"))
                    grp_lines[k] = []
        else:
            for m in arr["m1"]:
                j1_by_id[m["id"]] = m
                if m.get("k1") is None:
                    continue  # a fee row: nothing in the books to pair with
                b = take(open_b1.get(m["k1"], []), lambda x: ok_pair(x, m))
                if b is not None:
                    res1[b["id"]] = res1[m["id"]] = D
                    pairs1.append((b["id"], m["id"], D, "key"))
                else:
                    open_m1[m["k1"]].append(m)
            for r in arr["b1"]:
                m = take(open_m1.get(r["k1"], []), lambda x: ok_pair(r, x))
                if m is not None:
                    res1[r["id"]] = res1[m["id"]] = D
                    pairs1.append((r["id"], m["id"], D, "key"))
                else:
                    open_b1[r["k1"]].append(r)
        # ---- voids (county): close the payment in both joins and its open lines
        for v in arr["v"]:
            voided.add(v["k1"])
            for lst in (open_m1.get(v["k1"], []), open_b1.get(v["k1"], []), grp_lines.get(v["k1"], [])):
                for x in list(lst):
                    res1.setdefault(x["id"], D)
                    lst.remove(x)
            for key, lst in list(open_m2.items()):
                for m in list(lst):
                    if m.get("doc") == v["k1"]:
                        res2.setdefault(m["id"], D)
                        lst.remove(m)
                        drop_amt(m)
        # ---- join 2: intermediary to bank, key pairs first
        for m in arr["m2"]:
            if m.get("doc") in voided:
                res2.setdefault(m["id"], D)
                continue
            b = take(open_k2.get(m["k2"], []), lambda x: ok_pair(x, m))
            if b is not None:
                res2[b["id"]] = res2[m["id"]] = D
                pairs2.append((m["id"], b["id"], D, "key"))
            else:
                open_m2[m["k2"]].append(m)
                amt_m2[m["c"] // 100].append(m)
        fallback_queue = []
        for b in sorted(arr["k2"], key=lambda x: (x["d"], x["id"])):
            m = take(open_m2.get(b["k2"], []), lambda x: ok_pair(b, x))
            if m is not None:
                drop_amt(m)
                res2[b["id"]] = res2[m["id"]] = D
                pairs2.append((m["id"], b["id"], D, "key"))
            else:
                fallback_queue.append(b)
        for b in fallback_queue:
            if rule == "R2":
                cands = []
                for bucket in (b["c"] // 100 - 1, b["c"] // 100, b["c"] // 100 + 1):
                    cands.extend(x for x in amt_m2.get(bucket, []) if abs(x["c"] - b["c"]) <= tol_c
                                 and 0 <= b["d"] - x["d"] <= W)
                if cands:
                    m = min(cands, key=lambda x: (x["d"], x["id"]))
                    drop_amt(m)
                    open_m2[m["k2"]].remove(m)
                    res2[b["id"]] = res2[m["id"]] = D
                    pairs2.append((m["id"], b["id"], D, "fallback"))
                    continue
            open_k2[b["k2"]].append(b)
    return {"rule": rule, "W": W, "j1": (b1, m1), "j2": (m2, k2), "res1": res1, "res2": res2,
            "pairs1": pairs1, "pairs2": pairs2}


def truth_arrivals(feeds, rule):
    """for each record and join, the close at which its true counterpart has arrived (None if it has none)"""
    b1, m1 = _j1_records(feeds, rule)
    m2, k2 = _j2_records(feeds, rule)
    d_of = {r["id"]: r["d"] for r in feeds["books"] + feeds["mids"] + feeds["banks"]}
    void_d = {v["k1"]: v["d"] for v in feeds.get("voids", [])}
    if feeds["kind"] == "processor" and rule == "R3":
        for g in m2:
            d_of[g["id"]] = g["d"]
    ca1, ca2 = {}, {}
    lines_of = defaultdict(list)
    for r in b1:
        if r.get("t1") is not None:
            lines_of[r["t1"]].append(r["d"])
    for r in b1:
        ca1[r["id"]] = d_of.get(r.get("t1")) if r.get("t1") is not None else None
    for m in m1:
        if m["kind"] == "fee":
            ca1[m["id"]] = m["d"]  # explained by its batch, which is there: the rule cannot pair it
        elif feeds["kind"] == "county":
            ca1[m["id"]] = max(lines_of[m["id"]]) if lines_of.get(m["id"]) else None
        else:
            ca1[m["id"]] = d_of.get(m.get("t1")) if m.get("t1") is not None else None
    for m in m2:
        t = m.get("t2")
        if t is not None and t in d_of:
            ca2[m["id"]] = d_of[t]
        elif m.get("doc") in void_d:
            ca2[m["id"]] = void_d[m["doc"]]
        else:
            ca2[m["id"]] = None
    for b in k2:
        t = b.get("t2")
        if feeds["kind"] == "processor" and rule == "R3" and t is not None:
            t = "G" + t[2:] if t.startswith("PO") else t
        ca2[b["id"]] = d_of.get(t) if t is not None else None
    return ca1, ca2


def break_intervals(feeds, run, W, horizon):
    """per (join, record id): (first close as a break, first close no longer a break), record, why-arrival"""
    ca1, ca2 = truth_arrivals(feeds, run["rule"])
    out = []
    for join, recs, res, ca in ((1, run["j1"][0] + run["j1"][1], run["res1"], ca1),
                                (2, run["j2"][0] + run["j2"][1], run["res2"], ca2)):
        for r in recs:
            start = r["d"] + W + 1
            end = res.get(r["id"])
            end = horizon + 1 if end is None else end
            if end > start and start <= horizon:
                out.append((join, r, start, end, ca.get(r["id"])))
    return out


def money_by_close(feeds, run, W, lo, hi, horizon):
    """US$ cents of break records at each close lo..hi, total and by why: rule (counterpart there), timing, none"""
    n = hi - lo + 2
    tot = {k: [0] * n for k in ("all", "rule", "timing", "none")}

    def add(key, a, b, v):  # closes a..b-1
        a, b = max(a, lo), min(b, hi + 1)
        if a < b:
            tot[key][a - lo] += v
            tot[key][b - lo] -= v

    for join, r, s, e, ca in break_intervals(feeds, run, W, horizon):
        v = abs(r["usd"])
        add("all", s, e, v)
        if ca is None:
            add("none", s, e, v)
        else:
            add("timing", s, min(e, ca), v)
            add("rule", max(s, ca), e, v)
    for k in tot:
        acc, arr = 0, []
        for x in tot[k][:-1]:
            acc += x
            arr.append(acc)
        tot[k] = arr
    return tot


def break_ages(feeds, run, W, horizon):
    ages, censored = [], 0
    for join, r, s, e, ca in break_intervals(feeds, run, W, horizon):
        if e > horizon:
            censored += 1
        else:
            ages.append(e - s)
    ages.sort()
    q = (lambda p: ages[min(len(ages) - 1, int(p * len(ages)))] if ages else None)
    return {"breaks": len(ages) + censored, "closed": len(ages), "censored": censored, "median": q(0.5), "p90": q(0.9)}


def false_matches(feeds, run):
    """pairs whose two records do not truly belong together"""
    ids = {r["id"]: r for r in feeds["books"] + feeds["mids"] + feeds["banks"]}
    out = []
    for a, b, D, how in run["pairs1"]:
        ra = ids[a]
        if ra.get("t1") != b:
            out.append({"join": 1, "a": a, "b": b, "close": D, "how": how, "usd": abs(ra["usd"])})
    for m, b, D, how in run["pairs2"]:
        rb = ids[b]
        t = rb.get("t2")
        if feeds["kind"] == "processor" and run["rule"] == "R3" and t is not None and t.startswith("PO"):
            t = "G" + t[2:]
        if t != m:
            out.append({"join": 2, "a": m, "b": b, "close": D, "how": how, "usd": abs(rb["usd"])})
    return out


def flagged(feeds, run, W, touched, first_d, last_d, horizon_bd=20):
    """an instance is flagged when a record it touched is a break at some close in [first_d, last_d + horizon_bd]"""
    touched = set(touched)
    hi = last_d + horizon_bd
    hits = []
    for join, r, s, e, ca in break_intervals(feeds, run, W, max(hi, 0) + 1):
        if r["id"] in touched and s <= hi and e > first_d:
            hits.append((join, r["id"], max(s, first_d)))
    return (min(h[2] for h in hits) if hits else None), hits
