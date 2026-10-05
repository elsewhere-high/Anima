import os,httpx

class CloudReasoner:
    """Optional generic JSON gateway. No external traffic without per-request consent."""
    def __init__(self):
        self.url=os.getenv('SOCIAL_CLOUD_URL',''); self.token=os.getenv('SOCIAL_CLOUD_TOKEN','')
        self.protocol=os.getenv('SOCIAL_CLOUD_PROTOCOL','json_gateway')
        self.model=os.getenv('SOCIAL_CLOUD_MODEL','')
    def reason(self,o,decision):
        if not self.url: return {'status':'unconfigured','reply':'这个问题我暂时无法在本地可靠回答，可以请人协助。'}
        if not o['cloud_consent']: return {'status':'consent_required','reply':'需要联网进一步分析，请先允许这次云端请求。'}
        # Identity, stored memories, raw sensors are deliberately not sent.
        try:
            if self.protocol=='chat_completions':
                if not self.model: return {'status':'unconfigured','reply':'云端模型名称尚未配置，可以请人协助。'}
                payload={'model':self.model,'messages':[{'role':'system','content':'你是机器人的社会交互顾问。只给简短建议，不执行任何动作，不诊断心理或医疗问题。不确定时说明不确定并建议向当事人温和确认。请用中文在150字以内回答。'},{'role':'user','content':o['speech']}],'max_tokens':256,'temperature':.3,'stream':False}
            else: payload={'speech':o['speech'],'task':'social_reasoning','max_reply_chars':300}
            r=httpx.post(self.url,json=payload,headers={'Authorization':'Bearer '+self.token} if self.token else {},timeout=8)
            r.raise_for_status(); data=r.json()
            if self.protocol=='chat_completions': data={'reply':data['choices'][0]['message']['content']}
            if not isinstance(data.get('reply'),str): raise ValueError('gateway reply must be a string')
            return {'status':'ok','reply':data['reply'][:300]}
        except (httpx.HTTPError,ValueError,TypeError,KeyError,IndexError):
            return {'status':'unavailable','reply':'暂时无法连接进一步分析服务，可以请人协助。'}
