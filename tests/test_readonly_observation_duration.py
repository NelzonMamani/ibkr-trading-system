"""Real operator argument/preflight binding; supervisor replaced by a stub child."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
CHILD = r'''
import json, pathlib, runpy, sys, types
# Keep installed offline socket/HTTP guards; hide only the operator's deliberate
# offline-observation refusal so its stubbed dispatch can be exercised.
sys.modules['sitecustomize'] = types.SimpleNamespace()
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
root = pathlib.Path(sys.argv[1])
def controlled_main(args):
    (root/'stub-supervisor-args.json').write_text(json.dumps(args))
    return 0
supervisor.main = controlled_main
sys.argv = ['operator','observe',str(root),'a'*40,sys.argv[2]]
runpy.run_path(sys.argv_path, run_name='__main__')
'''.replace('sys.argv_path', repr(str(REPO/'scripts/certification/natural_readonly_operator.py')))


@pytest.mark.parametrize('requested,preflight,success', [('180',180,True),('900',900,True),('1800',1800,True),
    ('900',180,False),('179',179,False),('1801',1801,False),('nan',900,False),('900.0',900,False)])
def test_bounded_duration_reaches_only_stub_supervisor_after_matching_preflight(tmp_path, requested, preflight, success):
    (tmp_path/'s').mkdir()
    (tmp_path/'e').mkdir()
    (tmp_path/'e/preflight.json').write_text(json.dumps(dict(head='a'*40,seconds=preflight)))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(REPO/'tests/offline'),str(REPO))))
    result = subprocess.run([sys.executable,'-c',CHILD,str(tmp_path),requested], env=env,
                            capture_output=True,text=True,timeout=15)
    assert (result.returncode == 0) is success, result.stderr
    recorded = tmp_path/'stub-supervisor-args.json'
    assert recorded.exists() is success
    assert (tmp_path/'e/observation-attempt.json').exists() is success
    if success:
        args = json.loads(recorded.read_text())
        assert args == ['--seconds',requested,'--output',str(tmp_path/'e/terminal'),'--expected-commit','a'*40]
