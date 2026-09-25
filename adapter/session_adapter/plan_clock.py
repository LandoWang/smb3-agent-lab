"""Frame-based minimum dwell time for ordinary replans; explicit urgent bypass."""
from dataclasses import dataclass


@dataclass
class PlanClock:
    minimum: int
    maximum: int
    installed_frame: int = 0
    due_frame: int = 0
    reason: str = 'session_start'

    def install(self,frame,requested_interval):
        self.installed_frame=frame
        self.due_frame=frame+max(self.minimum,min(self.maximum,requested_interval))
        self.reason='frame_cadence'

    def request(self,frame,reason,urgent=False):
        requested_due=frame if urgent else max(frame,self.installed_frame+self.minimum)
        if requested_due<=self.due_frame:
            self.due_frame=requested_due
            self.reason=reason
        return {'reason':reason,'urgent':urgent,'effective_frame':self.due_frame,
            'deferred':self.due_frame>frame,'frames_since_plan':frame-self.installed_frame,
            'minimum_frames':self.minimum,
            'minimum_bypassed':urgent and frame-self.installed_frame<self.minimum}

    def due(self,frame): return frame>=self.due_frame
    def remaining(self,frame): return max(0,self.due_frame-frame)
