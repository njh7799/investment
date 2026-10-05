import {label,money,pct} from './format';
const titles:Record<string,string>={'period-summary':'고정 기간 성과','rolling-summary':'롤링 기간 성과','stress-summary':'위기 구간 성과','fee-summary':'비용 민감도','annual-summary':'연도별 성과',variants:'전체 변형 규칙','screening-summary':'후보 선별 결과','promotion-audit':'승격 검증',summary:'요약',regimes:'모든 변동성 구간','yearly_returns':'연도별 수익률','cash_equity':'VO 현금 일별 자산','sgov_equity':'VO SGOV 일별 자산'};
const headers:Record<string,string>={model:'모델',period:'평가 구간',start:'시작일',end:'종료일',start_equity:'초기자산',end_equity:'최종자산',total_return:'총수익률',cagr:'연평균 복리수익률',mdd:'최대 낙폭',trade_count:'리밸런싱 일수',annual_trades:'연평균 리밸런싱',fees:'수수료',longest_time_underwater_days:'최장 미회복 일수',recovery_period_days:'저점 이후 회복 일수',recovery_date:'회복일',mdd_peak:'고점일',mdd_trough:'저점일',drawdown_duration_days:'고점→저점 일수',mdd_time_underwater_days:'최대 낙폭 미회복 일수',fee_rate:'편도 수수료율',window_years:'롤링 연수',median_cagr:'CAGR 중앙값',worst_cagr:'최저 CAGR',worst_mdd:'최악 낙폭',year:'연도',name:'변형 이름',family:'규칙 계열',scenario:'시나리오'};
const periods:Record<string,string>={actual_tqqq:'실제 TQQQ 전체',actual_tqqq_full:'실제 TQQQ 전체',synthetic_full:'합성 포함 전체',full_synthetic:'합성 포함 전체',common_full:'공통 데이터 전체',recent_10y:'최근 10년',full_pre2026:'합성 포함 · 2025년까지',actual_pre2026:'실제 TQQQ · 2025년까지',decade_2016_2025:'2016–2025년',full_current:'합성 포함 · 연구 기준일까지',actual_current:'실제 TQQQ · 연구 기준일까지','2026_ytd':'2026년 YTD'};
const coreColumns=['period','model','scenario','start','end','cagr','mdd','longest_time_underwater_days','annual_trades'];
const esc=(v:any)=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
type Table={name:string;columns:string[];rows:Record<string,any>[]};
function display(key:string,value:any){
  if(value==null)return '—';
  if(typeof value!=='number')return key==='model'?label(value):key==='period'?(periods[value]||value):String(value);
  if(key==='annual_trades')return value.toFixed(2);
  if(/equity|fees/.test(key))return money(value);
  if(/cagr|mdd$|return|fee_rate|win_rate/.test(key))return pct(value);
  return Number.isInteger(value)?String(value):String(Math.trunc(value*1e8)/1e8);
}
document.querySelectorAll<HTMLElement>('[data-tables]').forEach(root=>{
  let tables:Table[],table:Table,page=0,sort='',ascending=true;
  const kind=root.querySelector<HTMLSelectElement>('.table-kind')!;
  const period=root.querySelector<HTMLSelectElement>('.table-period')!;
  const columnMode=root.querySelector<HTMLSelectElement>('.column-mode')!;
  const search=root.querySelector<HTMLInputElement>('.table-search')!;
  const sorter=root.querySelector<HTMLSelectElement>('.table-sort')!;
  const prev=root.querySelector<HTMLButtonElement>('.prev')!;
  const next=root.querySelector<HTMLButtonElement>('.next')!;
  function draw(){
    if(!table)return;
    const columns=columnMode.value==='key'&&table.columns.includes('cagr')&&table.columns.includes('mdd')?coreColumns.filter(c=>table.columns.includes(c)):table.columns;
    const records=table.rows.filter(r=>(!period.value||r.period===period.value)&&Object.values(r).join(' ').toLowerCase().includes(search.value.trim().toLowerCase()));
    if(sort)records.sort((a,b)=>{
      if(a[sort]==null)return 1;if(b[sort]==null)return -1;
      return (typeof a[sort]==='number'?a[sort]-b[sort]:String(a[sort]).localeCompare(String(b[sort])))*(ascending?1:-1);
    });
    const total=Math.max(1,Math.ceil(records.length/25));page=Math.min(page,total-1);
    root.querySelector('.data-table')!.innerHTML='<table><thead><tr>'+columns.map(c=>`<th title="${esc(c)}">${esc(headers[c]||c)}</th>`).join('')+'</tr></thead><tbody>'+records.slice(page*25,(page+1)*25).map(row=>'<tr>'+columns.map(c=>`<td${c==='model'||c==='name'?' class="model-name"':''}>${esc(display(c,row[c]))}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
    root.querySelector('.table-count')!.textContent=`${records.length}행 · ${page+1} / ${total}`;
    prev.disabled=page===0;next.disabled=page===total-1;
    root.querySelector('.table-description')!.textContent=`${titles[table.name]||table.name} · 원본 CSV 기준. 빈 회복일은 미회복 또는 해당 없음입니다.`;
  }
  function choose(){
    table=tables.find(t=>t.name===kind.value)!;sort='';page=0;
    period.innerHTML='<option value="">전체 구간</option>'+[...new Set<string>(table.rows.map(r=>r.period).filter(Boolean))].map(p=>`<option value="${esc(p)}">${esc(periods[p]||p)}</option>`).join('');
    const available=new Set(table.rows.map(r=>r.period));
    period.value=['actual_tqqq','actual_tqqq_full','actual_current','common_full'].find(p=>available.has(p))||'';
    root.querySelector<HTMLElement>('.period-filter-label')!.hidden=!table.columns.includes('period');
    sorter.innerHTML='<option value="">원본 순서</option>'+table.columns.map(c=>`<option value="${esc(c)}">${esc(headers[c]||c)}</option>`).join('');
    draw();
  }
  kind.addEventListener('change',choose);
  period.addEventListener('change',()=>{page=0;draw()});
  columnMode.addEventListener('change',draw);
  search.addEventListener('input',()=>{page=0;draw()});
  sorter.addEventListener('change',()=>{sort=sorter.value;page=0;draw()});
  root.querySelector('.sort-order')!.addEventListener('click',e=>{ascending=!ascending;(e.target as HTMLElement).textContent=ascending?'오름차순 ↑':'내림차순 ↓';draw()});
  prev.addEventListener('click',()=>{page--;draw()});next.addEventListener('click',()=>{page++;draw()});
  fetch(root.dataset.tables!).then(r=>{if(!r.ok)throw Error('결과 파일을 불러오지 못했습니다.');return r.json()}).then((items:Table[])=>{
    tables=items;if(!tables.length){root.hidden=true;return}
    tables.sort((a,b)=>a.name==='period-summary'?-1:b.name==='period-summary'?1:0);
    kind.innerHTML=tables.map(t=>`<option value="${t.name}">${titles[t.name]||t.name} (${t.rows.length}행)</option>`).join('');choose();
  }).catch(e=>root.querySelector('.table-error')!.textContent=String(e));
});
