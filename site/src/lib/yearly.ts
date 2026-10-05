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
  const requestedModel=root.dataset.yearlyModel;
  const availableRows=requestedModel?rows.filter(row=>row.model===requestedModel):rows;
  if(!availableRows.length){empty.hidden=false;empty.textContent='이 방법의 연도별 값을 표시할 수 없습니다.';return}
  const controls=root.querySelector<HTMLElement>('.yearly-controls')!;
  const model=root.querySelector<HTMLSelectElement>('.yearly-model')!;
  const toggle=root.querySelector<HTMLButtonElement>('.yearly-range-toggle')!;
  const models=[...new Set(availableRows.map(row=>row.model))];
  const modelName=(name:string)=>availableRows.find(row=>row.model===name)?.display_name||label(name);
  model.innerHTML=models.map(name=>`<option value="${esc(name)}">${esc(modelName(name))}</option>`).join('');
  model.value=models.includes('vo')?'vo':models[0];
  let expanded=false;
  const render=()=>{
   const modelRows=availableRows.filter(row=>row.model===model.value).sort((a,b)=>b.year-a.year);
   const selected=expanded?modelRows:modelRows.slice(0,10);
   const returnMax=Math.max(...selected.map(row=>Math.abs(row.total_return)),.01);
   const mddMax=Math.max(...selected.map(row=>Math.abs(row.mdd)),.01);
   root.querySelector<HTMLElement>('.yearly-bars')!.innerHTML=selected.map(row=>`<article class="yearly-row">
    <strong>${row.year}${row.partial?'*':''}</strong>
    <div class="yearly-measure"><span>수익률</span><div class="yearly-track"><i class="${row.total_return>=0?'positive':'negative'}" style="width:${Math.abs(row.total_return)/returnMax*50}%"></i></div><b>${pct(row.total_return)}</b></div>
    <div class="yearly-measure"><span>연중 MDD</span><div class="yearly-track"><i class="drawdown negative" style="width:${Math.abs(row.mdd)/mddMax*50}%"></i></div><b>${pct(row.mdd)}</b></div>
   </article>`).join('');
   toggle.hidden=modelRows.length<=10;
   toggle.innerHTML=expanded?'최근 10년만 보기 <span aria-hidden="true">↑</span>':'전체 보기 <span aria-hidden="true">↓</span>';
   toggle.setAttribute('aria-expanded',String(expanded));
   controls.hidden=models.length===1;
   const qualifier=selected.some(row=>row.partial)?' *는 1년 전체가 아닌 부분 연도입니다.':'';
   root.querySelector<HTMLElement>('.yearly-bars')!.setAttribute('aria-label',`${modelName(model.value)} ${selected.at(-1)!.year}년부터 ${selected[0].year}년까지 연도별 수익률과 최대 낙폭.${qualifier}`);
  };
  model.addEventListener('change',()=>{expanded=false;render()});
  toggle.addEventListener('click',()=>{expanded=!expanded;render()});
  render();
 }catch(error){empty.hidden=false;empty.textContent=`연도별 결과를 불러오지 못했습니다. (${error})`}
});
