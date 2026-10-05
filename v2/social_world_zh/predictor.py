import json,time,os
import numpy as np
import torch
from .model import SocialModel
from .spec import ROOT,HEADS,MAX_LENGTH,state_text,transition_text
from .transition import TransitionPrior,candidate_state_text
from .labels_zh import label_zh

class Predictor:
    def __init__(self,device='cuda',checkpoint=None):
        torch.set_num_threads(int(os.getenv('SOCIAL_THREADS','4')))
        self.device=device
        quantized=ROOT/'models/social_zh/cpu_int8.pt'
        if device=='cpu' and quantized.exists():
            from .quantized import QuantizedSocialModel
            self.model=QuantizedSocialModel(quantized)
        else:self.model=SocialModel(device,checkpoint or ROOT/'models/social_zh/best').eval()
        self.temperature={k:1. for k in HEADS}
        path=ROOT/'reports/calibration.json'
        if not path.exists():raise RuntimeError('Missing calibration.json: finish evaluate.py before serving this checkpoint')
        calibration=json.loads(path.read_text())
        if calibration.get('checkpoint_fingerprint')!=self.model.checkpoint_fingerprint:raise RuntimeError('Calibration checkpoint mismatch: rerun evaluate.py and export_cpu.py')
        self.temperature.update(calibration['temperatures'])
        self.backend='pytorch_int8_linears_bf16_embedding' if device=='cpu' and quantized.exists() else 'pytorch_bf16'
        self.transition=TransitionPrior() if (ROOT/'models/social_zh/transition_config.json').exists() else None
        if self.transition and self.transition.config.get('checkpoint_fingerprint')!=self.model.checkpoint_fingerprint:raise RuntimeError('Transition checkpoint mismatch: rerun evaluate.py')
    def batch(self,texts,heads):
        encoded=self.model.tokenizer(texts,padding=True,truncation=True,max_length=MAX_LENGTH,return_tensors='pt')
        encoded={k:v.to(self.device) for k,v in encoded.items()}
        with torch.inference_mode():logits=self.model(**encoded)
        results=[{} for _ in texts]
        for head in heads:
            probs=(logits[head]/self.temperature[head]).softmax(-1).cpu().numpy()
            for i,p in enumerate(probs):
                idx=int(p.argmax());label=HEADS[head][idx];results[i][head]={'label':label,'label_zh':label_zh(head,label),'confidence':float(p[idx]),'distribution':{label:float(v) for label,v in zip(HEADS[head],p)}}
        return results
    def state(self,history,speech):
        if not speech.strip():
            defaults={'emotion':'unknown','dialog_act':'unknown','intent':'unknown','boundary':'unspecified','policy':'WAIT','task_domain':'unknown'}
            return {k:{'label':label,'label_zh':label_zh(k,label),'confidence':0.,'distribution':{},'source':'not_evaluated_no_speech'} for k,label in defaults.items()}
        return self.batch([state_text(history,speech)],['emotion','dialog_act','intent','boundary','policy','task_domain'])[0]
    def imagine(self,history,speech,candidates):
        texts=[transition_text(history,speech,c) for c in candidates]
        if self.transition:texts += [state_text(history,speech)]+[candidate_state_text(history,speech,c) for c in candidates]
        raw=self.batch(texts,['next_emotion','next_act','emotion','dialog_act']);outputs=[{k:r[k] for k in ['next_emotion','next_act']} for r in raw[:len(candidates)]]
        if self.transition:
            for key,current_key in [('next_emotion','emotion'),('next_act','dialog_act')]:
                neural=np.array([[r[key]['distribution'][label] for label in HEADS[key]] for r in outputs])
                current=np.array([[raw[len(candidates)][current_key]['distribution'][label] for label in HEADS[current_key]]]*len(candidates))
                candidate=np.array([[r[current_key]['distribution'][label] for label in HEADS[current_key]] for r in raw[len(candidates)+1:]])
                probabilities=self.transition.combine(key,neural,current,candidate)
                for r,p in zip(outputs,probabilities):
                    idx=int(p.argmax());label=HEADS[key][idx];r[key]={'label':label,'label_zh':label_zh(key,label),'confidence':float(p[idx]),'distribution':{label:float(v) for label,v in zip(HEADS[key],p)}}
        negative={'anger','negative-other','depress','worried','sadness','fear','disgust'}
        for candidate,result in zip(candidates,outputs):
            result['candidate']=candidate
            result['negative_probability']=sum(p for e,p in result['next_emotion']['distribution'].items() if e in negative)
        return {'predictions':outputs,'semantics':'observational_next_turn_prediction_not_causal_effect','advisory_only':True,'horizon':1,'transition_method':'shared_encoder_neural_head_plus_learned_transition_prior' if self.transition else 'neural_head','domain':'Chinese television dyadic dialogue; home-robot domain not validated'}
    def generate_local(self,speech,max_new_tokens=96):
        """Frozen-base text fallback shares the backbone; generated text is never an action."""
        if not hasattr(self.model.backbone,'disable_adapter'):
            return {'status':'cpu_templates_only','reply':'这个复杂问题暂时无法在当前本地后端可靠回答，可以请人协助。','action_authority':False}
        tokenizer=self.model.tokenizer
        messages=[{'role':'system','content':'你是中国家庭机器人的对话助手。用简短自然的中文回答，最多120字。不执行动作，不声称已经完成现实任务。不推断他人隐藏心理，遇到不确定的问题明确说明。'},{'role':'user','content':speech}]
        ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=False).to(self.device)
        generated=[];cache=None;start=time.monotonic();stop={tokenizer.eos_token_id,tokenizer.convert_tokens_to_ids('<|im_end|>')}
        with torch.inference_mode(),self.model.backbone.disable_adapter(),torch.autocast(self.device,dtype=torch.bfloat16):
            for _ in range(max_new_tokens):
                out=self.model.backbone(input_ids=ids,past_key_values=cache,use_cache=True)
                cache=out.past_key_values
                scores=out.last_hidden_state[:,-1]@self.model.backbone.get_input_embeddings().weight.T
                token=int(scores.argmax(-1).item())
                if token in stop:break
                generated.append(token);ids=torch.tensor([[token]],device=self.device)
                if time.monotonic()-start>20:break
        return {'status':'local_base_model','reply':tokenizer.decode(generated,skip_special_tokens=True)[:300],'tokens':len(generated),'elapsed_seconds':time.monotonic()-start,'action_authority':False}
