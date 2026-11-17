#!/usr/bin/env python3
"""Compare VO cash-sleeve rules using SGOV cash distributions."""
from __future__ import annotations

import argparse, hashlib, html, json, re, sys
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from backtests import BacktestResult, build_target_weights, layered_sgov_state, load_assets, load_market_data, summarize
from backtests.vo_v_recovery import build_active_vo_weights

ISHARES_SGOV_URL = "https://www.ishares.com/us/products/314116/ishares-0-3-month-treasury-bond-etf"
VARIANTS = ("cash", "immediate_full_sleeve", "delayed_15_sessions",
            "monthly_entry_after_5_sessions", "high_band_full_then_hold",
            "high_band_half_then_hold", "layered_15_sessions")
SCENARIOS={"cash":"VO cash","immediate_full_sleeve":"VO SGOV"}

def parse_args():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--end")
    p.add_argument("--initial-cash",type=float,default=100_000.0)
    p.add_argument("--distribution-tax",type=float,default=0.0)
    p.add_argument("--sgov-fee",type=float,default=.001)
    p.add_argument("--sgov-half-spread",type=float,default=0.0)
    p.add_argument("--distribution-html",type=Path)
    p.add_argument("--output",type=Path,default=ROOT/"results"/"vo-sgov")
    return p.parse_args()

def fetch_distribution_html():
    req=Request(ISHARES_SGOV_URL,headers={"User-Agent":"Mozilla/5.0"})
    with urlopen(req,timeout=30) as response: return response.read().decode()

def parse_ishares_distributions(page):
    m=re.search(r'data-componentname="DistributionV3".*?componentprops="(.*?)"',page,re.S)
    if not m: raise ValueError("SGOV distribution table not found")
    props=json.loads(html.unescape(m.group(1)))
    data={item["name"]:item.get("value",item.get("formattedValue")) for item in props["distributionTableData"]}
    names={"recordDate":"RecordDate","exDate":"ExDate","payableDate":"PayableDate","totalDistribution":"Distribution"}
    if not set(names).issubset(data): raise ValueError("SGOV distribution columns missing")
    frame=pd.DataFrame({new:data[old] for old,new in names.items()})
    for column in ("RecordDate","ExDate","PayableDate"):
        frame[column]=pd.to_datetime(frame[column].astype(str),format="%Y%m%d")
    frame["Distribution"]=pd.to_numeric(frame["Distribution"],errors="raise")
    frame=frame.sort_values(["ExDate","PayableDate"]).reset_index(drop=True)
    if frame.empty or frame.ExDate.duplicated().any() or (frame.Distribution<0).any():
        raise ValueError("invalid SGOV distributions")
    return frame

def _pending(signal,index):
    signal=signal.sort_index().astype(float); loc=signal.index.searchsorted(index,side="left")-1
    if (loc<0).any(): raise ValueError("prior VO signal unavailable")
    duration=[]; last=None; count=0
    for value in signal:
        count=count+1 if last is not None and np.isclose(value,last) else 1
        duration.append(count); last=value
    return (pd.Series(signal.iloc[loc].to_numpy(),index=index),
            pd.Series(np.asarray(duration)[loc],index=index,dtype=int))

def _previous_values(signal,index):
    signal=signal.sort_index().astype(float); loc=signal.index.searchsorted(index,side="left")-1
    if (loc<0).any(): raise ValueError("prior signal unavailable")
    return pd.Series(signal.iloc[loc].to_numpy(),index=index)

def build_execution_targets(vo_signal,index,variant,tqqq_signal=None):
    if variant not in VARIANTS: raise ValueError(f"unknown variant {variant}")
    tqqq,duration=_pending(vo_signal if tqqq_signal is None else tqqq_signal,index)
    if variant=="layered_15_sessions":
        capacity=_previous_values(layered_sgov_state(vo_signal)["SGOVCapacity"],index)
        return pd.DataFrame({"TQQQ":tqqq.to_numpy(),"SGOV":np.minimum(capacity.to_numpy(),1.-tqqq.to_numpy())},index=index)
    values=[]; sgov=0.; activated=False
    for offset,(date,risk) in enumerate(tqqq.items()):
        defensive=1.-risk
        if variant=="cash": sgov=0.
        elif variant=="immediate_full_sleeve": sgov=defensive
        elif variant in {"delayed_15_sessions","monthly_entry_after_5_sessions"}:
            if np.isclose(risk,1): sgov=0.
            else:
                sgov=min(sgov,defensive)
                days=15 if variant=="delayed_15_sessions" else 5
                first=offset==0 or index[offset-1].month!=date.month
                if duration.loc[date]>=days and (variant=="delayed_15_sessions" or first): sgov=defensive
        else:
            if np.isclose(risk,0): activated=True
            elif np.isclose(risk,1): activated=False
            cap=1. if variant=="high_band_full_then_hold" else .5
            sgov=min(defensive,cap) if activated else 0.
        values.append(sgov)
    return pd.DataFrame({"TQQQ":tqqq.to_numpy(),"SGOV":values},index=index)

def _fee(gross,rate):
    return 0. if gross<=10 or rate==0 else float(np.floor(gross*rate*100)/100)

def _affordable(cash,price,wanted,rate):
    q=min(wanted,int(cash//price))
    while q and q*price+_fee(q*price,rate)>cash+1e-12: q-=1
    return q

def run_sgov_strategy(assets,targets,distributions,*,initial_cash=100_000.,tqqq_fee=.001,
                      sgov_fee=.001,sgov_half_spread=0.,distribution_tax=0.):
    if not 0<=distribution_tax<1: raise ValueError("invalid distribution tax")
    index=targets.index; by_ex={row.ExDate:row for row in distributions.itertuples(index=False)}
    cash=float(initial_cash); shares={"TQQQ":0,"SGOV":0}; receivables=[]; trades=[]; positions=[]; equity=[]
    last_target=None; gross_div=net_div=0.
    for date,target in targets.iterrows():
        event=by_ex.get(date)
        if event is not None and shares["SGOV"]:
            gross=shares["SGOV"]*float(event.Distribution); net=gross*(1-distribution_tax)
            receivables.append((pd.Timestamp(event.PayableDate),net)); gross_div+=gross; net_div+=net
        paid=sum(amount for payable,amount in receivables if payable<=date)
        if paid:
            cash+=paid; receivables=[item for item in receivables if item[0]>date]
        opens={name:float(frame.loc[date,"Open"]) for name,frame in assets.items()}
        key=(float(target.TQQQ),float(target.SGOV))
        if last_target is None or not np.allclose(key,last_target):
            wealth=cash+sum(receivables_value for _,receivables_value in receivables)+sum(shares[n]*opens[n] for n in shares)
            changed={"TQQQ":last_target is None or not np.isclose(key[0],last_target[0]),
                     "SGOV":last_target is None or not np.isclose(key[1],last_target[1])}
            desired={n:(int(np.floor(wealth*float(target[n])/opens[n])) if changed[n] else shares[n]) for n in shares}
            for name in shares:
                q=max(0,shares[name]-desired[name])
                if not q: continue
                price=opens[name]*(1-sgov_half_spread if name=="SGOV" else 1)
                gross=q*price; fee=_fee(gross,sgov_fee if name=="SGOV" else tqqq_fee)
                cash+=gross-fee; shares[name]-=q
                trades.append(dict(Date=date,Asset=name,Side="SELL",Quantity=q,Price=price,Gross=gross,Fee=fee,TargetWeight=float(target[name])))
            for name in ("TQQQ","SGOV"):
                wanted=max(0,desired[name]-shares[name])
                price=opens[name]*(1+sgov_half_spread if name=="SGOV" else 1)
                rate=sgov_fee if name=="SGOV" else tqqq_fee; q=_affordable(cash,price,wanted,rate)
                if not q: continue
                gross=q*price; fee=_fee(gross,rate); cash-=gross+fee; shares[name]+=q
                trades.append(dict(Date=date,Asset=name,Side="BUY",Quantity=q,Price=price,Gross=gross,Fee=fee,TargetWeight=float(target[name])))
            last_target=key
        rec=sum(amount for _,amount in receivables)
        equity.append(cash+rec+sum(shares[n]*float(assets[n].loc[date,"Close"]) for n in shares))
        positions.append(dict(Date=date,Cash=cash,Receivable=rec,TQQQShares=shares["TQQQ"],SGOVShares=shares["SGOV"],TQQQTarget=key[0],SGOVTarget=key[1]))
    trade_frame=pd.DataFrame(trades)
    if not trade_frame.empty: trade_frame=trade_frame.set_index("Date")
    result=BacktestResult(pd.Series(equity,index=index,name="Equity"),trade_frame,pd.DataFrame(positions).set_index("Date"),float(initial_cash))
    return result,{"gross_distributions":gross_div,"net_distributions":net_div,"ending_receivable":result.positions.Receivable.iloc[-1]}

def holding_diagnostics(result):
    held=result.positions.SGOVShares>0; starts=list(held.index[held&~held.shift(fill_value=False)]); ends=list(held.index[~held&held.shift(fill_value=False)])
    completed=[]
    for start in starts:
        later=[end for end in ends if end>start]
        if later: completed.append(held.index.get_loc(later[0])-held.index.get_loc(start))
    trades=result.trades
    st=trades[trades.Asset=="SGOV"] if not trades.empty else trades
    out={"sgov_orders":len(st),"sgov_buy_orders":int((st.get("Side",pd.Series(dtype=str))=="BUY").sum()),"sgov_sell_orders":int((st.get("Side",pd.Series(dtype=str))=="SELL").sum()),"completed_holds":len(completed),"mean_hold_sessions":np.mean(completed) if completed else np.nan,"median_hold_sessions":np.median(completed) if completed else np.nan}
    out.update({f"exits_within_{n}_sessions":sum(x<=n for x in completed) for n in (5,10,15,20)}); return out

def run_all(assets,weights,distributions,*,initial_cash,sgov_fee,sgov_half_spread,distribution_tax):
    index=assets["TQQQ"].index.intersection(assets["SGOV"].index); rows=[]; results={}; target_map={}
    for variant in VARIANTS:
        targets=build_execution_targets(weights,index,variant)
        result,divs=run_sgov_strategy(assets,targets,distributions,initial_cash=initial_cash,sgov_fee=sgov_fee,sgov_half_spread=sgov_half_spread,distribution_tax=distribution_tax)
        fees={"TQQQ":0.,"SGOV":0.}; orders={"TQQQ":0,"SGOV":0}
        if not result.trades.empty:
            fees.update(result.trades.groupby("Asset").Fee.sum().to_dict()); orders.update(result.trades.groupby("Asset").size().to_dict())
        rows.append({"variant":variant,"scenario":SCENARIOS.get(variant,variant),**summarize(result),**holding_diagnostics(result),**divs,"tqqq_orders":orders["TQQQ"],"tqqq_fees":fees["TQQQ"],"sgov_fees":fees["SGOV"]})
        results[variant]=result; target_map[variant]=targets.SGOV
    return pd.DataFrame(rows),results,pd.DataFrame(target_map)

def profile_row(name,result,divs):
    fees={"TQQQ":0.,"SGOV":0.}; orders={"TQQQ":0,"SGOV":0}
    if not result.trades.empty:
        fees.update(result.trades.groupby("Asset").Fee.sum().to_dict()); orders.update(result.trades.groupby("Asset").size().to_dict())
    return {"variant":name,**summarize(result),**holding_diagnostics(result),**divs,
            "tqqq_orders":orders["TQQQ"],"tqqq_fees":fees["TQQQ"],"sgov_fees":fees["SGOV"]}

def run_active_profiles(assets,core_weights,active_weights,distributions,*,initial_cash,sgov_fee,sgov_half_spread,distribution_tax):
    index=assets["TQQQ"].index.intersection(assets["SGOV"].index); rows=[]; results={}
    for name,variant in (("active_vo_5_20_cash","cash"),("active_vo_5_20_layered_15_sessions","layered_15_sessions")):
        targets=build_execution_targets(core_weights,index,variant,tqqq_signal=active_weights)
        result,divs=run_sgov_strategy(assets,targets,distributions,initial_cash=initial_cash,sgov_fee=sgov_fee,sgov_half_spread=sgov_half_spread,distribution_tax=distribution_tax)
        rows.append(profile_row(name,result,divs)); results[name]=result
    return pd.DataFrame(rows),results

def yearly_returns(equity,initial):
    ends=equity.groupby(equity.index.year).last(); prior=pd.concat([pd.Series([initial]),ends.iloc[:-1]],ignore_index=True)
    return {int(year):float(value/base-1) for (year,value),base in zip(ends.items(),prior)}

def main():
    args=parse_args(); page=args.distribution_html.read_text() if args.distribution_html else fetch_distribution_html()
    distributions=parse_ishares_distributions(page); data=load_market_data(ROOT); sgov=load_assets(("SGOV",),ROOT)["SGOV"]
    _,weights=build_target_weights("vo",data); _,active_weights,_=build_active_vo_weights(data); common=data.tqqq.index.intersection(sgov.index)
    if args.end: common=common[common<=pd.Timestamp(args.end)]
    assets={"TQQQ":data.tqqq.loc[common],"SGOV":sgov.loc[common]}
    summary,results,targets=run_all(assets,weights,distributions,initial_cash=args.initial_cash,sgov_fee=args.sgov_fee,sgov_half_spread=args.sgov_half_spread,distribution_tax=args.distribution_tax)
    active_summary,active_results=run_active_profiles(assets,weights,active_weights,distributions,initial_cash=args.initial_cash,sgov_fee=args.sgov_fee,sgov_half_spread=args.sgov_half_spread,distribution_tax=args.distribution_tax)
    pending,_=_pending(weights,common); groups=pending.ne(pending.shift()).cumsum(); episodes=[]
    for _,series in pending.groupby(groups):
        episodes.append({"tqqq_target":series.iloc[0],"start":series.index[0],"end":series.index[-1],"sessions":len(series)})
    sensitivity=[]
    active_sensitivity=[]
    for fee in (0.,.0005,.001,.002):
        for tax in (0.,.15):
            table,_,_=run_all(assets,weights,distributions,initial_cash=args.initial_cash,sgov_fee=fee,sgov_half_spread=0.,distribution_tax=tax)
            for row in table.itertuples(): sensitivity.append(dict(variant=row.variant,sgov_fee_each_side=fee,distribution_tax=tax,end_equity=row.end_equity,cagr=row.cagr,mdd=row.mdd,fees=row.fees))
            active_table,_=run_active_profiles(assets,weights,active_weights,distributions,initial_cash=args.initial_cash,sgov_fee=fee,sgov_half_spread=0.,distribution_tax=tax)
            for row in active_table.itertuples(): active_sensitivity.append(dict(variant=row.variant,sgov_fee_each_side=fee,distribution_tax=tax,end_equity=row.end_equity,cagr=row.cagr,mdd=row.mdd,fees=row.fees))
    spread,_,_=run_all(assets,weights,distributions,initial_cash=args.initial_cash,sgov_fee=.001,sgov_half_spread=.00005,distribution_tax=0.)
    subperiod=[]; active_subperiod=[]
    for period,start,end in (("near_zero_rates",common[0],pd.Timestamp("2021-12-31")),
                             ("hiking_and_high_rates",pd.Timestamp("2022-01-01"),pd.Timestamp("2024-12-31")),
                             ("recent",pd.Timestamp("2025-01-01"),common[-1])):
        selected=common[(common>=start)&(common<=end)]
        table,_,_=run_all({n:f.loc[selected] for n,f in assets.items()},weights,distributions,initial_cash=args.initial_cash,sgov_fee=args.sgov_fee,sgov_half_spread=args.sgov_half_spread,distribution_tax=args.distribution_tax)
        table.insert(1,"period",period); subperiod.extend(table.to_dict("records"))
        active_table,_=run_active_profiles({n:f.loc[selected] for n,f in assets.items()},weights,active_weights,distributions,initial_cash=args.initial_cash,sgov_fee=args.sgov_fee,sgov_half_spread=args.sgov_half_spread,distribution_tax=args.distribution_tax)
        active_table.insert(1,"period",period); active_subperiod.extend(active_table.to_dict("records"))
    output=args.output; output.mkdir(parents=True,exist_ok=True)
    summary.to_csv(output/"summary.csv",index=False,float_format="%.10f")
    active_summary.to_csv(output/"active_profile_summary.csv",index=False,float_format="%.10f")
    pd.DataFrame({v:yearly_returns(r.equity,args.initial_cash) for v,r in results.items()}).rename_axis("year").to_csv(output/"yearly_returns.csv",float_format="%.10f")
    pd.DataFrame(sensitivity).to_csv(output/"fee_tax_sensitivity.csv",index=False,float_format="%.10f")
    pd.DataFrame(active_sensitivity).to_csv(output/"active_profile_sensitivity.csv",index=False,float_format="%.10f")
    spread[["variant","end_equity","cagr","mdd","fees"]].to_csv(output/"spread_sensitivity.csv",index=False,float_format="%.10f")
    pd.DataFrame(subperiod).to_csv(output/"subperiod_summary.csv",index=False,float_format="%.10f")
    pd.DataFrame(active_subperiod).to_csv(output/"active_profile_subperiod.csv",index=False,float_format="%.10f")
    pd.DataFrame(episodes).to_csv(output/"regime_episodes.csv",index=False,date_format="%Y-%m-%d")
    distributions.to_csv(output/"distributions.csv",index=False,date_format="%Y-%m-%d",float_format="%.6f"); targets.to_csv(output/"sgov_targets.csv",float_format="%.1f")
    for variant,result in results.items():
        result.equity.rename(variant).to_csv(output/f"{variant}_equity.csv",float_format="%.10f"); result.trades.to_csv(output/f"{variant}_trades.csv",float_format="%.10f")
    for variant,result in active_results.items():
        result.equity.rename(variant).to_csv(output/f"{variant}_equity.csv",float_format="%.10f"); result.trades.to_csv(output/f"{variant}_trades.csv",float_format="%.10f")
    results["cash"].equity.rename("VO cash").to_csv(output/"cash_equity.csv",float_format="%.10f")
    results["immediate_full_sleeve"].equity.rename("VO SGOV").to_csv(output/"sgov_equity.csv",float_format="%.10f")
    metadata={"start":str(common[0].date()),"end":str(common[-1].date()),"initial_cash":args.initial_cash,"tqqq_fee_each_side":.001,"sgov_fee_each_side":args.sgov_fee,"sgov_half_spread":args.sgov_half_spread,"distribution_tax":args.distribution_tax,"distribution_source":ISHARES_SGOV_URL,"distribution_treatment":"official cash distributions; pre-ex-close entitlement; payable-date cash; no automatic reinvestment","asset_sha256":{n:hashlib.sha256((ROOT/"assets"/f"{n}.csv").read_bytes()).hexdigest() for n in ("TQQQ","SGOV")}}
    (output/"metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    return 0
if __name__=="__main__": raise SystemExit(main())
