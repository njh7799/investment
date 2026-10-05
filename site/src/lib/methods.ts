import {url,feeNote,originNote} from './format';

export function methodInfo(s:any){
 const usesTqqq=!(s.category.includes('다중자산')||s.id==='jordan-public');
 const role=s.id==='volatility-allocation'?'현재 기본 방법':s.id==='tqqq-buy-hold'?'비교 기준':s.category==='VO 확장'?'VO 추가·대체 규칙':usesTqqq?'TQQQ 운용 전략':'다중자산 참고 전략';
 const status=s.status==='실행 실패'?'재현 실패':s.status==='추가 검증 대기'?'추가 검증 대기':'과거 데이터 평가';
 const verdict=s.status==='미채택'?'기본 방법에 미채택':s.status==='실행 실패'?'성과 미생성':s.status==='추가 검증 대기'?'보류':s.id==='volatility-allocation'?'현재 기본값 유지':s.id==='tqqq-buy-hold'?'비교용 기준선':s.status==='독립 전략'?'별도 규칙으로 보존':'참고 결과로 보존';
 const m=s.metrics,rows=s.result_rows||[];
 const start=m?.start||rows[0]?.start,end=m?.end||rows[0]?.end;
 return {usesTqqq,role,status,verdict,start,end,fee:feeNote(s.batch),origin:start&&end?originNote(start,end,usesTqqq):'성과 미생성'};
}
export function resultLink(s:any){
 if(s.status==='실행 실패')return url(`research/${s.batch}/#failure`);
 const m=s.metrics;
 const query=new URLSearchParams({table:s.batch==='vo-sgov'?'summary':'period-summary'});
 if(m?.period)query.set('period',m.period);
 if(m?.model||m?.scenario)query.set('model',m.model||m.scenario);
 return url(`research/${s.batch}/?${query}#results`);
}
export function compareLink(s:any){
 const query=new URLSearchParams({study:s.batch});
 const m=s.metrics;
 if(m){
  query.set('cohort',JSON.stringify([m.period||'',m.start,m.end,m.start_equity]));
  query.set('models',(s.batch==='vo-sgov'?['VO cash','VO SGOV']:s.peers||[m.model,'vo','tqqq_hold']).filter(Boolean).slice(0,3).join(','));
 }
 return url(`compare/?${query}`);
}
