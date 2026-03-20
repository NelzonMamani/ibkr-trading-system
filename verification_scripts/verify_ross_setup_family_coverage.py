from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'AUDIT_EVIDENCE' / 'ross_setup_family_coverage_report.json'

if __name__ == '__main__':
    rc = pytest.main(['-q', 'src/strategies/ross_momentum/tests/test_setup_family_manifest.py'])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({'pytest_exit_code': rc, 'report': 'src/strategies/ross_momentum/tests/test_setup_family_manifest.py'}, indent=2), encoding='utf-8')
    raise SystemExit(rc)
