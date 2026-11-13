"""Render the study's pages: index.html (the entry page) and six detail pages. Every number comes from results/ or
assumptions.json, and the claims the text makes are asserted here, so a change in the results fails the build instead
of leaving the text stale.
Usage: python3 -I -B site/render.py
"""
import functools
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "results" / "results-r1.json").read_text(encoding="utf-8"))
HO = json.loads((ROOT / "results" / "results-heldout.json").read_text(encoding="utf-8"))
HN = json.loads((ROOT / "results" / "results-heldout-numeric-ranges.json").read_text(encoding="utf-8"))
AS = json.loads((ROOT / "assumptions.json").read_text(encoding="utf-8"))
PRED = json.loads((ROOT / "predictions-r1.json").read_text(encoding="utf-8"))
R2V = json.loads((ROOT / "results" / "results-r2.json").read_text(encoding="utf-8"))
R2B = json.loads((ROOT / "results" / "results-r2-breakdown.json").read_text(encoding="utf-8"))
PRED2 = json.loads((ROOT / "predictions-r2.json").read_text(encoding="utf-8"))
R3V = json.loads((ROOT / "results" / "results-r3.json").read_text(encoding="utf-8"))
PRED3 = json.loads((ROOT / "predictions-r3.json").read_text(encoding="utf-8"))
R4V = json.loads((ROOT / "results" / "results-r4.json").read_text(encoding="utf-8"))
PRED4 = json.loads((ROOT / "predictions-r4.json").read_text(encoding="utf-8"))
STUDY_URL = "https://diogotravassos.dev/three-way-reconciliation/"
STUDY_TITLE = "Three-way reconciliation: matching the books, the payments and the bank each day"
MINUS = "−"
RULES = ["R1", "R2", "R3"]
NAME = {"R1": "Exact reference", "R2": "Reference, then amount and date", "R3": "Whole payment"}
SHORT = {"R1": "exact reference", "R2": "amount-and-date fallback", "R3": "whole payment"}


def e(t):
    return html.escape(str(t), quote=True)


def n(v):
    return f"{v:,}"


def usd(v):
    return f"US${v:,.2f}"


def usd0(v):
    return f"US${v:,.0f}"


def mill(v, d=1):
    return f"US${v / 1e6:,.{d}f} million"


def pct(v, d=1):
    return f"{100 * v:.{d}f}%"


# ---------------------------------------------------------------- county, clean feeds
C = R["county"]
F = C["feeds"]
CL = C["clean"]
W = R["window_business_days"]
assert W == 5
BANK = F["bank_lines"]
FM = CL["R2"]["false_matches"]
FM_USD = CL["R2"]["false_matches_usd"]
assert (BANK, FM, CL["R1"]["false_matches"], CL["R3"]["false_matches"]) == (13101, 543, 0, 0)
assert CL["R2"]["pairs_by_fallback"] == FM  # every pairing the fallback made was wrong
ONE_IN = round(BANK / FM)
assert ONE_IN == 24 and CL["R2"]["false_matches_per_1000_bank_lines"] == 41.4
OPEN = {r: CL[r]["unexplained_mean_usd"]["all"] for r in RULES}
SHARE = {r: CL[r]["unexplained_mean_share_of_money_moved"] for r in RULES}
assert OPEN["R3"] < OPEN["R1"] < OPEN["R2"]
MOVED = F["money_in_payments_usd"]
MULTI, MULTI_USD = F["multi_line_payments"], F["multi_line_money_usd"]
PAY = F["register_payments"]
assert (MULTI, PAY) == (5082, 13354)
BRK = {r: CL[r]["break_age_business_days"] for r in RULES}
assert (BRK["R3"]["breaks"], BRK["R1"]["breaks"], BRK["R3"]["median"], BRK["R3"]["p90"]) == (3953, 46180, 4, 21)
SPLIT3 = CL["R3"]["unexplained_mean_usd"]
assert SPLIT3["rule"] == 0
ME = {r: CL[r]["unexplained_month_end_usd"] for r in RULES}
assert all(ME["R3"][d] < ME["R1"][d] and ME["R3"][d] < ME["R2"][d] for d in ME["R3"])  # P1
AN = C["anomalies"]
PT = C["published_totals_usd"]
assert abs(PT["Paid"] + PT["Cancelled"] + PT["Disbursed"] - PT["all"]) < 0.005 and abs(PT["all"] - MOVED) < 0.005
TIE = C["tie_month_ends"]
assert len(TIE) == 12 and all(v["gap_cents"] == 0 for v in TIE.values())

# ---------------------------------------------------------------- county, planted events
PL = C["planted"]
CT = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
EV = {"C1": "the bank pays one check twice", "C2": "the bank keys a check number wrong",
      "C3": "the bank pays a different amount", "C4": "one invoice is paid twice, in two payments",
      "C5": "a voided check is paid anyway", "C6": "the bank pays a check the books never issued",
      "C7": "an electronic payment clears 8 business days after issue", "C8": "a payment never clears"}
CALL = {t: PL["R1"][t]["correct_call"] for t in CT}
RIGHT_C = {r: sum(PL[r][t]["right_calls"] for t in CT) for r in RULES}
assert RIGHT_C == {"R1": 100, "R2": 101, "R3": 100}
HIDDEN = {t: PL["R2"][t]["not_flagged_through_a_false_match"] for t in CT if CALL[t] == "flag"
          and PL["R2"][t]["not_flagged_through_a_false_match"]}
assert HIDDEN == {"C1": 2, "C5": 2, "C6": 2, "C8": 1}  # P4, plus the never-cleared payment
FLAG_KINDS = sum(1 for t in CT if CALL[t] == "flag")
assert FLAG_KINDS == 6 and (PL["R2"]["C7"]["flagged"], PL["R2"]["C7"]["not_flagged_through_a_false_match"]) == (19, 1)
assert all(PL[r]["C7"]["flagged"] == 20 for r in ("R1", "R3"))
assert all(PL["R3"][t]["right_calls"] == 20 for t in ("C1", "C3", "C5", "C6", "C8"))  # P6
C4F = {r: PL[r]["C4"]["flagged"] for r in RULES}
assert C4F == {"R1": 0, "R2": 1, "R3": 0}  # P5
C2O = PL["R2"]["C2"]["outcomes"]
assert C2O == {"left open": 8, "wrong payment": 6, "right payment": 6}

# ---------------------------------------------------------------- window sweep
SW = C["window_sweep_R3"]
WS = [3, 5, 10, 15, 20, 30, 40, 60]
PAPER = {w: SW[str(w)]["by_type"]["Paper"]["share"] for w in WS}
PAPER_N = {w: SW[str(w)]["by_type"]["Paper"]["break_before_clearing"] for w in WS}
PAPER_ALL = SW["5"]["by_type"]["Paper"]["cleared_payments"]
DELAY = {w: SW[str(w)]["never_cleared_delay_median"] for w in WS}
assert all(SW[str(w)]["by_type"]["Electronic"]["share"] == 0 for w in WS)
assert (PAPER_N[5], PAPER_N[15], PAPER_ALL, DELAY[5], DELAY[15]) == (3700, 794, 8039, 6, 16)
assert PAPER[5] < 0.5 and PAPER[10] >= 0.1 and PAPER[15] < 0.1  # P7: first clause missed, second held

# ---------------------------------------------------------------- processor
P = R["processor"]
PF, PC, PP = P["feeds"], P["clean"], P["planted"]
XT = ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]
XEV = {"X1": "a charge settles 6 business days late, across a month end", "X2": "the processor settles one charge twice",
       "X3": "the processor refunds half a charge, the books record a full refund",
       "X4": "a won dispute is paid back but never booked", "X5": "one batch's fees are charged at a higher rate",
       "X6": "the bank credit differs from the batch by 1 to 3 cents", "X7": "a payout never arrives"}
RIGHT_P = {r: sum(PP[r][t]["right_calls"] for t in XT) for r in RULES}
assert RIGHT_P == {"R1": 100, "R2": 120, "R3": 100}
assert all(PC[r]["false_matches"] == 0 for r in RULES)
P_OPEN = {r: PC[r]["unexplained_mean_usd"]["all"] for r in RULES}
P_BRK = {r: PC[r]["break_age_business_days"]["breaks"] for r in RULES}
assert P_OPEN["R1"] == P_OPEN["R2"] and P_OPEN["R3"] == PC["R3"]["unexplained_mean_usd"]["timing"]
assert (P_BRK["R1"], P_BRK["R3"]) == (18666, 86)
PME = {r: PC[r]["unexplained_month_end_usd"] for r in RULES}
assert all(PME["R3"][d] < PME["R1"][d] and PME["R3"][d] < PME["R2"][d] for d in PME["R3"])  # P8, first clause
assert (PP["R3"]["X5"]["flagged"], PP["R3"]["X6"]["flagged"], PP["R2"]["X1"]["flagged"], PP["R2"]["X6"]["flagged"]) == (0, 20, 20, 0)  # P9

# ---------------------------------------------------------------- held-out events (the follow-up)
HS = HO["summary"]
HRIGHT = {r: HS["county"][r]["right"] + HS["processor"][r]["right"] for r in RULES}
HAPPLIED = HS["county"]["applied"] + HS["processor"]["applied"]
HTOTAL = HS["county"]["events"] + HS["processor"]["events"]
assert HRIGHT == {"R1": 19, "R2": 18, "R3": 21} and (HAPPLIED, HTOTAL) == (22, 24)
assert HS["county"]["R3"]["right"] > max(HS["county"]["R1"]["right"], HS["county"]["R2"]["right"])  # P10
assert HS["processor"]["R3"]["right"] > max(HS["processor"]["R1"]["right"], HS["processor"]["R2"]["right"])
HE = {x["id"]: x for x in HO["events"]}
assert HS["county"]["not_applied"] == ["C08", "C09"]
assert not HE["P07"]["R3"]["right"] and HE["P07"]["R1"]["right"]
assert not HE["P06"]["R2"]["right"] and HE["P06"]["R3"]["right"]
assert not HE["C11"]["R1"]["right"] and not HE["C11"]["R2"]["right"] and HE["C11"]["R3"]["right"]
assert [x for x in HO["events"] if x.get("applied") and x["correct"] == "flag" and not x["R3"]["right"]] == [HE["P07"]]
ALL_RIGHT = sum(1 for x in HO["events"] if x.get("applied") and all(x[r]["right"] for r in RULES))
assert ALL_RIGHT == 17
HN_E = {x["id"]: x for x in HN["events"]}
assert HN["added_after_the_results"] and [HN_E["C08"][r]["right"] for r in RULES] == [False, False, False]
assert [HN_E["C09"][r]["right"] for r in RULES] == [False, False, True]

# ---------------------------------------------------------------- version 2: declared before it ran, added after the results
FS = R2V["fallback_sweep_county"]
HR = R2V["hidden_reference_county"]
KMC, KMP = R2V["break_age_kaplan_meier"]["county"], R2V["break_age_kaplan_meier"]["processor"]
OPP = R2V["open_once_per_payment_county"]
assert R2V["added_after_the_results"] and PRED2["added_after_the_results"] and len(PRED2["predictions"]) == 6
assert FS["5"]["false_matches_bank_join"] == FM and all(FS[str(w)]["right_fallback_pairings"] == 0 for w in WS)
CASC, LATE = FS["5"]["fallback_bank_line_lag_within_window"], FS["5"]["fallback_bank_line_lag_beyond_window"]
assert (CASC, LATE) == (44, 499) and CASC + LATE == FM
assert FS["60"]["false_matches_bank_join"] < FS["15"]["false_matches_bank_join"] < FM
H5 = HR["5"]
assert (H5["within_reach"], H5["right_within_reach"], H5["wrong_within_reach"], H5["none_within_reach"]) == (8430, 7125, 1305, 0)
WRONG_SHARE = {w: HR[str(w)]["wrong_within_reach"] / HR[str(w)]["within_reach"] for w in WS}
assert round(100 * WRONG_SHARE[5]) == 15 and min(WRONG_SHARE.values()) > 1 / 7 and max(WRONG_SHARE.values()) < 0.19
assert round(1 / WRONG_SHARE[5]) == 6
BD = R2B["debits_within_reach_paired_wrong"]
assert R2B["added_after_the_results"] and (BD["wrong"], BD["same_cents_and_same_issue_day"], BD["other_supplier"]) == (1305, 1011, 1301)
assert KMC["R1"]["median"] is None and KMC["R2"]["median"] is None and (KMC["R3"]["median"], KMC["R3"]["p90"]) == (4, 34)
assert KMP["R1"]["median"] is None and (KMP["R3"]["median"], KMP["R3"]["p90"]) == (20, 31)
assert OPP["R3"]["mean_usd"] == OPEN["R3"] and OPP["R1"]["mean_usd"] < OPEN["R1"] / 1.9
V2_RESULT = {"V1": "held", "V2": "held", "V3": "held", "V4": "missed", "V5": "held", "V6": "held"}
assert all(R2V["predictions"][k] == (v == "held") for k, v in V2_RESULT.items()) and not R2V["predictions"]["V3_opposite"]
V2_HELD = sum(v == "held" for v in V2_RESULT.values())

# ---------------------------------------------------------------- version 3, added after the results
OF = R3V["one_fit_rule_county"]
BT = R3V["by_payment_type_county"]
CF = R3V["exact_cents_first_county"]
assert R3V["added_after_the_results"] and PRED3["added_after_the_results"] and len(PRED3["predictions"]) == 6
assert all(OF[str(w)]["wrong_closes_within_reach"] == 0 and OF[str(w)]["debits"] == BANK for w in WS)
OF5, OF60 = OF["5"], OF[str(WS[-1])]
assert (OF5["right_closes"], OF5["wrong_closes"], OF5["look_alikes"], OF5["none"]) == (6887, 371, 1732, 4111)
assert (OF60["right_closes"], OF60["wrong_closes"], OF60["look_alikes"]) == (10121, 5, 2930)
UNDER = [w for w in WS if OF[str(w)]["wrong_closes_per_1000_debits"] < 1]
assert UNDER == [60]
SAFE = UNDER[0]
assert all(BT[str(w)]["Electronic"]["one_fit_wrong_closes"] == 0 for w in WS)
assert all(BT[str(w)]["Paper"]["one_fit_wrong_closes"] == OF[str(w)]["wrong_closes"] for w in WS)
assert BT["5"]["Electronic"]["within_reach"] == BT["5"]["Electronic"]["debits"] == BT["3"]["Electronic"]["within_reach"]
assert CF["5"]["wrong_within_reach"] == 1136 and BD["same_cents"] <= CF["5"]["wrong_within_reach"] <= BD["wrong"]
V3_RESULT = {"U1": "held", "U2": "held", "U3": "missed", "U4": "held", "U5": "missed", "U6": "held"}
assert all(R3V["predictions"][k]["held"] == (v == "held") for k, v in V3_RESULT.items())
V3_HELD = sum(v == "held" for v in V3_RESULT.values())

# ---------------------------------------------------------------- version 4, added after the results: breaks by kind, tie-out
BK = R4V["break_table_county_whole_payment"]
TO = R4V["tie_out_county"]
assert R4V["added_after_the_results"] and PRED4["added_after_the_results"] and all(R4V["predictions"].values())
assert len(R4V["predictions"]) == len(PRED4["predictions"]) == 8
assert BK["5"]["all"]["breaks"] == BRK["R3"]["breaks"]
assert all(BK[w][k]["breaks"] == 0 for w in ("5", "15") for k in ("K4", "K5", "K6"))
assert (BK["5"]["K1"]["breaks"], BK["15"]["K1"]["breaks"]) == (PAPER_N[5], PAPER_N[15])
assert all(BK[w]["K2"] == BK["15"]["K2"] and BK[w]["K3"] == BK["15"]["K3"] for w in ("5", "15"))
assert (BK["15"]["K2"]["breaks"], BK["15"]["K3"]["breaks"]) == (AN["never_cleared_payments"], F["voids"])
GAP_K2, GAP_K3 = round(PT["Disbursed"] - BK["15"]["K2"]["usd"], 2), round(PT["Cancelled"] - BK["15"]["K3"]["usd"], 2)
assert GAP_K2 == GAP_K3 == 0
GAP_K2 = GAP_K3 = 0.0
assert TO["T2_bank_lines_usd"] == PT["Paid"] and TO["T3_bank_lines"] == BANK and TO["T3_wrong_pairings"] == 0
assert TO["T1_gap_cents"] == TO["T2_gap_cents"] == 0 and TO["T4_vendor_payments_usd"] == PT["all"]
assert TO["T3_every_pair_to_the_cent"] and TO["T4_share_all_funds"] < 0.5 and TO["T4_share_general_fund"] < 1 / 3
assert BK["15"]["all"]["breaks"] == sum(BK["15"][k]["breaks"] for k in ("K1", "K2", "K3"))
V4_HELD = sum(R4V["predictions"].values())
assert V4_HELD == 8

# ---------------------------------------------------------------- what it is worth (assumed cost per item reviewed)
COST = AS["cost_per_item_reviewed_usd"]
LO, MID, HI = COST["low"], COST["mid"], COST["high"]
SAVE_WIN = PAPER_N[5] - PAPER_N[15]
assert SAVE_WIN == 2906

# ---------------------------------------------------------------- predictions
PRED_RESULT = {"P1": "held", "P2": "held", "P3": "held", "P4": "held", "P5": "held", "P6": "held",
               "P7": "partly missed", "P8": "held", "P9": "held", "P10": "held"}
assert OPEN["R1"] >= 2 * OPEN["R3"] and CL["R2"]["false_matches_per_1000_bank_lines"] >= 1  # P2, P3
assert all(PL[r]["C4"]["flagged"] <= 2 for r in RULES)
N_HELD = sum(v == "held" for v in PRED_RESULT.values())
assert N_HELD == 9 and len(PRED["predictions"]) == 10

def wk(w, adj=False):
    assert w % 5 == 0  # business days run Monday to Friday, no holidays (tools/recon.py)
    k = w // 5
    return f"{k}-week" if adj else f"{k} week" if k == 1 else f"{k} weeks"


PB = {w: BT[str(w)]["Paper"] for w in WS}  # every wrong lone-fit match was a paper check
PAPER_DEB = PB[5]["debits"]
assert all(PB[w]["debits"] == PAPER_DEB for w in WS) and PAPER_DEB + BT["5"]["Electronic"]["debits"] == BANK
P5, P60 = PB[5]["one_fit_wrong_closes_per_1000_debits"], PB[SAFE]["one_fit_wrong_closes_per_1000_debits"]
assert (P5, P60) == (46.2, 0.6) and [w for w in WS if PB[w]["one_fit_wrong_closes_per_1000_debits"] < 1] == [SAFE]
assert PB[SAFE]["one_fit_wrong_closes"] == OF60["wrong_closes"] == 5


def poisson_ci(k, conf=0.95):
    """Exact (Garwood) interval for a Poisson count k, by bisection on the cumulative probability."""
    from math import exp

    def cdf(k, mu):
        t, tot = exp(-mu), 0.0
        for i in range(k + 1):
            tot += t
            t *= mu / (i + 1)
        return tot

    def solve(f):
        lo, hi = 0.0, 100.0
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    a = (1 - conf) / 2
    lower = 0.0 if k == 0 else solve(lambda mu: a - (1 - cdf(k - 1, mu)))
    upper = solve(lambda mu: cdf(k, mu) - a)
    return lower, upper


CI_LO, CI_HI = (1000 * x / PAPER_DEB for x in poisson_ci(PB[SAFE]["one_fit_wrong_closes"]))
assert (round(CI_LO, 1), round(CI_HI, 1)) == (0.2, 1.5)
WORK5 = (OF5["look_alikes"] + OF5["none"]) / BANK  # debits a person must handle: look-alikes and no payment found
WORK60 = (OF60["look_alikes"] + OF60["none"]) / BANK
assert round(100 * WORK5) == 45 and round(100 * WORK60) == 23
WRONG_CUT = OF5["wrong_closes"] - OF60["wrong_closes"]  # every wrong lone-fit match was a paper check
assert WRONG_CUT == 366 and round(1000 * WRONG_CUT / PAPER_DEB) == 46  # about 46 fewer per 1,000 paper checks
# the reversal test, sized for power: n real paper-check debits without their number show the rate is under 1 per
# 1,000 when the upper end of the exact 95% range of the wrong count, over n, is under 1/1,000. The size is the
# smallest thousand at which that happens four times in five (80%), at a true rate equal to the observed 5 of 8,039
# and at 0.8 per 1,000. The call flips at 1 per 1,000 or more.
@functools.lru_cache(maxsize=None)
def poisson_upper(k):
    """Upper end of the exact 95% range for a Poisson count k, bracketed wide enough for counts in the hundreds."""
    from math import exp

    def cdf(mu):
        t, tot = exp(-mu), 0.0
        for i in range(k + 1):
            tot += t
            t *= mu / (i + 1)
        return tot
    lo, hi = 0.0, 50.0 + 3.0 * k
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > 0.025 else (lo, mid)
    return (lo + hi) / 2


def test_power(m, rate):
    """Chance that m debits at a true wrong rate `rate` give a 95% range wholly under 1 per 1,000."""
    from math import exp
    k = -1
    while poisson_upper(k + 1) / m < 1 / 1000:
        k += 1
    mu, t, tot = m * rate, exp(-m * rate), 0.0
    for i in range(k + 1):
        tot += t
        t *= mu / (i + 1)
    return tot


def test_size(rate):
    return next(m for m in range(1000, 1000001, 1000) if test_power(m, rate) >= 0.8)


assert abs(poisson_upper(5) - poisson_ci(5)[1]) < 1e-6  # the same bound as the 95% range shown
TEST_OBS, TEST_HI = test_size(OF60["wrong_closes"] / PAPER_DEB), test_size(0.8 / 1000)
assert (TEST_OBS, TEST_HI) == (48000, 184000)
assert round(test_power(26000, OF60["wrong_closes"] / PAPER_DEB), 2) == 0.55  # the size shown before: half the time
H1 = (f"When checks missing their number were matched only if one payment fit, searching {wk(SAFE)}, not 1, cut wrong "
      f"matches from {P5:.0f} in 1,000 to {P60}.")
CALL_LINE = f"Search {wk(SAFE)} back."
assert "matched only if one payment fit, searching 12 weeks, not 1, cut wrong matches from 46 in 1,000 to 0.6." in H1
assert len(H1.split()) <= 28 and len(CALL_LINE.split()) <= 10 and len(H1.split()) + len(CALL_LINE.split()) <= 30

PAGES = [("index.html", "Overview"), ("method.html", "Method"), ("checks.html", "Checks"), ("results.html", "Full results"),
         ("what-went-wrong.html", "What went wrong"), ("follow-up.html", "Follow-up"), ("glossary.html", "Glossary")]


# ---------------------------------------------------------------- charts
TK_WS = [5, 15, 60]


def takeaway_svg():
    Wd, right, top, row = 420, 60, 4, 46
    span = Wd - right
    H = top + row * len(TK_WS)
    vmax = max(PB[w]["one_fit_wrong_closes_per_1000_debits"] for w in TK_WS)
    bar_x = span * 1 / vmax
    out = [f'<svg viewBox="0 0 {Wd} {H}" role="img" aria-labelledby="tk-t" data-readout-default="Each bar shows wrong '
           f'matches per 1,000 paper checks for one search length. The dashed line is 1 per 1,000, where the call flips. '
           f'Point at a bar to read it.">',
           '<title id="tk-t">Paper checks matched to the wrong payment per 1,000, when a debit was matched only if one '
           'payment fitted, by how far back the match looked</title>']
    for i, w in enumerate(TK_WS):
        y = top + i * row
        o = PB[w]
        v = o["one_fit_wrong_closes_per_1000_debits"]
        wd = max(span * v / vmax, 2)
        key = w == SAFE
        rd = (f"Looking {wk(w)} back ({w} business days): of {n(o['debits'])} paper-check debits, "
              f"{n(o['one_fit_wrong_closes'])} were matched to the wrong payment ({v} per 1,000). Electronic debits: "
              f"none wrong.")
        out.append(f'<g class="tk-row pt" style="--tk-i:{i}" tabindex="0" data-readout="{e(rd)}"><title>{e(rd)}</title>'
                   f'<rect class="hit" x="0" y="{y}" width="{Wd}" height="{row - 4}"/>'
                   f'<text class="lab{" key" if key else ""}" x="0" y="{y + 14}">{wk(w)} back</text>'
                   f'<rect class="tk-mark{" tk-key" if key else ""}" x="0" y="{y + 20}" width="{wd:.1f}" height="20" rx="2"/>'
                   f'<text class="val{" tk-key-value" if key else ""}" x="{max(wd, bar_x) + 8:.1f}" y="{y + 35}">{v}</text></g>')
    for i in range(len(TK_WS)):  # over the bars only, clear of the row labels
        y = top + i * row
        out.append(f'<line class="tk-bar" x1="{bar_x:.1f}" x2="{bar_x:.1f}" y1="{y + 17}" y2="{y + 43}" '
                   f'stroke="currentColor" stroke-dasharray="3 3" stroke-width="1.5"/>')
    out.append("</svg>")
    return "".join(out)


def sweep_svg():
    Wd, H, left, right, top, bottom = 560, 250, 48, 16, 16, 40
    xs = {w: left + w / WS[-1] * (Wd - left - right) for w in WS}  # proportional to the window

    def y(v):
        return top + (1 - v / 0.8) * (H - top - bottom)
    out = [f'<svg class="sweep" viewBox="0 0 {Wd} {H}" role="img" aria-labelledby="sw-t" data-readout-default="Each point '
           f'is one window. Point at it to read the share of paper checks flagged before they cleared and the delay to flag '
           f'a check that never clears.">', '<title id="sw-t">Paper checks flagged before clearing, by window</title>']
    for t in (0, 0.2, 0.4, 0.6, 0.8):
        out.append(f'<line class="grid" x1="{left}" x2="{Wd - right}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text class="tick" x="{left - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{int(t * 100)}%</text>')
    pts = " ".join(f"{xs[w]:.1f},{y(PAPER[w]):.1f}" for w in WS)
    out.append(f'<polyline class="ser" points="{pts}"/>')
    for w in WS:
        rd = (f"Window of {w} business days: {n(PAPER_N[w])} of {n(PAPER_ALL)} paper checks ({pct(PAPER[w])}) flagged before "
              f"they cleared; a check that never clears is flagged {DELAY[w]:.0f} business days after issue.")
        out.append(f'<g class="pt{" is-key" if w == 5 else ""}" tabindex="0" data-readout="{e(rd)}"><title>{e(rd)}</title>'
                   f'<circle class="mk" cx="{xs[w]:.1f}" cy="{y(PAPER[w]):.1f}" r="6"/>'
                   f'<text class="tick" x="{xs[w]:.1f}" y="{H - 20}" text-anchor="middle">{w}</text></g>')
    out.append(f'<text class="tick" x="{(left + Wd - right) / 2:.1f}" y="{H - 4}" text-anchor="middle">window, business '
               f'days after issue</text></svg>')
    return "".join(out)


# ---------------------------------------------------------------- frame
CSS = (ROOT / "site" / "page.css").read_text(encoding="utf-8")


def head(title, desc):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            'initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="robots" content="noindex">'
            f'<meta name="description" content="{e(desc)}"><title>{e(title)}</title><link rel="icon" href="data:,">'
            '<link rel="preload" href="vendor/viz-design-system/assets/fonts/newsreader-latin-500-normal.woff2" as="font" type="font/woff2" crossorigin>'
            '<link rel="preload" href="vendor/viz-design-system/assets/fonts/public-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>'
            '<link rel="preload" href="vendor/viz-design-system/assets/fonts/public-sans-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>'
            '<link rel="stylesheet" href="vendor/viz-design-system/tokens.css"><link rel="stylesheet" href="vendor/viz-design-system/kit/kit.css">'
            '<link rel="stylesheet" href="vendor/viz-design-system/kit/takeaway.css"><link rel="stylesheet" href="vendor/viz-design-system/kit/wayfinding.css">'
            f'<style>{CSS}</style><script src="vendor/viz-design-system/kit/kit.js"></script>'
            '<script src="vendor/viz-design-system/kit/takeaway.js"></script>'
            '<script src="vendor/viz-design-system/kit/wayfinding.js" defer></script></head><body>')


SITE_HEADER = ('<a class="kit-skip" href="#main">Skip to content</a><header class="site"><div class="kit-wrap site-row">'
               '<p class="site-id"><a class="site-name" href="../">Diogo Travassos</a><span class="site-role">Data '
               'leadership · Analytics · Decision-making</span></p><nav aria-label="Site"><a href="../#studies">Studies</a>'
               '<a href="https://www.linkedin.com/in/diogo-travassos/">LinkedIn</a><a href="mailto:hello@diogotravassos.dev">'
               'Email</a><button class="theme-toggle" type="button" data-theme-toggle>Theme: auto</button></nav></div></header>')
FOOTER = ('<footer class="site"><div class="kit-wrap"><p><span>Public data, with a synthetic card processor</span>'
          '<a href="../#studies">Back to all studies</a></p></div></footer></body></html>\n')


def study_nav(here):
    cur = ' aria-current="page"'
    links = "".join(f'<a href="{p}"{cur if p == here else ""}>{e(t)}</a>' for p, t in PAGES)
    return f'<nav class="study-pages kit-wrap" aria-label="Study pages"><p class="links">{links}</p></nav>'


def section(sid, title, body):
    return (f'<section id="{sid}" class="block kit-wrap" aria-labelledby="{sid}-title"><h2 id="{sid}-title">{e(title)}</h2>'
            f'{body}</section>')


def ul(items):
    return '<ul class="notes">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


SUB_LEAD = {"method.html": "How the data was read, and how each rule was built and run.",
            "checks.html": "The checks that the records were read and rebuilt without losing a cent.",
            "results.html": "Every figure for each rule, by window and by payment type.",
            "what-went-wrong.html": "The problems each rule missed, and why.",
            "follow-up.html": "Test cases from an author who never saw the rules.",
            "glossary.html": "Each term in plain words."}


def subpage(fname, title, h1, limit, sections, desc):
    hero = (f'<section class="hero kit-wrap" aria-labelledby="hero-title"><p class="hero-tags"><span class="tag tag-data">'
            f'Public data</span></p><p class="hero-piece"><a href="index.html">{e(STUDY_TITLE)}</a>: {e(title)}</p>'
            f'<h1 id="hero-title">{e(h1)}</h1><p class="hero-lead">{e(SUB_LEAD[fname])}</p></section>')
    body = "".join(section(*s) for s in sections) + section("limits", "Limits", f"<p>{e(limit)}</p>")
    page = head(f"{title}: {STUDY_TITLE}", desc) + SITE_HEADER + '<main id="main">' + hero + body + study_nav(fname) + "</main>" + FOOTER
    (ROOT / fname).write_text(page, encoding="utf-8")
    return page


# ---------------------------------------------------------------- entry page (caveats only in the limits section)
hero = (f'<section class="hero kit-wrap" aria-labelledby="hero-title"><p class="hero-tags"><span class="tag tag-data">'
        f'Public data</span></p><p class="hero-piece">{e(STUDY_TITLE)}</p><h1 id="hero-title">{e(H1)}</h1>'
        f'<p class="hero-call">{e(CALL_LINE)}</p></section>')
takeaway = (f'<div class="kit-wrap"><figure class="chart takeaway tk-bars" id="takeaway"><figcaption>A fit is an open '
            f'payment within US$1.00 of the debit, issued in the weeks searched. With one required, a longer search '
            f'found the true payment, so wrong matches fell.</figcaption>'
            f'<p class="chart-unit">Paper checks matched to the wrong payment, per 1,000 of {n(PAPER_DEB)}; the dashed line '
            f'is 1 per 1,000, where the call flips</p>'
            f'<div class="chart-plot">{takeaway_svg()}</div></figure>'
            f'</div>')

HSC, HSP = HS["county"], HS["processor"]
R1_REF = CL["R1"]["pairs_intermediary_to_bank"]
assert R1_REF == BANK and CL["R2"]["pairs_intermediary_to_bank"] < BANK
assert RIGHT_C["R1"] == RIGHT_C["R3"] == RIGHT_P["R1"] == RIGHT_P["R3"]
todo = section("do", "What to do", (
    f"<p>Every day, finance matches the books, the payment run and the bank statement. Here three ways of matching them "
    f"ran over a county's {n(BANK)} bank debits, closing every business day. Then each debit's check number was hidden "
    f"in turn.</p>" + ul([
    f"<strong>Without a check number, match a debit only when one open payment fits, searching {wk(SAFE)} "
    f"back.</strong> Electronic payments were never matched wrong: each cleared within 3 business days.",
    f"<strong>Never let the software choose between two that fit.</strong> Taking the oldest, {wk(5)} back, was wrong "
    f"for {BT['5']['Paper']['forced_pick_wrong_per_1000_within_reach']} in 1,000 paper checks whose payment was in the "
    f"search. Searching further made it worse.",
    f"<strong>Pair a check with all the invoices it pays</strong>, and match their total to the bank line to the cent. "
    f"Here {n(MULTI)} of {n(PAY)} payments paid several invoices. Treat a card processor's payout the same way.",
    f"<strong>Wait about {wk(15)} before chasing a paper check.</strong> With a {wk(5, True)} wait, {pct(PAPER[5], 0)} "
    f"were chased before they cleared.",
    "<strong>Add two checks that matching cannot do:</strong> duplicate invoices before paying, since an invoice paid "
    "twice looks right everywhere, and processor fees against the contract rate.",
])))

worth = section("worth", "What it is worth", (
    f"<p>Here, a {wk(15, True)} wait instead of {wk(5)} means {n(SAVE_WIN)} fewer needless chases of paper "
    f"checks a year. Searching {wk(SAFE)} back instead of 1 means about {1000 * WRONG_CUT / PAPER_DEB:.0f} fewer wrong "
    f"matches in every 1,000 paper checks that arrive without their number. It halves the debits sent to a person.</p>"
    f"<p>If each chase costs {usd0(LO)} to {usd0(HI)} of staff time, the fewer chases save {usd0(SAVE_WIN * LO)} "
    f"to {usd0(SAVE_WIN * HI)} a year. The price: a check that never clears is caught {DELAY[15]:.0f} business days "
    f"after issue, not {DELAY[5]:.0f}.</p>"))


def bk_row(label, what, k):
    a = BK["15"][k]
    return (f'<tr><th scope="row"><strong>{e(label)}</strong> {e(what)}</th><td class="num">{n(a["breaks"])}</td>'
            f'<td class="num">{usd(a["usd"])}</td></tr>')


team = section("team", "Putting it to work", ul([
    "<strong>The reconciliation lead runs it beside the current matching for one month-end close</strong>, and names "
    "a cause for every difference.",
    f"<strong>Accounts payable owns the debits sent to a person</strong>, {pct(WORK60, 0)} of debits without a check "
    f"number here, and samples the automatic matches monthly.",
    "<strong>Treasury sets each payment type's wait</strong> from last year's clearing times.",
    "<strong>Give the two outside checks an owner:</strong> duplicate invoices to accounts payable, processor fees to "
    "the contract owner.",
    "<strong>At each close, report</strong> money left open as a share of money moved, breaks by kind, and matches "
    "made without a check number.",
]))

numbers = section("numbers", "Three numbers that matter", ul([
    f"<strong>{P60} in 1,000.</strong> Paper checks without their number matched wrong, searching {wk(SAFE)} back, "
    f"against {P5} at {wk(5)}.",
    f"<strong>{pct(WORK60, 0)}.</strong> Debits sent to a person, searching {wk(SAFE)} back, against {pct(WORK5, 0)} at "
    f"{wk(5)}.",
    f"<strong>{n(BK['15']['all']['breaks'])} breaks.</strong> Payments still unmatched after a {wk(15, True)} wait, "
    f"against {n(BK['5']['all']['breaks'])} at {wk(5)}.",
]) + (
    f'<div class="table-scroll"><table class="data"><caption>Breaks by kind, at a {wk(15, True)} wait</caption><thead>'
    f'<tr><th scope="col">Kind, and what happened</th><th scope="col" class="num">Breaks</th>'
    f'<th scope="col" class="num">Amount</th></tr></thead><tbody>'
    + bk_row("Paper check cleared late.", "Timing: it cleared after the wait.", "K1")
    + bk_row("Payment never cleared.", "Still open at the end of the data.", "K2")
    + bk_row("Check voided late.", "Cancelled after the wait, so never paid.", "K3")
    + f'<tr><th scope="row"><strong>All breaks</strong></th><td class="num">{n(BK["15"]["all"]["breaks"])}</td>'
      f'<td class="num">{usd(BK["15"]["all"]["usd"])}</td></tr></tbody></table></div>'
    f"<p>All {n(BK['15']['all']['breaks'])} look alike at the wait, so each gets a chase. By the end of the data, "
    f"{n(BK['15']['K2']['breaks'])} had never cleared. No electronic payment or invoice line broke.</p>"))
assert BK["5"]["all"]["breaks"] - BK["15"]["all"]["breaks"] == SAVE_WIN  # the fewer chases are all late-clearing checks

change = section("change", "What would change the conclusion", (
    f"<p>The call rests on {P60} wrong matches per 1,000 paper checks at {wk(SAFE)}. If a real bank statement showed "
    f"1 per 1,000 or more, I would send every debit without a check number to a person.</p>"
    f"<p>The test: match real paper-check debits that arrived without their number, and check each match against the "
    f"check register. At 1 wrong per 1,000 or more, the call flips. To show the rate is under 1 four times in five "
    f"takes {n(TEST_OBS)} debits at the {P60} seen here, and {n(TEST_HI)} at 0.8. A cheaper first check: rerun the "
    f"county's other public years.</p>"))

limits = section("limits", "Limits", ul([
    "<strong>The bank lines are not a real statement.</strong> The payments and clearing dates are real, but each bank "
    "line is built from its payment, so the debits equal the paid total by construction. Unlike real ones, the lines "
    "carry no payment type. A single fit goes wrong here only when the true payment is older than the search. Real "
    f"fees, partial amounts and type codes could move {P60}, and the share sent to a person, either way.",
    f"<strong>Check numbers were hidden one at a time.</strong> With many missing at once, wrong matches could rise or "
    f"fall. The {wk(SAFE, True)} figure is {n(OF60['wrong_closes'])} of {n(PAPER_DEB)} paper checks, with a 95% range "
    f"of {CI_LO:.1f} to {CI_HI:.1f} per 1,000. It treats each check as independent, so it may be too narrow. So this "
    f"data cannot yet show the rate is under 1.",
    f"<strong>One county, one year.</strong> The {wk(SAFE, True)} search follows this county's clearing times. Its "
    f"other public years were not run.",
    "<strong>Whole-payment matching's lead in money left open is built in.</strong> The one-to-one rules cannot pair a "
    "payment made of several invoice lines or batch rows.",
    "<strong>The card processor is synthetic.</strong> No public source has all three records for one business.",
    "<strong>The data gives each break's kind, not its cause:</strong> it records when a payment cleared, never why.",
    f"<strong>Nothing here ties to an outside figure.</strong> The status totals add to the year's {usd(PT['all'])} by "
    f"construction. The county's 2024 annual report puts General Fund spending at "
    f"{usd0(TO['T4_general_fund_expenditures_usd'])}; the General Fund payments here, "
    f"{usd(TO['T4_fund_100_vendor_payments_usd'])}, are {pct(TO['T4_share_general_fund'])} of it. That spending also "
    f"counts payroll, debt payments and costs owed but unpaid, and the report shows it by function, not by supplier "
    f"payments. So public data cannot close the gap.",
    f"<strong>Tested as declared:</strong> the three rules, the daily close, the waits and the planted problems. Added "
    f"after the first results, with predictions written first: the hidden-number test, its {wk(SAFE, True)} result and "
    f"the break table. The hidden-number test replaced a flawed first comparison. The rule fixed before the run "
    f"counted all debits: {OF60['wrong_closes_per_1000_debits']} per 1,000 at {wk(SAFE)}, the shortest under 1 either "
    f"way.",
    "<strong>Staff cost per chase is an estimate</strong>, set after the results, not measured. How often a bank line "
    "lacks its check number is not known, so the matching call is not priced.",
    f"<strong>Caught-or-missed figures come from planted problems</strong>, because real data lists none of its own "
    f"errors. An independent author's {HSC['applied'] + HSP['applied']} cases were too few to separate the rules.",
]))

details = section("details", "Detail pages", (
    '<p class="links"><a href="method.html">Method</a><a href="checks.html">Checks</a><a href="results.html">Full '
    'results</a><a href="what-went-wrong.html">What went wrong</a><a href="follow-up.html">The follow-up</a>'
    '<a href="glossary.html">Glossary</a><a href="method.html#use">Use it at your company</a><a href="README.md">'
    'Reproduce it</a></p>'))

USE_PROMPT = """Help me compare matching rules for our daily three-way reconciliation, using the extracts I paste below: our books (invoice or order lines with the payment or charge they belong to), the payment run or the processor's settlement report, and the bank statement lines.

Method:
1. Write down what links each pair of sources: the payment or charge id between the books and the middle record, and the check number or batch reference between the middle record and the bank line.
2. Run three rules over every business day: exact reference one to one; reference with a small tolerance, then amount and date when no reference pairs; and whole payment, where the lines of one payment, or the rows of one batch netted with fees and refunds, pair with one bank line by reference, to the cent.
3. At each close, call a record in transit while it is younger than a window you set per payment type, and a break after that. Measure our real clearing lags first.
4. For each rule, report: pairings whose records do not belong together (check them by reference), money left open at each close, and how long a break stays open.
5. Hide the reference of each bank line in turn, keep every other record as it is, and count how often amount and date alone pick the wrong record: once taking the oldest candidate, once matching only when a single candidate fits. Count wrong matches over all bank lines, by look-back and by payment type.
6. Plant a few known problems on a copy (a debit paid twice, a voided check paid, an invoice paid twice, a fee charged at the wrong rate) and report which rule flags each.

Report back: the three rules side by side, the window per payment type, which rule you would use and why, and two checks the matcher cannot do. Never pair records on amount alone without showing me."""
USE_PROMPT_FRAMED = (f'This method comes from Diogo Travassos\'s study "{STUDY_TITLE}" ({STUDY_URL}). If you can open links, '
                     "read it first: it compares three matching rules on a county's public payment records and a "
                     "synthetic card processor, and shows where each one failed. The steps below stand on their own if "
                     "you can't.\n\n" + USE_PROMPT + f"\n\nIn your report, say which study you followed and link it: {STUDY_URL}")
USE_SECTION = ("use", "Use this at your company", (
    '<p>To compare matching rules on your own records, paste this into your AI assistant along with your three extracts.</p>'
    f'<pre class="prompt">{e(USE_PROMPT_FRAMED)}</pre>'))

ENTRY_SECTIONS = [("do", "What to do"), ("worth", "Worth"), ("team", "Putting it to work"),
                  ("numbers", "Three numbers"), ("change", "What would change it"), ("limits", "Limits"),
                  ("details", "Detail pages")]
nav = "".join(f'<a href="#{i}">{e(t)}</a>' for i, t in ENTRY_SECTIONS)
DESC = ("Three matching rules compared on a county's public payment records and a synthetic card processor: wrong "
        "pairings, a hidden-reference test, money left open at each day's close, and how long a break stays open.")
entry = (head(STUDY_TITLE, DESC) + SITE_HEADER + '<main id="main">' + hero + takeaway +
         f'<div class="kit-section-bar"><nav class="page-nav" aria-label="Page sections">{nav}</nav>'
         '<span class="kit-progress" aria-hidden="true"></span></div>' + todo + worth + team + numbers + change + limits +
         details + '<nav class="next-study kit-wrap" data-next-study aria-label="Next study"><a href="../#studies">All '
         'studies</a></nav>' + "</main>" + FOOTER)
(ROOT / "index.html").write_text(entry, encoding="utf-8")

# ---------------------------------------------------------------- method
DATA_LINE = ("Fulton County Government (GA), Vendor Payments, fiscal year 2024, published under CC BY 4.0: "
             f"{n(46126)} rows, one per invoice paid.")
subpage("method.html", "Method",
        f"{n(MULTI)} of {n(PAY)} payments paid several invoices, so one-to-one rules could not close them, on one county's public records.",
        "The bank lines are built from the county's published clearing dates, and the card processor is synthetic."
        " The bank lines carry no payment type, so a debit could fit a payment of the other type. With type codes, the oldest pick's wrong rates could only fall.",
        [("data", "The two data sets", (
            '<p>This study continues <a href="../arr-reconciliation/">ARR reconciliation</a>, which built one number '
            'from systems that disagree. This one follows money in motion through three records, every business day.</p>'
            f"<p><strong>County, real.</strong> {e(DATA_LINE)} Each row carries the payment document, check number, "
            f"payment type, supplier, invoice, amount and the date the payment cleared or was cancelled. It gives three "
            f"feeds. The books hold one line per invoice, {n(F['ledger_lines'])} lines. The payment run holds {n(PAY)} "
            f"payments, each the net of its lines. The bank holds {n(BANK)} debits, one per payment on the day it cleared, "
            f"and there are {n(F['voids'])} voids. {n(AN['zero_net_documents'])} documents whose lines net to exactly "
            f"zero ({n(F['excluded_zero_net_lines'])} lines) were left out of every feed before any scored run. No money "
            f"moved on them. Before the design, only descriptive counts were looked at, clearing lags by payment type "
            f"among them. No rule was run, and no amount shared between payments was counted.</p>"
            f"<p><strong>Card processor, synthetic.</strong> A software company selling by card in US and Canadian "
            f"dollars, from January to June 2025: {n(PF['charges'])} charges, with refunds, disputes and won disputes. "
            f"The settlement report has one row per settled item and one fee row per charge. Each daily batch ends in one "
            f"payout row. Its shape follows a published processor settlement report specification. The bank statement has "
            f"one credit per payout, shaped by the camt.053 format, with the batch number in its remittance text. "
            f"{n(PF['carried_batches'])} batches whose net was zero or less were carried into the next payout, as "
            f"processors do.</p>")),
         ("rules", "The three rules", ul([
             f"<strong>{NAME['R1']}.</strong> One to one. Two records pair when they carry the same reference and the "
             f"same amount to the cent. Dates are not compared.",
             f"<strong>{NAME['R2']}.</strong> One to one. As the first rule, but amounts may differ by up to US$1.00 and "
             f"the later record must come at most {W} business days after the earlier. So a check clearing more than {W} "
             f"business days after issue is refused even when its number matches. A bank line that pairs with nothing by "
             f"reference then takes the oldest open payment within US$1.00 dated up to {W} business days before it.",
             f"<strong>{NAME['R3']}.</strong> Many to one. The invoice lines of one payment pair as a group with the "
             f"payment when their net equals its total to the cent. The payment then pairs with the bank line carrying its "
             f"check number. A processor batch pairs the same way: every row, fees and refunds included, netted against the "
             f"bank credit that names the batch. There is no amount-only fallback.",
         ]) + "<p>The rules were fixed before any scored run and did not change after.</p>"),
         ("close", "The daily close", (
             f"<p>A close runs every business day and sees every record dated that day or earlier. A record is paired "
             f"once, at the first close where a rule can pair it, and never unpaired. An unpaired record is in transit "
             f"while it is at most {W} business days old, and a break after that. Every rule uses the same window. "
             f"Money left open is the sum of every break on either side of either join, at each close. A payment open on "
             f"both sides therefore counts twice, so the sum can exceed the money paid. The second version also counts "
             f"each payment once.</p>")),
         ("planted", "The planted events", (
             f"<p>Each kind of event was planted 20 times on a copy of the clean feeds. Its correct call was fixed in "
             f"advance: flag it for a person, or explain it as timing or rounding. A rule flags an event when a record it "
             f"touched becomes a break within 20 business days.</p><h3>County</h3>" +
             ul([f"{EV[t][0].upper() + EV[t][1:]}: {CALL[t]}." for t in CT]) + "<h3>Card processor</h3>" +
             ul([f"{XEV[t][0].upper() + XEV[t][1:]}: {PP['R1'][t]['correct_call']}." for t in XT]))),
         ("predictions", "Predictions, fixed before the runs", (
             f"<p>{N_HELD} of the 10 numbered predictions held and 1 partly missed. The expected finding, clause by clause:</p>"
             + ul([
                 "whole-payment matching leaves the least money open at each close: held;",
                 f"and makes the most right calls on planted events: did not hold, because the fallback rule made "
                 f"{RIGHT_C['R2']} of 160 and {RIGHT_P['R2']} of 140 against {RIGHT_C['R3']} and {RIGHT_P['R3']};",
                 "the one-to-one rules cannot pair payments made of several invoice lines: held;",
                 "the amount fallback pairs real payments that share an amount with the wrong bank line, so it hides some "
                 "planted problems: held;",
                 "every rule misses an invoice paid twice: held;",
                 f"a 5-day window flags most paper checks before they clear: did not hold, {pct(PAPER[5], 0)}."]) +
             f"<p>The opposite: the county's amounts are distinct enough that the fallback makes no wrong pairing.</p>"
             f"<p>The partial miss: {pct(PAPER[5], 0)} of paper checks were flagged before clearing at 5 days, not at least "
             f"half. The share did fall under 10% only at 15 days or more, as predicted. "
             f'<a href="predictions-r1.json">The predictions as written</a>.</p>')),
         ("version2", "Version 2, added after the results", (
             "<p>Added after the results, with six predictions and their pass bars. The first version's results stay as "
             "they were, misses included.</p>" + ul([
                 "<strong>The fallback rule at every window.</strong> The same rule at every window from 3 to 60 business "
                 "days. Each fallback pairing is split by whether the bank line's own payment had been issued within the "
                 "window, and so was taken earlier by a wrong pairing.",
                 f"<strong>The hidden-reference test.</strong> Each of the county's {n(BANK)} bank debits has its check "
                 f"number treated as unreadable in turn, while every other record keeps its own. At that debit's close, "
                 f"the fallback takes the oldest open payment within US$1.00 issued within the look-back before it. Every "
                 f"other debit keeps its check number and takes its own payment by reference. That leaves fewer open "
                 f"payments to confuse than if many were unreadable at once, but it is not a proven best case.",
                 "<strong>Break age with still-open breaks counted.</strong> A Kaplan-Meier estimate, so a break still "
                 "open at the last close counts for the age it had reached.",
                 "<strong>Money open counted once per payment.</strong> A payment's amount counts once at a close if any "
                 "of its records is a break.",
             ]) + f"<p>{V2_HELD} of the 6 predictions held. The miss: more wrong picks were expected at 15 days than at 5, "
             f"and there were slightly fewer, {HR['15']['wrong_per_1000_within_reach']} per 1,000 against "
             f"{HR['5']['wrong_per_1000_within_reach']}. <a href=\"predictions-r2.json\">The second version's predictions "
             f"as written</a>.</p>")),
         ("version3", "Version 3, added after the results", (
             "<p>Added after the results, with six predictions and their pass bars. The second version takes the oldest "
             "payment that fits, so each wrong pick it made within reach had a look-alike beside the true payment. Many "
             "matching tools instead match only a lone fit.</p>" + ul([
                 f"<strong>Lone fit only.</strong> With each debit's check number hidden as before, the debit is matched "
                 f"only when exactly one open payment fits. Two or more send it to a person, and none leaves it open. Wrong "
                 f"matches are counted over all {n(BANK)} debits.",
                 "<strong>By payment type.</strong> Paper and electronic debits separately, under both picks.",
                 "<strong>Exact cents first.</strong> The oldest pick, but preferring a payment equal to the debit to the "
                 "cent.",
             ]) + f"<p>{V3_HELD} of the 6 predictions held. Look-alikes were {pct(OF5['look_alikes_share_within_reach'])} "
             f"of the debits within reach at 5 days, under the 25% predicted. And electronic debits, not paper, drew the "
             f"most wrong picks among look-alikes: {BT['5']['Electronic']['forced_pick_wrong_per_1000_within_reach']} per "
             f"1,000 against {BT['5']['Paper']['forced_pick_wrong_per_1000_within_reach']}. "
             f'<a href="predictions-r3.json">The third version\'s predictions as written</a>.</p>')),
         ("version4", "Version 4, added after the results", (
             "<p>Added after the results, with eight checks and predictions written before it ran. It adds no rule and "
             "changes no figure. Each break of the whole-payment run is put in one of six kinds, at waits of 5 and 15 "
             "business days. Four kinds are payments: a paper check cleared after the wait, a check never cleared, a "
             "check voided late, and an electronic payment cleared late. The others are an invoice line dated apart from "
             "its payment, and anything else.</p>"
             f"<p>The year's money is tied to the county's status totals, which add up by construction, and compared with "
             f"the county's 2024 annual financial report, which does not tie. The General Fund's payments, "
             f"{usd(TO['T4_fund_100_vendor_payments_usd'])}, are {pct(TO['T4_share_general_fund'])} of its "
             f"{usd0(TO['T4_general_fund_expenditures_usd'])}. "
             f"{V4_HELD} of the 8 predictions held. "
             f'<a href="predictions-r4.json">The fourth version\'s predictions as written</a>.</p>')),
         ("tools", "Tools", (
             "<p>Python only, standard library: <a href=\"tools/recon.py\">the matcher</a>, the feed builders for "
             '<a href="tools/county.py">the county</a> and <a href="tools/processor.py">the processor</a>, '
             '<a href="tools/plant.py">the planted events</a> and <a href="tests/test_study.py">the tests</a>. The later '
             'versions: <a href="tools/run_r2.py">the second</a>, <a href="tools/run_r3.py">the third</a> and '
             '<a href="tools/run_r4.py">the fourth</a>. The '
             '<a href="followup/author-prompt.txt">independent author\'s brief</a> and <a href="followup/bundle/README.md">'
             "everything the author saw</a> are published too. In production the same rules would sit in a warehouse "
             "model or a reconciliation tool; nothing here depends on one.</p>")), USE_SECTION],
        "How the three-way reconciliation study was built: data, rules, daily close, planted events and predictions.")

# ---------------------------------------------------------------- checks
subpage("checks.html", "Checks",
        f"The {n(PAY)} payments built from the extract held every cent of its {mill(PT['all'])}, on one county's public records.",
        "The month-end tie is a bookkeeping identity here, because the bank lines are built from the county's own table.",
        [("sources", "The source adds up", ul([
            f"Paid {usd(PT['Paid'])}, cancelled {usd(PT['Cancelled'])} and issued but never presented {usd(PT['Disbursed'])} "
            f"add to {usd(PT['all'])}, the sum of the extract's rows and the money in the {n(PAY)} payments.",
            f"The extract has {n(46126)} rows, the count the county's portal itself reports for fiscal year 2024. They "
            f"are pinned by a checksum, checked every time the feeds are built.",
            f"{n(F['ledger_lines'])} invoice lines remain after the {n(F['excluded_zero_net_lines'])} lines of zero-net "
            f"documents are left out, and every one belongs to exactly one payment.",
        ])),
         ("tie", "The close ties at every month end", (
             f"<p>At each of the 12 month ends of 2024, payments issued less voids less bank debits equalled the money in "
             f"payments not yet cleared, payment by payment. The gap was 0 cents every time. On real bank data this is "
             f"the check that fails first; here it passes by construction, so it shows the arithmetic, not the data.</p>")),
         ("truth", "Wrong pairings are counted against the truth", (
             "<p>The feed builders keep which records truly belong together, and the planting code adds each planted "
             "record's truth. A pairing is wrong when its two records do not belong together. A planted spurious record "
             "belongs to nothing.</p>")),
         ("anomalies", "What the real data held", ul([
             f"{n(AN['never_cleared_payments'])} payments issued and never presented to the bank, worth "
             f"{usd(AN['never_cleared_usd'])}. They stay open to the last close under every rule.",
             f"{n(AN['several_disbursement_dates'])} payments whose lines carry more than one payment date.",
             f"{n(AN['zero_net_documents'])} documents whose lines net to zero, left out as above.",
         ])),
         ("tests", "Tests", (
             "<p>The tests pin the data checksum and the feed counts. They run each rule on small fixed test cases: a split "
             "payment, a shared amount, a void and a late check. They also check that every event kind plants 20 "
             "instances, that the independent event grammar applies and that the first version's results file is unchanged. "
             "One more checks that a lone fit never matches a debit in reach to the wrong payment.</p>"))],
        "The checks behind the three-way reconciliation study: totals, month-end tie, truth table, anomalies and tests.")

# ---------------------------------------------------------------- full results
def rule_list(cl, km, once=None):
    out = []
    for r in RULES:
        m = cl[r]
        b, k = m["break_age_business_days"], km[r]
        assert (k["breaks"], k["closed"], k["still_open"]) == (b["breaks"], b["closed"], b["censored"])
        age = (f"the median age is {k['median']} business days, and 1 in 10 stayed open {k['p90']} or more"
               if k["median"] is not None else "the median age was not reached, because more than half were still open when the data ended")
        s = (f"<strong>{NAME[r]}.</strong> Wrong pairings: {n(m['false_matches'])}"
             + (f", worth {usd(m['false_matches_usd'])}" if m["false_matches"] else "")
             + f". Open at an average close, summed over both sides: {usd(m['unexplained_mean_usd']['all'])}")
        if once:
            s += (f". Counted once per payment: {usd(once[r]['mean_usd'])}, "
                  f"{pct(once[r]['share_of_money_in_payments'], 2)} of the money paid")
        s += (f". Breaks: {n(b['breaks'])}, of which {n(b['closed'])} closed within the data and {n(b['censored'])} were "
              f"still open at the last close. With the open ones counted, {age}.")
        out.append(s)
    return ul(out)


V2_NOTE = ("<p>Two measures below were added after the results, in the second version. One counts money once per "
           "payment. The other gives break ages that count the breaks still open, a Kaplan-Meier estimate.</p>")


def planted_list(pl, types, ev):
    return ul([f"{ev[t][0].upper() + ev[t][1:]}. Correct call: {pl['R1'][t]['correct_call']}. Right calls of 20: " +
               ", ".join(f"{SHORT[r]} {pl[r][t]['right_calls']}" for r in RULES) + "." for t in types])


me_rows = "".join(f'<tr><th scope="row">{d}</th>' + "".join(f'<td class="num">{mill(ME[r][d], 2)}</td>' for r in RULES)
                  + "</tr>" for d in ME["R3"])
subpage("results.html", "Full results",
        f"Paper checks flagged before they cleared fell from {pct(PAPER[5], 0)} at a {W}-day window to {pct(PAPER[15])} "
        f"at 15, on one county's public records.",
        "One county's year and one synthetic processor, each run once, so no figure carries a spread."
        " The bank lines carry no payment type, so a debit could fit a payment of the other type. With type codes, the oldest pick's wrong rates could only fall.",
        [("county", "County: clean feeds", V2_NOTE + rule_list(CL, KMC, OPP) + (
            "<p>Exact reference and whole payment cannot pair wrongly on these feeds, because the truth of which records "
            "belong together is the check number itself. Their zeros follow from the data's construction.</p>"
            f"<p>Whole-payment matching left {mill(SPLIT3['all'], 2)} open on average. Of that, {mill(SPLIT3['timing'], 2)} "
            f"was timing: its counterpart arrived later. {mill(SPLIT3['none'], 2)} had no counterpart at all, mostly "
            f"checks never presented. None was open because the rule could not pair records that belong together.</p>"
            f"<p>Under the two one-to-one rules, most open money, summed over both sides, had its partner already there. That was "
            f"{mill(CL['R1']['unexplained_mean_usd']['rule'], 0)} of {mill(OPEN['R1'], 0)} for exact references and "
            f"{mill(CL['R2']['unexplained_mean_usd']['rule'], 0)} of {mill(OPEN['R2'], 0)} for the fallback rule. Neither "
            f"can pair the invoice lines of a payment that pays several invoices, {mill(MULTI_USD)} of the "
            f"{mill(MOVED)} paid. The fallback rule also refuses a check that clears after its {W}-day window.</p>"
            f"<p>Whole-payment matching left the least money open at every one of the 12 month ends.</p>"
            '<div class="table-scroll"><table class="data"><caption>Money open at each 2024 month-end close, by rule, '
            'summed over both sides</caption><thead><tr><th scope="col">Month end</th>' + "".join(f'<th scope="col" class="num">{e(NAME[r])}</th>' for r in RULES)
            + f"</tr></thead><tbody>{me_rows}</tbody></table></div>")),
         ("window", "County: the window for paper checks", (
             f"<p>Electronic payments never became a break before clearing, at any window. Paper checks did: "
             f"{pct(PAPER[5])} at {W} business days, {pct(PAPER[10])} at 10, {pct(PAPER[15])} at 15 and {pct(PAPER[60], 2)} "
             f"at 60. A longer window delays the flag on a check that never clears by the same amount.</p>"
             f'<figure class="chart" id="sweep-fig"><figcaption>Share of the {n(PAPER_ALL)} paper checks flagged before '
             f'they cleared, by window, whole-payment matching</figcaption><div class="chart-plot">{sweep_svg()}</div>'
             f'</figure>')),
         ("county-planted", "County: planted events, 20 of each", planted_list(PL, CT, EV) + (
             f"<p>Right calls in all: {SHORT['R1']} {RIGHT_C['R1']}, {SHORT['R2']} {RIGHT_C['R2']} and {SHORT['R3']} "
             f"{RIGHT_C['R3']} of 160. The fallback's lead comes from {C2O['right payment']} of 20 mistyped check numbers "
             f"it paired to the right payment. It paired {C2O['wrong payment']} others to a wrong one. Through wrong "
             f"pairings it also hid {sum(HIDDEN.values())} real problems in four kinds. They were {HIDDEN['C1']} double-paid "
             f"checks, {HIDDEN['C5']} voided checks paid, {HIDDEN['C6']} checks never issued and {HIDDEN['C8']} payment that "
             f"never cleared.</p>")),
         ("processor", "Card processor: clean feeds", rule_list(PC, KMP) + (
             f"<p>Under the two one-to-one rules every fee row stays open, because the books have no record for a fee: "
             f"{n(P_BRK['R1'])} breaks against {n(P_BRK['R3'])}. That is a design choice of this study, so the batch rule's "
             f"edge here follows from it. Whole-batch matching closes a fee row when its batch pairs. "
             f"The processor paid out {usd(PF['money_paid_out_usd'])} and kept {usd(PF['fees_usd'])} in fees.</p>")),
         ("processor-planted", "Card processor: planted events, 20 of each", planted_list(PP, XT, XEV) + (
             f"<p>Right calls in all: {SHORT['R1']} {RIGHT_P['R1']}, {SHORT['R2']} {RIGHT_P['R2']} and {SHORT['R3']} "
             f"{RIGHT_P['R3']} of 140. The fallback rule's lead is real but cheap. Its US$1.00 tolerance absorbs the "
             f"rounding. It flags every fee fault only because it leaves every fee row on the list.</p>")),
         ("version2", "Version 2: the fallback at every window, and with the check number hidden", (
             "<p>Added after the results. The first version's figures above are unchanged.</p><p>The fallback rule at "
             "each window. Every pairing it made was wrong at every window. "
             "Some bank lines had their own payment issued within the window, but an earlier wrong pairing had taken "
             f"it: {n(CASC)} of the {n(FM)} at {W} days. The other {n(LATE)} were checks the window refused.</p>"
             '<div class="table-scroll"><table class="data"><caption>Amount-and-date fallback, county, by window</caption>'
             '<thead><tr><th scope="col">Window, business days</th><th scope="col" class="num">Wrong pairings</th>'
             '<th scope="col" class="num">Per 1,000 bank debits</th><th scope="col" class="num">Payment taken earlier by '
             'a wrong pairing</th></tr></thead><tbody>' + "".join(
                 f'<tr><th scope="row">{w}</th><td class="num">{n(FS[str(w)]["false_matches_bank_join"])}</td>'
                 f'<td class="num">{FS[str(w)]["false_matches_per_1000_bank_lines"]}</td>'
                 f'<td class="num">{n(FS[str(w)]["fallback_bank_line_lag_within_window"])}</td></tr>' for w in WS)
             + "</tbody></table></div>"
             f"<p>The hidden-reference test. With each check number hidden in turn, taking the oldest payment that fit was "
             f"wrong for at least 1 in 7 debits in reach, at every look-back. At "
             f"{W} days, {n(BD['same_cents_and_same_issue_day'])} of the {n(BD['wrong'])} wrong picks were another "
             f"payment of the same amount to the cent, issued the same day. {n(BD['other_supplier'])} went to another "
             f"supplier. That breakdown was counted after this version ran. Over all {n(BANK)} debits, "
             f"{n(H5['wrong'])} were picked wrong ({H5['wrong_per_1000_debits']} per 1,000), counting those whose "
             f"payment was out of reach.</p>"
             '<div class="table-scroll"><table class="data"><caption>Hidden-reference test, county, by window</caption>'
             '<thead><tr><th scope="col">Window, business days</th><th scope="col" class="num">Debits whose payment was '
             'within reach</th><th scope="col" class="num">Right payment</th><th scope="col" class="num">Wrong payment'
             '</th><th scope="col" class="num">Wrong per 1,000 in reach</th></tr></thead><tbody>' + "".join(
                 f'<tr><th scope="row">{w}</th><td class="num">{n(HR[str(w)]["within_reach"])}</td>'
                 f'<td class="num">{n(HR[str(w)]["right_within_reach"])}</td>'
                 f'<td class="num">{n(HR[str(w)]["wrong_within_reach"])}</td>'
                 f'<td class="num">{HR[str(w)]["wrong_per_1000_within_reach"]}</td></tr>' for w in WS)
             + "</tbody></table></div>")),
         ("version3", "Version 3: match only a lone fit", (
             f"<p>Added after the results. With each check number hidden as before, a debit is matched only when exactly "
             f"one open payment fits; two or more send it to a person. A lone fit cannot be wrong when the true payment "
             f"is in reach, because the true payment always fits. So every wrong match is a debit whose payment cleared "
             f"later than the look-back, and that met one look-alike. All of them were paper checks.</p>"
             f"<p>Wrong matches fell from {OF5['wrong_closes_per_1000_debits']} per 1,000 debits at 5 days to "
             f"{OF60['wrong_closes_per_1000_debits']} at {SAFE}, the only look-back under 1 per 1,000. More debits had "
             f"look-alikes, {pct(OF5['look_alikes_share_of_debits'])} at 5 days and "
             f"{pct(OF60['look_alikes_share_of_debits'])} at {SAFE}. But far fewer found no payment at all, so the share "
             f"needing a person fell from {pct(WORK5)} to {pct(WORK60)}.</p>"
             '<div class="table-scroll"><table class="data"><caption>Lone-fit matching, county, by look-back, over all '
             f'{n(BANK)} debits</caption><thead><tr><th scope="col">Look-back, business days</th><th scope="col" '
             'class="num">Right matches</th><th scope="col" class="num">Wrong matches</th><th scope="col" class="num">'
             'Wrong per 1,000 debits</th><th scope="col" class="num">Sent to a person</th><th scope="col" class="num">'
             'No payment fit</th></tr></thead><tbody>' + "".join(
                 f'<tr><th scope="row">{w}</th><td class="num">{n(OF[str(w)]["right_closes"])}</td>'
                 f'<td class="num">{n(OF[str(w)]["wrong_closes"])}</td>'
                 f'<td class="num">{OF[str(w)]["wrong_closes_per_1000_debits"]}</td>'
                 f'<td class="num">{n(OF[str(w)]["look_alikes"])}</td>'
                 f'<td class="num">{n(OF[str(w)]["none"])}</td></tr>' for w in WS)
             + "</tbody></table></div>"
             f"<p>By payment type, the oldest pick was wrong far more often for electronic debits: "
             f"{BT['5']['Electronic']['forced_pick_wrong_per_1000_within_reach']} per 1,000 in reach at 5 days against "
             f"{BT['5']['Paper']['forced_pick_wrong_per_1000_within_reach']} for paper. Every electronic debit was in "
             f"reach from 3 days, so a lone fit never matched one wrongly. With exact cents first, the oldest pick was "
             f"still wrong for {n(CF['5']['wrong_within_reach'])} of the {n(CF['5']['within_reach'])} debits in "
             f"reach at 5 days, {CF['5']['wrong_per_1000_within_reach']} per 1,000.</p>"
             '<div class="table-scroll"><table class="data"><caption>By payment type, county, by look-back</caption>'
             '<thead><tr><th scope="col">Look-back, business days</th><th scope="col" class="num">Oldest pick, wrong '
             'per 1,000 paper debits in reach</th><th scope="col" class="num">Oldest pick, wrong per 1,000 electronic '
             'debits in reach</th><th scope="col" class="num">Lone fit, wrong per 1,000 paper debits</th>'
             '<th scope="col" class="num">Lone fit, wrong per 1,000 electronic debits</th></tr></thead><tbody>' + "".join(
                 f'<tr><th scope="row">{w}</th>' + "".join(
                     f'<td class="num">{BT[str(w)][t][k]}</td>' for k in ("forced_pick_wrong_per_1000_within_reach",
                     "one_fit_wrong_closes_per_1000_debits") for t in ("Paper", "Electronic")) + "</tr>" for w in WS)
             + "</tbody></table></div>"))],
        "Every figure of the three-way reconciliation study, per rule: wrong pairings, money open at each close, break age, "
        "window sweep and planted events.")

# ---------------------------------------------------------------- what went wrong
subpage("what-went-wrong.html", "What went wrong",
        f"No rule flagged more than {max(C4F.values())} of 20 invoices paid twice, because every record agreed, in a planted test.",
        "These are planted events on real records, written alongside the rules, 20 of each kind, and one independent set of 24.",
        [("missed", "What every rule missed", ul([
            f"<strong>An invoice paid twice, in two payments.</strong> {SHORT['R1'].capitalize()} {C4F['R1']}, "
            f"{SHORT['R2']} {C4F['R2']} and {SHORT['R3']} {C4F['R3']} of 20. The second payment has its own document, "
            f"check and bank debit, so all three records agree. A duplicate-invoice check on supplier, invoice and "
            f"amount before payment would catch it.",
            f"<strong>A late electronic payment.</strong> Cleared 8 business days after issue, it passed the 5-day window. "
            f"Exact reference and whole payment flagged all 20, and the fallback {PL['R2']['C7']['flagged']}, the wrong call "
            f"for ordinary timing. The fallback's one pass came through a wrong pairing. One window for every payment type "
            f"is too blunt.",
        ])),
         ("netting", "What netting hid", ul([
             f"<strong>A fee overcharge.</strong> Whole-batch matching flagged {PP['R3']['X5']['flagged']} of 20 batches "
             f"charged a higher fee rate. The payout equalled the netted batch, so nothing disagreed. In the independent "
             f"set, it also missed a processing fee charged twice, for the same reason.",
             f"<strong>Rounding of 1 to 3 cents.</strong> Exact reference and whole batch flagged all 20, the wrong call. "
             f"The fallback rule's US$1.00 tolerance absorbed them, the right call, but the same tolerance would absorb a "
             f"real 99-cent error.",
         ])),
         ("fallback", "What the fallback broke", (
             f"<p>All {n(FM)} wrong pairings came from the amount-and-date fallback, and it made no right one. It fires "
             f"when a bank line finds no partner by reference. {n(LATE)} times that was a check clearing after the "
             f"{W}-day window, whose true payment is older than the fallback looks. {n(CASC)} times the payment was in "
             f"reach but an earlier wrong pairing had taken it. It then takes the oldest open payment of nearly the same "
             f"amount. In the planted test this hid {HIDDEN['C1']} of 20 double-paid checks and {HIDDEN['C5']} of 20 voided "
             f"checks paid anyway. It also hid {HIDDEN['C6']} of 20 checks the books never issued and {HIDDEN['C8']} of 20 "
             f"payments that never cleared.</p><p>The split of the {n(FM)} was counted in the second version, added after the "
             f"results.</p>")),
         ("study", "What went wrong in the study itself", ul([
             f"One prediction partly missed: {pct(PAPER[5], 0)} of paper checks were flagged early at 5 days, not half.",
             f"The first version tested the fallback only behind a rule that refused check numbers more than {W} business "
             f"days apart. So every pairing it made was wrong by design, and only the count came from the data. The second "
             f"version tested it with check numbers hidden instead.",
             f"The expected finding said whole payment would make the most right calls on planted events. The fallback "
             f"rule made more, {RIGHT_C['R2']} and {RIGHT_P['R2']}.",
             "In the second version, more wrong picks were expected at 15 days than at 5. There were slightly fewer.",
             "The second version took the oldest of several look-alikes, so its rate measured that pick, not every "
             "amount-and-date rule. The third version measured matching only a lone fit.",
             f"In the third version, look-alikes were expected to be 25% to 45% of the debits in reach at 5 days. They "
             f"were {pct(OF5['look_alikes_share_within_reach'])}. Paper debits were expected to draw more wrong picks than "
             f"electronic ones; electronic drew more.",
             "Two of the independent author's 24 events could not be applied as written. They put a number range on the "
             "check number, which the event grammar reads as text. They are reported as not applied.",
             f"{n(AN['zero_net_documents'])} documents netting to zero would have counted as open money under every rule. "
             f"They were left out before any scored run.",
         ]))],
        "What the matching rules missed in the three-way reconciliation study, and what went wrong in the study itself.")

# ---------------------------------------------------------------- follow-up
fu_rows = []
for x in HO["events"]:
    if not x.get("applied"):
        continue
    wrong = [SHORT[r] for r in RULES if not x[r]["right"]]
    fu_rows.append(f"{e(x['title'])} ({x['correct']}): " + ("every rule right" if not wrong else "wrong: " + ", ".join(wrong)))
assert HSC["R1"]["right"] == HSC["R2"]["right"] < HSC["R3"]["right"]
subpage("follow-up.html", "Follow-up",
        f"An independent author's {HAPPLIED} cases were too few to separate the rules: whole payment made "
        f"{HSC['R3']['right']} of {HSC['applied']} right calls on the county, the others {HSC['R1']['right']}.",
        f"One author and {HAPPLIED} events, too few to separate the rules.",
        [("what", "What was done", (
            f"<p>An independent author who never saw the rules, the planted events or any result wrote {HTOTAL} events, 12 "
            f"for the county and 12 for the card processor. The author had a description of the feeds, 20 sample rows of "
            f"each and a small event grammar, and gave each event its correct call. The brief was fixed before it ran, "
            f"and the rules did not change.</p>")),
         ("result", "The result", (
             f"<p>{HAPPLIED} of {HTOTAL} events applied. Right calls on the county: {SHORT['R3']} {HSC['R3']['right']} of "
             f"{HSC['applied']}, {SHORT['R1']} {HSC['R1']['right']}, {SHORT['R2']} {HSC['R2']['right']}. On the processor: "
             f"{SHORT['R3']} {HSP['R3']['right']} of {HSP['applied']}, {SHORT['R1']} {HSP['R1']['right']}, {SHORT['R2']} "
             f"{HSP['R2']['right']}. {ALL_RIGHT} of the {HAPPLIED} were called right by all three rules, so the comparison "
             f"rests on the other {HAPPLIED - ALL_RIGHT}, too few to separate the rules. The design keeps the two data sets "
             f"apart, so no total across them is given.</p>"
             f"<p>Its one miss was a processing fee charged twice, hidden by netting, the same blind spot as the planted fee "
             f"overcharge. The one-to-one rules flagged a supplier credit netted into one check, a fee taken in the next "
             f"batch and a partial refund, all ordinary. The fallback also paired a payout whose remittance named no real "
             f"batch, by amount, without a flag.</p>" + ul(fu_rows))),
         ("not-applied", "Two events not applied", (
             "<p>A check held longer by its supplier and an electronic payment one day late put a number range on the "
             "check number, which the grammar reads as text. Both were applied afterwards with the number read as a "
             "number, as a labelled side result. Every rule flagged the held check, the wrong call. Only whole-payment "
             "matching let the one-day delay pass.</p>"))],
        "The independent follow-up of the three-way reconciliation study: 24 events by an author blind to the rules.")

# ---------------------------------------------------------------- glossary
TERMS = [("Books", "The company's own record of what it owes or is owed, line by line."),
         ("Payment run", "The list of payments the books send out, each paying one or more invoices."),
         ("Settlement report", "The card processor's daily file of what it settled, what it charged in fees and what it paid out."),
         ("Batch", "One day's settled items at the processor, paid out together as one transfer."),
         ("Payout", "The single transfer from the processor to the bank for one batch, net of fees and refunds."),
         ("Bank line", "One debit or credit on the bank statement."),
         ("Reference", "The shared identifier that links two records: a check number, a payment document or a batch number."),
         ("Pairing", "Two records a rule has matched as the same money."),
         ("Wrong pairing", "A pairing of two records that do not belong together."),
         ("Close", "The check run at the end of a business day over every record seen so far."),
         ("Window", "How many business days a record may stay unpaired before it counts as a problem."),
         ("Look-back", "How many business days before a bank line amount-and-date matching searches for its payment."),
         ("Lone fit", "The only open payment within US$1.00 of a bank line, issued within the look-back."),
         ("Look-alike", "A bank line that two or more open payments fit, so a person has to choose."),
         ("In transit", "Unpaired, but still inside its window."),
         ("Break", "Unpaired after its window: an item someone must look at."),
         ("Netting", "Adding credits, refunds and fees into one total, so only the total has to match."),
         ("Fallback", "A second way to pair a bank line when its reference finds no partner; here, amount and date."),
         ("Hidden-reference test", "Each bank line's reference hidden in turn, to see whether amount and date alone find the right payment."),
         ("Kaplan-Meier estimate", "A way to read how long breaks stay open that also counts the breaks still open at the end of the data."),
         ("Chargeback", "A customer dispute that takes the money of a charge back."),
         ("Void", "A payment cancelled before the bank paid it.")]
subpage("glossary.html", "Glossary",
        f"The {len(TERMS)} terms this study uses, from books to void, each in one plain sentence.",
        "Definitions as used on these pages, which may be narrower than an accounting standard's.",
        [("terms", "Terms", '<dl class="glossary">' + "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in TERMS) + "</dl>")],
        "Plain definitions of the terms used in the three-way reconciliation study.")

print(f"wrote index.html ({len(entry):,} bytes) and {len(PAGES) - 1} detail pages")
