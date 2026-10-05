import {esc,label,pct} from './format';

type Row={model:string;display_name?:string;year:number;start:string;end:string;total_return:number;mdd:number;partial:boolean};

document.querySelectorAll<HTMLElement>('[data-yearly]').forEach(async root=>{
 const note=root.querySelector<HTMLElement>('.yearly-note')!;
 const empty=root.querySelector<HTMLElement>('.yearly-empty')!;
 try{
  const payload=await fetch(root.dataset.yearly!).then(response=>{if(!response.ok)throw new Error(`${response.status}`);return response.json()});
  const rows:Row[]=payload.rows||[];
  note.textContent=payload.note||'';
  if(!rows.length){empty.hidden=false;empty.textContent='이 분석에서는 연도별 값을 표시할 수 없습니다.';return}
  const controls=root.querySelector<HTMLElement>('.yearly-controls')!;
  const model=root.querySelector<HTMLSelectElement>('.yearly-model')!;
  const start=root.querySelector<HTMLSelectElement>('.yearly-start')!;
  const models=[...new Set(rows.map(row=>row.model))];
  const modelName=(name:string)=>rows.find(row=>row.model===name)?.display_name||label(name);
  model.innerHTML=models.map(name=>`<option value="${esc(name)}">${esc(modelName(name))}</option>`).join('');
  model.value=models.includes('vo')?'vo':models[0];
  const years=[...new Set(rows.map(row=>row.year))].sort((a,b)=>a-b);
  const recent=Math.max(years[0],years.at(-1)!-9);
  start.innerHTML=`<option value="${recent}">최근 10개 연도</option><option value="${years[0]}">전체 · ${years[0]}년부터</option>`+years.filter(year=>year!==recent&&year!==years[0]).map(year=>`<option value="${year}">${year}년부터</option>`).join('');
  start.value=String(recent);controls.hidden=false;
  const render=()=>{
   const selected=rows.filter(row=>row.model===model.value&&row.year>=Number(start.value));
   const returnMax=Math.max(...selected.map(row=>Math.abs(row.total_return)),.01);
   const mddMax=Math.max(...selected.map(row=>Math.abs(row.mdd)),.01);
   root.querySelector<HTMLElement>('.yearly-bars')!.innerHTML=selected.map(row=>`<article class="yearly-row">
    <strong>${row.year}${row.partial?'*':''}</strong>
    <div class="yearly-measure"><span>수익률</span><div class="yearly-track"><i class="${row.total_return>=0?'positive':'negative'}" style="width:${Math.abs(row.total_return)/returnMax*100}%"></i></div><b>${pct(row.total_return)}</b></div>
    <div class="yearly-measure"><span>연중 MDD</span><div class="yearly-track"><i class="drawdown" style="width:${Math.abs(row.mdd)/mddMax*100}%"></i></div><b>${pct(row.mdd)}</b></div>
   </article>`).join('');
   root.querySelector<HTMLElement>('.yearly-table')!.innerHTML=`<table><caption>${esc(modelName(model.value))} · 연도별 정확한 값</caption><thead><tr><th>연도</th><th>평가 시작</th><th>평가 종료</th><th>수익률</th><th>연중 MDD</th></tr></thead><tbody>${selected.map(row=>`<tr><th>${row.year}${row.partial?'*':''}</th><td>${row.start}</td><td>${row.end}</td><td>${pct(row.total_return)}</td><td>${pct(row.mdd)}</td></tr>`).join('')}</tbody></table>`;
   const qualifier=selected.some(row=>row.partial)?' *는 1년 전체가 아닌 부분 연도입니다.':'';
   root.querySelector<HTMLElement>('.yearly-bars')!.setAttribute('aria-label',`${modelName(model.value)} ${selected[0].year}년부터 ${selected.at(-1)!.year}년까지 연도별 수익률과 최대 낙폭.${qualifier}`);
  };
  model.addEventListener('change',render);start.addEventListener('change',render);render();
 }catch(error){empty.hidden=false;empty.textContent=`연도별 결과를 불러오지 못했습니다. (${error})`}
});
