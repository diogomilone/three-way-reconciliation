# How to write an event

An event is a JSON object:

```json
{"id": "H01", "dataset": "county", "title": "short name", "correct": "flag", "why": "one line",
 "ops": [ ... ]}
```

`dataset` is `county` or `processor`. `correct` is `flag` (a person must look at it) or `explain` (an ordinary
difference that resolves or needs no one). The ops run in order on a copy of the records.

## Ops

- `{"op": "pick", "as": "<name>", "feed": "<feed>", "where": {"<field>": <value>, "<field>": {"min": <v>, "max": <v>}}, "nth": <k>}`
  chooses one existing record: among those that match every condition, sorted by their id, the k-th (counting from 0;
  k wraps around if it is too large). Dates are compared as dates, amounts as numbers. The name refers to it later.
- `{"op": "copy", "of": "<name>", "as": "<name>", "set": {"<field>": <value>}, "shift_days": <n>}` adds a new record
  that copies a picked one, with the fields you set changed, moved n business days (optional).
- `{"op": "add", "feed": "<feed>", "as": "<name>", "fields": {"<field>": <value>}}` adds a new record from scratch. It
  needs at least an amount and a date (a void needs `payment_doc` and `date`).
- `{"op": "set", "on": "<name>", "set": {"<field>": <value>}}` changes fields of a picked record (not its id).
- `{"op": "shift", "on": "<name>", "days": <n>}` moves a picked record's date by n business days (negative is earlier).
- `{"op": "remove", "on": "<name>"}` deletes a picked record.
- `{"op": "repay"}` (processor only) recomputes every payout row and bank line from the settlement rows as they then
  stand, as when the processor pays out what its own report says. Without it, payouts and bank lines stay as they were.

A payment's `status` is descriptive only: a voided payment is recorded by adding a record to `voids`. A new record
keeps the copied fields unless you change them. Amounts are in the feed's currency as written in the
samples (US$ for every county field). A change to a settlement row's `amount` updates its `usd`. Changing a settlement
row's date with `shift` moves it to that day's batch. A bank line's remittance text must be `batch <n>` for the bank to
name a batch.

## Feeds and fields you may use

| Data set | Feed | Fields |
|---|---|---|
| county | `ledger_lines` | `line_id`, `payment_doc`, `vendor`, `invoice`, `amount`, `date` |
| county | `payments` | `payment_doc`, `check_number`, `payment_type`, `total`, `issue_date`, `status` |
| county | `bank_lines` | `bank_line_id`, `reference`, `amount`, `date` |
| county | `voids` | `payment_doc`, `date` |
| processor | `ledger_items` | `item_id`, `charge_id`, `kind`, `currency`, `amount`, `date` |
| processor | `settlement_rows` | `row_id`, `charge_id`, `kind`, `currency`, `amount`, `batch`, `date` |
| processor | `bank_lines` | `bank_line_id`, `remittance`, `amount`, `date` |

The samples show real values of every field. You cannot see every record: write `pick` conditions that match many
records (a payment type, a status, an amount range, a date range, a kind) and let `nth` choose one. An event whose pick
finds nothing is reported as not applied.

## Syntax example (not a suggestion of what to write)

```json
{"id": "H00", "dataset": "county", "title": "syntax example", "correct": "explain", "why": "shows the syntax only",
 "ops": [{"op": "pick", "as": "x", "feed": "ledger_lines", "where": {"amount": {"min": 100, "max": 200}}, "nth": 4},
         {"op": "set", "on": "x", "set": {"invoice": "INV-1"}}]}
```

## Hand-back

End your answer with a line that reads exactly `JSON:` and, after it, one JSON array of your 24 events and nothing else.
