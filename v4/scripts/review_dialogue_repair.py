"""Compute the declared gates from separately recorded manual semantic ratings."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'reports/dialogue_repair_development_responses.jsonl'
    rows=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
    ratings=json.loads((ROOT/'reports/dialogue_repair_manual_ratings.json').read_text(encoding='utf-8'))
    assert set(ratings['items'])=={r['id'] for r in rows}
    evaluation=json.loads((ROOT/'reports/dialogue_repair_evaluation.json').read_text(encoding='utf-8'))
    items=[]
    for row in rows:
        rating=ratings['items'][row['id']]
        assert rating['base_score'] in [0,1,2] and rating['trained_score'] in [0,1,2] and rating['reason']
        items.append({'id':row['id'],'category':row['category'],**rating})
    totals={k:sum(r[k+'_score'] for r in items) for k in ['base','trained']}
    context={k:sum(r[k+'_score'] for r in items if r['category']=='context') for k in ['base','trained']}
    regressions=[r['id'] for r in items if r['category'] in ['grounding','device_boundary'] and r['trained_score']==0 and r['base_score']>0]
    gates={'nll':evaluation['nll_gate_passed'],'total_points_not_lower':totals['trained']>=totals['base'],'context_points_not_lower':context['trained']>=context['base'],'no_new_critical_failure':not regressions}
    result={'approved':all(gates.values()),'summary':ratings['summary'],'responses_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'protocol':'data/dialogue_repair_review_protocol.json','reviewer':'project assistant manual semantic review; not blinded, not independent human panel','total_points':totals,'context_points':context,'max_points':len(items)*2,'items':items,'critical_regressions':regressions,'gates':gates,'not_dialogue_accuracy':True,'known_development_adaptation':True}
    (ROOT/'reports/dialogue_repair_manual_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['approved','total_points','gates']},ensure_ascii=False))

if __name__=='__main__':main()
