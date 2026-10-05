"""Publication invariants, independent of network and account credentials."""
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from reporting.catalog import catalog, validate_coverage
from reporting.build import periods, clean
from scripts.send_daily_briefing import build_briefing, load_prices
from backtests import load_market_data, build_target_weights, run_weight_strategy

ROOT=Path(__file__).resolve().parents[1]


def test_research_catalog_has_no_omitted_results_or_reports():
    validate_coverage(ROOT)
    ids=[e['id'] for e in catalog(ROOT)]
    assert len(ids)==len(set(ids))
    assert {'batch-01','batch-11','vo-upside','vo-sgov','vo-regimes'}<=set(ids)


def test_period_partitions_have_no_overlapping_calendar_boundaries():
    latest=pd.Timestamp('2026-10-02'); first=pd.Timestamp('1999-03-10')
    ranges=periods(latest,first)[2:]
    ordered=sorted((pd.Timestamp(s),pd.Timestamp(e)) for _,_,s,e in ranges)
    assert ordered[0][0]==first
    assert ordered[-1][1]==latest
    for (_,end),(start,_) in zip(ordered,ordered[1:]):
        assert end+pd.Timedelta(days=1)==start


def test_site_signal_matches_briefing_and_last_signal_is_pending():
    b=build_briefing(load_prices(ROOT)); data=load_market_data(ROOT)
    prices,weights=build_target_weights('vo',data)
    assert weights.iloc[-1]==b.stock_weight
    assert weights.iloc[-2]==b.previous_stock_weight
    # Force a different final close signal; there is no following open to execute it.
    baseline=run_weight_strategy(prices,weights,start=prices.index[-20])
    changed=weights.copy();changed.iloc[-1]=1-weights.iloc[-1]
    pending=run_weight_strategy(prices,changed,start=prices.index[-20])
    pd.testing.assert_series_equal(baseline.equity,pending.equity)
    pd.testing.assert_frame_equal(baseline.trades,pending.trades)


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
        assert set(method['studies'])<=known
        for curve in charts[method['chart']]:
            assert (curve['dates'][0],curve['dates'][-1])==(expected.start,expected.end)
            assert len(curve['dates'])==len(curve['equity'])
        assert charts[method['chart']][0]['model']==method['model']
    pp=next(m for m in methods if m['id']=='permanent-portfolio')
    assert set(pp['peers'])=={'permanent_band','permanent_annual_equal','permanent_buyhold'}


def test_research_methods_cover_studies_without_invented_or_selected_best_metrics():
    from reporting.methods import research_method_data
    studies=catalog(ROOT)
    methods=research_method_data(ROOT,studies)
    assert len(methods)==len({m['id'] for m in methods})==25
    assert {m['batch'] for m in methods}=={s['id'] for s in studies}-{'batch-10','vo-regimes'}
    for method in methods:
        assert '배치' not in method['title']
        if method['status']=='실행 실패':
            assert method['metrics'] is None and not method['result_rows']
            continue
        frame=pd.read_csv(ROOT/method['metric_source'])
        for row in method['result_rows']:
            expected=frame[(frame.model==row['model']) & (frame.period==row['period'])].iloc[0] if 'model' in row else frame[frame.scenario==row['scenario']].iloc[0]
            for field in ('cagr','mdd','start','end','longest_time_underwater_days','annual_trades'):
                assert row[field]==expected[field]
        assert (method['metrics'] is None)==(len(method['result_rows'])>1)
    assert len(next(m for m in methods if m['id']=='moving-average-vo')['result_rows'])==458
    assert len(next(m for m in methods if m['id']=='vo-bull')['result_rows'])==68


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
