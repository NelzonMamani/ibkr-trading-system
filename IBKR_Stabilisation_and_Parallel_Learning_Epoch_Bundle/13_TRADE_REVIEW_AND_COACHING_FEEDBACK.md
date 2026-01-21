# 13 — TRADE REVIEW AND COACHING FEEDBACK (POST-TRADE)

## Objective
Provide a “coach” output after trades close:
- what was done right
- what was done wrong
- what to change next time
Grounded strictly in:
- the executed trade
- the recorded context
- the strategy’s documented rules/policy
Not in vague motivational text.

## Inputs
For each closed trade:
- Trade details (symbol, times, prices, pnl)
- Strategy name and active policy version
- Scanner metrics at entry time
- Pattern/signal context (if present)
- Risk decision context (position sizing, stop rules)
- Execution context (fills, slippage)
- Any logged violations (stop loss, chasing, late entry)

## Output (per-trade review)
Generate a structured object:
- `grade`: A/B/C/D/F (rules adherence + outcome)
- `what_went_well`: list[str]
- `what_went_wrong`: list[str]
- `rule_checks`: dict[rule_name, PASS/FAIL]
- `next_time`: list[str] (actionable)
- `evidence`: pointers to event ids / timestamps

Persist as:
- `learning_trade_reviews` table (optional)
or as report attachments within daily report.

## Special case: user portfolio advice (e.g., TSLA hold/buy/sell)
This is **not** the job of the learning epoch for intraday trading.
Learning epoch can provide:
- “Based on your recorded trades in TSLA, your biggest losses came from X behaviour.”
It must not attempt to do full discretionary macro/fundamental analysis unless a separate “Advisory” epoch exists.

## Acceptance criteria
- After a trade closes, a review is produced and available in the daily report.
- With no trades, the module outputs nothing (but does not error).

END
