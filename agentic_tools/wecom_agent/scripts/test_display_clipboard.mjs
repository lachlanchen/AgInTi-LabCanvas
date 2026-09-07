import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import http from 'node:http';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';

const root=fs.mkdtempSync(path.join(os.tmpdir(),'labcanvas-clipboard-test-'));
const html=fs.readFileSync(process.argv[2] || fileURLToPath(new URL('../web/displays/index.html',import.meta.url)));
console.log('Synthetic browser-test artifacts: '+root);
const original='Fixture 中文 日本語 🐼🙂\nSecond line with \' and "';
let remoteText=original, reads=0, writes=0, rejectWrite=false;
const mock=`export default class RFB extends EventTarget { constructor(){super();setTimeout(()=>this.dispatchEvent(new Event('connect')),50)} disconnect(){this.dispatchEvent(new Event('disconnect'))} }`;
const server=http.createServer(async(req,res)=>{
 if(req.url==='/novnc/core/rfb.js'){res.setHeader('Content-Type','text/javascript');res.end(mock);return}
 if(req.url==='/clipboard'){
  let body='';for await(const chunk of req)body+=chunk;
  const data=JSON.parse(body);res.setHeader('Content-Type','application/json');
  if(data.action==='read'){reads++;res.end(JSON.stringify({text:remoteText}));return}
  if(rejectWrite){res.statusCode=409;res.end('{}');return}
  writes++;remoteText=data.text;res.end('{"ok":true}');return;
 }
 res.setHeader('Content-Type','text/html');res.end(html);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}/wechat`;
const profile=fs.mkdtempSync(root+'/clipboard-browser-');
const log=fs.openSync(root+'/headless-chrome.log','a');
const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore',log,log]});
let browser,page;let seq=0;
function connect(endpoint){return new Promise((resolve,reject)=>{
 const socket=new WebSocket(endpoint);const pending=new Map();
 socket.addEventListener('open',()=>resolve({socket,call(method,params={}){const id=++seq;return new Promise((ok,fail)=>{const timer=setTimeout(()=>{pending.delete(id);fail(new Error(method+' timeout'))},10000);pending.set(id,{ok,fail,timer});socket.send(JSON.stringify({id,method,params}))})}}));
 socket.addEventListener('error',reject);
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(!m.id)return;const p=pending.get(m.id);if(!p)return;clearTimeout(p.timer);pending.delete(m.id);m.error?p.fail(new Error(JSON.stringify(m.error))):p.ok(m.result)});
})}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function evaluate(expression){const r=await page.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expression){for(let n=0;n<60;n++){if(await evaluate(expression))return;await sleep(50)}throw new Error('Wait failed: '+expression)}
async function click(id){await evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);await sleep(70)}
const results=[];
try{
 const active=profile+'/DevToolsActivePort';for(let n=0;n<100&&!fs.existsSync(active);n++){if(chrome.exitCode!==null)throw new Error('Chrome exited');await sleep(50)}
 const port=fs.readFileSync(active,'utf8').split('\n')[0];
 const version=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();browser=await connect(version.webSocketDebuggerUrl);
 await browser.call('Browser.grantPermissions',{origin:new URL(url).origin,permissions:['clipboardReadWrite','clipboardSanitizedWrite']});
 const target=await(await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,{method:'PUT'})).json();page=await connect(target.webSocketDebuggerUrl);
 await page.call('Page.enable');await page.call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await until(`document.getElementById('status')?.textContent==='Viewing'`);
 assert.equal(await evaluate(`document.getElementById('clipboard').disabled`),true);assert.equal(reads,0);results.push('view-only access does not read clipboard');
 await evaluate(`navigator.clipboard.writeText('client seed')`);
 await click('control');await until(`!document.getElementById('clipboard').disabled`);await click('clipboard');await until(`!document.getElementById('paste').disabled`);
 assert.equal(await evaluate(`document.querySelector('textarea').value`),original);assert.equal(await evaluate('navigator.clipboard.readText()'),'client seed');results.push('opening panel does not overwrite local clipboard');
 await click('copy-local');assert.equal(await evaluate('navigator.clipboard.readText()'),original);results.push('CJK, emoji, quotes and multiline copied to browser clipboard');
 const incoming='Client 中文 🙂\nNext line \' "';await evaluate(`navigator.clipboard.writeText(${JSON.stringify(incoming)})`);await click('read-local');assert.equal(await evaluate(`document.querySelector('textarea').value`),incoming);assert.equal(remoteText,original);
 await click('paste');assert.equal(remoteText,incoming);assert.equal(writes,1);results.push('client-to-Windows transfer requires explicit send');
 rejectWrite=true;const draft='unsent draft 中文\nkeep me';await evaluate(`document.querySelector('textarea').value=${JSON.stringify(draft)};document.querySelector('textarea').dispatchEvent(new Event('input'))`);await click('paste');assert.equal(remoteText,incoming);assert.equal(await evaluate(`document.querySelector('#clip').open`),true);await click('close');await click('control');await sleep(100);await click('control');await until(`!document.getElementById('clipboard').disabled`);await click('clipboard');assert.equal(await evaluate(`document.querySelector('textarea').value`),draft);assert.equal(reads,1);results.push('failed send and control reconnect preserve draft');
 await evaluate(`document.querySelector('textarea').value='x'.repeat(65537);document.querySelector('textarea').dispatchEvent(new Event('input'))`);await click('paste');assert.match(await evaluate(`document.getElementById('clip-status').textContent`),/65,536/);assert.equal(await evaluate(`document.querySelector('textarea').value.length`),65537);assert.equal(writes,1);results.push('oversized draft is rejected without truncation');await evaluate(`document.querySelector('textarea').value=${JSON.stringify(draft)}`);
 await evaluate(`Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});document.execCommand=()=>false`);await click('read-local');assert.match(await evaluate(`document.getElementById('clip-status').textContent`),/long-press Paste/);await click('copy-local');assert.match(await evaluate(`document.getElementById('clip-status').textContent`),/long-press and Copy/);assert.equal(await evaluate(`document.querySelector('textarea').selectionEnd-document.querySelector('textarea').selectionStart`),draft.length);results.push('manual phone fallback without clipboard permission or API');
 assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true);results.push('390px mobile layout without horizontal overflow');
 const png=await page.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(root+'/novnc-clipboard-mobile.png',Buffer.from(png.data,'base64'));
 fs.writeFileSync(root+'/novnc-clipboard-results.json',JSON.stringify({passed:results,urlIsFixture:true},null,2)+'\n');console.log(JSON.stringify(results,null,2));
}finally{
 try{await browser?.call('Browser.close')}catch{}
 page?.socket.close();browser?.socket.close();
 if(chrome.exitCode===null){chrome.kill('SIGTERM');await Promise.race([new Promise(resolve=>chrome.once('close',resolve)),sleep(3000)]);}
 if(chrome.exitCode===null){chrome.kill('SIGKILL');await new Promise(resolve=>chrome.once('close',resolve));}
 fs.rmSync(profile,{recursive:true,force:true});
 server.closeAllConnections();server.close();fs.closeSync(log);
}
