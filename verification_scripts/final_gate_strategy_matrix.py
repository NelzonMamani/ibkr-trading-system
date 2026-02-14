from __future__ import annotations

import json, os, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'AUDIT_EVIDENCE' / 'final_gate'


def strategy_keys() -> list[str]:
    raw = (ROOT / 'src' / 'strategy' / 'strategy_runner.py').read_text(encoding='utf-8')
    regs = re.findall(r'StrategyRegistration\(\s*"[^"]+"\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*"([^"]+)"', raw)
    keys = [k for k in regs if k not in {'gap_and_go','momentum_continuation'}]
    if len(keys) != 20:
        raise SystemExit(f'expected 20 keys got {len(keys)}')
    return keys


def run_case(key: str, mode: str, micro: bool) -> dict:
    env = os.environ.copy(); env['SELECTED_STRATEGY']=key
    env['CYCLE_SLEEP_SECONDS']='0'
    if micro: env['RISK_PROFILE']='MICRO'
    cmd = f"timeout 45s python -m src.main --mode {mode} --cycles 1"
    start=time.time()
    proc=subprocess.run(cmd,cwd=ROOT,env=env,shell=True,text=True,capture_output=True)
    dur=round(time.time()-start,3)
    suffix='PAPER_MICRO' if micro else 'SIM'
    log=EVIDENCE / f'05_strategy_{key}_{suffix}.txt'
    txt=(proc.stdout or '')+'\n\n# STDERR\n'+(proc.stderr or '')
    log.write_text(f"$ {cmd}\n# SELECTED_STRATEGY={key}\n# RISK_PROFILE={env.get('RISK_PROFILE','<default>')}\n\n{txt}",encoding='utf-8')
    alltxt=txt
    checks={
      'rc_zero': proc.returncode==0,
      'strategy_selected': f'selected={key}' in alltxt or f'Selected strategy={key}' in alltxt,
      'strategy_pipeline': '[STRATEGY][PROCESS]' in alltxt,
      'decision_artifact': '[TRACE] stage=ACTION' in alltxt or '[STRATEGY] No trade intents generated.' in alltxt,
      'no_live_submission': 'LIVE ORDER SUBMITTED' not in alltxt,
    }
    if micro:
        checks['paper_mode_resolved']='RUN_MODE: PAPER' in alltxt or 'Run mode: PAPER' in alltxt
        checks['risk_profile_micro']='RISK_PROFILE: MICRO' in alltxt
        qs=[int(x) for x in re.findall(r'(?:quantity|qty|shares)=([0-9]+)',alltxt,re.I)]
        checks['micro_size_if_present']=all(q<=1 for q in qs) if qs else True
    return {'strategy':key,'mode':suffix,'ok':all(checks.values()),'return_code':proc.returncode,'duration_sec':dur,'assertions':checks,'artifact':str(log.relative_to(ROOT))}


def main()->int:
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    for p in EVIDENCE.glob('05_strategy_*_SIM.txt'): p.unlink()
    for p in EVIDENCE.glob('05_strategy_*_PAPER_MICRO.txt'): p.unlink()
    keys=strategy_keys(); results=[]
    for k in keys:
        results.append(run_case(k,'SIM',False))
        results.append(run_case(k,'PAPER',True))
    sim=sum(1 for r in results if r['mode']=='SIM' and r['ok'])
    pap=sum(1 for r in results if r['mode']=='PAPER_MICRO' and r['ok'])
    summary={'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'strategies':keys,'results':results,'passes':{'SIM':sim,'PAPER_MICRO':pap},'success':sim==20 and pap==20}
    (EVIDENCE/'05_strategy_matrix_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return 0 if summary['success'] else 1

if __name__=='__main__':
    raise SystemExit(main())
