"""Read-only corpus accounting; hashes, split isolation and target-mask checks."""
import json,hashlib,unicodedata,re,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def norm(s):return re.sub(r'\W+','',unicodedata.normalize('NFKC',s)).lower()
def main():
    result={}
    for dataset in ['state','dialogue']:
        folder=ROOT/'data'/dataset;manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));rows={};entry={'files':{},'split_checks':{}}
        for split in ['train','validation','test']:
            file=folder/(split+'.jsonl');actual=hashlib.sha256(file.read_bytes()).hexdigest();assert actual==manifest['files'][split]['sha256'];rows[split]=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
            entry['files'][split]={'sha256':actual,'n':len(rows[split]),'sources':dict(collections.Counter(r['source'] for r in rows[split]))}
            if dataset=='dialogue':
                for r in rows[split]:
                    p=r['prompt_length'];assert r['labels'][:p]==[-100]*p and r['labels'][p:]==r['input_ids'][p:]
                    assert len(r['labels'])==len(r['input_ids'])<=512 and r['target_tokens']==len(r['labels'])-p
                    assert 'reasoning_content' not in r
                entry['files'][split]['assistant_only_mask_verified']=True
        for a,b in [('train','validation'),('train','test'),('validation','test')]:
            same_ids={r['id'] for r in rows[a]}&{r['id'] for r in rows[b]};assert not same_ids
            checks={'id_overlap':len(same_ids)}
            if dataset=='dialogue':
                groups=lambda split:{(r['source'],r['group']) for r in rows[split]}
                prompts=lambda split:{json.dumps(r['messages'][:-1],ensure_ascii=False,sort_keys=True) for r in rows[split]}
                normalized_last_queries=lambda split:{norm(r['messages'][-2]['content']) for r in rows[split]}
                checks.update(source_group_overlap=len(groups(a)&groups(b)),exact_full_prompt_overlap=len(prompts(a)&prompts(b)),normalized_last_query_overlap=len(normalized_last_queries(a)&normalized_last_queries(b)))
                assert checks['source_group_overlap']==0 and checks['exact_full_prompt_overlap']==0
            else:
                # Existing CPED dialogue identity is preserved by its official/V3 split.
                groups=lambda split:{(r['source'],r.get('dialogue',r['id'])) for r in rows[split] if r['source']=='cped_state'}
                checks['cped_dialogue_overlap']=len(groups(a)&groups(b));assert checks['cped_dialogue_overlap']==0
            entry['split_checks'][a+'_'+b]=checks
        result[dataset]=entry
    result['limitations']=['Split checks do not prove semantic independence or data provenance beyond upstream cards.','CPED is television dialogue; MEDD mixes daily/movie/synthetic language; OpenS2S is synthetic. No real home field benchmark.','Development probes are authored and are not a statistical dialogue accuracy benchmark.']
    (ROOT/'reports/data_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
