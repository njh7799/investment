import {url,label,pct,money,esc,periods,defaultPeriod} from './format';
const study=document.querySelector<HTMLSelectElement>('#compare-study')!;
const period=document.querySelector<HTMLSelectElement>('#compare-period')!;
const pickers=[...document.querySelectorAll<HTMLSelectElement>('.compare-model')];
const result=document.querySelector('#compare-results')!,status=document.querySelector('#compare-status')!;
let groups:Map<string,any[]>=new Map(),generation=0;
const params=new URLSearchParams(location.search);
if([...study.options].some(o=>o.value===params.get('study')))study.value=params.get('study')!;
const key=(r:any)=>JSON.stringify([r.period||'',r.start,r.end,r.start_equity]);
const model=(r:any)=>r.model||r.scenario;
function draw(){
 const rows=groups.get(period.value)||[];
 const chosen=[...new Set(pickers.map(p=>p.value).filter(Boolean))].map(id=>rows.find(r=>model(r)===id)).filter(Boolean);
 const u=new URL(location.href);u.searchParams.set('study',study.value);u.searchParams.set('cohort',period.value);u.searchParams.set('models',chosen.map(model).join(','));history.replaceState(null,'',u);
 status.textContent=chosen.length<2?'비교할 방법을 두 개 이상 선택하세요.':`${chosen.length}개 방법 · 동일 조건 비교`;
 const baseline=chosen[0];
 result.innerHTML=chosen.map(r=>`<article class="paper"><h2>${esc(label(model(r)))}</h2><dl><dt>연평균 복리수익률</dt><dd>${pct(r.cagr)} <small>${r===baseline?'기준':(r.cagr-baseline.cagr>=0?'+':'')+((r.cagr-baseline.cagr)*100).toFixed(2)+'%p'}</small></dd><dt>최대 낙폭</dt><dd>${pct(r.mdd)}</dd><dt>최장 미회복</dt><dd>${esc(r.longest_time_underwater_days)}일</dd><dt>연평균 리밸런싱</dt><dd>${Number(r.annual_trades).toFixed(2)}회</dd><dt>최종 자산</dt><dd>${money(r.end_equity)}</dd></dl></article>`).join('');
 const r=rows[0];
 document.querySelector('#compare-conditions')!.textContent=r?`${r.start} — ${r.end} · ${periods[r.period]||'공통 가용 구간'} · 초기 ${money(r.start_equity)} · ${study.selectedOptions[0].dataset.fee} · 세금·슬리피지 0. ${r.start<'2010-02-11'?'이 기간의 TQQQ 비교에는 2010-02-11 이전 QQQ 기반 합성이 포함됩니다.':''}`:'';
 (document.querySelector('#compare-source') as HTMLAnchorElement).href=url(`research/${study.value}/?table=${study.value==='vo-sgov'?'summary':'period-summary'}${r?.period?'&period='+encodeURIComponent(r.period):''}#results`);
}
function choose(wanted?:string[]){
 const rows=groups.get(period.value)||[];
 const old=wanted||pickers.map(p=>p.value),used=new Set<string>();
 pickers.forEach((p,i)=>{p.innerHTML='<option value="">선택 안 함</option>'+rows.map(r=>`<option value="${esc(model(r))}">${esc(label(model(r)))}</option>`).join('');const preferred=old[i];p.value=rows.some(r=>model(r)===preferred)&&!used.has(preferred)?preferred:(i<2?model(rows.find(r=>!used.has(model(r)))||{})||'':'');if(p.value)used.add(p.value)});draw();
}
async function load(initial=false){
 const ticket=++generation;result.innerHTML='';status.textContent='결과를 불러오는 중입니다…';pickers.forEach(p=>p.disabled=true);period.disabled=true;
 try{const response=await fetch(url(`data/${study.value}-tables.json`));if(!response.ok)throw Error('결과를 불러오지 못했습니다.');const tables=await response.json();if(ticket!==generation)return;
 const table=tables.find((t:any)=>t.name===(study.value==='vo-sgov'?'summary':'period-summary'));
 groups=new Map();for(const r of table.rows){if(r.cagr==null||r.mdd==null)continue;const id=key(r);groups.set(id,[...(groups.get(id)||[]),r])}
 groups=new Map([...groups].filter(([,rows])=>rows.length>=2));
 period.innerHTML=[...groups].map(([id,rows])=>`<option value="${esc(id)}">${esc(periods[rows[0].period]||'공통 가용 구간')} · ${rows[0].start} — ${rows[0].end}</option>`).join('');
 const preferred=defaultPeriod(new Set([...groups.values()].map(rows=>rows[0].period)));
 period.value=(initial&&groups.has(params.get('cohort')||''))?params.get('cohort')!:[...groups].find(([,rows])=>rows[0].period===preferred)?.[0]||[...groups.keys()][0]||'';
 if(!groups.size){status.textContent='동일 조건으로 비교할 두 개 이상의 저장된 결과가 없습니다.';return}
 period.disabled=false;pickers.forEach(p=>p.disabled=false);
 choose(initial&&params.has('models')?params.get('models')!.split(','):study.value==='vo-sgov'?['VO cash','VO SGOV']:['vo','tqqq_hold','vr5']);
 }catch(e){status.textContent=String(e)}
}
period.addEventListener('change',()=>choose());study.addEventListener('change',()=>load());pickers.forEach(p=>p.addEventListener('change',draw));load(true);
