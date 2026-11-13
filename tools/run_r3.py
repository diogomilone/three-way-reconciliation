"""Declared version 3 (DESIGN-r3.md), added after the results: the one-fit rule (close a debit whose check number is
hidden only when exactly one open payment fits), the forced pick by payment type, and exact cents first. Imports the
frozen county module and version 2's constants and changes neither; writes results/results-r3.json.
Usage: python3 -I -B tools/run_r3.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import run_r2  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SWEEP = run_r2.SWEEP
TOL = run_r2.TOL
TYPES = ("Paper", "Electronic")


def per_1000(a, b):
    return round(1000 * a / b, 1) if b else None


def candidates(c):
    """For each window, each debit: (debit, true payment, within reach, list of payments that fit). Same filter as
    run_r2.hidden_reference."""
    void_d = {v["k1"]: v["d"] for v in c["voids"]}
    bank_of = {b["t2"]: b for b in c["banks"]}
    pay = {m["id"]: m for m in c["mids"]}
    bucket = defaultdict(list)
    for m in c["mids"]:
        bucket[m["c"] // 100].append(m)
    for w in SWEEP:
        rows = []
        for b in c["banks"]:
            D, p = b["d"], b["t2"]
            fit = []
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
                    fit.append(x)
            rows.append((b, pay[p], D - pay[p]["d"] <= w, fit))
        yield w, rows


def oldest(fit):
    return min(fit, key=lambda x: (x["d"], x["id"])) if fit else None


def main():
    c = county.build()
    r2 = json.loads((ROOT / "results" / "results-r2.json").read_text(encoding="utf-8"))["hidden_reference_county"]
    one_fit, by_type, cents_first = {}, {}, {}
    for w, rows in candidates(c):
        k = str(w)
        # forced pick, as version 2: must reproduce its counts exactly
        f = defaultdict(int)
        for b, p, reach, fit in rows:
            best = oldest(fit)
            res = "none" if best is None else ("right" if best["id"] == p["id"] else "wrong")
            f[res] += 1
            if reach:
                f["reach"] += 1
                f[res + "_reach"] += 1
        assert (f["reach"], f["right_reach"], f["wrong_reach"], f["wrong"], f["none"]) == (
            r2[k]["within_reach"], r2[k]["right_within_reach"], r2[k]["wrong_within_reach"], r2[k]["wrong"],
            r2[k]["none"]), k
        # (a) one-fit rule
        u = defaultdict(int)
        for b, p, reach, fit in rows:
            n = len(fit)
            res = "none" if n == 0 else ("look_alike" if n > 1 else ("right" if fit[0]["id"] == p["id"] else "wrong"))
            u[res] += 1
            if reach:
                u["reach"] += 1
                u[res + "_reach"] += 1
        assert u["wrong_reach"] == 0, k  # the true payment always fits within reach
        n_all = len(rows)
        one_fit[k] = {"debits": n_all, "right_closes": u["right"], "wrong_closes": u["wrong"],
                      "look_alikes": u["look_alike"], "none": u["none"],
                      "wrong_closes_per_1000_debits": per_1000(u["wrong"], n_all),
                      "right_closes_share_of_debits": round(u["right"] / n_all, 4),
                      "look_alikes_share_of_debits": round(u["look_alike"] / n_all, 4),
                      "within_reach": u["reach"], "right_closes_within_reach": u["right_reach"],
                      "wrong_closes_within_reach": u["wrong_reach"], "look_alikes_within_reach": u["look_alike_reach"],
                      "look_alikes_share_within_reach": round(u["look_alike_reach"] / u["reach"], 4)}
        # (b) by payment type
        t = {}
        for ty in TYPES:
            sub = [r for r in rows if r[1]["type"] == ty]
            reach = [r for r in sub if r[2]]
            fw = sum(1 for b, p, rc, fit in reach if oldest(fit)["id"] != p["id"])
            uw = sum(1 for b, p, rc, fit in sub if len(fit) == 1 and fit[0]["id"] != p["id"])
            t[ty] = {"debits": len(sub), "within_reach": len(reach), "forced_pick_wrong_within_reach": fw,
                     "forced_pick_wrong_per_1000_within_reach": per_1000(fw, len(reach)),
                     "one_fit_wrong_closes": uw, "one_fit_wrong_closes_per_1000_debits": per_1000(uw, len(sub))}
        assert sum(t[ty]["debits"] for ty in TYPES) == n_all, k
        by_type[k] = t
        # (c) exact cents first
        e = defaultdict(int)
        for b, p, reach, fit in rows:
            if not reach:
                continue
            exact = [x for x in fit if x["c"] == b["c"]]
            best = oldest(exact) or oldest(fit)
            e["right" if best["id"] == p["id"] else "wrong"] += 1
        cents_first[k] = {"within_reach": f["reach"], "right_within_reach": e["right"], "wrong_within_reach": e["wrong"],
                          "wrong_per_1000_within_reach": per_1000(e["wrong"], f["reach"])}
    pred = json.loads((ROOT / "predictions-r3.json").read_text(encoding="utf-8"))
    o, bt, cf = one_fit, by_type, cents_first
    held = {
        "U1": all(o[k]["wrong_closes_per_1000_debits"] >= 1 for k in ("5", "10", "15")),
        "U2": o["60"]["wrong_closes_per_1000_debits"] < 1,
        "U3": 0.25 <= o["5"]["look_alikes_share_within_reach"] <= 0.45
              and o["60"]["look_alikes_share_within_reach"] > o["5"]["look_alikes_share_within_reach"],
        "U4": 0.35 <= o["5"]["right_closes_share_of_debits"] <= 0.55,
        "U5": bt["5"]["Paper"]["forced_pick_wrong_per_1000_within_reach"]
              > bt["5"]["Electronic"]["forced_pick_wrong_per_1000_within_reach"],
        "U6": 1121 <= cf["5"]["wrong_within_reach"] <= 1200,
    }
    assert set(held) == {p["id"] for p in pred["predictions"]}
    out = {"version": 3, "added_after_the_results": True, "declared_in": "DESIGN-r3.md",
           "one_fit_rule_county": one_fit, "by_payment_type_county": by_type, "exact_cents_first_county": cents_first,
           "predictions": {p["id"]: {"claim": p["claim"], "held": held[p["id"]]} for p in pred["predictions"]}}
    path = ROOT / "results" / "results-r3.json"
    assert not path.exists(), "results-r3.json exists; version 3 is scored once"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(ROOT))
    for k in ("5", "15", "60"):
        print(k, {x: o[k][x] for x in ("right_closes", "wrong_closes", "look_alikes", "none", "wrong_closes_per_1000_debits")})
    print({k: v for k, v in held.items()})


if __name__ == "__main__":
    main()
