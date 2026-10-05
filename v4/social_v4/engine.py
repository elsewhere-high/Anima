"""Chinese multi-turn responses with existing memory and controller contracts."""
import time
from .runtime_model import V2
from social_world_zh.engine import SocialEngine as OriginalEngine
from .response_guard import guard_reply,missing_visual_input

CONVERSATION_ACTIONS = {'GREET', 'RESPOND', 'COMFORT', 'ENCOURAGE', 'OFFER_HELP', 'CHANGE_TOPIC'}


class SocialEngine(OriginalEngine):
    def step(self, observation):
        started = time.monotonic()
        with self.lock:
            key = (observation.session_id, observation.user_id)
            session = self.sessions.get(key)
            history = list(session['history']) if session and time.monotonic() - session['time'] < 300 else []
            # Original controller, consent and memory rules run before text generation.
            result = super().step(observation.model_copy(update={'local_reasoning': False}))
            action = result['action']
            conversational = action in CONVERSATION_ACTIONS
            if action == 'CLOUD_REASON' and result.get('reasoning', {}).get('status') != 'ok': conversational = True
            # Both confident and uncertain clarification policies need the same
            # context. Hardware authorization remains exactly the controller's.
            if action == 'CLARIFY':
                conversational = True
            if action == 'TASK_REQUEST' and not result['task']['authorized']:
                conversational = True
            if action == 'CALL_HUMAN' and not observation.emergency_verified:
                # A learned class on ordinary frustration is not permission to
                # contact another person. Retain the class as a suggestion only.
                result['human_request'] = False
                result['human_assistance'] = {'status':'unconfirmed_suggestion','authorized':False}
                conversational = True
            allowed = (conversational and observation.person_present and bool(observation.speech.strip())
                       and observation.asr_confidence >= .65 and not observation.emergency_verified
                       and result['boundary_state'] != 'do_not_disturb'
                       and result['state']['user_preference']['style'] != 'silent')
            result['dialogue'] = {'status': 'controller_template', 'action_authority': False, 'history_turns_used': 0}
            if allowed:
                policy = {'action': action, 'style': result['state']['user_preference']['style'], 'boundary': result['boundary_state'], 'emotion_is_uncertain_hypothesis': True}
                if action == 'TASK_REQUEST':policy['设备执行尚未授权，只可询问或解释'] = True
                if action == 'CALL_HUMAN':policy.update(action='RESPOND',no_human_contact_sent=True)
                if missing_visual_input(observation.speech):
                    generated = {'status':'capability_boundary','reply':'我目前没有收到图像，不能判断眼前物品的颜色或外观。你可以用文字描述一下。','tokens':0,'action_authority':False,'reason':'no_image_input'}
                else:
                    generated = self.predictor.generate_dialogue(history, observation.speech, result['retrieved_memories'], policy)
                result['dialogue'] = {**generated, 'history_turns_used': min(10, len(history))}
                if generated.get('reply'):
                    checked = guard_reply(generated['reply'],observation.speech)
                    result['response'] = checked['reply']
                    result['dialogue']['reply'] = checked['reply']
                    result['dialogue']['grounding_guard'] = checked['reason']
            if 'sentiment' in result['neural']:
                result['state']['sentiment_cped'] = result['neural']['sentiment']
            if observation.person_present and key in self.sessions:
                turns = ([('用户', observation.speech)] if observation.speech.strip() else []) + ([('对方', result['response'])] if result['response'] else [])
                self.sessions[key]['history'] = (history + turns)[-12:]
            result['forecast_enabled'] = False
            result['version'] = '4.0.0'
            result['latency_ms'] = (time.monotonic() - started) * 1000
            return result
