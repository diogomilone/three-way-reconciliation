"""Added after the results: the two held-out county events whose pick put a numeric range on the check-number text
field (not defined by the grammar, so not applied in the main score) are applied here with digit-only text compared as
numbers. Reported beside the main score, never in it. Writes results/results-heldout-numeric-ranges.json.
Usage: python3 -I -B tools/heldout_numeric_ranges.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import events  # noqa: E402
import recon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W = 5
_orig = events._matches


def _numeric_text(ds, feed, rec, where, cal):
    conv = {}
    for fname, want in where.items():
        key = events.FIELDS[(ds, feed)].get(fname)
        if isinstance(want, dict) and key not in ("c", "d", "grp") and key is not None:
            v = str(rec.get(key, ""))
            if not v.isdigit():
                return False
            lo, hi = want.get("min"), want.get("max")
            if (lo is not None and int(v) < int(lo)) or (hi is not None and int(v) > int(hi)):
                return False
        else:
            conv[fname] = want
    return _orig(ds, feed, rec, conv, cal)


def main():
    events._matches = _numeric_text
    main_res = json.loads((ROOT / "results" / "results-heldout.json").read_text(encoding="utf-8"))
    ids = [e["id"] for e in main_res["events"] if not e["applied"]]
    evs = [e for e in json.loads((ROOT / "followup" / "heldout-events.json").read_text(encoding="utf-8")) if e["id"] in ids]
    clean = county.build()
    out = []
    for ev in evs:
        f, inst = events.apply(clean, ev)
        row = {"id": ev["id"], "title": ev["title"], "correct": ev["correct"]}
        for rule in recon.RULES:
            run = recon.match(f, rule, W)
            first, _ = recon.flagged(f, run, W, inst["touched"], inst["first_d"], inst["last_d"])
            row[rule] = {"flagged": first is not None, "right": (first is not None) == (ev["correct"] == "flag")}
        out.append(row)
    res = {"added_after_the_results": True, "what": __doc__.strip().splitlines()[0], "events": out}
    (ROOT / "results" / "results-heldout-numeric-ranges.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
