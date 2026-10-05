"""Real bounded SenseVoice CTC fine-tuning; speaker-disjoint validation selects.

Synthetic corruptions are engineering probes, NOT household/dysarthria data.
Test is run only after selection. This script never promotes runtime weights.
"""
import os
os.environ.setdefault('HF_HUB_OFFLINE','1')
import argparse,copy,hashlib,json,random,re,time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from scipy.signal import fftconvolve,lfilter,resample_poly

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/speech_pilot';OUT=ROOT/'reports/speech_20261005';WEIGHTS=ROOT/'models/sensevoice_pilot'

def normalize(text):return ''.join(re.findall(r'[\u3400-\u9fffA-Za-z0-9]',re.sub(r'<\|.*?\|>','',text))).lower()

def distance(a,b):
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=cur
    return prev[-1]

def corrupt(x,kind,seed):
    rng=np.random.default_rng(seed);x=x.copy()
    if kind=='quiet':return (x*.08).astype(np.float32)
    if kind=='slow':return resample_poly(x,5,4).astype(np.float32) # pitch also changes; not natural dysarthria
    if kind in {'reverb_noise','noise'}:
        if kind=='reverb_noise':
            t=np.arange(6400)/16000;rir=rng.normal(size=len(t))*np.exp(-t*6.91/.45)*.025;rir[0]=1
            x=fftconvolve(x,rir)[:len(x)]
        n=lfilter([1],[1,-.9],rng.normal(size=len(x)));n/=max(np.std(n),1e-8)
        snr=10 if kind=='noise' else 5
        n*=np.sqrt(np.mean(x*x))/10**(snr/20);x=x+n
        x*=min(1,.95/max(np.max(np.abs(x)),1e-8))
    return x.astype(np.float32)

def rows(split):return [json.loads(line) for line in (DATA/f'{split}.jsonl').read_text(encoding='utf-8').splitlines()]

def seed_for(row,kind):return int(hashlib.sha256((row['id']+kind).encode()).hexdigest()[:8],16)

def main():
    global DATA,OUT,WEIGHTS
    parser=argparse.ArgumentParser();parser.add_argument('--epochs',type=int,default=3);parser.add_argument('--expanded',action='store_true');args=parser.parse_args()
    if args.expanded:
        DATA=ROOT/'data/speech_expanded';OUT=OUT/'expanded';WEIGHTS=ROOT/'models/sensevoice_expanded'
    from funasr import AutoModel
    from funasr.utils.load_utils import extract_fbank
    random.seed(20261005);np.random.seed(20261005);torch.manual_seed(20261005);torch.set_num_threads(4)
    OUT.mkdir(parents=True,exist_ok=True);WEIGHTS.mkdir(parents=True,exist_ok=True)
    auto=AutoModel(model=os.path.relpath(ROOT/'models/sensevoice_train'),device='cuda:0',disable_update=True,disable_pbar=True,trust_remote_code=False)
    model=auto.model;tokenizer=auto.kwargs['tokenizer'];frontend=auto.kwargs['frontend']
    train,val,test=rows('train'),rows('validation'),rows('test')
    sets=[{r['speaker'] for r in split} for split in [train,val,test]]
    assert not sets[0]&sets[1] and not sets[0]&sets[2] and not sets[1]&sets[2]
    if args.expanded:
        cantonese=[]
        for split,dest in [('train',train),('validation',val),('test',test)]:
            values=[json.loads(line) for line in (ROOT/'data/cantonese_probe'/f'{split}.jsonl').read_text(encoding='utf-8').splitlines()];dest.extend(values);cantonese.append({r['episode'] for r in values})
        assert not cantonese[0]&cantonese[1] and not cantonese[0]&cantonese[2] and not cantonese[1]&cantonese[2]
    allrows=train+val+test;audio={r['id']:sf.read(r['path'],dtype='float32')[0] for r in allrows}
    noises={}
    if args.expanded:
        for kind in ['car','cafe']:
            value,rate=sf.read(ROOT/'data/speech_noise'/f'{kind}.wav',dtype='float32')
            if value.ndim>1:value=value.mean(1)
            assert rate==16000
            noises[kind]=value
    conditions=['clean','noise','reverb_noise','quiet']+(['car','cafe','reverb_cafe'] if args.expanded else [])
    noisy_conditions=[k for k in conditions if k not in {'clean','quiet'}]
    # Freeze lower acoustic stack, adapt last two encoder blocks plus CTC classifier.
    names=[name for name,_ in model.named_parameters()]
    blocks=sorted({'.'.join(name.split('.')[:3]) for name in names if name.startswith('encoder.tp_encoders.')},key=lambda x:int(x.split('.')[-1]))
    assert len(blocks)>=2, names[-15:]
    prefixes=tuple(blocks[-2:]+['ctc.ctc_lo'])
    for name,p in model.named_parameters():p.requires_grad_(name.startswith(prefixes))
    trainable={name:p for name,p in model.named_parameters() if p.requires_grad}
    initial={name:p.detach().cpu().clone() for name,p in trainable.items()}
    protocol={'seed':20261005,'epochs':args.epochs,'micro_batch':2,'accumulation':4,'lr':1e-5,'trainable_parameters':sum(p.numel() for p in trainable.values()),'prefixes':prefixes,'selection':'validation mean CER clean/noise/reverb_noise/quiet; clean <= baseline + 0.01; noisy mean lower than baseline','test_used_for_selection':False,'promote_runtime':False,'speaker_disjoint':True,'pretraining_overlap':'unknown','augmentation':'synthetic colored noise, exponential random RIR, gain, resampling; NOT actual distance, TV, elderly or dysarthria validation'}
    protocol.update(conditions=conditions,recorded_noise='THCHS-30 Apache-2.0 car/cafe; train/validation/test use disjoint 60/20/20 temporal regions of the same recording' if args.expanded else None,test_history='expanded Mandarin diagnostic includes prior pilot test items; Cantonese single narrator episode disjoint, possible overlap prior diagnostic; not newly blind' if args.expanded else 'first local use',speaker_disjoint='Mandarin only; Cantonese episode-disjoint single narrator' if args.expanded else True,language_query='auto' if args.expanded else 'zh',counts={'train':len(train),'validation':len(val),'test':len(test)})
    protocol['selection']='validation mean CER across listed conditions; clean <= baseline + 0.01; mean of all conditions except clean/quiet lower than baseline'
    (OUT/'training_protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8');print(json.dumps(protocol),flush=True)
    def features(batch,kind='clean',epoch=0):
        signals=[]
        for r in batch:
            seed=seed_for(r,kind)+epoch*1009;x=corrupt(audio[r['id']],kind,seed)
            if kind in ['car','cafe','reverb_cafe']:
                if kind=='reverb_cafe':
                    rng=np.random.default_rng(seed);t=np.arange(8000)/16000;rir=rng.normal(size=len(t))*np.exp(-t*6.91/.55)*.025;rir[0]=1;x=fftconvolve(x,rir)[:len(x)]
                n=noises['cafe' if 'cafe' in kind else 'car'];a,b={'train':(0,.6),'validation':(.6,.8),'test':(.8,1)}[r['split']]
                region=n[int(a*len(n)):int(b*len(n))];offset=seed%max(1,len(region)-len(x));noise=region[offset:offset+len(x)]
                if len(noise)<len(x):noise=np.resize(noise,len(x))
                snr=5 if not epoch else [0,5,10,15][seed%4]
                x=x+noise*np.sqrt(np.mean(x*x)/max(np.mean(noise*noise),1e-10))/10**(snr/20);x=x*min(1,.95/max(np.max(np.abs(x)),1e-8))
            signals.append(x.astype(np.float32))
        with torch.no_grad():f,l=extract_fbank(signals,frontend=frontend)
        return f.cuda(),l.reshape(-1).cuda()
    def encode(f,l):
        b=f.size(0);device=f.device
        q=model.embed(torch.tensor([[model.lid_dict['auto' if args.expanded else 'zh'],1,2,model.textnorm_dict['woitn']]],device=device)).repeat(b,1,1)
        encoded,lengths=model.encoder(torch.cat([q,f],1),l+4)
        return encoded,lengths
    @torch.no_grad()
    def evaluate(part,tag):
        model.eval();metrics={};samples=[]
        for kind in conditions:
            errors=characters=0;start=time.monotonic()
            for i in range(0,len(part),2):
                batch=part[i:i+2];f,l=features(batch,kind);encoded,lengths=encode(f,l);ids=model.ctc.argmax(encoded[:,4:])
                for j,row in enumerate(batch):
                    tokens=torch.unique_consecutive(ids[j,:int(lengths[j])-4]);tokens=tokens[tokens!=model.blank_id].tolist()
                    pred=normalize(tokenizer.decode(tokens));ref=normalize(row['text']);e=distance(ref,pred);errors+=e;characters+=len(ref)
                    samples.append({'id':row['id'],'speaker':row['speaker'],'accent':row['accent'],'condition':kind,'reference':ref,'prediction':pred,'errors':e,'characters':len(ref)})
            metrics[kind]={'cer':errors/max(1,characters),'errors':errors,'characters':characters,'seconds':time.monotonic()-start}
        result={'conditions':metrics,'macro_condition_cer':sum(x['cer'] for x in metrics.values())/len(metrics),'samples':samples}
        (OUT/f'{tag}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(tag,{k:round(v['cer'],4) for k,v in metrics.items()},flush=True);return result
    baseline=evaluate(val,'validation_baseline');best=baseline['macro_condition_cer'];selected=0;history=[]
    optimizer=torch.optim.AdamW(trainable.values(),lr=1e-5,weight_decay=.01)
    start=time.monotonic();step=0
    for epoch in range(1,args.epochs+1):
        order=train[:];random.Random(20261005+epoch).shuffle(order);model.eval();optimizer.zero_grad();losses=[]
        for i in range(0,len(order),2):
            kinds=['clean','noise','clean','reverb_noise','quiet','slow'] if not args.expanded else ['clean','car','clean','cafe','reverb_cafe','clean','quiet','slow']
            batch=order[i:i+2];kind=kinds[(i//2)%len(kinds)]
            f,l=features(batch,kind,epoch);encoded,lengths=encode(f,l)
            targets=[torch.tensor(tokenizer.encode(normalize(row['text'])),dtype=torch.long) for row in batch]
            target_lens=torch.tensor([len(t) for t in targets],device='cuda');target=torch.nn.utils.rnn.pad_sequence(targets,batch_first=True,padding_value=-1).cuda()
            loss=model.ctc(encoded[:,4:],lengths-4,target,target_lens)
            if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss')
            (loss/4).backward();losses.append(float(loss.detach()))
            if (i//2+1)%4==0 or i+2>=len(order):
                torch.nn.utils.clip_grad_norm_(trainable.values(),1);optimizer.step();optimizer.zero_grad();step+=1
                if step%10==0:print(f'epoch={epoch} step={step} loss={np.mean(losses[-40:]):.4f} elapsed={time.monotonic()-start:.1f}s',flush=True)
        result=evaluate(val,f'validation_epoch_{epoch}')
        clean_ok=result['conditions']['clean']['cer']<=baseline['conditions']['clean']['cer']+.01
        noisy_ok=sum(result['conditions'][k]['cer'] for k in noisy_conditions)<sum(baseline['conditions'][k]['cer'] for k in noisy_conditions)
        accepted=clean_ok and noisy_ok and result['macro_condition_cer']<best
        history.append({'epoch':epoch,'mean_training_loss':float(np.mean(losses)),'validation_cer':result['macro_condition_cer'],'accepted':accepted})
        torch.save({k:p.detach().cpu() for k,p in trainable.items()},WEIGHTS/f'epoch_{epoch}.pt')
        if accepted:best=result['macro_condition_cer'];selected=epoch
    candidate_state={k:p.detach().cpu().clone() for k,p in trainable.items()}
    for name,p in trainable.items():p.data.copy_(initial[name].to(p.device))
    base_test=evaluate(test,'test_baseline')
    chosen=torch.load(WEIGHTS/f'epoch_{selected}.pt',weights_only=True) if selected else initial
    for name,p in trainable.items():p.data.copy_(chosen[name].to(p.device))
    candidate_test=evaluate(test,'test_selected')
    report={'completed':True,'epochs':args.epochs,'optimizer_steps':step,'seconds':time.monotonic()-start,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'selected_epoch':selected,'history':history,'test_baseline_cer':base_test['macro_condition_cer'],'test_selected_cer':candidate_test['macro_condition_cer'],'runtime_promoted':False,'reason':'pilot_only_requires_broader_dialect_noise_safety_and_export_validation'}
    (OUT/'training_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
