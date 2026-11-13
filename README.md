# Three-way reconciliation: matching the books, the payments and the bank each day

A business pays and is paid through three records that never agree on the same day: its books, the party that moves
the money (a payment run, or a card processor's settlement report) and the bank. This study runs three matching rules
over every business-day close of a year and measures, per rule, the pairings that are wrong, the money left open at
each close, how long a break stays open, and which planted and independently written events each rule flags. The
entry page is `index.html`; the detail pages are `method.html`, `checks.html`, `results.html`,
`what-went-wrong.html`, `follow-up.html` and `glossary.html`.

## Data

- **County, real.** Fulton County Government (GA), Vendor Payments, fiscal year 2024, from the county's open data
  portal, published under the Creative Commons Attribution 4.0 licence (CC BY 4.0); credit: Fulton County Government
  (GA). Dataset `kp4p-scak` at https://sharefulton.fultoncountyga.gov/d/kp4p-scak. Each row is one invoice paid:
  payment document, check number, payment type, supplier code, invoice, amount, status and the date the payment
  cleared or was cancelled. The bank lines are built from those clearing dates; the county publishes no bank
  statement. The extract is not copied into this folder, because its free-text invoice field carries the names of
  private people and businesses. Fetch it into `data/` with:

  ```
  curl -fsSL -G 'https://sharefulton.fultoncountyga.gov/resource/kp4p-scak.csv' \
    --data-urlencode '$select=fiscal_year,fy_period,disb_date,amount,vendor_code,check_no,dis_doc_id,payment_document,vendor_invoice_date,vendor_invoice_no,check_status,check_clearance_or_cancel_date,payment_type,fund,dept' \
    --data-urlencode '$where=fiscal_year=2024' --data-urlencode '$limit=200000' \
    --data-urlencode '$order=dis_doc_id,vendor_invoice_no' -o fy2024.csv
  gzip -n -9 -c fy2024.csv > data/county-fy2024.csv.gz
  ```

  The study used 46,126 rows whose uncompressed sha256 is
  `897aaea38ed2a1281f9eaa2b21211970166842fb764d97a211fcceebd10f9791`; the build checks it and stops on any other file.
  If the county has since corrected fiscal-year 2024 rows, the figures will differ.
- **Card processor, synthetic.** `tools/processor.py` generates a software company's card sales, refunds, disputes and
  won disputes (January to June 2025, US and Canadian dollars), the processor's settlement report (one row per settled
  item, one fee row per charge, one payout row per daily batch) and the bank's credits. The fields follow a published
  processor settlement report specification and the ISO 20022 camt.053 bank statement format. Every rate in it is an
  assumption of the study, set in the code.

## Reproduce

Python 3.12, standard library only.

```
python3 -B tests/test_study.py
python3 -I -B tools/run_study.py            # writes results/results-r1.json
python3 -I -B tools/run_heldout.py          # scores followup/heldout-events.json, writes results/results-heldout.json
python3 -I -B tools/heldout_numeric_ranges.py   # the labelled side result for the two events not applied as written
python3 -I -B tools/run_r2.py              # the second version, writes results/results-r2.json
python3 -I -B tools/r2_breakdown.py        # breakdown of its wrong picks, writes results/results-r2-breakdown.json
python3 -I -B tools/run_r3.py              # the third version, writes results/results-r3.json once
python3 -I -B tools/run_r4.py              # the fourth version, writes results/results-r4.json once
python3 -I -B site/render.py                # writes the seven pages
```

Every run is deterministic: the processor and the planted events use fixed seeds, set in the code.

## Files

- `tools/county.py`, `tools/processor.py`: build the three feeds of each data set and keep which records truly belong
  together.
- `tools/recon.py`: the three rules, the daily close and the measures.
- `tools/plant.py`: the planted events, 20 of each kind, with their correct calls.
- `tools/run_study.py`: the declared run.
- `tools/events.py`, `tools/run_heldout.py`: the event grammar the independent author wrote in, and its scoring with
  the rules unchanged. `followup/author-prompt.txt` is the author's brief and `followup/bundle/` everything else the
  author saw, except its 20 sample rows of each feed: the county rows carry people's names in the invoice field, so
  `tools/make_bundle.py` rebuilds them from the extract instead. `followup/heldout-events.json` is what the author
  wrote.
- `tools/make_bundle.py`: writes the author's sample rows.
- `predictions-r1.json`: the predictions, as written before any scored run.
- `tools/run_r2.py`, `tools/r2_breakdown.py`, `predictions-r2.json`: the second version, added after the results and
  with its predictions written before it ran: the fallback rule at every window, the hidden-reference test, break ages that count the
  breaks still open, and money open counted once per payment. It imports the first version's modules unchanged, and
  a test pins the first version's results file.
- `tools/run_r3.py`, `predictions-r3.json`: the third version, added after the results, with its predictions written
  before it ran: matching a bank line whose check number is hidden only when one payment fits, both picks by payment
  type, and exact cents first. It imports the earlier modules unchanged and refuses to overwrite its results file.
- `tools/run_r4.py`, `predictions-r4.json`: the fourth version, added after the results, with its predictions written
  before it ran: the breaks of the declared whole-payment run by kind, and the year's money tied to the county's status
  totals and compared with the county's 2024 annual financial report. It adds no rule, imports the earlier modules
  unchanged and refuses to overwrite its results file.
- `assumptions.json`: the one assumed cost behind the "What it is worth" section.
- `site/render.py`, `site/page.css`: the pages. Every number on them comes from `results/` or `assumptions.json`, and
  the claims the text makes are asserted in `render.py`.
- `vendor/viz-design-system/`: the chart kit (version 2.3.0) with its licences.

## Licence of the data

The county extract is © Fulton County Government (GA), CC BY 4.0. Results derived from it are credited to the county.
The synthetic processor data and the code are the author's.
