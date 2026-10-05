"""Independent bounded perception lanes: no backlog, no Qwen on video frames."""
import threading
from concurrent.futures import ThreadPoolExecutor

class BusyError(RuntimeError):pass

class PerceptionScheduler:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='social-perception')
        self.slots={k:threading.BoundedSemaphore(1) for k in ['face','body','audio']}
    def submit(self,lane,fn,*args,**kwargs):
        slot=self.slots[lane]
        if not slot.acquire(blocking=False):raise BusyError(lane+' perception busy; drop stale sample')
        def work():
            try:return fn(*args,**kwargs)
            finally:slot.release()
        try:return self.pool.submit(work)
        except Exception:slot.release();raise
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
