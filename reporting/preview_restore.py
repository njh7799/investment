"""Explicit one-time restoration of card previews from original research inputs."""
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from reporting.catalog import catalog
from reporting.methods import METHODS, RESEARCH_METHODS
from reporting.restore import ROOT, git, WORKER, SCRIPTS


def restore(entry, names):
    dest=ROOT/'reporting/archive/previews'/f'{entry["id"]}.json.gz'
    if dest.exists() and '--force' not in sys.argv:
        print(entry['id'],'cached',flush=True)
        return
    folder=entry['results']
    meta=ROOT/folder/'metadata.json'
    metadata=json.loads(meta.read_text())
    revision=git('log','-1','--format=%H','--',folder).decode().strip()
    hashes=metadata['asset_sha256']
    with tempfile.TemporaryDirectory(prefix='investment-preview-') as td:
        target=Path(td)
        with tarfile.open(fileobj=io.BytesIO(git('archive',revision,'backtests','scripts','assets',folder))) as archive:
            archive.extractall(target,filter='data')
        for symbol,expected in hashes.items():
            filename=symbol if symbol.endswith('.csv') else symbol+'.csv'
            asset=target/'assets'/filename
            if hashlib.sha256(asset.read_bytes()).hexdigest()!=expected:
                for commit in git('log','--format=%H',revision,'--','assets/'+filename).decode().splitlines():
                    blob=git('show',commit+':assets/'+filename)
                    if hashlib.sha256(blob).hexdigest()==expected:
                        asset.write_bytes(blob)
                        break
                else: raise ValueError('Missing original input: '+filename)
        if entry['id']=='vo-sgov':
            worker=SGOV_WORKER
            args=[folder,'unused']
        else:
            worker=WORKER
            start=worker.index('period=next(');end=worker.index('\nid=Path',start)
            worker=worker[:start]+f"period='recent_and_full'\nfull=next(p for p in ['actual_tqqq','actual_tqqq_full','common_full'] if p in set(rows.period))\nrows=rows[rows.period.isin(['recent_10y',full])&rows.model.isin({sorted(names)!r})]"+worker[end:]
            marker="  curves.append({'model':name"
            pos=worker.index(marker)
            worker=worker[:pos]+'''  benchmark_prices,benchmark_weights=build_target_weights('tqqq_hold',data)
  benchmark_result=run_weight_strategy(benchmark_prices,benchmark_weights,start=row.start,end=row.end,fee_rate=.001)
  benchmark={'model':'tqqq_hold','dates':benchmark_result.equity.index.strftime('%Y-%m-%d').tolist(),'equity':benchmark_result.equity.tolist(),'metrics':summarize(benchmark_result)}
  if benchmark['dates']!=result.equity.index.strftime('%Y-%m-%d').tolist(): raise ValueError('Benchmark calendar mismatch')
  vo_prices,vo_weights=build_target_weights('vo',data)
  vo_result=run_weight_strategy(vo_prices,vo_weights,start=row.start,end=row.end,fee_rate=.001)
  vo={'model':'vo','dates':vo_result.equity.index.strftime('%Y-%m-%d').tolist(),'equity':vo_result.equity.tolist(),'metrics':summarize(vo_result)}
  if vo['dates']!=result.equity.index.strftime('%Y-%m-%d').tolist(): raise ValueError('VO calendar mismatch')
'''+worker[pos:]
            worker=worker.replace("'metrics':metrics})", "'metrics':metrics,'benchmark':benchmark,'vo':vo,'period':row.period})")
            args=[folder,SCRIPTS[entry['id']]]
        path=target/'preview_worker.py';path.write_text(worker)
        output=target/'preview.json'
        subprocess.run([sys.executable,str(path),*args,str(output)],cwd=target,check=True,timeout=600)
        payload=json.loads(output.read_text())
        if payload.get('failures'): raise ValueError(payload['failures'])
        if {c['model'] for c in payload['curves']}!=set(names): raise ValueError('Incomplete preview: '+entry['id'])
    payload.update(source_commit=revision,asset_sha256=hashes,metadata_sha256=hashlib.sha256(meta.read_bytes()).hexdigest())
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(gzip.compress(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode(),mtime=0))
    print(entry['id'],len(payload['curves']),'verified previews',flush=True)


SGOV_WORKER=r'''
import sys,json
from pathlib import Path
import pandas as pd
root=Path.cwd();sys.path.insert(0,str(root))
from backtests import load_market_data,build_target_weights,run_weight_strategy,summarize,toss_us_stock_fee
folder,_,output=sys.argv[1:];folder=Path(folder)
row=pd.read_csv(folder/'summary.csv').query('scenario == "VO SGOV"').iloc[0]
frame=pd.read_csv(folder/'sgov_equity.csv',index_col=0,parse_dates=True)
equity=frame.iloc[:,0]
assert abs(equity.iloc[-1]-row.end_equity)<.000001
assert abs((equity/equity.cummax()-1).min()-row.mdd)<.000001
data=load_market_data(root);p,w=build_target_weights('tqqq_hold',data)
b=run_weight_strategy(p,w,start=row.start,end=row.end,fee_rate=0,fee_calculator=toss_us_stock_fee)
curve={'model':'VO SGOV','period':'available','dates':equity.index.strftime('%Y-%m-%d').tolist(),'equity':equity.tolist(),'metrics':row.where(pd.notna(row),None).to_dict()}
curve['benchmark']={'model':'tqqq_hold','dates':b.equity.index.strftime('%Y-%m-%d').tolist(),'equity':b.equity.tolist(),'metrics':summarize(b)}
p,w=build_target_weights('vo',data)
v=run_weight_strategy(p,w,start=row.start,end=row.end,fee_rate=0,fee_calculator=toss_us_stock_fee)
curve['vo']={'model':'vo','dates':v.equity.index.strftime('%Y-%m-%d').tolist(),'equity':v.equity.tolist(),'metrics':summarize(v)}
assert curve['dates']==curve['benchmark']['dates']==curve['vo']['dates']
Path(output).write_text(json.dumps({'period':'available','curves':[curve],'failures':[]},allow_nan=False))
'''

if __name__=='__main__':
    wanted={}
    for spec in METHODS.values():
        if spec['model']!='vo': wanted.setdefault(spec['batch'],set()).add(spec['model'])
    for _,_,study,model,*_ in RESEARCH_METHODS:
        if model and '*' not in model: wanted.setdefault(study,set()).add(model)
    wanted['vo-sgov']={'VO SGOV'}
    for entry in catalog(ROOT):
        if entry['id'] in wanted: restore(entry,wanted[entry['id']])
