import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve('dist'),errors=[];
function walk(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(dir,e.name)):[path.join(dir,e.name)])}
const files=walk(root),html=files.filter(f=>f.endsWith('.html'));
for(const file of html){
 const text=fs.readFileSync(file,'utf8');
 for(const [,raw] of text.matchAll(/(?:href|src)="([^"]+)"/g)){
  if(!raw.startsWith('/investment/'))continue;
  let target=path.join(root,decodeURIComponent(raw.split(/[?#]/)[0].slice('/investment/'.length)));
  if(raw.split(/[?#]/)[0].endsWith('/'))target=path.join(target,'index.html');
  if(!fs.existsSync(target))errors.push(`${path.relative(root,file)} → ${raw}`);
 }
}
for(const file of files){if(/(?:^|\/)(?:\.env[^/]*|\.git|toss_api\.py|authorize_kakao\.py)$/.test(file))errors.push('Private file published: '+file)}
if(errors.length){console.error(errors.join('\n'));process.exit(1)}
console.log(`Verified ${html.length} pages and ${files.length} public files.`);
