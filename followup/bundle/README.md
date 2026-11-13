# Two sets of payment records, and what can go wrong between them

You are asked to write events: things that happen to money between the books, the party that moves it and the bank,
as a reconciliation team meets them. Some need a person to look (`flag`), some are ordinary differences that sort
themselves out or need no one (`explain`). Write what happens in the real world. You are not told how anyone matches
the records, and you should not try to guess it.

Each data set has three feeds. A reconciliation team pairs records across them every business day (Monday to Friday)
and keeps a list of what is still open.

## Data set 1: county (real public records)

A US county government's payments to its suppliers, paid in 2024, as the county publishes them.

- **ledger_lines** (the books): one line per supplier invoice paid. `payment_doc` is the payment that paid it; one
  payment often pays several invoices of one supplier, and a credit (negative line) can be netted into a payment.
  Fields: `line_id`, `payment_doc`, `vendor` (a code), `invoice`, `amount` (US$), `date` (YYYY-MM-DD). About 45,000.
- **payments** (the payment run): one record per payment, its total the net of its lines. Fields: `payment_doc`,
  `check_number`, `payment_type` (`Paper` for a check, `Electronic`), `total`, `issue_date`, `status` (`Paid`: the
  bank has paid it; `Disbursed`: issued, never presented to the bank; `Cancelled`: voided). About 13,350.
- **bank_lines** (the bank): one debit per payment the bank paid, on the day it paid it. `reference` is the check
  number. Fields: `bank_line_id`, `reference`, `amount`, `date`. About 13,100. Paper checks are paid from a couple of
  days to several months after issue; electronic payments 1 to 3 days after.
- **voids**: a voided payment and the day it was voided (`payment_doc`, `date`). 24.

Dates run from 2024-01-02 to 2026-02-06.

## Data set 2: card processor (synthetic records)

A software company selling subscriptions and one-off orders by card, from 2025-01-01 to 2025-06-30. Its card processor
settles the charges and pays the company out; the bank receives the payouts.

- **ledger_items** (the company's books): every `charge`, `refund`, `chargeback` (a customer dispute that took the
  money back) and `reversal` (a dispute the company won, money back again), in the currency the customer paid (`USD`
  or `CAD`). Fields: `item_id`, `charge_id`, `kind`, `currency`, `amount`, `date`. About 20,000.
- **settlement_rows** (the processor's settlement report): one row per settled `charge`, `refund`, `chargeback`,
  `reversal`, one `fee` row per charge, and one `payout` row per batch. Rows are grouped in a daily `batch`; the payout
  is the batch's net in US$ (charges and reversals, less refunds, chargebacks and fees). Fields: `row_id`, `charge_id`,
  `kind`, `currency`, `amount` (the customer's currency; for a fee or payout, US$), `usd` (signed, US$), `batch`,
  `date`. A batch is numbered by its business day. About 40,000.
- **bank_lines** (the bank statement): one credit per payout, a business day after the batch, its remittance text
  `batch <n>`. Fields: `bank_line_id`, `remittance`, `amount`, `date`. About 100.

## Your output

Read `GRAMMAR.md` and the samples in `samples/`. Then write 12 events for the county and 12 for the card processor:
varied, realistic, each with its correct call and one line of why. Mix `flag` and `explain`. Keep each event to one
occurrence (one payment, one batch, one customer), so each can be judged on its own.
