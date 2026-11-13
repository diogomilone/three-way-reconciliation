"""Tests: the data checksum and feed counts, each rule on small fixed cases, the planting, the event grammar, and
the published results. Standard library only.
Usage: python3 -B tests/test_study.py
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import county  # noqa: E402
import events  # noqa: E402
import plant  # noqa: E402
import processor  # noqa: E402
import recon  # noqa: E402

RES = json.loads((ROOT / "results" / "results-r1.json").read_text(encoding="utf-8"))
HO = json.loads((ROOT / "results" / "results-heldout.json").read_text(encoding="utf-8"))


def row(doc, inv, amount, issued, check, status="Paid", cleared="", ptype="Paper", vendor="v1"):
    return {"dis_doc_id": doc, "vendor_invoice_no": inv, "amount": amount, "disb_date": issued + "T00:00:00.000",
            "check_no": check, "payment_type": ptype, "check_status": status,
            "check_clearance_or_cancel_date": (cleared + "T00:00:00.000") if cleared else "", "vendor_code": vendor}


def pairs(run):
    return {(a, b) for a, b, *_ in run["pairs1"]}, {(a, b) for a, b, *_ in run["pairs2"]}


class HandMade(unittest.TestCase):
    def test_split_payment_pairs_only_as_a_whole(self):
        f = county.build([row("D1", "I1", "60.00", "2024-03-04", "1001", cleared="2024-03-06"),
                          row("D1", "I2", "40.00", "2024-03-04", "1001", cleared="2024-03-06")])
        self.assertEqual(len(f["mids"]), 1)
        self.assertEqual(f["mids"][0]["c"], 10000)
        for rule in ("R1", "R2"):
            p1, p2 = pairs(recon.match(f, rule, 5))
            self.assertEqual(p1, set(), rule)  # no single line equals the payment
            self.assertEqual(p2, {("PD1", "BD1")}, rule)
        p1, p2 = pairs(recon.match(f, "R3", 5))
        self.assertEqual(len(p1), 2)
        self.assertEqual(p2, {("PD1", "BD1")})

    def test_shared_amount_makes_the_fallback_pair_wrongly(self):
        # D1's check clears long after the window; D2, same amount, was issued just before D1's bank line
        f = county.build([row("D1", "I1", "250.00", "2024-03-04", "2001", cleared="2024-04-01"),
                          row("D2", "I2", "250.00", "2024-03-27", "2002", cleared="2024-05-01")])
        run2 = recon.match(f, "R2", 5)
        self.assertIn(("PD2", "BD1"), pairs(run2)[1])
        self.assertTrue(any(p[3] == "fallback" for p in run2["pairs2"]))
        self.assertTrue(recon.false_matches(f, run2))
        for rule in ("R1", "R3"):
            run = recon.match(f, rule, 5)
            self.assertEqual(pairs(run)[1], {("PD1", "BD1"), ("PD2", "BD2")}, rule)
            self.assertEqual(recon.false_matches(f, run), [], rule)

    def test_void_closes_the_payment(self):
        f = county.build([row("D1", "I1", "75.00", "2024-03-04", "3001", status="Cancelled", cleared="2024-03-08")])
        self.assertEqual(len(f["voids"]), 1)
        for rule in recon.RULES:
            run = recon.match(f, rule, 5)
            self.assertIn("PD1", run["res2"], rule)

    def test_late_check_is_a_break_only_inside_a_short_window(self):
        f = county.build([row("D1", "I1", "90.00", "2024-03-04", "4001", cleared="2024-04-15")])
        brk = lambda w: [x for x in recon.break_intervals(f, recon.match(f, "R3", w), w, county.HORIZON) if x[0] == 2]
        self.assertTrue(brk(5))
        self.assertFalse(brk(40))


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = county.build()  # load_rows checks the pinned sha256
        cls.p = processor.build()

    def test_feed_counts_match_the_results(self):
        fd = RES["county"]["feeds"]
        self.assertEqual((len(self.c["books"]), len(self.c["mids"]), len(self.c["banks"]), len(self.c["voids"])),
                         (fd["ledger_lines"], fd["register_payments"], fd["bank_lines"], fd["voids"]))
        self.assertEqual(len(county.load_rows()), 46126)
        self.assertEqual(len(self.p["banks"]), RES["processor"]["feeds"]["bank_lines"])

    def test_every_planted_kind_gives_20_instances(self):
        for t in plant.COUNTY_TYPES:
            _, inst = plant.plant_county(self.c, t)
            self.assertEqual(len(inst), 20, t)
        for t in plant.PROC_TYPES:
            _, inst = plant.plant_processor(self.p, t)
            self.assertEqual(len(inst), 20, t)

    def test_event_grammar(self):
        ev = {"id": "H00", "dataset": "county", "title": "syntax example", "correct": "explain", "why": "syntax",
              "ops": [{"op": "pick", "as": "x", "feed": "ledger_lines", "where": {"amount": {"min": 100, "max": 200}},
                       "nth": 4}, {"op": "set", "on": "x", "set": {"invoice": "INV-1"}}]}
        f, info = events.apply(self.c, ev)
        self.assertEqual(sum(1 for x in f["books"] if x["invoice"] == "INV-1") >= 1, True)
        self.assertTrue(info["touched"])
        self.assertEqual(sum(1 for x in self.c["books"] if x["invoice"] == "INV-1"),
                         sum(1 for x in county.build()["books"] if x["invoice"] == "INV-1"))  # the clean copy is untouched
        none = dict(ev, ops=[{"op": "pick", "as": "x", "feed": "ledger_lines", "where": {"amount": {"min": 10 ** 12}}}])
        with self.assertRaises(events.NotApplied):
            events.apply(self.c, none)


class PinnedResults(unittest.TestCase):
    def test_headline_figures(self):
        cl = RES["county"]["clean"]
        self.assertEqual([cl[r]["false_matches"] for r in recon.RULES], [0, 543, 0])
        self.assertEqual(cl["R2"]["pairs_by_fallback"], 543)
        self.assertEqual(cl["R3"]["unexplained_mean_usd"]["all"], 4378524.91)
        self.assertEqual(RES["county"]["window_sweep_R3"]["5"]["by_type"]["Paper"]["break_before_clearing"], 3700)

    def test_heldout_events_and_scores(self):
        raw = (ROOT / "followup" / "heldout-events.json").read_bytes()
        self.assertEqual(len(json.loads(raw)), 24)
        self.assertEqual(hashlib.sha256(raw).hexdigest()[:8], "570c0b28")
        s = HO["summary"]
        self.assertEqual([s["county"][r]["right"] + s["processor"][r]["right"] for r in recon.RULES], [19, 18, 21])

    def test_first_version_results_unchanged(self):
        raw = (ROOT / "results" / "results-r1.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "82ebe362c1f685d24a3862b0350012244d4cbd7635f465da079a554efbdbae30")


class SecondVersion(unittest.TestCase):
    def test_hidden_reference_picks_the_older_payment_of_the_same_amount(self):
        import run_r2
        mids = [{"id": "pay-old", "kind": "payment", "doc": "A", "c": 5000, "d": 10, "vendor": "x"},
                {"id": "pay-own", "kind": "payment", "doc": "B", "c": 5000, "d": 11, "vendor": "y"},
                {"id": "pay-other", "kind": "payment", "doc": "C", "c": 7000, "d": 11, "vendor": "z"}]
        banks = [{"id": "bank-own", "c": 5000, "d": 13, "t2": "pay-own"}, {"id": "bank-other", "c": 7000, "d": 12, "t2": "pay-other"}]
        out = run_r2.hidden_reference({"mids": mids, "banks": banks, "voids": []})["5"]
        # bank-own's payment is in reach, but pay-old (same amount, older, still open) is taken instead: wrong
        # bank-other has no other payment within US$1.00: right
        self.assertEqual((out["within_reach"], out["right_within_reach"], out["wrong_within_reach"]), (2, 1, 1))

    def test_second_version_figures(self):
        r2 = json.loads((ROOT / "results" / "results-r2.json").read_text(encoding="utf-8"))
        h = r2["hidden_reference_county"]["5"]
        self.assertEqual((h["within_reach"], h["right_within_reach"], h["wrong_within_reach"]), (8430, 7125, 1305))
        f = r2["fallback_sweep_county"]["5"]
        self.assertEqual((f["false_matches_bank_join"], f["fallback_bank_line_lag_within_window"],
                          f["fallback_bank_line_lag_beyond_window"]), (543, 44, 499))
        k = r2["break_age_kaplan_meier"]["county"]
        self.assertEqual((k["R1"]["median"], k["R3"]["median"], k["R3"]["p90"]), (None, 4, 34))


class ThirdVersion(unittest.TestCase):
    def test_a_lone_fit_is_never_wrong_when_the_payment_is_in_reach(self):
        import run_r3
        pay = lambda i, c, d: {"id": i, "kind": "payment", "doc": i, "c": c, "d": d, "vendor": i, "type": "Paper"}
        mids = [pay("pay-a", 5000, 10), pay("pay-b", 5000, 11), pay("pay-c", 7000, 1), pay("pay-d", 7000, 15)]
        banks = [{"id": "bank-b", "c": 5000, "d": 13, "t2": "pay-b"}, {"id": "bank-c", "c": 7000, "d": 20, "t2": "pay-c"}]
        rows = dict(run_r3.candidates({"mids": mids, "banks": banks, "voids": []}))[5]
        got = {b["id"]: (reach, sorted(x["id"] for x in fit)) for b, p, reach, fit in rows}
        # bank-b: its payment is in reach and fits, beside a look-alike, so it goes to a person
        # bank-c: its payment cleared 19 days after issue, out of reach; one other payment fits, a wrong lone fit
        self.assertEqual(got, {"bank-b": (True, ["pay-a", "pay-b"]), "bank-c": (False, ["pay-d"])})
        self.assertTrue(all(p in [x["id"] for x in fit] for b, p, reach, fit in
                            [(b, p["id"], reach, fit) for b, p, reach, fit in rows] if reach))

    def test_third_version_figures(self):
        r3 = json.loads((ROOT / "results" / "results-r3.json").read_text(encoding="utf-8"))
        o5, o60 = r3["one_fit_rule_county"]["5"], r3["one_fit_rule_county"]["60"]
        self.assertEqual((o5["right_closes"], o5["wrong_closes"], o5["look_alikes"], o5["none"]), (6887, 371, 1732, 4111))
        self.assertEqual((o60["wrong_closes"], o60["wrong_closes_per_1000_debits"]), (5, 0.4))
        self.assertTrue(all(v["wrong_closes_within_reach"] == 0 for v in r3["one_fit_rule_county"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=1)
