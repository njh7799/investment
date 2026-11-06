export const PROFILE_CHANGE_EVENT='strategy-profile-change';

export type ProfileStrategy='volatility-allocation'|'ixic-three-percent-rule';

type ProfileChangeDetail={
 strategy:ProfileStrategy;
 profile:string;
};

const defaultProfiles:Record<ProfileStrategy,string>={
 'volatility-allocation':'addon',
 'ixic-three-percent-rule':'core',
};

const profileModels:Record<ProfileStrategy,Record<string,string>>={
 'volatility-allocation':{
  addon:'vo_addon_5_20',
  core:'vo',
 },
 'ixic-three-percent-rule':{
  core:'ixic_core',
  full:'ixic_full_after_regime',
  recovery:'ixic_qqq_recovery',
  all:'ixic_all_addons',
 },
};

export const allProfileModels=Object.values(profileModels).flatMap(Object.values);

export function isProfileStrategy(value:string):value is ProfileStrategy{
 return value in defaultProfiles;
}

export function defaultProfileFor(strategy:ProfileStrategy){
 return defaultProfiles[strategy];
}

export function profileFromAddons(strategy:ProfileStrategy,active:Set<string>){
 if(strategy==='volatility-allocation')return active.has('sma_5_20')?'addon':'core';
 const full=active.has('full');
 const recovery=active.has('recovery');
 if(full&&recovery)return 'all';
 if(full)return 'full';
 if(recovery)return 'recovery';
 return 'core';
}

export function selectedProfile(strategy:ProfileStrategy){
 const root=document.documentElement;
 return root.dataset.profileStrategy===strategy
  ?root.dataset.strategyProfile||defaultProfileFor(strategy)
  :defaultProfileFor(strategy);
}

export function modelForProfile(strategy:ProfileStrategy,profile=selectedProfile(strategy)){
 return profileModels[strategy][profile]||profileModels[strategy][defaultProfileFor(strategy)];
}

export function applyProfile(strategy:ProfileStrategy,profile:string){
 const root=document.documentElement;
 root.dataset.profileStrategy=strategy;
 root.dataset.strategyProfile=profile;
 document.querySelectorAll<HTMLElement>(`[data-profile-strategy="${strategy}"][data-profile-view]`).forEach(view=>{
  view.hidden=view.dataset.profileView!==profile;
 });
 window.dispatchEvent(new CustomEvent<ProfileChangeDetail>(PROFILE_CHANGE_EVENT,{detail:{strategy,profile}}));
}
