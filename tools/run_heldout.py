"""Score the independent author's held-out events (followup/heldout-events.json) under the three rules as declared,
window 5 business days, nothing changed. Writes results/results-heldout.json.
Usage: python3 -I -B tools/run_heldout.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county  # noqa: E402
import events  # noqa: E402
import processor  # noqa: E402
import recon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W = 5


def main():
    evs = json.loads((ROOT / "followup" / "heldout-events.json").read_text(encoding="utf-8"))
    clean = {"county": county.build(), "processor": processor.build()}
    base_fm = {(ds, r): {(x["a"], x["b"]) for x in recon.false_matches(clean[ds], recon.match(clean[ds], r, W))}
               for ds in clean for r in recon.RULES}
    out = []
    for ev in evs:
        row = {"id": ev["id"], "dataset": ev.get("dataset"), "title": ev.get("title"), "correct": ev.get("correct"),
               "why": ev.get("why")}
        try:
            f, inst = events.apply(clean[ev["dataset"]], ev)
        except (events.NotApplied, KeyError, TypeError, ValueError) as ex:
            # never repaired (followup/author-brief.md): the reason is reported as the applier gave it
            row["applied"] = False
            row["reason"] = f"{type(ex).__name__}: {ex}"
            out.append(row)
            continue
        row["applied"] = True
        row["touched"] = inst["touched"]
        for rule in recon.RULES:
            run = recon.match(f, rule, W)
            first, hits = recon.flagged(f, run, W, inst["touched"], inst["first_d"], inst["last_d"])
            fm = [x for x in recon.false_matches(f, run) if (x["a"], x["b"]) not in base_fm[(ev["dataset"], rule)]]
            fl = first is not None
            row[rule] = {"flagged": fl, "right": fl == (ev["correct"] == "flag"),
                         "new_false_matches": len(fm),
                         "false_match_on_touched": any(x["a"] in inst["touched"] or x["b"] in inst["touched"] for x in fm),
                         "first_flag_after_business_days": None if first is None else first - inst["first_d"]}
        out.append(row)
    summary = {}
    for ds in ("county", "processor"):
        rows = [r for r in out if r["dataset"] == ds]
        app = [r for r in rows if r.get("applied")]
        summary[ds] = {"events": len(rows), "applied": len(app), "not_applied": [r["id"] for r in rows if not r.get("applied")],
                       "flag_events": sum(r["correct"] == "flag" for r in app),
                       "explain_events": sum(r["correct"] == "explain" for r in app)}
        for rule in recon.RULES:
            summary[ds][rule] = {"right": sum(r[rule]["right"] for r in app),
                                 "right_on_flag": sum(r[rule]["right"] for r in app if r["correct"] == "flag"),
                                 "right_on_explain": sum(r[rule]["right"] for r in app if r["correct"] == "explain"),
                                 "missed_through_false_match": sum((not r[rule]["flagged"]) and r[rule]["false_match_on_touched"]
                                                                   for r in app if r["correct"] == "flag")}
    res = {"window_business_days": W, "summary": summary, "events": out}
    (ROOT / "results" / "results-heldout.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
