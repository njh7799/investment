import content from '../generated/content.json';
import {marked} from 'marked';
import path from 'node:path';
export const data = content as any;
import {url} from './format';
export * from './format';
export function docUrl(source:string):string {
 const research=data.studies.find((s:any)=>s.document===source);
 if(research)return url(`research/${research.id}/`);
 const strategy=data.strategies.find((s:any)=>`docs/strategies/${s.id}/README.md`===source);
 if(strategy)return url(`strategies/${strategy.id}/`);
 if(data.documents.some((d:any)=>d.path===source))return url('guide/'+source.replace(/^docs\//,'').replace(/\.md$/,'')+'/');
 return 'https://github.com/njh7799/investment/blob/main/'+source;
}
export function markdown(body:string,source='docs/research/model-census.md') {
 let html=marked.parse(body,{async:false}) as string;
 const seen=new Map<string,number>();
 html=html.replace(/<h([1-6])>(.*?)<\/h\1>/g,(_m,level,text)=>{const slug=text.replace(/<[^>]+>/g,'').toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu,'').replace(/ /g,'-');const count=seen.get(slug)||0;seen.set(slug,count+1);return `<h${level} id="${slug}${count?'-'+count:''}">${text}</h${level}>`});
 return html.replace(/(href|src)="([^"]+)"/g,(_m,key,target)=>{
  if(/^(https?:|mailto:|#)/.test(target))return `${key}="${target}"`;
  const [raw,anchor]=target.split('#');
  let resolved=path.posix.normalize(path.posix.join(path.posix.dirname(source),raw));
  if(resolved.endsWith('/'))resolved+='README.md';
  let dest=resolved.endsWith('.md')?docUrl(resolved):url('downloads/'+resolved);
  if(!/\.(md|csv|json|yaml|png)$/.test(resolved))dest=docUrl(resolved+'/README.md');
  return `${key}="${dest}${anchor?'#'+anchor:''}"`;
 });
}
export const document=(source:string)=>data.documents.find((d:any)=>d.path===source);
