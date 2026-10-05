"""Reuse trained V4 adapters; supply source-labelled memories and visual cues."""
import os
from social_v4.predictor import Predictor as V4Predictor
from social_v4.chat_model import generate_text

class Predictor(V4Predictor):
    def generate_dialogue(self,history,speech,memories=None,policy=None):
        selected=[];used=0
        for memory in memories or []:
            if used+len(memory)>600:continue
            selected.append(memory);used+=len(memory)
        from .conversation import build_messages
        messages=build_messages(history,speech,selected,policy)
        with self.lock:
            # State adapters remain active for classification. Dialogue route is independently selectable.
            route=os.getenv('SOCIAL_DIALOGUE_ROUTE','dialogue')
            if route not in {'base','dialogue'}:raise ValueError('SOCIAL_DIALOGUE_ROUTE must be base or dialogue')
            if route=='dialogue' and not self.model.dialogue_loaded:route='base'
            with self.model.route(route):
                result=generate_text(self.model.backbone,self.model.tokenizer,messages,device=self.device,max_context_tokens=4096, max_new_tokens=128,max_sentences=2)
            result['adapter']=route;result['memory_records_used']=len(selected);return result
