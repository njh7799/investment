"""Build allowlisted public data from existing analysis engines and frozen research."""
from __future__ import annotations
import csv, gzip, hashlib, json, re, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from backtests import load_market_data, build_target_weights, run_weight_strategy, summarize
from reporting.catalog import catalog, validate_coverage, STRATEGIES
from reporting.methods import buy_hold_card, method_data, research_method_data
from reporting.previews import attach_previews
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'site/public'
GENERATED=ROOT/'site/src/generated'

def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    if isinstance(value,(pd.Timestamp,datetime)): return value.isoformat()
    if isinstance(value,np.generic): value=value.item()
    if isinstance(value,float) and not np.isfinite(value): return None
    return value

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean(value),ensure_ascii=False,allow_nan=False,separators=(',',':')))

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def commit(path=None):
    args=['git','log','-1','--format=%H']
    if path: args+=['--',str(path)]
    return subprocess.check_output(args,cwd=ROOT,text=True).strip()

def events():
    result=[]
    for line in (ROOT/'docs/reference/market-events.md').read_text().splitlines():
        cells=[c.strip() for c in line.strip('|').split('|')]
        if len(cells)>=8 and re.fullmatch(r'\d{4}\.\d{2}\.\d{2}',cells[0]):
            result.append(dict(date=cells[0].replace('.','-'),title=cells[6],background=cells[7]))
    return result

def periods(latest,first):
    year=latest.year
    # An unqualified TQQQ "full period" always includes the pre-listing synthetic history.
    values=[('synthetic','합성 포함 전체',str(first.date()),str(latest.date())),('actual',f'실제 TQQQ 구간 · 2010-02-11–{latest.date()}','2010-02-11',str(latest.date()))]
    values += [(str(y),f'{y}년'+(' YTD' if y==year else ''),f'{y}-01-01',min(f'{y}-12-31',str(latest.date()))) for y in range(year,year-5,-1)]
    values += [(f'{year-hi}-{year-lo}',f'{year-hi}–{year-lo}년',f'{year-hi}-01-01',f'{year-lo}-12-31') for lo,hi in [(5,9),(10,14),(15,19)]]
    if first.year<=year-20: values.append(('early',f'합성 시작–{year-20}년',str(first.date()),f'{year-20}-12-31'))
    return values

def rolling_decades(latest,first):
    recent=latest-pd.DateOffset(years=10)
    prior=latest-pd.DateOffset(years=20)
    earliest=max(first,latest-pd.DateOffset(years=30))
    return [
        ('early-10y','',str(earliest.date()),str((prior-pd.Timedelta(days=1)).date())),
        ('prior-10y','',str(prior.date()),str((recent-pd.Timedelta(days=1)).date())),
        ('recent-10y','',str(recent.date()),str(latest.date())),
    ]

def comparison():
    data=load_market_data(ROOT)
    frames=(data.ixic,data.qqq,data.tqqq)
    if len({frame.index[-1] for frame in frames})!=1 or any(frame.isna().any().any() for frame in frames):
        raise ValueError('Comparison data dates must match and OHLC must be complete')
    index=data.index; latest=index[-1]; choices=[]
    ranges=periods(latest,index[0])
    ranges[2:2]=rolling_decades(latest,index[0])
    for key,label,start,end in ranges:
        curves=[]
        for name in ('vo','tqqq_hold','qqq_hold'):
            prices,weights=build_target_weights(name,data)
            result=run_weight_strategy(prices,weights,start=start,end=end)
            curves.append(dict(model=name,dates=result.equity.index.strftime('%Y-%m-%d').tolist(),equity=result.equity.tolist(),metrics=summarize(result)))
        if key in ('recent-10y','prior-10y','early-10y'):
            label=f'{curves[0]["metrics"]["start"]} — {curves[0]["metrics"]["end"]}'
        filename=f'backtest-{key}.json'; write(PUBLIC/'data'/filename,dict(curves=curves,events=events()))
        choices.append(dict(id=key,label=label,file='data/'+filename,metrics=[dict(model=c['model'],**c['metrics']) for c in curves]))
    # Calendar-aware lateness is evaluated again in the browser from this public schedule.
    import exchange_calendars as xcals
    cal=xcals.get_calendar('XNAS',start=latest-pd.Timedelta(days=10),end=latest+pd.Timedelta(days=90))
    next_session=cal.schedule.loc[cal.schedule.index>latest].iloc[0]
    due=next_session['close']+pd.Timedelta(hours=2)
    return dict(market_date=str(latest.date()),periods=choices,next_expected_date=str(next_session.name.date()),next_expected_after=due.isoformat(),source_commit=commit(),asset_sha256={s:sha(ROOT/'assets'/f'{s}.csv') for s in ('IXIC','QQQ','TQQQ','SPY')},fee_rate=.001,initial_cash=100000)

def copy_public(path):
    relative=path.relative_to(ROOT); dest=PUBLIC/'downloads'/relative
    dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,dest)
    return 'downloads/'+relative.as_posix()

def yearly_performance(curves):
    """Summarize frozen daily curves without rerunning the original research."""
    rows=[]
    for curve in curves:
        frame=pd.DataFrame({'date':pd.to_datetime(curve['dates']),'equity':curve['equity']}).dropna()
        if frame.empty: continue
        frame=frame.sort_values('date').drop_duplicates('date',keep='last').set_index('date')
        previous=float(curve.get('metrics',{}).get('start_equity') or frame.equity.iloc[0])
        first_date,last_date=frame.index[0],frame.index[-1]
        for year,group in frame.groupby(frame.index.year):
            path=pd.concat([pd.Series([previous],index=[group.index[0]-pd.Timedelta(days=1)]),group.equity.astype(float)])
            drawdown=path/path.cummax()-1
            end_equity=float(group.equity.iloc[-1])
            partial=(year==first_date.year and first_date>pd.Timestamp(year=year,month=1,day=15)) or (year==last_date.year and last_date<pd.Timestamp(year=year,month=12,day=20))
            rows.append(dict(model=curve['model'],display_name=curve.get('display_name'),year=int(year),start=str(group.index[0].date()),end=str(group.index[-1].date()),total_return=end_equity/previous-1,mdd=float(drawdown.min()),partial=partial))
            previous=end_equity
    return rows

def study_data(entry):
    folder=ROOT/entry['results']; tables=[]; metadata={}; downloads=[]
    for path in sorted(folder.glob('*')):
        if path.suffix not in ('.csv','.json'): continue
        downloads.append(dict(name=path.name,url=copy_public(path)))
        if path.suffix=='.csv':
            frame=pd.read_csv(path); records=clean(frame.to_dict('records'))
            tables.append(dict(name=path.stem,columns=list(frame.columns),rows=records))
        else: metadata[path.stem]=json.loads(path.read_text())
    # Full tables stay separate from page HTML to keep hundreds of variants cheap to browse.
    write(PUBLIC/'data'/f'{entry["id"]}-tables.json',tables)
    archive=ROOT/'reporting/archive'/f'{entry["id"]}.json.gz'
    chart=None; provenance={}; failure=[]; yearly_curves=[]
    if archive.exists():
        restored=json.loads(gzip.decompress(archive.read_bytes()))
        if restored['metadata_sha256']!=sha(folder/'metadata.json'): raise ValueError('Stale archive: '+entry['id'])
        failure=restored.get('failures',[]); provenance={k:v for k,v in restored.items() if k not in ('curves','failures')}
        if restored['curves']:
            yearly_curves=restored['curves']
            chart='data/'+entry['id']+'-chart.json'; write(PUBLIC/chart,dict(curves=restored['curves'],events=events()))
    if entry['id']=='vo-sgov':
        curves=[]
        summary=pd.read_csv(folder/'summary.csv')
        for name in ('cash','sgov'):
            frame=pd.read_csv(folder/f'{name}_equity.csv'); curves.append(dict(model='VO '+('현금' if name=='cash' else 'SGOV'),dates=frame.iloc[:,0].tolist(),equity=frame.iloc[:,1].tolist(),metrics=clean(summary.loc[summary.scenario==('VO cash' if name=='cash' else 'VO SGOV')].iloc[0].to_dict())))
        yearly_curves=curves
        chart='data/vo-sgov-chart.json'; write(PUBLIC/chart,dict(curves=curves,events=events()))
    if entry['id']=='vo-regimes':
        chart='data/vo-regimes-chart.json'
        write(PUBLIC/chart,dict(analysis='regimes',rows=clean(pd.read_csv(folder/'regimes.csv').to_dict('records'))))
    if chart and entry['id'] not in ('vo-regimes',):
        payload=json.loads((PUBLIC/chart).read_text())
        names=[c['model'] for c in payload['curves']]
        if entry['id']=='batch-11': independent=[n for n in names if n in ('jordan_public_proxy','qqq_hold')]
        elif entry['family']=='VO 확장': independent=[n for n in names if n not in ('tqqq_hold','qqq_hold')]
        else: independent=[n for n in names if n not in ('vo','tqqq_hold','qqq_hold')]
        payload['independent_models']=independent or names
        write(PUBLIC/chart,payload)
    yearly='data/'+entry['id']+'-yearly.json'
    yearly_rows=yearly_performance(yearly_curves)
    if yearly_rows:
        yearly_note='연구 때 저장한 일별 자산 곡선으로 계산했습니다. 연 수익률은 전년도 마지막 평가액 대비 해당 연도 마지막 평가액의 변화율이며, 연중 MDD는 전년도 마지막 평가액을 첫 기준점으로 포함해 그해 고점 대비 최대 하락률을 계산합니다.'
    else:
        yearly_note='이 분석에는 일별 포트폴리오 자산 곡선이 저장되어 있지 않아 연도별 수익률과 MDD를 계산할 수 없습니다. 기존 결과만으로 값을 추정하거나 전략을 다시 실행하지 않았습니다.'
    write(PUBLIC/yearly,dict(rows=yearly_rows,note=yearly_note))
    table=next((t for t in tables if t['name']=='period-summary'),None)
    ranges=sorted({(r['start'],r['end']) for r in table['rows']}) if table else []
    return dict(**entry,metadata=metadata,downloads=downloads,tables=[dict(name=t['name'],count=len(t['rows'])) for t in tables],ranges=ranges,chart=chart,yearly=yearly,yearly_count=len(yearly_rows),restoration_failures=failure,provenance=provenance,source_commit=commit(entry['results']))

def documents():
    result=[]
    for section in ('research','strategies','reference'):
        for p in sorted((ROOT/'docs'/section).rglob('*.md')):
            relative=p.relative_to(ROOT).as_posix()
            result.append(dict(path=relative,title=p.read_text().splitlines()[0].lstrip('# '),body=p.read_text(),slug=relative.removeprefix('docs/').removesuffix('.md')))
            copy_public(p)
    for p in sorted((ROOT/'docs/research/preregistrations').glob('*.yaml')): copy_public(p)
    return result

def audits():
    text=(ROOT/'docs/research/model-census.md').read_text(); entries=[]
    for heading,body in re.findall(r'^## (.+)\n(.*?)(?=^## |\Z)',text,re.M|re.S):
        if '자동 탐색' in heading:
            entries.append(dict(title=heading,body=body,status='재현 불가' if '재현 불가' in body else '연구 기록'))
    entries.append(dict(title='중복 조사와 자동 탐색 이력',body=(ROOT/'docs/research/automation-log.md').read_text(),status='조사 기록'))
    return entries

def main():
    validate_coverage(ROOT)
    for dest in (PUBLIC/'data',PUBLIC/'downloads',PUBLIC/'previews',GENERATED):
        if dest.exists(): shutil.rmtree(dest)
        dest.mkdir(parents=True)
    entries=[study_data(e) for e in catalog(ROOT)]
    op=comparison()
    write(PUBLIC/'data/backtest-metadata.json',{k:v for k,v in op.items() if k != 'periods'})
    strategies=method_data(ROOT,STRATEGIES,lambda file,curves:write(PUBLIC/file,dict(curves=curves,events=events())))
    strategies.insert(1,buy_hold_card(ROOT))
    research_methods=research_method_data(ROOT,entries)
    attach_previews(ROOT,PUBLIC,strategies+research_methods,op,events(),write)
    write(GENERATED/'content.json',dict(studies=entries,documents=documents(),audits=audits(),research_methods=research_methods,strategies=strategies,comparison=op,generated_at=datetime.now(timezone.utc).isoformat()))
    PUBLIC.joinpath('vendor').mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'site/node_modules/plotly.js-dist-min/plotly.min.js',PUBLIC/'vendor/plotly.min.js')
    print(f'Built {len(entries)} research reports; market date {op["market_date"]}')

if __name__=='__main__': main()
