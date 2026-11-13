"""Apply events written in the held-out grammar (DESIGN-r1.md section 8; the grammar is the bundle's GRAMMAR.md).

An event: {"id", "dataset": "county" | "processor", "title", "correct": "flag" | "explain", "why", "ops": [...]}.
Ops, applied in order to a copy of the clean feeds:
  pick   {"op": "pick", "as": name, "feed": feed, "where": {field: value | {"min": v, "max": v}}, "nth": k}
  copy   {"op": "copy", "of": name, "as": name, "set": {field: value}, "shift_days": n}   (a new record, no true partner)
  add    {"op": "add", "feed": feed, "as": name, "fields": {field: value}}                (a new record, no true partner)
  set    {"op": "set", "on": name, "set": {field: value}}                                 (the same money, changed)
  shift  {"op": "shift", "on": name, "days": n}                                           (business days)
  remove {"op": "remove", "on": name}
  repay  {"op": "repay"}   (processor only: payouts and bank lines recomputed from the settlement rows as they stand)
An event the grammar cannot apply (an unknown op, feed or field, a pick that finds nothing) is reported as not
applied, with the reason, and never repaired.
"""
import copy
import datetime as dt

import plant
import processor

FEEDS = {
    "county": {"ledger_lines": "books", "payments": "mids", "bank_lines": "banks", "voids": "voids"},
    "processor": {"ledger_items": "books", "settlement_rows": "mids", "bank_lines": "banks"},
}
FIELDS = {
    ("county", "ledger_lines"): {"line_id": "id", "payment_doc": "k1", "vendor": "vendor", "invoice": "invoice",
                                 "amount": "c", "date": "d"},
    ("county", "payments"): {"payment_doc": "k1", "check_number": "k2", "payment_type": "type", "total": "c",
                             "issue_date": "d", "status": "status"},
    ("county", "bank_lines"): {"bank_line_id": "id", "reference": "k2", "amount": "c", "date": "d"},
    ("county", "voids"): {"payment_doc": "k1", "date": "d"},
    ("processor", "ledger_items"): {"item_id": "id", "charge_id": "cid", "kind": "kind", "currency": "cur",
                                    "amount": "c", "date": "d"},
    ("processor", "settlement_rows"): {"row_id": "id", "charge_id": "cid", "kind": "kind", "currency": "cur",
                                       "amount": "c", "batch": "grp", "date": "d"},
    ("processor", "bank_lines"): {"bank_line_id": "id", "remittance": "remittance", "amount": "c", "date": "d"},
}


class NotApplied(Exception):
    pass


def _to_internal(ds, feed, fname, value, cal):
    m = FIELDS[(ds, feed)]
    if fname not in m:
        raise NotApplied(f"unknown field {fname} on {feed}")
    key = m[fname]
    if key == "c":
        try:
            return key, int(round(float(value) * 100))
        except (TypeError, ValueError):
            raise NotApplied(f"amount not a number: {value!r}")
    if key == "d":
        try:
            return key, cal.bday(dt.date.fromisoformat(str(value)[:10]))
        except (KeyError, ValueError):
            raise NotApplied(f"date outside the calendar or unreadable: {value!r}")
    if key == "grp":
        return key, int(value)
    return key, ("" if value is None else str(value)) if key != "cid" else str(value)


def _matches(ds, feed, rec, where, cal):
    for fname, want in where.items():
        key = FIELDS[(ds, feed)].get(fname)
        if key is None:
            raise NotApplied(f"unknown field {fname} on {feed}")
        have = rec.get(key)
        if isinstance(want, dict):
            lo, hi = want.get("min"), want.get("max")
            if key in ("c", "d"):
                lo = None if lo is None else _to_internal(ds, feed, fname, lo, cal)[1]
                hi = None if hi is None else _to_internal(ds, feed, fname, hi, cal)[1]
            elif key == "grp":
                lo = None if lo is None else int(lo)
                hi = None if hi is None else int(hi)
            if have is None or (lo is not None and have < lo) or (hi is not None and have > hi):
                return False
        else:
            if key in ("c", "d", "grp"):
                if have != _to_internal(ds, feed, fname, want, cal)[1]:
                    return False
            elif str(have) != str(want):
                return False
    return True


def _refresh_keys(ds, feed, r):
    if ds == "county":
        if feed in ("ledger_lines", "payments", "voids"):
            r["doc"] = r.get("k1")
        r["usd"] = r.get("c", 0)
    else:
        if feed == "ledger_items" or (feed == "settlement_rows" and r.get("kind") in ("charge", "refund", "chargeback", "reversal")):
            r["k1"] = f"{r['cid']}|{r['kind']}"
            sign = {"charge": 1, "refund": -1, "chargeback": -1, "reversal": 1}[r["kind"]]
            r["usd"] = sign * processor.to_usd(r["c"], r.get("cur", "USD"), r["d"])
        elif feed == "settlement_rows" and r.get("kind") == "fee":
            r["k1"] = None
            r["usd"] = -r["c"]
        elif feed == "settlement_rows" and r.get("kind") == "payout":
            r["k2"] = str(r["grp"])
            r["usd"] = r["c"]
        elif feed == "bank_lines":
            rem = str(r.get("remittance", ""))
            r["k2"] = rem.split()[-1] if rem.split() else ""
            r["usd"] = r["c"]


def _counterparts(f, rec_ids):
    """true counterparts in either join (amendment 2), and the processor rows' batch records"""
    out = set()
    allr = f["books"] + f["mids"] + f["banks"]
    byid = {r["id"]: r for r in allr}
    for i in list(rec_ids):
        r = byid.get(i)
        if r is None:
            continue
        for k in ("t1", "t2"):
            if r.get(k):
                out.add(r[k])
        if f["kind"] == "processor" and r.get("grp") is not None and r.get("kind") != "bankline":
            out |= {f"G{r['grp']}", f"PO{r['grp']}"}
        if f["kind"] == "processor" and r.get("kind") == "bankline":
            out |= {f"G{r['k2']}", f"PO{r['k2']}"}
    for r in allr:
        if r.get("t1") in rec_ids or r.get("t2") in rec_ids:
            out.add(r["id"])
    return out


def _link_created(f, created):
    """a record the author created truly belongs with a record of the same key that has no partner yet (a new payment
    with its lines and bank line is a real, if wrong, payment); a copy of a record whose partner is taken stays alone"""
    if not created:
        return
    books, mids, banks = f["books"], f["mids"], f["banks"]
    if f["kind"] == "county":
        pays = [m for m in mids if m["kind"] == "payment"]
        for ln in books:
            if ln["id"] in created and ln.get("t1") is None:
                cand = [p for p in pays if p.get("k1") == ln.get("k1") and (p["id"] in created or not p.get("lines"))]
                if cand:
                    ln["t1"] = cand[0]["id"]
                    cand[0].setdefault("lines", []).append(ln["id"])
        linked = {b.get("t2") for b in banks}
        for p in pays:
            if p["id"] in created and p.get("t2") is None:
                cand = [b for b in banks if b.get("k2") == p.get("k2") and b.get("t2") is None]
                if cand:
                    p["t2"], cand[0]["t2"] = cand[0]["id"], p["id"]
        for b in banks:
            if b["id"] in created and b.get("t2") is None:
                cand = [p for p in pays if p.get("k2") == b.get("k2") and p.get("t2") is None and p["id"] not in linked]
                if cand:
                    b["t2"], cand[0]["t2"] = cand[0]["id"], b["id"]
    else:
        rows = [m for m in mids if m.get("k1")]
        for x in books + rows:
            if x["id"] in created and x.get("t1") is None:
                other = rows if x in books else books
                cand = [o for o in other if o.get("k1") == x.get("k1") and o.get("t1") is None and o is not x]
                if cand:
                    x["t1"], cand[0]["t1"] = cand[0]["id"], x["id"]


def apply(clean, ev):
    f = copy.deepcopy({k: v for k, v in clean.items() if k != "cal"})
    f["cal"] = cal = clean["cal"]
    ds = ev.get("dataset")
    if ds not in FEEDS or ds != clean["kind"]:
        raise NotApplied(f"dataset {ds!r}")
    names, created, changed, removed_cp, dates = {}, set(), set(), set(), []
    n_new = 0
    for op in ev.get("ops", []):
        kind = op.get("op")
        if kind == "pick":
            feed = op.get("feed")
            if feed not in FEEDS[ds]:
                raise NotApplied(f"unknown feed {feed!r}")
            recs = sorted((r for r in f[FEEDS[ds][feed]] if _matches(ds, feed, r, op.get("where", {}), cal)),
                          key=lambda r: r.get("id", ""))
            if not recs:
                raise NotApplied(f"pick {op.get('as')!r} found nothing")
            r = recs[int(op.get("nth", 0)) % len(recs)]
            names[op["as"]] = (feed, r)
            dates.append(r["d"])
        elif kind in ("copy", "add"):
            if kind == "copy":
                feed, src = names[op["of"]]
                r = dict(src)
            else:
                feed = op.get("feed")
                if feed not in FEEDS[ds]:
                    raise NotApplied(f"unknown feed {feed!r}")
                r = {"kind": {"bank_lines": "bankline", "payments": "payment", "ledger_lines": "line", "voids": "void"}.get(feed, "charge")}
                if ds == "processor" and feed == "bank_lines":
                    r["kind"] = "bankline"
            n_new += 1
            r["id"] = f"{r.get('id', 'NEW')}+{ev['id']}{n_new}"
            r["t1"] = r["t2"] = None
            if r.get("kind") == "payment":
                r["lines"] = []
            for fname, v in (op.get("set") or op.get("fields") or {}).items():
                key, val = _to_internal(ds, feed, fname, v, cal)
                r[key] = val
            if "shift_days" in op:
                r["d"] += int(op["shift_days"])
            for need in ("d", "c") if feed != "voids" else ("d", "k1"):
                if need not in r:
                    raise NotApplied(f"new record on {feed} lacks {need}")
            if ds == "processor" and feed == "settlement_rows" and r.get("grp") is None:
                r["grp"] = r["d"]
            if ds == "county" and feed == "payments":
                r.setdefault("type", "Paper")
                r.setdefault("status", "Paid")
            try:
                _refresh_keys(ds, feed, r)
            except (KeyError, TypeError, ValueError) as ex:
                raise NotApplied(f"new record on {feed} lacks a field: {ex}")
            f[FEEDS[ds][feed]].append(r)
            names[op["as"]] = (feed, r)
            created.add(r["id"])
            dates.append(r["d"])
        elif kind in ("set", "shift"):
            if op.get("on") not in names:
                raise NotApplied(f"unknown name {op.get('on')!r}")
            feed, r = names[op["on"]]
            if kind == "set":
                for fname, v in op.get("set", {}).items():
                    key, val = _to_internal(ds, feed, fname, v, cal)
                    if key == "id":
                        raise NotApplied("an id cannot be changed")
                    r[key] = val
            else:
                r["d"] += int(op.get("days", 0))
            if ds == "processor" and feed == "settlement_rows" and kind == "shift":
                r["grp"] = r["d"]
            try:
                _refresh_keys(ds, feed, r)
            except (KeyError, TypeError, ValueError) as ex:
                raise NotApplied(f"changed record on {feed} lacks a field: {ex}")
            changed.add(r["id"])
            dates.append(r["d"])
        elif kind == "remove":
            if op.get("on") not in names:
                raise NotApplied(f"unknown name {op.get('on')!r}")
            feed, r = names[op["on"]]
            lst = f[FEEDS[ds][feed]]
            if r not in lst:
                raise NotApplied("record already removed")
            removed_cp |= _counterparts(f, {r["id"]})
            lst.remove(r)
            for o in f["books"] + f["mids"] + f["banks"]:
                for k in ("t1", "t2"):
                    if o.get(k) == r["id"]:
                        o[k] = None
            dates.append(r["d"])
        elif kind == "repay":
            if ds != "processor":
                raise NotApplied("repay is for the processor data")
            plant.rebuild_payouts(f)
        else:
            raise NotApplied(f"unknown op {kind!r}")
    for r in f["books"] + f["mids"] + f["banks"]:
        if r.get("d") is not None and not (0 <= r["d"] < len(cal.days)):
            raise NotApplied("a date moved outside the calendar")
    _link_created(f, created)
    ids_now = {r["id"] for r in f["books"] + f["mids"] + f["banks"]}
    touched = (created | changed) & ids_now
    for v in f.get("voids", []):  # a void touches the payment it closes and that payment's bank line
        if v["id"] in created:
            for m in f["mids"]:
                if m.get("k1") == v["k1"]:
                    touched |= {m["id"], m.get("t2")} - {None}
    touched |= _counterparts(f, touched) | removed_cp
    if not touched:
        raise NotApplied("the event touches no record")
    return f, {"touched": sorted(touched), "first_d": min(dates), "last_d": max(dates)}
