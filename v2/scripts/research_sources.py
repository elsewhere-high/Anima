import requests,pathlib,json,concurrent.futures
ROOT=pathlib.Path(__file__).resolve().parents[1]
urls={
 'cped_license':'https://raw.githubusercontent.com/scutcyr/CPED/main/LICENSE',
 'cped_readme':'https://raw.githubusercontent.com/scutcyr/CPED/main/README-zh.md',
 'crosswoz_license':'https://raw.githubusercontent.com/thu-coai/CrossWOZ/master/LICENSE',
 'crosswoz_readme':'https://raw.githubusercontent.com/thu-coai/CrossWOZ/master/README.md',
 'cold_license':'https://raw.githubusercontent.com/thu-coai/COLDataset/main/LICENSE',
 'cold_readme':'https://raw.githubusercontent.com/thu-coai/COLDataset/main/README.md',
 'massive_card':'https://huggingface.co/datasets/AmazonScience/massive/raw/main/README.md',
 'massive_tree':'https://huggingface.co/api/datasets/AmazonScience/massive/tree/main',
 'qwen08_config':'https://huggingface.co/Qwen/Qwen3.5-0.8B/raw/main/config.json',
 'qwen2_config':'https://huggingface.co/Qwen/Qwen3.5-2B/raw/main/config.json',
 'qwen08_api':'https://huggingface.co/api/models/Qwen/Qwen3.5-0.8B',
 'qwen2_api':'https://huggingface.co/api/models/Qwen/Qwen3.5-2B',
 'transformers_version':'https://pypi.org/pypi/transformers/json',
 'peft_version':'https://pypi.org/pypi/peft/json',
}
def get(item):
    name,url=item
    try:
        r=requests.get(url,timeout=60); (ROOT/'research'/f'{name}.txt').write_text(r.text,encoding='utf-8')
        preview=r.text[:700] if 'license' in name else ''
        if name.endswith('_api'): preview=json.dumps({'sha':r.json().get('sha'),'files':[x['rfilename'] for x in r.json().get('siblings',[])]})
        if name.endswith('_version'):preview=r.json()['info']['version']
        return {'name':name,'url':url,'status':r.status_code,'preview':preview}
    except Exception as e:return {'name':name,'error':str(e)}
results=list(concurrent.futures.ThreadPoolExecutor(6).map(get,urls.items()))
(ROOT/'research/sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for r in results: print(json.dumps(r,ensure_ascii=False))
