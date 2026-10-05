"""Live Qwen dialogue samples, not an accuracy benchmark. Uses/deletes a test member."""
import argparse, base64, json, secrets, time, urllib.request
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='after');args=parser.parse_args()
    headers={'Content-Type':'application/json'};report={'samples':[]}
    def call(path, data=None, method=None):
        request=urllib.request.Request('http://127.0.0.1:8768'+path,
            data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers=headers,method=method)
        with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
    member=call('/v1/members',{'user_id':'dialogue_test_'+secrets.token_hex(5),'display_name':'对话回归测试',
                             'pin':secrets.token_urlsafe(16),'memory_consent':False})
    headers['X-Member-Session']=member['session_token']
    try:
        report['health']=call('/health')
        cases={
            'listen':['今天我花了很久做晚饭，儿子回来就说不好吃，我挺难过的。先别给我建议。',
                      '主要是他连尝都没尝，就看了一眼。','对，我就是觉得自己忙活了半天，心意没人看见。',
                      '你一直问问题也让我挺累的，像在做访谈。','现在帮我想一句可以对他说的话吧。'],
            'joy':['今天我种的茉莉终于开花了，特别开心。','白色的小花，一共开了三朵。',
                   '我不是说难过，我是觉得很惊喜。','我刚才说种的是什么，开了几朵？']}
        for session,turns in cases.items():
            for speech in turns:
                start=time.monotonic();result=call('/v1/step',{'observation':{'speech':speech,'session_id':session}})
                item={'session':session,'speech':speech,'response':result['response'],
                      'seconds':round(time.monotonic()-start,3),'dialogue':result.get('dialogue'),
                      'plan':result.get('response_plan',{}).get('conversation')}
                assert not result['motion']['authorized']
                report['samples'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
        if args.label != 'before':
            asset=Path(__file__).resolve().parents[1]/'tests/assets/astronaut.png'
            encoded=base64.b64encode(asset.read_bytes()).decode()
            for _ in range(3):
                visual=call('/v1/vision/analyze',{'image_base64':encoded,'camera_id':'geometry-test'})
                time.sleep(1.05)
            face=visual['human_state']['face']
            report['geometry']={'fixture':'astronaut.png (repeated fixture, not live emotion accuracy)',
                'mesh_points':len(face['face_mesh']),'blendshapes':len(face['facial_blendshapes']),
                'actions':face['stable_actions'],'samples':face['action_sample_count'],
                'latency_ms':visual['latency_ms']}
            assert len(face['face_mesh'])==478 and len(face['facial_blendshapes'])==52
            result=call('/v1/step',{'observation':{'speech':'看看我的表情','session_id':'geometry-test','visual_frame_id':visual['frame_id']}})
            report['geometry']['reply']=result['response']
    finally:
        call('/v1/member',method='DELETE');report['test_member_deleted']=True
        path=Path(__file__).resolve().parents[1]/'reports'/('emotion_dialogue_'+args.label+'.json')
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
