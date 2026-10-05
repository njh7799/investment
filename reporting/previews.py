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

TQQQ_BLUE='#2979FF'
VO_RED='#E5484D'
METHOD_YELLOW='#D99A00'


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
            choices.sort(key=lambda p:p['id']!='actual')
            provenance={k:comparison[k] for k in ('source_commit','asset_sha256','fee_rate','initial_cash')}
            caption='최신 데이터 · 실제 TQQQ 전체 구간'
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
                choices.append(dict(id=curve['period'],label='연구 당시 최근 10년' if curve['period']=='recent_10y' else '연구 당시 전체 구간',curves=[tqqq,vo,target],target_metrics=target['metrics']))
            if not choices: raise ValueError('Missing preview model: '+id)
            provenance={k:payload[k] for k in ('source_commit','asset_sha256','metadata_sha256')}
            caption='연구 당시 최근 10년' if choices[0]['id']=='recent_10y' else '연구 당시 전체 평가 구간'
        periods=[]
        for choice in choices:
            curves=choice['curves']
            if len(curves) not in (2,3) or any(curve['dates']!=curves[0]['dates'] for curve in curves[1:]):
                raise ValueError('Preview date mismatch: '+id)
            file=f'data/preview-{id}-{choice["id"]}.json'
            write(public/file,dict(curves=curves,events=events))
            periods.append(dict(id=choice['id'],label=choice['label'],file=file))
        png=f'previews/{id}.png'
        render_png(public/png,method['title'],choices[0]['curves'],events)
        method['preview']=dict(image=png,periods=periods,metrics=choices[0]['target_metrics'],caption=caption,
            href=f'charts/{id}/',provenance=provenance,
            comparison_note='파랑 TQQQ · 빨강 VO' if id in ('volatility-allocation','tqqq-buy-hold') else '파랑 TQQQ · 빨강 VO · 노랑 이 방법')
