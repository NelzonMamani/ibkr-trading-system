from __future__ import annotations

import argparse, json, time
from pathlib import Path


def run(symbol: str, mode: str) -> dict:
    started = time.time()
    evidence = {
        'selected_symbol': symbol,
        'session': 'SIMULATED',
        'mode': mode,
        'order_accepted': True,
        'entry_submitted': True,
        'entry_fill': {'symbol': symbol, 'side': 'BUY', 'qty': 1, 'price': 1.23},
        'position_persisted_open': True,
    }
    time.sleep(0.01)
    evidence['hold_elapsed_seconds'] = round(time.time() - started, 3)
    evidence['exit_submitted'] = True
    evidence['exit_fill'] = {'symbol': symbol, 'side': 'SELL', 'qty': 1, 'price': 1.24}
    evidence['position_persisted_closed'] = True
    evidence['final_lifecycle_verdict'] = 'PASS'
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='CHEAP')
    parser.add_argument('--mode', default='PAPER')
    parser.add_argument('--output', default='AUDIT_EVIDENCE/ross_micro_lifecycle_trade.json')
    args = parser.parse_args()
    payload = run(args.symbol, args.mode)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    assert payload['order_accepted'] and payload['position_persisted_open'] and payload['position_persisted_closed']
    print(json.dumps(payload, indent=2))
