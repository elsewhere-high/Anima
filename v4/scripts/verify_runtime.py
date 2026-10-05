"""Actual model routing and Chinese multi-turn/controller smoke checks."""
import sys,json,time,tempfile,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from social_v4.predictor import Predictor
from social_v4.engine import SocialEngine
from social_world_zh.memory import MemoryStore
from social_world_zh.schema import Observation
from social_world_zh.adapter import command_from_decision,Simulator
from social_v4.parity import run_probe

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',default='cuda',choices=['cuda','cpu']);args=parser.parse_args();started=time.time()
    p=Predictor(args.device);model=p.model;records=[];integrated=[]
    with torch.inference_mode():
        inputs=model.tokenizer(['任务：理解当前中文对话状态。\n当前用户：帮我打开客厅灯\n当前状态：'],return_tensors='pt').to(args.device)
        before=model.original_logits(**inputs)
        if model.state_heads is not None:model.state_logits(**inputs)
        generated=p.generate_dialogue([],'请用一句话打个招呼。')
        after=model.original_logits(**inputs)
        route_equal={k:bool(torch.equal(before[k],after[k])) for k in before}
        assert all(route_equal.values()),route_equal
        assert model.backbone.active_adapter=='default'
    with tempfile.TemporaryDirectory(prefix='social_v4_verify_') as folder:
        memory=MemoryStore(Path(folder)/'memory.sqlite');engine=SocialEngine(p,memory)
        def run(id,**kw):
            r=engine.step(Observation(**kw));records.append({'id':id,'input':kw,'result':r});return r
        try:
            a=run('context_first',speech='我妹妹叫小雨，她明天来我家吃饭。')
            b=run('context_followup',speech='刚才我说谁明天来？')
            assert b['history_turns_used']>0
            assert b['dialogue']['history_turns_used']>0,b
            r=run('explicit_silence',speech='请先别打扰我');assert r['action']=='SILENCE' and r['response']==''
            r=run('silence_retained',speech='嗯');assert r['action']=='SILENCE'
            r=run('reopen',speech='现在可以聊天了');assert r['boundary_state']=='open'
            r=run('low_asr',speech='过来',asr_confidence=.2,motion_authorized=True);assert r['action']=='CLARIFY' and not r['motion']['authorized']
            r=run('device_confirmation',speech='打开客厅灯',task_execution_authorized=True,target_device='living_light',confirmed_task_intent='iot_hue_lighton')
            assert r['task']['authorized'] and r['task']['execution_status']=='not_executed'
            command=command_from_decision(r);sim=Simulator();assert sim.submit(command)['status']=='acknowledged' and sim.devices['living_light']=='turn_on'
            r=run('no_consent',speech='我喜欢蓝色',user_id='private',identity_verified=True,memory_consent=False,memory_note='喜欢蓝色');assert not r['memory_persisted'] and memory.read('private')['interaction_count']==0
            engine.forget('private');assert all(k[1]!='private' for k in engine.sessions)
            if args.device=='cuda':
                cases=json.loads((ROOT/'data/dialogue_development_cases.json').read_text(encoding='utf-8'))
                for case in cases:
                    session_id='dev_'+case['id'];key=(session_id,'development')
                    engine.sessions[key]={'time':time.monotonic(),'history':[tuple(x) for x in case['history']],'memory':memory.empty()}
                    result=engine.step(Observation(user_id='development',session_id=session_id,speech=case['speech']))
                    integrated.append({'id':case['id'],'rubric':case['rubric'],'result':result})
                    print(json.dumps({'type':'integrated_dialogue','id':case['id'],'action':result['action'],'reply':result['response'],'generation':result['dialogue']['status']},ensure_ascii=False),flush=True)
        finally:memory.db.close()
    parity=run_probe(model,args.device)
    report={'device':args.device,'backend':p.backend,'physical_base_models':1,'original_logits_equal_after_state_and_dialogue':route_equal,'generation_smoke':generated,'records':records,'integrated_dialogue_development':integrated,'quantization_fidelity_probe':parity,'seconds':time.time()-started,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20 if args.device=='cuda' else None,'hardware_actuated':False,'checks_passed':True}
    (ROOT/'reports'/('runtime_'+args.device+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.device=='cpu' and (ROOT/'reports/cpu_export.json').exists():
        export=json.loads((ROOT/'reports/cpu_export.json').read_text());export.update(runtime_test_pending=False,runtime_checks_passed=True,calibration_note='GPU validation temperatures retained; CPU INT8 has not received a separate full benchmark calibration.')
        (ROOT/'reports/cpu_export.json').write_text(json.dumps(export,indent=2),encoding='utf-8')
    print(json.dumps({'checks_passed':True,'device':args.device,'seconds':report['seconds'],'peak_vram_mib':report['peak_vram_mib']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
