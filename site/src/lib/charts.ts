import {base,label,money,pct} from './format';
// Plotly is loaded once and only when a chart reaches the viewport.
let ready:Promise<any>;
function plotly(){return ready ||= new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=base+'vendor/plotly.min.js';s.onload=()=>resolve((window as any).Plotly);s.onerror=()=>reject(new Error('차트 라이브러리를 불러오지 못했습니다. 새로고침해 주세요.'));document.head.appendChild(s)})}
const colors=['#FF9100','#00C853','#D500F9','#FF1744','#AA00FF','#FFD600'];
async function json(path:string){const r=await fetch(path);if(!r.ok)throw new Error('차트 데이터를 불러오지 못했습니다.');return r.json()}
const esc=(s:any)=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
async function mount(root:HTMLElement){
 const canvas=root.querySelector('.chart-canvas') as HTMLElement,status=root.querySelector('.chart-status')!,metrics=root.querySelector('.chart-metrics')!;
 const periods=JSON.parse(root.dataset.periods||'null');
 const mode=root.querySelector('.metric-picker') as HTMLSelectElement,comparison=root.querySelector('.comparison-picker') as HTMLSelectElement;
 const picker=root.querySelector('.period-picker') as HTMLSelectElement;
 if(comparison&&!periods)comparison.value='independent';
 let source=root.dataset.source!,payload:any,P:any,figure:any,serial=0;
 async function render(){
  const generation=++serial;
  try{
   status.textContent='';P=await plotly();const next=await json(source);if(generation!==serial)return;payload=next;
   let traces:any[]=[], shapes:any[]=[],annotations:any[]=[],layout:any;
   if(payload.analysis==='regimes'){
    root.querySelector<HTMLElement>('.chart-controls')!.hidden=true;
    root.querySelector('.chart-note')!.textContent='각 점은 하나의 변동성 유지 구간입니다. 구간 길이가 다르며 포트폴리오 수익률이 아닙니다. 실제·합성 구간을 범례에서 선택할 수 있습니다.';
    let colorIndex=0;
    const groups=[...new Set(payload.rows.map((r:any)=>r.data_origin+' / '+r.band))];
    traces=groups.map((g:any)=>{const rows=payload.rows.filter((r:any)=>r.data_origin+' / '+r.band===g);return {type:'scatter',mode:'markers',name:g,x:rows.map((r:any)=>r.signal_end),y:rows.map((r:any)=>r.tqqq_return),text:rows.map((r:any)=>`${r.signal_start} ~ ${r.signal_end}<br>${r.trading_days}거래일 · ${r.band}`),marker:{color:colors[colorIndex++%colors.length],size:7},hovertemplate:'%{text}<br>구간 등락률 %{y:.4%}<extra>%{fullData.name}</extra>',visible:g.startsWith('actual')?true:'legendonly'}});
    layout={yaxis:{title:{text:'기초자산 구간 등락률'},tickformat:'.0%',showgrid:false}};
   }else{
    const filter=comparison?.value;
    let curves=payload.curves.filter((c:any)=>filter==='independent'?(payload.independent_models||payload.curves.map((v:any)=>v.model)).includes(c.model):true);
    if(!curves.length)curves=payload.curves;
    let n=0;
    traces=curves.map((c:any)=>{let peak=-Infinity;const y=mode.value==='drawdown'?c.equity.map((v:number)=>{peak=Math.max(peak,v);return v/peak-1}):c.equity;
     const color=c.display_color|| (c.model==='tqqq_hold'?'#2979FF':c.model==='qqq_hold'?'#40C4FF':colors[n++%colors.length]);
     return {x:c.dates,y,name:c.display_name||label(c.model),type:'scatter',mode:'lines',line:{color,width:.5,simplify:false},hovertemplate:'%{x}<br>%{y:.8g}<extra>%{fullData.name}</extra>'};});
    const allDates=curves.flatMap((c:any)=>[c.dates[0],c.dates.at(-1)]).sort();
    const events=(payload.events||[]).filter((e:any)=>e.date>=allDates[0]&&e.date<=allDates.at(-1));
    shapes=events.map((e:any)=>({type:'line',x0:e.date,x1:e.date,y0:0,y1:1,yref:'paper',layer:'below',opacity:.8,line:{color:'#78909C',width:.5,dash:'dot'}}));
    annotations=events.map((e:any,i:number)=>({x:e.date,y:.03+.065*(i%3),yref:'paper',text:e.title,hovertext:e.background,showarrow:false,textangle:-90,font:{color:'#607d8b',size:12},xanchor:'right',yanchor:'bottom'}));
    layout={yaxis:{type:mode.value==='drawdown'?'linear':'log',title:{text:mode.value==='drawdown'?'고점 대비 낙폭':'포트폴리오 가치 · 달러'},tickformat:mode.value==='drawdown'?'.0%':undefined,showgrid:false}};
    metrics.innerHTML='<table><caption>선택한 평가 기간의 성과 · 확대와 무관</caption><thead><tr><th>모델</th><th>평가 기간</th><th>연평균 복리수익률</th><th>최대 낙폭</th><th>최장 미회복</th><th>최종 자산</th></tr></thead><tbody>'+curves.map((c:any)=>{const m=c.metrics||{};return `<tr><th>${esc(c.display_name||label(c.model))}</th><td>${esc(m.start)} ~ ${esc(m.end)}</td><td>${esc(pct(m.cagr))}</td><td>${esc(pct(m.mdd))}</td><td>${m.longest_time_underwater_days==null?'—':esc(m.longest_time_underwater_days)+'일'}</td><td>${m.end_equity==null?'—':esc(money(m.end_equity))}</td></tr>`}).join('')+'</tbody></table>';
   }
   const narrow=window.innerWidth<600;
   layout={...layout,autosize:true,height:narrow?420:500,margin:{l:65,r:25,t:20,b:90},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'system-ui, sans-serif',size:12,color:'#28342f'},xaxis:{showgrid:false,dtick:'M12',tickformat:'%Y',rangeslider:{visible:false}},legend:{orientation:'h',y:-.15,font:{size:12}},hovermode:'x unified',shapes,annotations};
   figure={traces,layout};canvas.innerHTML='';await P.newPlot(canvas,traces,layout,{responsive:true,scrollZoom:false,displaylogo:false,toImageButtonOptions:{format:'png',width:2880,height:1440,scale:1}});
  }catch(e){status.textContent=String(e);canvas.innerHTML='';}
 }
 picker?.addEventListener('change',()=>{source=base+periods.find((p:any)=>p.id===picker.value).file;render()});
 mode?.addEventListener('change',render);comparison?.addEventListener('change',render);
 root.querySelector('.download-chart')?.addEventListener('click',async event=>{
  event.preventDefault();if(!figure)return;
  const script=await (await fetch(base+'vendor/plotly.min.js')).text();
  const spec=JSON.stringify(figure).replace(/</g,'\\u003c');
  const blob=new Blob([`<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>투자 연구 차트</title><body><p>데이터 기준: ${esc(payload.curves?.[0]?.dates.at(-1)||payload.dates?.at(-1)||payload.rows?.at(-1)?.signal_end)} · 저장 당시 선택한 계열과 평가 기간</p><div id="chart"></div><script>${script.replace(/<\/script/gi,'<\\/script')}</script><script>const f=${spec};Plotly.newPlot('chart',f.traces,f.layout,{responsive:true,displaylogo:false});</script></body></html>`],{type:'text/html'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='investment-chart.html';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
 });
 await render();
 let lastWidth=canvas.clientWidth;new ResizeObserver(()=>{if(P&&canvas.clientWidth!==lastWidth){lastWidth=canvas.clientWidth;P.Plots.resize(canvas)}}).observe(canvas);
}
const observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){observer.unobserve(e.target);mount(e.target as HTMLElement)}},{rootMargin:'300px'});
document.querySelectorAll<HTMLElement>('[data-chart]').forEach(root=>observer.observe(root));
