export const base = '/investment/';
export const url = (value='') => base+value.replace(/^\//,'');
export const pct = (value:number|null) => value==null?'—':`${(value*100).toFixed(2)}%`;
export const money = (value:number) => '$'+(Math.trunc(value*100)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const names:Record<string,string>={vo:'VO · 변동성 배분',three_percent:'IXIC 3% 규칙',vr5:'VR 5.0 · 가치 리밸런싱',tqqq_hold:'TQQQ 단순 보유',qqq_hold:'QQQ 단순 보유',faber_10m:'Faber 10개월 이동평균',sma_200:'200일 이동평균',golden_cross:'골든크로스 · 50/200일',absolute_momentum_12m:'12개월 절대모멘텀 · 0% 비교',tsmom_12m:'12개월 시계열 모멘텀 · 주식/현금',turtle_55_20:'터틀 · 55/20일 돌파',halloween:'핼러윈 계절성',turn_of_month:'월말·월초 효과',macd:'MACD · 12/26/9',rsi2:'RSI(2) · 단기 평균회귀',faa_default:'FAA · 수익·위험·상관 배분',faa7_equal_monthly:'7자산 월별 동일비중',permanent_band:'Permanent Portfolio · 15/35 밴드',permanent_annual_equal:'연례 동일비중',permanent_buyhold:'초기 동일비중 보유',paa2:'PAA2 · 방어 자산배분',gem:'GEM · 글로벌 주식 모멘텀',gtaa5:'GTAA · 5자산 추세 배분',vaa_g4:'VAA-G4 · 빠른 방어',daa_g12:'DAA-G12 · 카나리 방어',jordan_public_proxy:'조던 -3% · QQQ/TLT 공개형 프록시','VO cash':'VO · 현금','VO 현금':'VO · 현금','VO SGOV':'VO · 현금 대신 SGOV'};
export const label = (name:string) => names[name]||name;
export const periods:Record<string,string>={actual_tqqq:'실제 TQQQ 구간',actual_tqqq_full:'실제 TQQQ 구간',synthetic_full:'합성 포함 전체',full_synthetic:'합성 포함 전체',common_full:'공통 데이터 전체',recent_10y:'최근 10년',full_pre2026:'합성 포함 · 2025년까지',actual_pre2026:'실제 TQQQ · 2025년까지',decade_2016_2025:'2016–2025년',full_current:'합성 포함 · 연구 기준일까지',actual_current:'실제 TQQQ · 연구 기준일까지','2026_ytd':'2026년 YTD'};
export const defaultPeriod=(available:Set<string>)=>['full_synthetic','synthetic_full','full_current','full_pre2026','actual_tqqq','actual_tqqq_full','actual_current','actual_pre2026','common_full'].find(p=>available.has(p))||'';
export const esc=(v:any)=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export const feeNote=(study:string)=>study==='vo-sgov'?'매수·매도 각각 0.1% · $10 이하 주문 무료 · 수수료 센트 미만 절사':'매수·매도 각각 0.1%';
export const originNote=(start:string,end:string,tqqq=true)=>!tqqq?'실제 자산 데이터 · 공통 가용 구간':end<'2010-02-11'?'QQQ 기반 TQQQ 합성 구간':start<'2010-02-11'?'합성+실제 · 2010-02-11 이전 TQQQ는 합성':'실제 TQQQ 구간';

export const judgmentLabels:Record<string,string>={'미채택':'기본 방법에 미채택','외부 참고':'참고 결과로 보존','실행 실패':'재현 실패 · 성과 미생성','추가 검증 대기':'판단 보류','연구 기록':'참고 결과로 보존'};
