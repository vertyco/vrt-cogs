"""A Flash sprite's playhead, for the animations whose frames decide game timing: a unit's blow lands, and a turret
fires, on a set frame of its animation. web/flash.js steps the same timelines the same way to draw them"""

import random

HOOKS = ("hit", "rhit", "shoot")


class Timeline:
    def __init__(self, spec: dict, rng: random.Random):
        self.frames: int = spec["frames"]
        self.actions: dict[int, list[tuple]] = spec["actions"]
        self.rng = rng
        self.frame = 0
        self.playing = True
        # A new timeline shows its first frame for a whole frame before it moves on
        self.fresh = True
        # Hooks reached while entering frames, collected until the owner takes them
        self.hooks: list[str] = []
        self.enter(1)

    def enter(self, frame: int) -> None:
        self.frame = frame
        for action in self.actions.get(frame, ()):
            if self.run(action):
                break

    def run(self, action: tuple) -> bool:
        """Do one frame action. True when it moved the playhead, which ends that frame's script"""
        kind = action[0]
        if kind == "stop":
            self.playing = False
        elif kind == "play":
            self.playing = True
            self.enter(max(1, action[1]))
            return True
        elif kind == "pick":
            self.playing = True
            self.enter(self.rng.choice(action[1]))
            return True
        elif kind == "rstop":
            self.playing = False
            self.frame = self.rng.randint(action[1], action[2])
            return True
        elif kind == "rplay":
            self.playing = True
            self.enter(max(1, self.rng.randint(action[1], action[2])))
            return True
        elif kind in HOOKS:
            self.hooks.append(kind)
        return False

    def play(self) -> None:
        self.playing = True

    def advance(self) -> list[str]:
        """One frame of the clock. Returns the game hooks the playhead reached"""
        if self.fresh:
            self.fresh = False
        elif self.playing and self.frames > 1:
            self.enter(1 if self.frame >= self.frames else self.frame + 1)
        hooks, self.hooks = self.hooks, []
        return hooks
