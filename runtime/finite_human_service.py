"""Explicit finite service;original commands,projections,principals and HTTP."""
from collections import deque
import queue
import threading
from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from .hierarchical_human_service import InteractiveHumanService as BaseService,ObservedKernel
from .hierarchical_human_kernel import LiveKernelConfiguration
from .finite_human_kernel import FiniteLiveRealtimeKernel
from .live_operation_receipts import LiveOperationReceipts


class ObservedFiniteKernel(ObservedKernel,FiniteLiveRealtimeKernel):
    pass


class FiniteHumanService(BaseService):
    def __init__(self,directory,*,finite_catalogue,capacity=None):
        self.kernel = ObservedFiniteKernel(directory,t.EpisodeSettings(100,0.,0.,0.),LiveKernelConfiguration(
            capacity or EpisodeCapacity(4096,256,128,4096,65536,65536)),finite_catalogue=finite_catalogue)
        self.normal = queue.Queue(256); self.safety = queue.Queue(64)
        self.lock = threading.Lock(); self.stop_event = threading.Event()
        self.operations = {}; self.latest = {'protocol':'vsem.core-human.v3','availability':'INITIALIZING'}
        self.live_receipts = LiveOperationReceipts()
        self.image_records = {}; self.latest_image = None; self.history = []
        self.failure = None; self._image_index = 0
        self.thread = threading.Thread(target=self._run,name='vsem-trusted-service',daemon=True); self.thread.start()
