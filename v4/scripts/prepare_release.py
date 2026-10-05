"""Assemble only reviewed adapters; never silently promote a completed training job."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    reports=ROOT/'reports'
    state=json.loads((reports/'current_state_evaluation.json').read_text(encoding='utf-8'))
    dialogue=json.loads((reports/'dialogue_repair_evaluation.json').read_text(encoding='utf-8'))
    review=json.loads((reports/'dialogue_repair_manual_review.json').read_text(encoding='utf-8'))
    response_file=reports/'dialogue_repair_development_responses.jsonl'
    if response_file.exists():
        if review['responses_sha256']!=hashlib.sha256(response_file.read_bytes()).hexdigest():raise RuntimeError('Review does not match generated responses')
    elif review.get('approved') or dialogue.get('checkpoint'):
        raise RuntimeError('Cannot approve a candidate without generated-response evidence')
    release={'version':'4.0.0','status':'validated','scope':'Public-data current social understanding and Chinese dialogue; not a real-home acceptance certificate','base':'../v2/models/qwen35_2B','base_revision':'15852e8c16360a2fea060d615a32b45270f8a8fc','original_tasks':'../v2/models/social_zh/best','state':None,'dialogue':None,'future_prediction_enabled':False,'physical_base_models':1,'state_evaluation':'reports/current_state_evaluation.json','dialogue_evaluation':'reports/dialogue_evaluation.json','dialogue_review':'reports/dialogue_manual_review.json'}
    if state.get('accepted_heads'):
        path=Path(state['checkpoint']);release['state']={'checkpoint':path.relative_to(ROOT).as_posix(),'fingerprint':state['checkpoint_fingerprint'],'accepted_heads':state['accepted_heads'],'temperatures':state['calibration']['temperatures']}
    if dialogue.get('nll_gate_passed') and review.get('approved'):
        path=Path(dialogue['checkpoint']);release['dialogue']={'checkpoint':path.relative_to(ROOT).as_posix(),'sha256':dialogue['adapter_sha256']}
    release['fallbacks']={'current_heads_not_accepted':'Original V2 head and task adapter','dialogue_not_accepted':'Frozen Qwen base with full Chinese conversation context'}
    release.update(dialogue_evaluation='reports/dialogue_repair_evaluation.json',dialogue_review='reports/dialogue_repair_manual_review.json',dialogue_prompt_version='v4-grounded-2',first_dialogue_candidate_rejected=True)
    release['recommended_device']='cuda'
    cpu=reports/'cpu_export.json'
    if cpu.exists():
        export=json.loads(cpu.read_text(encoding='utf-8'))
        release['cpu_base']={'file':'models/cpu_base_int8.pt','sha256':export['sha256']}
        runtime=reports/'runtime_cpu.json'
        if runtime.exists():
            probe=json.loads(runtime.read_text(encoding='utf-8'))['quantization_fidelity_probe']['comparison']['current_emotion']
            release['cpu_base'].update(quality_status='experimental_runtime_only',emotion_top1_agreement_with_gpu=probe['top1_agreement'],probe_n=probe['n'])
    folder=ROOT/'models';folder.mkdir(exist_ok=True)
    path=folder/'release.json'
    if path.exists():raise RuntimeError('Do not overwrite an existing release without a new review')
    path.write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(release,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
