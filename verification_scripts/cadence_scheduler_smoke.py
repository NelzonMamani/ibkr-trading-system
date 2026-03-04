from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

import json
import os
import tempfile
import time
from pathlib import Path

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator


def _read_stages(trace_dir: Path) -> list[str]:
    stages: list[str] = []
    for path in sorted(trace_dir.glob('trace_*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            stages.append(json.loads(line).get('stage', ''))
    return stages


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='cadence_trace_') as td:
        os.environ['TRACE_LOG_DIR'] = td
        set_config_overrides({
            'RUN_MODE': 'PAPER',
            'TOPN_REFRESH_SECONDS': 300,
            'WATCHLIST_REFRESH_SECONDS': 60,
            'FOCUS_REFRESH_SECONDS': 10,
        })
        orch = CoreOrchestrator()
        start = time.time()
        while time.time() - start < 30:
            orch.run_once()
            time.sleep(5)

        stages = _read_stages(Path(td))
        assert 'TOPN_REFRESH' in stages, 'TopN refresh missing'
        assert 'WATCHLIST_REFRESH' in stages, 'Watchlist refresh missing'
        focus_count = stages.count('FOCUS_REFRESH')
        assert focus_count >= 2, f'Expected repeated focus refresh, got {focus_count}'
        print(f'cadence_scheduler_smoke=PASS focus_refresh_count={focus_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
