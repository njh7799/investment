import {data,url} from './content';
import {defaultProfileFor,modelForProfile,type ProfileStrategy} from './profiles';

type ProfileRule={
 id:string;
 title:string;
 description:string;
 core?:boolean;
};

export type StrategyProfileConfig={
 kind:'vo'|'ixic';
 strategy:ProfileStrategy;
 initialProfile:string;
 controlTitle:string;
 badge:string;
 pageSummary:string;
 heading:string;
 marketDate:string;
 yearlyStudy:{yearly:string};
 stressProfiles:Record<string,unknown>;
 downloads:Array<{href:string;label:string}>;
 historicalLabel:string;
 addons:any[];
 profiles:any[];
 rules:ProfileRule[];
};

const metrics=(period:any,model:string)=>period?.metrics.find((metric:any)=>metric.model===model);
const resultProfile=(strategy:ProfileStrategy,id:string,full:any,recent:any,labels:Record<string,string>)=>{
 const model=modelForProfile(strategy,id);
 return {id,model,...labels,full:metrics(full,model),recent:metrics(recent,model)};
};

function voConfig():StrategyProfileConfig{
 const comparison=data.comparison;
 const full=comparison.periods.find((period:any)=>period.id==='full');
 const recent=comparison.periods.find((period:any)=>period.id==='recent-10y');
 const strategy='volatility-allocation';
 return {
  kind:'vo',
  strategy,
  initialProfile:defaultProfileFor(strategy),
  controlTitle:'VO',
  badge:'addon ON',
  pageSummary:'현재 운용 프로필은 기본 VO에 5/20 상향돌파·고변동성 구간당 1회 addon을 활성화합니다. 오른쪽 아래 ADDON 버튼으로 기본 VO와 즉시 비교할 수 있습니다.',
  heading:'현재 운용 프로필',
  marketDate:comparison.market_date,
  yearlyStudy:{yearly:comparison.yearly},
  stressProfiles:comparison.stress_profiles,
  downloads:[
   {href:url('research/batch-15/#results'),label:'addon 연구 결과'},
   {href:'#addon-one-shot-sma-reentry',label:'정확한 addon 규칙'},
  ],
  historicalLabel:'기본 VO 선정 당시 결과 보기',
  addons:[{
   id:'sma_5_20',
   anchor:'one-shot-sma-reentry',
   label:'5/20 돌파 · 구간당 1회',
   default:true,
   source:'docs/strategies/volatility-allocation/addons/one-shot-sma-reentry.md',
  }],
  profiles:[
   resultProfile(strategy,'addon',full,recent,{
    label:'VO + 5/20 addon 활성화',
    yearlyLabel:'VO + addon',
   }),
   resultProfile(strategy,'core',full,recent,{
    label:'기본 VO · addon 비활성화',
    yearlyLabel:'기본 VO',
   }),
  ],
  rules:[
   {
    id:'addon',
    title:'활성 addon',
    description:'VO 목표가 100% 미만일 때 TQQQ 5일선이 20일선을 새로 상향돌파하면 구간당 한 번, 다음 시가에 목표를 50%p 높입니다. 실제 매수가보다 종가가 낮아지면 addon 비중만 다음 시가에 제거합니다.',
   },
   {
    id:'core',
    title:'addon 비활성화',
    description:'30일 변동성만으로 100%·50%·0% 목표를 정하는 기본 VO를 표시합니다.',
    core:true,
   },
  ],
 };
}

function ixicConfig():StrategyProfileConfig{
 const ixic=data.ixic_addons;
 const full=ixic.periods.find((period:any)=>period.id==='full');
 const recent=ixic.periods.find((period:any)=>period.id==='recent-10y');
 const strategy='ixic-three-percent-rule';
 return {
  kind:'ixic',
  strategy,
  initialProfile:defaultProfileFor(strategy),
  controlTitle:'IXIC 3% 규칙',
  badge:'addon 선택 가능',
  pageSummary:'기본 IXIC 규칙에 두 가지 선택 addon을 조합할 수 있습니다. 오른쪽 아래 ADDON 버튼에서 켜면 현재 성과와 차트가 즉시 바뀝니다.',
  heading:'현재 선택 프로필',
  marketDate:ixic.market_date,
  yearlyStudy:{yearly:ixic.yearly},
  stressProfiles:ixic.stress_profiles,
  downloads:ixic.addons.map((addon:any)=>({href:`#addon-${addon.anchor}`,label:`${addon.short_label} 규칙`})),
  historicalLabel:'연구 당시 기본 IXIC 결과 보기',
  addons:ixic.addons,
  profiles:ixic.profiles.map((profile:any)=>resultProfile(strategy,profile.id,full,recent,{label:profile.label})),
  rules:[
   {
    id:'core',
    title:'addon 비활성화',
    description:'급락 상태와 10개 변동성 구간만 사용하는 기본 IXIC 규칙입니다.',
    core:true,
   },
   {
    id:'full',
    title:'상태 종료 후 전액 투자',
    description:'패닉 종료 다음 시가에 100%로 복귀하고, 진입 구간보다 한 단계 악화되거나 저장한 고점을 넘으면 기본 규칙으로 돌아갑니다.',
   },
   {
    id:'recovery',
    title:'QQQ 저점 대비 10% 회복',
    description:'패닉 중 QQQ 종가가 이후 저점에서 10% 회복하면 패닉 상태를 끝냅니다. 대공황 상태에는 적용하지 않습니다.',
   },
   {
    id:'all',
    title:'두 addon 조합',
    description:'QQQ 10% 회복으로 패닉을 끝낸 뒤 전액 투자 복귀 규칙까지 연속 적용합니다.',
   },
  ],
 };
}

export function strategyProfileConfig(strategyId:string):StrategyProfileConfig|null{
 if(strategyId==='volatility-allocation')return voConfig();
 if(strategyId==='ixic-three-percent-rule')return ixicConfig();
 return null;
}
