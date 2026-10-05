import React,{type CSSProperties,type ReactNode} from 'react';

export type ChartConfig=Record<string,{label:string;color:string}>;

export function ChartContainer({config,className='',children}:{config:ChartConfig;className?:string;children:ReactNode}){
  const colors=Object.fromEntries(Object.entries(config).map(([key,value])=>[`--color-${key}`,value.color])) as CSSProperties;
  return <div className={`chart-container ${className}`} style={colors}>{children}</div>;
}

export function ChartTooltipContent({active,payload}:{active?:boolean;payload?:any[]}){
  const row=payload?.[0]?.payload;
  if(!active||!row)return null;
  return <div className="chart-tooltip-content" role="tooltip"><strong>{row.period}</strong><span>{row.depthLabel} · {row.days.toLocaleString()}일</span></div>;
}
