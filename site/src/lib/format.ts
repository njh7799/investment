export const base = '/investment/';
export const url = (value='') => base+value.replace(/^\//,'');
export const pct = (value:number|null) => value==null?'—':`${(value*100).toFixed(2)}%`;
export const money = (value:number) => '$'+(Math.trunc(value*100)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
export const label = (name:string) => ({vo:'VO · 변동성 배분',three_percent:'IXIC 3% · 10구간',vr5:'VR 5.0 거치식',tqqq_hold:'TQQQ 단순 보유',qqq_hold:'QQQ 단순 보유',faa_default:'FAA 기본형',faa7_equal_monthly:'7자산 월별 동일비중',permanent_band:'Permanent 15/35',permanent_annual_equal:'연례 동일비중',permanent_buyhold:'초기 동일비중 보유',paa2:'PAA2',gem:'GEM',gtaa5:'GTAA 5',vaa_g4:'VAA-G4',daa_g12:'DAA-G12'}[name]||name);
