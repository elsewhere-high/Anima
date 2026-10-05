import json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from transformers import AutoTokenizer
from social_world_zh.spec import MAX_LENGTH
import numpy as np
tokenizer=AutoTokenizer.from_pretrained(ROOT/'models/qwen35_2B',local_files_only=True)
report={}
for split in ['train','validation','test']:
    rows=[json.loads(line) for line in (ROOT/'data/processed'/f'{split}.jsonl').read_text(encoding='utf-8').splitlines()]
    tokens=tokenizer([r['text'] for r in rows],truncation=False)['input_ids'];lengths=np.array([len(x) for x in tokens]);report[split]={}
    for source in sorted(set(r['source'] for r in rows)):
        values=lengths[np.array([r['source']==source for r in rows])]
        report[split][source]={'n':len(values),'median':float(np.median(values)),'p95':float(np.percentile(values,95)),'max':int(max(values)),'fraction_over_256':float(np.mean(values>MAX_LENGTH))}
(ROOT/'reports/token_statistics.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
