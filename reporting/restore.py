"""One-time reconstruction of historical curves, isolated from today's inputs.
Run: .venv/bin/python -m reporting.restore [study-id ...]
"""
from __future__ import annotations
import hashlib, io, json, subprocess, sys, tarfile, tempfile, gzip
from pathlib import Path
from reporting.catalog import catalog
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS={'batch-01':'model','batch-02':'model','batch-03':'allocation','batch-04':'paa','batch-06':'defensive_allocation','batch-07':'faa','batch-10':'permanent_portfolio','batch-11':'jordan_three_percent'}
WORKER=r'''
import sys,json,importlib,math
from pathlib import Path
import pandas as pd
root=Path.cwd(); sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'scripts'))
from backtests import load_market_data,run_weight_strategy,build_target_weights,summarize
study,script,output=sys.argv[1:]
rows=pd.read_csv(Path(study)/'period-summary.csv')
period=next((p for p in ['actual_tqqq','actual_tqqq_full','actual_current','common_full'] if p in set(rows.period)),rows.period.iloc[0])
rows=rows[rows.period==period]
id=Path(study).name
if script=='ma':
 from backtests.ma_research import build_ma_weights
 data=load_market_data(root); prices,weights,specs=build_ma_weights(data)
elif script=='bull':
 from backtests.vo_bull import build_vo_bull_weights
 from backtests import load_assets
 data=load_market_data(root); extra=load_assets(('SPY','IWM'),root)
 breadth=pd.concat({'QQQ':data.qqq.Close,'SPY':extra['SPY'].Close,'IWM':extra['IWM'].Close},axis=1)
 prices,weights,specs=build_vo_bull_weights(data,breadth)
elif script=='upside':
 from backtests.vo_upside import build_vo_upside_weights
 data=load_market_data(root); prices,weights,specs=build_vo_upside_weights(data)
else:
 module=importlib.import_module('analyze_'+script+'_batch'); data=load_market_data(root)
if script in ('ma','bull','upside'):
 names=list(rows.model)
 # Every model is available in the original tables; curves illustrate documented families.
 chosen=[n for n in names if n in ('vo','tqqq_hold','qqq_hold')]
 if script=='ma': chosen += [n for n in names if 'qqq_price_sma_' in n and any('_'+str(v)+'_' in n for v in (40,50,60)) and 'confirm' in n]
 elif script=='bull': chosen += [n for n in names if 'recovery' in n and ('15' in n or '10' in n)]
 else: chosen += [n for n in names if 'recovery' in n or n.startswith('ret_qqq_100_')]
 chosen=list(dict.fromkeys(chosen))[:12]
 rows=rows[rows.model.isin(chosen)]
curves=[]; failures=[]
for _,row in rows.iterrows():
 try:
  name=row.model
  if script in ('ma','bull','upside'):
   if name in ('tqqq_hold','qqq_hold'):
    p,w=build_target_weights(name,data)
   else: p,w=prices,weights[name]
   result=run_weight_strategy(p,w,start=row.start,end=row.end,fee_rate=.001)
  elif script=='model': result=module.run(name,data,row.start,row.end)
  else: result=module.run(name,row.start,row.end)
  metrics=summarize(result)
  for key in ('end_equity','cagr','mdd','trade_count','fees','longest_time_underwater_days'):
   if key in row and pd.notna(row[key]) and not math.isclose(float(metrics[key]),float(row[key]),rel_tol=1e-8,abs_tol=1e-7):
    raise ValueError(f'{key} mismatch: {metrics[key]} != {row[key]}')
  curves.append({'model':name,'dates':result.equity.index.strftime('%Y-%m-%d').tolist(),'equity':result.equity.tolist(),'metrics':metrics})
 except Exception as exc: failures.append({'model':row.model,'reason':str(exc)})
Path(output).write_text(json.dumps({'period':period,'curves':curves,'failures':failures},allow_nan=False))
'''

def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def restore(entry):
    dest=ROOT/'reporting/archive'/f'{entry["id"]}.json.gz'
    if dest.exists():
        print(entry['id'],'cached',flush=True); return
    folder=entry['results']; meta=ROOT/folder/'metadata.json'
    if not (ROOT/folder/'period-summary.csv').exists(): return
    metadata=json.loads(meta.read_text())
    commit=git('log','-1','--format=%H','--',folder+'/period-summary.csv').decode().strip()
    hashes=metadata.get('asset_sha256',{})
    payload={'source_commit':commit,'metadata_sha256':hashlib.sha256(meta.read_bytes()).hexdigest(),'asset_sha256':hashes,'curves':[],'failures':[]}
    try:
        with tempfile.TemporaryDirectory(prefix='investment-history-') as td:
            target=Path(td)
            # Only code, public market CSVs and public results are exported.
            with tarfile.open(fileobj=io.BytesIO(git('archive',commit,'backtests','scripts','assets',folder))) as archive:
                archive.extractall(target,filter='data')
            for symbol,expected in hashes.items():
                filename=symbol if symbol.endswith('.csv') else symbol+'.csv'
                asset=target/'assets'/filename
                if hashlib.sha256(asset.read_bytes()).hexdigest()!=expected:
                    # Find the exact stored input, never substitute today's price history.
                    found=False
                    for revision in git('log','--format=%H',commit,'--','assets/'+filename).decode().splitlines():
                        blob=git('show',revision+':assets/'+filename)
                        if hashlib.sha256(blob).hexdigest()==expected:
                            asset.write_bytes(blob); found=True; break
                    if not found: raise ValueError('Historical input hash not found: '+filename)
            script=SCRIPTS.get(entry['id'],{'batch-05':'ma','batch-08':'bull','vo-upside':'upside'}.get(entry['id']))
            worker=target/'restore_worker.py'; worker.write_text(WORKER)
            output=target/'curves.json'
            subprocess.run([sys.executable,str(worker),folder,script,str(output)],cwd=target,check=True,timeout=600)
            payload.update(json.loads(output.read_text()))
    except Exception as exc:
        payload['failures'].append({'model':'all','reason':str(exc)})
    # Deterministic compressed archival artifact; rebuilt only explicitly.
    dest.write_bytes(gzip.compress(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode(),mtime=0))
    print(entry['id'],len(payload['curves']),'curves',payload['failures'],flush=True)

if __name__=='__main__':
    for entry in catalog(ROOT):
        if len(sys.argv)==1 or entry['id'] in sys.argv[1:]: restore(entry)
