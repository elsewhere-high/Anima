"""Interactive UTF-8 client for the local V4 HTTP service."""
import os,uuid,argparse
import requests

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8767');parser.add_argument('--user',default='demo');args=parser.parse_args()
    session=uuid.uuid4().hex;headers={}
    if os.getenv('SOCIAL_API_TOKEN'):headers['Authorization']='Bearer '+os.environ['SOCIAL_API_TOKEN']
    print('中文多轮对话。输入 /quit 结束；当前不保存长期记忆。')
    while True:
        try:speech=input('你：').strip()
        except (EOFError,KeyboardInterrupt):break
        if speech=='/quit':break
        if not speech:continue
        response=requests.post(args.url+'/v1/step',json={'observation':{'user_id':args.user,'session_id':session,'speech':speech}},headers=headers,timeout=120)
        response.raise_for_status();data=response.json();emotion=data['state']['emotion']
        print('机器人：'+(data['response'] or '（保持安静）'))
        print(f"[当前情绪假设：{emotion.get('label_zh',emotion['label'])}，置信度 {emotion['confidence']:.2f}；策略 {data['action']}；{data['latency_ms']/1000:.2f} 秒]")

if __name__=='__main__':main()
