"""Publish static card previews and matching interactive, full-resolution data."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
from backtests.metrics import _drawdown_stats

TQQQ_BLUE='#2979FF'
VO_RED='#E5484D'
METHOD_YELLOW='#D99A00'
SYNTHETIC_PERIODS={'full_synthetic','synthetic_full','full_current','full_pre2026'}
ACTUAL_PERIODS={'actual_tqqq','actual_tqqq_full','actual_current','actual_pre2026'}


def historical_period_label(period):
    if period=='recent_10y': return '연구 당시 최근 10년'
    if period in SYNTHETIC_PERIODS: return '연구 당시 합성 포함 전체'
    if period in ACTUAL_PERIODS: return '연구 당시 실제 TQQQ 구간'
    if period=='common_full': return '연구 당시 공통 데이터 전체'
    return '연구 당시 전체 평가 구간'


def window_choice(choice, id, title, start, end):
    """Rebase a verified full curve to a common $100,000 within one display window."""
    curves=[]
    for curve in choice['curves']:
        dates=pd.to_datetime(curve['dates'])
        keep=(dates>=pd.Timestamp(start))&(dates<=pd.Timestamp(end))
        kept_dates=dates[keep]
        equity=pd.Series(np.asarray(curve['equity'])[keep],index=kept_dates,dtype=float)
        equity=equity/equity.iloc[0]*100000
        initial=100000.0
        years=(equity.index[-1]-equity.index[0]).days/365.2425
        metrics=dict(start=equity.index[0].date().isoformat(),end=equity.index[-1].date().isoformat(),
            start_equity=initial,end_equity=float(equity.iloc[-1]),total_return=float(equity.iloc[-1]/initial-1),
            cagr=float((equity.iloc[-1]/initial)**(1/years)-1))
        metrics.update(_drawdown_stats(equity))
        curves.append(dict(curve,dates=equity.index.strftime('%Y-%m-%d').tolist(),equity=equity.tolist(),metrics=metrics))
    target=next(curve for curve in curves if curve.get('preview_role')=='target')
    label=f'{curves[0]["metrics"]["start"]} — {curves[0]["metrics"]["end"]}'
    return dict(id=id,label=label,curves=curves,
        target_metrics=target['metrics'])


def rolling_choices(choice):
    start=pd.Timestamp(choice['curves'][0]['dates'][0]);end=pd.Timestamp(choice['curves'][0]['dates'][-1])
    recent=end-pd.DateOffset(years=10);prior=end-pd.DateOffset(years=20);earliest=max(start,end-pd.DateOffset(years=30))
    specs=[
        ('early-10y','20~30년 전',earliest,prior-pd.Timedelta(days=1)),
        ('prior-10y','10~20년 전',prior,recent-pd.Timedelta(days=1)),
        ('recent-10y','최근 10년',recent,end),
    ]
    return [window_choice(choice,*spec) for spec in specs if spec[2]<=spec[3]]


def render_png(path, title, curves, events):
    font=next((p for p in (
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/Supplemental/AppleGothic.ttf',
    ) if Path(p).exists()),None)
    if not font: raise RuntimeError('Install fonts-noto-cjk to render Korean previews')
    font_manager.fontManager.addfont(font)
    with plt.rc_context({'font.family':font_manager.FontProperties(fname=font).get_name(),
                         'axes.unicode_minus':False,'path.simplify':False,'font.size':13}):
        fig,growth=plt.subplots(figsize=(16,8),dpi=180)
        for curve in curves:
            dates=pd.to_datetime(curve['dates']);equity=np.array(curve['equity'])
            growth.plot(dates,equity,color=curve['display_color'],lw=.65,label=curve['display_name'])
        growth.set_yscale('log');growth.set_ylabel('자산 · 달러 (로그 축)')
        growth.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:,.0f}'))
        growth.legend(loc='upper left',frameon=False,ncol=len(curves))
        dates=curves[0]['dates']
        growth.grid(False);growth.spines[['top','right']].set_visible(False)
        growth.spines[['left','bottom']].set_color('#dfe5ec')
        growth.set_xlim(pd.Timestamp(dates[0]),pd.Timestamp(dates[-1]))
        for event in events:
            if dates[0]<=event['date']<=dates[-1]:
                growth.axvline(pd.Timestamp(event['date']),color='#78909C',lw=.5,alpha=.8,ls=':',zorder=0)
        selected=[e for e in events if dates[0]<=e['date']<=dates[-1]]
        for i,event in enumerate(selected):
            growth.text(pd.Timestamp(event['date']),.025+.06*(i%3),event['title'],
                transform=growth.get_xaxis_transform(),rotation=90,va='bottom',ha='right',fontsize=9,color='#607d8b')
        growth.xaxis.set_major_locator(mdates.YearLocator());growth.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        fig.subplots_adjust(left=.1,right=.98,top=.96,bottom=.09)
        path.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(path,dpi=180,facecolor='white')
        plt.close(fig)


def render_period_strip(path, choices, events):
    """Render reset periods as one visually continuous, three-panel figure."""
    font=next((p for p in (
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/Supplemental/AppleGothic.ttf',
    ) if Path(p).exists()),None)
    if not font: raise RuntimeError('Install fonts-noto-cjk to render Korean previews')
    font_manager.fontManager.addfont(font)
    with plt.rc_context({'font.family':font_manager.FontProperties(fname=font).get_name(),
                         'axes.unicode_minus':False,'path.simplify':False,'font.size':12}):
        fig,axes=plt.subplots(1,len(choices),figsize=(16,8),dpi=180,sharey=True,
                              gridspec_kw={'wspace':.025})
        axes=np.atleast_1d(axes)
        handles=[]
        for panel,(ax,choice) in enumerate(zip(axes,choices)):
            for curve in choice['curves']:
                dates=pd.to_datetime(curve['dates']);equity=np.asarray(curve['equity'])
                line,=ax.plot(dates,equity,color=curve['display_color'],lw=.65,
                              label=curve['display_name'])
                if panel==0: handles.append(line)
            ax.set_yscale('log');ax.grid(False)
            ax.set_xlim(pd.Timestamp(choice['curves'][0]['dates'][0]),
                        pd.Timestamp(choice['curves'][0]['dates'][-1]))
            ax.set_title(choice['label'],fontsize=12,pad=16,color='#45576a')
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            ax.spines[['top','right']].set_visible(False)
            ax.spines['bottom'].set_color('#dfe5ec')
            if panel==0:
                ax.spines['left'].set_color('#dfe5ec')
                ax.set_ylabel('자산 · 달러 (로그 축)')
                ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:,.0f}'))
                reset='10만 달러 시작'
            else:
                ax.spines['left'].set_color('#8fa0b2')
                ax.spines['left'].set_linestyle(':')
                ax.spines['left'].set_linewidth(1.2)
                ax.tick_params(axis='y',left=False,labelleft=False)
                reset='10만 달러 재시작'
            ax.text(.025,.98,reset,transform=ax.transAxes,va='top',ha='left',fontsize=9,
                    color='#60758a',bbox={'facecolor':'white','edgecolor':'none','alpha':.82,'pad':2})
            dates=choice['curves'][0]['dates']
            selected=[e for e in events if dates[0]<=e['date']<=dates[-1]]
            for i,event in enumerate(selected):
                ax.axvline(pd.Timestamp(event['date']),color='#78909C',lw=.5,alpha=.8,ls=':',zorder=0)
                ax.text(pd.Timestamp(event['date']),.02+.05*(i%3),event['title'],
                        transform=ax.get_xaxis_transform(),rotation=90,va='bottom',ha='right',
                        fontsize=7,color='#607d8b')
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.065,.985),frameon=False,
                   ncol=len(handles))
        fig.subplots_adjust(left=.075,right=.985,top=.88,bottom=.09)
        path.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(path,dpi=180,facecolor='white')
        plt.close(fig)


def attach_previews(root, public, methods, comparison, events, write):
    cache={}
    for method in methods:
        if method['metrics'] is None: continue
        id=method['id'];choices=[]
        if id in ('volatility-allocation','tqqq-buy-hold'):
            for p in comparison['periods']:
                payload=json.loads((public/p['file']).read_text())
                by_model={c['model']:c for c in payload['curves']}
                target=id=='tqqq-buy-hold'
                tqqq=dict(by_model['tqqq_hold'],display_name='TQQQ Buy & Hold',display_color=TQQQ_BLUE,preview_role='target' if target else 'benchmark')
                vo=dict(by_model['vo'],display_name='VO · 변동성 배분',display_color=VO_RED,preview_role='default' if target else 'target')
                choices.append(dict(id=p['id'],label=p['label'],curves=[tqqq,vo],target_metrics=(tqqq if target else vo)['metrics']))
            order={'early-10y':0,'prior-10y':1,'recent-10y':2}
            choices=sorted((p for p in choices if p['id'] in order),key=lambda p:order[p['id']])
            provenance={k:comparison[k] for k in ('source_commit','asset_sha256','fee_rate','initial_cash')}
            caption='최신 데이터 · 세 10년 구간을 각각 $100,000으로 시작'
        else:
            archive=root/'reporting/archive/previews'/f'{method["batch"]}.json.gz'
            if not archive.exists():
                method['preview_unavailable']='당시 최근 10년 곡선의 복원 검증을 완료하지 못했습니다.'
                continue
            if str(archive) not in cache:
                cache[str(archive)]=json.loads(gzip.decompress(archive.read_bytes()))
            payload=cache[str(archive)]
            # These are frozen original inputs, not today's adjusted market data.
            result_dir=Path(method['metric_source']).parent
            if payload['metadata_sha256']!=hashlib.sha256((root/result_dir/'metadata.json').read_bytes()).hexdigest():
                raise ValueError('Stale preview archive: '+method['batch'])
            model=method['metrics'].get('model',method['metrics'].get('scenario'))
            matched=[c for c in payload['curves'] if c['model']==model]
            matched.sort(key=lambda c:c['period']=='recent_10y')
            for curve in matched:
                strategy={k:v for k,v in curve.items() if k not in ('benchmark','vo','period')}
                tqqq=dict(curve['benchmark'],display_name='TQQQ 단순 보유',display_color=TQQQ_BLUE,preview_role='benchmark')
                vo=dict(curve['vo'],display_name='VO · 변동성 배분',display_color=VO_RED,preview_role='default')
                target=dict(strategy,display_name=method['title'],display_color=METHOD_YELLOW,preview_role='target')
                period_label=historical_period_label(curve['period'])
                if curve['period'] in ACTUAL_PERIODS:
                    period_label=f'실제 TQQQ 구간 · {target["metrics"]["start"]}–{target["metrics"]["end"]}'
                choices.append(dict(id=curve['period'],label=period_label,curves=[tqqq,vo,target],target_metrics=target['metrics']))
            if not choices: raise ValueError('Missing preview model: '+id)
            provenance={k:payload[k] for k in ('source_commit','asset_sha256','metadata_sha256')}
            synthetic=next((p for p in choices if p['id'] in SYNTHETIC_PERIODS),None)
            if synthetic:
                choices=rolling_choices(synthetic)
                caption='연구 당시 데이터 · 세 10년 구간을 각각 $100,000으로 재기준화'
            else:
                choices=choices[:1]
                caption=choices[0]['label']
        periods=[]
        for choice in choices:
            curves=choice['curves']
            if len(curves) not in (2,3) or any(curve['dates']!=curves[0]['dates'] for curve in curves[1:]):
                raise ValueError('Preview date mismatch: '+id)
            file=f'data/preview-{id}-{choice["id"]}.json'
            write(public/file,dict(curves=curves,events=events))
            periods.append(dict(id=choice['id'],label=choice['label'],file=file))
        images=[];strip=len(choices)==3
        if strip:
            png=f'previews/{id}-periods.png'
            render_period_strip(public/png,choices,events)
            images.append(dict(src=png,label=' / '.join(choice['label'] for choice in choices)))
        else:
            for choice in choices:
                png=f'previews/{id}-{choice["id"]}.png'
                render_png(public/png,method['title'],choice['curves'],events)
                images.append(dict(src=png,label=choice['label']))
        metric_choice=next((choice for choice in choices if choice['id']=='recent-10y'),choices[-1])
        method['preview']=dict(images=images,periods=periods,strip=strip,metrics=metric_choice['target_metrics'],caption=caption,
            href=f'charts/{id}/',provenance=provenance,
            comparison_note='파랑 TQQQ · 빨강 VO' if id in ('volatility-allocation','tqqq-buy-hold') else '파랑 TQQQ · 빨강 VO · 노랑 이 방법')
