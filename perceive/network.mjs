import {execFileSync} from 'node:child_process';
import {EnvHttpProxyAgent,fetch as request} from 'undici';

export function systemProxyOptions(text='') {
  const values={};
  for(const line of text.split('\n')){
    const match=line.match(/^\s*(HTTPSEnable|HTTPEnable|HTTPSProxy|HTTPProxy|HTTPSPort|HTTPPort)\s*:\s*(.*?)\s*$/);
    if(match)values[match[1]]=match[2];
  }
  const options={};
  for(const [prefix,key] of [['HTTP','httpProxy'],['HTTPS','httpsProxy']]){
    const host=values[prefix+'Proxy'],port=Number(values[prefix+'Port']);
    if(values[prefix+'Enable']==='1'&&host&&port>0&&port<=65535){
      try{options[key]=new URL(`http://${host.includes(':')&&!host.startsWith('[')?`[${host}]`:host}:${port}`).href;}catch{}
    }
  }
  return options;
}

export function modelProxyOptions(env=process.env,platform=process.platform,readSystem=()=>execFileSync('/usr/sbin/scutil',['--proxy'],{encoding:'utf8',timeout:1500})){
  const httpProxy=env.http_proxy||env.HTTP_PROXY,httpsProxy=env.https_proxy||env.HTTPS_PROXY;
  let options={};
  if(httpProxy||httpsProxy){if(httpProxy)options.httpProxy=httpProxy;if(httpsProxy)options.httpsProxy=httpsProxy;}
  else if(platform==='darwin'){try{options=systemProxyOptions(readSystem());}catch{}}
  options.noProxy=env.no_proxy||env.NO_PROXY||'localhost,127.0.0.1,::1';
  return options;
}

let dispatcher;
export async function modelFetch(url,options={}){
  dispatcher??=new EnvHttpProxyAgent(modelProxyOptions());
  try{return await request(url,{...options,dispatcher});}
  catch(error){if(error.name==='AbortError'||error.name==='TimeoutError')throw error;throw new Error('无法连接 Gemini，请检查当前网络或代理。');}
}
