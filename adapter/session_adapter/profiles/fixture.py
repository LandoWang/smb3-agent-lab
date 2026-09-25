"""Deterministic toy environment. NOT Mario or evidence of model performance."""
import json
from ..contracts import Action, Sample


class Fixture:
    bootstrap_frames = 0
    metric_names = {"x", "y", "vx", "airborne", "reward"}
    skills = {"right":{"buttons":["RIGHT"],"description":"Move right"},
              "jump":{"buttons":["RIGHT","A"],"description":"Jump and continue right"},
              "release":{"buttons":[],"description":"Release controls for a simulated frame"}}
    actions = [Action(f"{s}_{n}",s,tuple(v["buttons"]),n) for s,v in skills.items() for n in (6,12,24,36)]

    def __init__(self, goal=96, death_at=None, hazard_at=40):
        self.metadata={"game":"fixture-not-mario","profile_version":"1", "fps":60.0,
            "goal_kinds":['reach_region','hit_block','collect_item','avoid_entity','clear_obstacle','custom'],
            "goal_verifiers":{'reach_region':{'method':'metric_region','x_metric':'x','y_metric':'y','airborne_metric':'airborne'}},
            "observation_mode":"synthetic_fixture","emulator":{"name":"deterministic-python-fixture","version":"1"},
            "reward_source":"synthetic_x_progress", "instructions":"Toy fixture, not Mario. Move right to the synthetic goal."}
        self.x=self.y=self.vy=self.frame=0
        self.a_held=0
        self.last=()
        self.goal,self.death_at,self.hazard_at=goal,death_at,hazard_at
        self.current=self._sample([])

    def _sample(self,events):
        terminal="death" if self.death_at is not None and self.x>=self.death_at else "complete" if self.x>=self.goal else None
        metrics={"x":self.x,"y":self.y,"vx":1 if "RIGHT" in self.last else 0,
                 "airborne":self.y>0,"reward":int("RIGHT" in self.last)}
        image=(f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240"><rect width="640" height="240" fill="#eaf3ef"/>'
            f'<text x="20" y="30" font-size="18">SCRIPTED FIXTURE — NOT MARIO · F{self.frame}</text>'
            f'<path d="M0 205H640" stroke="#24685a"/><rect x="{20+self.x*4}" y="{180-self.y*4}" width="20" height="25" fill="#d15b42"/>'
            f'<text x="20" y="65">A held: {self.a_held} frames</text></svg>').encode()
        return Sample({"player":metrics,"a_held_frames":self.a_held},metrics,events,terminal,image,"svg")

    def observe(self): return self.current

    def advance(self,buttons):
        old_x=self.x
        if "A" in buttons and "A" not in self.last and self.y==0: self.vy=4
        self.a_held=self.a_held+1 if "A" in buttons else 0
        self.x += int("RIGHT" in buttons)
        self.y=max(0,self.y+self.vy)
        self.vy=self.vy-1 if self.y else 0
        self.frame+=1; self.last=buttons
        events=["observe","replan"] if old_x<self.hazard_at<=self.x else []
        self.current=self._sample(events)
        return self.current

    def checkpoint(self):
        return json.dumps({"frame":self.frame,"x":self.x,"y":self.y,"vy":self.vy,"last":self.last,"a_held":self.a_held}).encode()

    def view(self,sample,role): return sample.state
    def eligible(self,action,sample): return True,""
    def close(self): pass
