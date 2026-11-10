"""Publication invariants, independent of network and account credentials."""
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from reporting.catalog import catalog, validate_coverage
from reporting.build import periods, rolling_decades, clean, events, audits, stress_history, yearly_performance, current_vo_snapshot
from scripts.send_daily_briefing import build_briefing, load_prices
from backtests import load_market_data, build_target_weights, run_weight_strategy
from backtests.vo_v_recovery import build_active_vo_weights

ROOT=Path(__file__).resolve().parents[1]


def test_research_catalog_has_no_omitted_results_or_reports():
    validate_coverage(ROOT)
    ids=[e['id'] for e in catalog(ROOT)]
    assert len(ids)==len(set(ids))
    assert {'batch-01','batch-11','vo-upside','vo-sgov','vo-regimes'}<=set(ids)


def test_period_partitions_have_no_overlapping_calendar_boundaries():
    latest=pd.Timestamp('2026-10-02'); first=pd.Timestamp('1999-03-10')
    ranges=periods(latest,first)[1:]
    ordered=sorted((pd.Timestamp(s),pd.Timestamp(e)) for _,_,s,e in ranges)
    assert ordered[0][0]==first
    assert ordered[-1][1]==latest
    for (_,end),(start,_) in zip(ordered,ordered[1:]):
        assert end+pd.Timedelta(days=1)==start


def test_rolling_decades_are_disjoint_and_use_available_history():
    windows=rolling_decades(pd.Timestamp('2026-10-12'),pd.Timestamp('1999-03-10'))
    assert [(key,start,end) for key,_,start,end in windows]==[
        ('early-10y','1999-03-10','2006-10-11'),
        ('prior-10y','2006-10-12','2016-10-11'),
        ('recent-10y','2016-10-12','2026-10-12'),
    ]


def test_current_vo_snapshot_uses_latest_30_returns_and_default_boundaries():
    prices=load_market_data(ROOT).tqqq
    returns=prices.Close.pct_change().dropna().tail(30)
    snapshot=current_vo_snapshot(prices)
    assert snapshot['mean_daily_return']==pytest.approx(returns.mean())
    assert snapshot['daily_standard_deviation']==pytest.approx(returns.std(ddof=1))
    assert snapshot['annualized_volatility']==pytest.approx(returns.std(ddof=1)*252**.5)
    expected=1.0 if snapshot['annualized_volatility']<=.60 else .5 if snapshot['annualized_volatility']<=.90 else 0.0
    assert snapshot['target_weight']==expected


def test_tqqq_research_has_no_actual_only_evaluation_period():
    forbidden={'actual_tqqq','actual_pre2026','actual_current'}
    folders=[
        ROOT/'results/research/batch-01',
        ROOT/'results/research/batch-02',
        ROOT/'results/research/ma-vo',
        ROOT/'results/research/vo-bull-participation',
        ROOT/'results/research/vo-upside-directional',
        ROOT/'results/research/batch-11',
    ]
    for folder in folders:
        for path in folder.glob('*.csv'):
            frame=pd.read_csv(path)
            if 'period' in frame:
                assert forbidden.isdisjoint(set(frame.period.dropna())),path

    expected_start='1999-03-10'
    checks=[
        (folders[0]/'period-summary.csv','full_synthetic'),
        (folders[1]/'period-summary.csv','full_synthetic'),
        (folders[2]/'period-summary.csv','full_current'),
        (folders[3]/'period-summary.csv','full_current'),
        (folders[4]/'period-summary.csv','full_pre2026'),
    ]
    for path,period in checks:
        rows=pd.read_csv(path).query('period == @period')
        assert not rows.empty and set(rows.start)=={expected_start},path

    jordan=pd.read_csv(folders[5]/'period-summary.csv')
    tqqq=jordan[(jordan.period=='synthetic_full') & jordan.model.str.contains('tqqq|three_percent|^vo$',regex=True)]
    assert not tqqq.empty and set(tqqq.start)=={expected_start}


def test_site_signal_matches_briefing_and_last_signal_is_pending():
    b=build_briefing(load_prices(ROOT)); data=load_market_data(ROOT)
    prices,weights,core=build_active_vo_weights(data)
    assert weights.iloc[-1]==b.stock_weight
    assert weights.iloc[-2]==b.previous_stock_weight
    assert core.iloc[-1]==b.core_stock_weight
    # Force a different final close signal; there is no following open to execute it.
    baseline=run_weight_strategy(prices,weights,start=prices.index[-20])
    changed=weights.copy();changed.iloc[-1]=1-weights.iloc[-1]
    pending=run_weight_strategy(prices,changed,start=prices.index[-20])
    pd.testing.assert_series_equal(baseline.equity,pending.equity)
    pd.testing.assert_frame_equal(baseline.trades,pending.trades)


def test_site_stress_distribution_matches_daily_briefing():
    briefing=build_briefing(load_prices(ROOT))
    data=load_market_data(ROOT)
    prices,weights,_=build_active_vo_weights(data)
    result=run_weight_strategy(prices,weights,fee_rate=.001)
    published=stress_history(result.equity)
    stress=briefing.stress_context
    assert stress is not None
    assert published['current']['drawdown']==pytest.approx(stress.vo_current_drawdown)
    assert published['current']['episode_mdd']==pytest.approx(stress.vo_episode_mdd)
    assert published['current']['underwater_days']==stress.underwater_days
    assert published['current']['depth_rank']==stress.depth_rank
    assert published['current']['duration_rank']==stress.duration_rank
    assert published['drawdowns']['count']==stress.mdd_qualifying_episodes
    assert published['drawdowns']['worst']==pytest.approx(stress.historical_worst_mdd)
    assert published['durations']['count']==stress.duration_qualifying_episodes
    assert published['durations']['longest']==stress.historical_longest_underwater_days
    assert published['episodes']
    assert all(row['mdd']<=-.10 or row['underwater_days']>=30 for row in published['episodes'])
    assert all({'mdd','underwater_days','peak_date','trough_date','recovery_date'}<=set(row) for row in published['episodes'])


def test_market_events_are_serializable_for_stress_details():
    rows=events()
    assert rows
    assert {'date','title','background'} <= rows[0].keys()
    assert any(row['title']=='코로나19 충격' for row in rows)


def test_audit_headings_do_not_swallow_following_sections():
    rows=audits()
    assert len(rows)>2
    assert all('\n' not in row['title'] for row in rows)
    assert any('자동 탐색' in row['title'] for row in rows)


@pytest.mark.parametrize('entry',[e for e in catalog(ROOT) if (ROOT/'reporting/archive'/f'{e["id"]}.json.gz').exists()],ids=lambda e:e['id'])
def test_historical_curves_match_immutable_results(entry):
    archive=json.loads(gzip.decompress((ROOT/'reporting/archive'/f'{entry["id"]}.json.gz').read_bytes()))
    folder=ROOT/entry['results']
    assert archive['metadata_sha256']==hashlib.sha256((folder/'metadata.json').read_bytes()).hexdigest()
    rows=pd.read_csv(folder/'period-summary.csv').set_index(['period','model'])
    assert archive['curves']
    for curve in archive['curves']:
        row=rows.loc[(archive['period'],curve['model'])]
        assert curve['equity'][-1]==pytest.approx(row.end_equity,rel=1e-8)
        assert curve['dates'][0]==row.start
        assert curve['dates'][-1]==row.end
        assert len(curve['dates'])==len(set(curve['dates']))
        assert curve['dates']==sorted(curve['dates'])
        equity=pd.Series(curve['equity'])
        assert float((equity/equity.cummax()-1).min())==pytest.approx(row.mdd,abs=1e-8)


def test_failed_erc_study_has_no_fabricated_curves():
    assert not (ROOT/'reporting/archive/batch-09.json.gz').exists()
    failure=json.loads((ROOT/'results/research/batch-09/failure.json').read_text())
    assert failure['result_status']=='failed_before_backtest'


def test_json_export_preserves_precision_and_missing_values():
    assert clean({'n':float('nan'),'v':123.1234567890123})=={'n':None,'v':123.1234567890123}


def test_yearly_performance_uses_previous_year_end_for_return_and_drawdown():
    rows=yearly_performance([{
        'model':'example',
        'dates':['2020-12-30','2020-12-31','2021-01-04','2021-01-05'],
        'equity':[100,110,99,120],
        'metrics':{'start_equity':100},
    }])
    assert rows[0]['total_return']==pytest.approx(.10)
    assert rows[0]['mdd']==0
    assert rows[1]['total_return']==pytest.approx(120/110-1)
    assert rows[1]['mdd']==pytest.approx(-.10)
    assert all(row['partial'] for row in rows)


def test_method_specs_and_curves_use_exact_frozen_model_and_period():
    from reporting.methods import method_data
    from reporting.catalog import STRATEGIES
    charts={}
    methods=method_data(ROOT,STRATEGIES,lambda file,curves:charts.update({file:curves}))
    assert len(methods)==4
    known={entry['id'] for entry in catalog(ROOT)}
    for method in methods:
        rows=pd.read_csv(ROOT/method['metric_source'])
        expected=rows[(rows.model==method['model']) & (rows.period==method['period'])].iloc[0]
        for key in ('cagr','mdd','annual_trades','longest_time_underwater_days'):
            assert method['metrics'][key]==expected[key]
        recent=rows[(rows.model==method['model']) & (rows.period=='recent_10y')]
        if len(recent)==1:
            assert method['recent_metrics']['cagr']==recent.iloc[0].cagr
            assert method['recent_metrics']['mdd']==recent.iloc[0].mdd
        assert set(method['studies'])<=known
        for curve in charts[method['chart']]:
            assert (curve['dates'][0],curve['dates'][-1])==(expected.start,expected.end)
            assert len(curve['dates'])==len(curve['equity'])
        assert charts[method['chart']][0]['model']==method['model']
    pp=next(m for m in methods if m['id']=='permanent-portfolio')
    assert set(pp['peers'])=={'permanent_band','permanent_annual_equal','permanent_buyhold'}


def test_strategy_shelf_excludes_rejected_research_families():
    from reporting.methods import buy_hold_card, method_data
    from reporting.catalog import STRATEGIES
    methods=method_data(ROOT,STRATEGIES,lambda *_:None)
    methods.insert(1,buy_hold_card(ROOT))
    assert [method['id'] for method in methods]==[
        'volatility-allocation',
        'tqqq-buy-hold',
        'ixic-three-percent-rule',
        'value-rebalancing',
        'permanent-portfolio',
    ]
    rejected={study['id'] for study in catalog(ROOT) if study['status'] in {'미채택','실행 실패'}}
    assert all(method['batch'] not in rejected or method['id'] in {
        'volatility-allocation','tqqq-buy-hold','ixic-three-percent-rule','value-rebalancing'
    } for method in methods)


@pytest.mark.parametrize('archive',sorted((ROOT/'reporting/archive/previews').glob('*.json.gz')),ids=lambda p:p.stem)
def test_preview_curves_match_original_periods_and_benchmark_dates(archive):
    payload=json.loads(gzip.decompress(archive.read_bytes()))
    study=next(s for s in catalog(ROOT) if s['id']==archive.name.removesuffix('.json.gz'))
    folder=ROOT/study['results']
    assert payload['metadata_sha256']==hashlib.sha256((folder/'metadata.json').read_bytes()).hexdigest()
    assert payload['asset_sha256']==json.loads((folder/'metadata.json').read_text())['asset_sha256']
    assert not payload['failures']
    table=pd.read_csv(folder/('summary.csv' if study['id']=='vo-sgov' else 'period-summary.csv'))
    for curve in payload['curves']:
        row=table[table.scenario=='VO SGOV'].iloc[0] if study['id']=='vo-sgov' else table[(table.model==curve['model'])&(table.period==curve['period'])].iloc[0]
        for field in ('cagr','mdd','annual_trades','fees','longest_time_underwater_days','end_equity'):
            assert curve['metrics'][field]==pytest.approx(row[field],rel=1e-8,abs=1e-7)
        benchmark=curve['benchmark']
        vo=curve['vo']
        assert curve['dates']==benchmark['dates']==vo['dates']
        assert (curve['dates'][0],curve['dates'][-1])==(row.start,row.end)
        for series in (curve,benchmark,vo):
            assert series['metrics']['start_equity']==100000
            assert len(series['dates'])==len(series['equity'])==len(set(series['dates']))
            equity=pd.Series(series['equity'])
            assert (equity/equity.cummax()-1).min()==pytest.approx(series['metrics']['mdd'],abs=1e-8)
            years=(pd.Timestamp(row.end)-pd.Timestamp(row.start)).days/365.2425
            assert (equity.iloc[-1]/100000)**(1/years)-1==pytest.approx(series['metrics']['cagr'],abs=1e-8)
