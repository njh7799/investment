import React,{useMemo,useState} from 'react';
import {CartesianGrid,ReferenceLine,ResponsiveContainer,Scatter,ScatterChart,Tooltip,XAxis,YAxis,ZAxis} from 'recharts';
import {ChartContainer,ChartTooltipContent,type ChartConfig} from './ui/chart';

type MarketEvent={date:string;title:string;background:string};
type StressRow={peak_date:string;trough_date:string;recovery_date:string|null;mdd:number;underwater_days:number;open:boolean};
type StressData={as_of:string;episodes:StressRow[];events?:MarketEvent[];current:{peak_date:string;drawdown:number;episode_mdd:number;underwater_days:number}};
type Point={id:string;depth:number;days:number;daysScale:number;period:string;depthLabel:string;peakDate:string;troughDate:string;recoveryDate:string|null;kind:'history'|'current';events:MarketEvent[]};

const config:ChartConfig={history:{label:'과거 회복 구간',color:'#9b87b5'},current:{label:'현재 상태',color:'#7c3aed'}};
const pct=(value:number)=>`${(value*100).toFixed(2)}%`;
const yTicks=[0,30,90,180,365,730,1000];

export default function StressChart({stress}:{stress:StressData}){
  const [selected,setSelected]=useState<Point|null>(null);
  const points=useMemo(()=>{
    const withEvents=(start:string,end:string)=>stress.events?.filter(event=>event.date>=start&&event.date<=end)??[];
    const history=stress.episodes.filter(row=>!row.open).map((row,index):Point=>({id:`episode-${index}`,depth:-row.mdd,days:row.underwater_days,daysScale:Math.log1p(row.underwater_days),period:`${row.peak_date} — ${row.recovery_date}`,depthLabel:pct(row.mdd),peakDate:row.peak_date,troughDate:row.trough_date,recoveryDate:row.recovery_date,kind:'history',events:withEvents(row.peak_date,row.recovery_date!)}));
    const currentBase={days:stress.current.underwater_days,daysScale:Math.log1p(stress.current.underwater_days),peakDate:stress.current.peak_date,recoveryDate:null,events:withEvents(stress.current.peak_date,stress.as_of)};
    return {history,current:[
      {...currentBase,id:'current',depth:-stress.current.drawdown,depthLabel:pct(stress.current.drawdown),period:`${stress.current.peak_date} — 기준일`,troughDate:stress.as_of,kind:'current'} as Point,
    ]};
  },[stress]);
  const all=[...points.history,...points.current];
  const maxDepth=Math.max(.2,...all.map(row=>row.depth));
  const xMax=Math.ceil(maxDepth/.1)*.1;
  const maxDays=Math.max(30,...all.map(row=>row.days));
  const ticks=yTicks.filter(value=>value<=maxDays*1.08);
  const select=(point:Point)=>setSelected(point);
  const Dot=(props:any)=>{const point=props.payload as Point;const active=selected?.id===point.id;const current=point.kind==='current';const depthName=current?'현재 낙폭':'최대 하락';return <circle cx={props.cx} cy={props.cy} r={active?8:current?6.5:5} fill={current?'var(--color-current)':'var(--color-history)'} stroke={active?'#fff':current?'#fff':'transparent'} strokeWidth={active?3:current?2:0} className="stress-chart-dot" role="button" tabIndex={0} data-episode-id={point.id} aria-label={`${point.period}, ${depthName} ${point.depthLabel}, ${point.days}일 미회복. 상세 보기`} onClick={()=>select(point)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select(point)}}}/>;};
  return <div className={`stress-explorer${selected?' has-selection':''}`} data-stress-chart>
    <ChartContainer config={config} className="stress-chart-card">
      <div className="stress-chart-canvas"><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:18,right:18,bottom:42,left:8}}>
        <CartesianGrid vertical={false} stroke="#ece7f1"/>
        <XAxis type="number" dataKey="depth" domain={[0,xMax]} tickFormatter={value=>`${Math.round(value*100)}%`} tick={{fill:'#786f82',fontSize:11}} tickLine={false} axisLine={false} label={{value:'하락폭',position:'bottom',offset:22,fill:'#5f566b',fontSize:11}}/>
        <YAxis type="number" dataKey="daysScale" domain={[0,Math.log1p(maxDays)*1.06]} ticks={ticks.map(Math.log1p)} tickFormatter={value=>Math.round(Math.expm1(value)).toLocaleString()} tick={{fill:'#786f82',fontSize:11}} tickLine={false} axisLine={false} width={48} label={{value:'고점 미회복 일수',angle:-90,position:'insideLeft',offset:8,fill:'#5f566b',fontSize:11}}/>
        <ZAxis range={[50,50]}/><ReferenceLine x={.1} stroke="#b8a7cc" strokeDasharray="4 4" label={{value:'10%',position:'insideTopRight',fill:'#887a96',fontSize:10}}/><ReferenceLine y={Math.log1p(30)} stroke="#b8a7cc" strokeDasharray="4 4" label={{value:'30일',position:'insideTopLeft',fill:'#887a96',fontSize:10}}/>
        <Tooltip content={<ChartTooltipContent/>} cursor={false} offset={12} isAnimationActive={false} wrapperStyle={{transition:'none',pointerEvents:'none'}}/><Scatter name="과거 회복 구간" data={points.history} shape={<Dot/>}/><Scatter name="현재 상태" data={points.current} shape={<Dot/>}/>
      </ScatterChart></ResponsiveContainer></div>
      <div className="stress-chart-foot"><span><i className="history"/>과거 회복 구간</span><span><i className="current"/>현재 상태</span><small>긴 기간은 간격만 압축해 표시합니다.</small></div>
    </ChartContainer>
    {selected&&<aside className="stress-detail-panel" aria-live="polite"><button type="button" className="stress-detail-close" aria-label="상세 닫기" onClick={()=>setSelected(null)}>×</button><span className="status-pill">{selected.kind==='history'?'과거 회복 구간':'현재 상태'}</span><h3>{selected.period}</h3><dl><div><dt>{selected.kind==='history'?'최대 하락':'현재 낙폭'}</dt><dd>{selected.depthLabel}</dd></div><div><dt>고점 미회복</dt><dd>{selected.days.toLocaleString()}일</dd></div><div><dt>{selected.kind==='history'?'저점':'기준일'}</dt><dd>{selected.troughDate}</dd></div></dl><div className="stress-event-list"><h4>이 기간의 주요 시장 악재</h4>{selected.events.length?selected.events.map(event=><article key={`${selected.id}-${event.date}`}><time>{event.date}</time><strong>{event.title}</strong><p>{event.background}</p></article>):<p className="stress-event-empty">저장된 주요 시장 사건과 겹치는 기록이 없습니다.</p>}</div><p className="stress-detail-note">사건의 대표 날짜가 이 하락 구간에 포함될 때 연결합니다.</p></aside>}
  </div>;
}
