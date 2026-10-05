"""Robot-controller contract and runnable simulator, never a physical actuator."""
import time,uuid
TASK_OPERATIONS={'iot_hue_lighton':'turn_on','iot_hue_lightoff':'turn_off','iot_wemo_on':'turn_on','iot_wemo_off':'turn_off','iot_hue_lightup':'increase_brightness','iot_hue_lightdim':'decrease_brightness','audio_volume_up':'increase_volume','audio_volume_down':'decrease_volume','audio_volume_mute':'mute','cancel_current_task':'cancel'}
def command_from_decision(decision):
    command={'command_id':str(uuid.uuid4()),'issued_at_unix':time.time(),'expires_after_ms':1000,'kind':'hold','operation':'HOLD','payload':{}}
    if decision['motion']['authorized']:
        command.update(kind='motion',operation=decision['motion']['command'],payload={'min_distance_m':decision['motion']['min_distance_m'],'collision_check_required':True})
    elif decision['task']['authorized'] and decision['task']['intent'] in TASK_OPERATIONS:
        command.update(kind='device',operation=TASK_OPERATIONS[decision['task']['intent']],payload={'device_id':decision['task']['target_device']})
    return command

class Simulator:
    """Executable acknowledgement model for integration tests; not real robot proof."""
    def __init__(self):self.seen=set();self.devices={}
    def submit(self,command,collision_free=False):
        cid=command['command_id']
        if cid in self.seen:return {'command_id':cid,'status':'duplicate','simulated':True}
        if not 0<=time.time()-command['issued_at_unix']<=command['expires_after_ms']/1000:return {'command_id':cid,'status':'expired','simulated':True}
        if command['kind']=='motion' and not collision_free:return {'command_id':cid,'status':'collision_check_required','simulated':True}
        if command['kind']=='device':
            if not command['payload'].get('device_id') or command['operation'] not in TASK_OPERATIONS.values():return {'command_id':cid,'status':'invalid','simulated':True}
            self.devices[command['payload']['device_id']]=command['operation']
        self.seen.add(cid)
        return {'command_id':cid,'status':'held' if command['kind']=='hold' else 'acknowledged','simulated':True}
