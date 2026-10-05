"""Run real learned model + state store + policy + simulated controller."""
import os,sys,json,time,argparse,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np,torch
from social_world_zh.predictor import Predictor
from social_world_zh.engine import SocialEngine
from social_world_zh.memory import MemoryStore
from social_world_zh.schema import Observation,ImagineRequest
from social_world_zh.adapter import command_from_decision,Simulator
from social_world_zh.spec import HEADS

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',default='cuda');p.add_argument('--generation',action='store_true');a=p.parse_args()
    started=time.time();predictor=Predictor(a.device);load_seconds=time.time()-started
    mem=MemoryStore(':memory:');engine=SocialEngine(predictor,mem);report={'device':a.device,'backend':predictor.backend,'load_seconds':load_seconds,'cases':[]}
    def case(name,obs,allowed):
        result=engine.step(Observation(**obs));ok=result['action'] in allowed
        report['cases'].append({'name':name,'observation':obs,'action':result['action'],'allowed':allowed,'passed':ok,'policy':result['neural']['policy']['label'],'policy_confidence':result['neural']['policy']['confidence'],'overrides':result['overrides'],'response':result['response']})
        return result
    common={'user_id':'alice','session_id':'home','identity_verified':True,'memory_consent':True}
    case('明确拒绝',dict(common,speech='我今天不太想说话，别打扰我'),['SILENCE'])
    case('下一轮维持边界',dict(common,speech='嗯，知道了'),['SILENCE'])
    case('另一人不继承边界',dict(user_id='bob',speech='你好，小助手'),['GREET','RESPOND','CLARIFY'])
    case('明确恢复',dict(common,speech='现在可以聊天了'),['RESPOND','GREET','CLARIFY'])
    case('保持距离',dict(common,speech='不要靠近，请保持距离'),['KEEP_DISTANCE'])
    case('结构化恢复',dict(common,speech='你好',boundary='open'),['GREET','RESPOND','CLARIFY'])
    case('低置信度语音',dict(speech='你过来一点',asr_confidence=.3,motion_authorized=True),['CLARIFY'])
    case('无人场景',dict(speech='',person_present=False),['SILENCE'])
    case('已核验紧急事件',dict(speech='别打扰我',emergency_verified=True),['CALL_HUMAN'])
    # New sessions avoid a refusal from previous cases leaking into these probes.
    probes=[('问候','早呀，我回来了',['GREET','RESPOND']),('倾诉','这几天工作压力好大，我想找人说说',['COMFORT']),('报喜','我努力了很久，终于通过考试啦',['ENCOURAGE']),('换话题','咱们别说工作的事了，聊点其他的吧',['CHANGE_TOPIC']),('取消任务','刚才安排的事情不用做了',['CANCEL_TASK']),('开灯','帮我打开客厅灯',['TASK_REQUEST']),('停止清扫','把扫地机器人关掉',['TASK_REQUEST','CLARIFY']),('含糊指代','帮我把那个搞一下',['CLARIFY']),('转述拒绝','电视里那个人说别打扰我',['RESPOND','CLARIFY']),('否定拒绝','我不是不想聊天，只是一时不知道说什么',['RESPOND','CLARIFY'])]
    for i,(name,speech,allowed) in enumerate(probes):case(name,dict(user_id='probe',session_id=f'p{i}',speech=speech),allowed)
    engine.forget('alice');report['forget_verified']=mem.read('alice')['interaction_count']==0
    imagination=engine.imagine(ImagineRequest(speech='今天工作不顺心，挺难过的',history=[('对方','今天过得怎么样？')],candidates=['听起来你很难受，我可以听你说。','这有什么好难过的。']))
    report['imagination']=imagination
    report['candidate_distribution_l1']=sum(abs(imagination['predictions'][0]['next_emotion']['distribution'][k]-imagination['predictions'][1]['next_emotion']['distribution'][k]) for k in HEADS['next_emotion'])
    device=engine.step(Observation(session_id='device',speech='帮我打开客厅灯',task_execution_authorized=True,target_device='living_light',confirmed_task_intent='iot_hue_lighton'))
    cmd=command_from_decision(device);sim=Simulator();report['controller']={'command':cmd,'ack':sim.submit(cmd),'devices':sim.devices,'raw_neural_intent':device['neural']['intent'],'task':device['task'],'overrides':device['overrides']}
    assert report['controller']['ack']['status']=='acknowledged' and sim.devices.get('living_light')=='turn_on',report['controller']
    texts=['你好，小助手','今天工作挺累的，想聊聊','请帮我打开客厅的灯','我想换个话题','这件事情让我有点为难']
    times=[]
    for i in range(45):
        t=time.perf_counter();engine.step(Observation(session_id='latency',speech=texts[i%len(texts)]))
        if a.device=='cuda':torch.cuda.synchronize()
        if i>=5:times.append((time.perf_counter()-t)*1000)
    report['latency']={'n':len(times),'warmup':5,'p50_ms':float(np.percentile(times,50)),'p95_ms':float(np.percentile(times,95)),'min_ms':min(times),'max_ms':max(times),'includes':'tokenization, real model, policy, in-memory state; up to four history turns','threads':torch.get_num_threads()}
    if a.device=='cpu':
        test=[json.loads(x) for x in (ROOT/'data/processed/test.jsonl').read_text(encoding='utf-8').splitlines()];gpu=np.load(ROOT/'reports/test_logits.npz');rng=np.random.default_rng(96);indices=rng.choice(len(test),256,replace=False)
        agree={k:[] for k in HEADS};correct={k:[] for k in HEADS};reference={k:[] for k in HEADS}
        for i in indices:
            active=list(test[i]['labels']);out=predictor.batch([test[i]['text']],active)[0]
            for k in active:
                actual=HEADS[k].index(out[k]['label']);expected=int(gpu[k][i].argmax());agree[k].append(actual==expected);correct[k].append(actual==test[i]['labels'][k]);reference[k].append(expected==test[i]['labels'][k])
        report['quantization_check']={k:{'n':len(v),'label_agreement':float(np.mean(v)),'cpu_accuracy':float(np.mean(correct[k])),'gpu_accuracy_same_subset':float(np.mean(reference[k]))} for k,v in agree.items() if v}
    if a.generation:report['local_generation']=predictor.generate_local('朋友最近不太愿意和我说话，我该怎么温和地问问原因？')
    report['passed']=sum(r['passed'] for r in report['cases']);report['total']=len(report['cases']);report['elapsed_seconds']=time.time()-started
    path=ROOT/'reports'/f'runtime_{a.device}.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['cases','imagination']},ensure_ascii=True,indent=2),flush=True)
    assert report['passed']==report['total'], 'Real-model development cases failed; see report'
if __name__=='__main__':main()
