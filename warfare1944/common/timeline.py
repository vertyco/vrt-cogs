"""A Flash sprite's playhead, for the animations whose frames decide game timing: a soldier is busy for as long as its
animation plays, a tank gun reloads while its animation runs, and a turret is turning until its animation stops. web/flash.js steps
the same timelines the same way to draw them (its Clip: enter, advance, gotoAndStop, gotoAndPlay), so the bot and the
page agree frame for frame."""

HOOKS = ("throw", "runloop", "rocket", "mortar", "mortarend")


class Timeline:
    def __init__(self, spec: dict, flags: dict | None = None):
        """`spec` is one of common/anims.py's timeline tables (SOLDIER, the guns, a turret). `flags` is the dict the
        frame scripts write into: the soldier's own variables, the tank's (the guns' `_parent`), or a turret's own. A new
        dict when left out"""
        self.frames: int = spec["frames"]
        self.labels: dict[str, int] = spec["labels"]
        self.actions: dict[int, list[tuple]] = spec["actions"]
        self.flags: dict = {} if flags is None else flags
        self.frame = 0
        self.playing = True
        # A new timeline shows its first frame for a whole frame before it moves on
        self.fresh = True
        # Hooks reached while entering frames, held until the next advance hands them to the owner
        self.hooks: list[str] = []
        self.enter(1)

    @property
    def busy(self) -> bool:
        return bool(self.flags.get("animating"))

    def frame_of(self, target: str | int) -> int:
        return self.labels[target] if isinstance(target, str) else target

    def enter(self, frame: int) -> None:
        """Arrive on a frame and run its script, which stops at the first action that moves the playhead"""
        self.frame = frame
        for action in self.actions.get(frame, ()):
            if self.run(action):
                break

    def run(self, action: tuple) -> bool:
        """Do one frame action. True when it moved the playhead, which ends that frame's script"""
        kind = action[0]
        if kind == "set":
            self.flags[action[1]] = action[2]
        elif kind == "stop":
            self.playing = False
        elif kind == "play":
            self.playing = True
        elif kind == "goto":
            self.goto_and_stop(action[1])
            self.playing = action[2]
            return True
        elif kind in HOOKS:
            self.hooks.append(kind)
        return False

    def goto_and_stop(self, target: str | int) -> None:
        """Flash's gotoAndStop: a jump to the frame already showing changes nothing"""
        frame = self.frame_of(target)
        self.playing = False
        if frame != self.frame:
            self.enter(min(frame, self.frames))
            self.playing = False

    def goto_and_play(self, target: str | int) -> None:
        """Flash's gotoAndPlay: plays from the frame's script, which may stop it again"""
        self.playing = True
        self.enter(min(self.frame_of(target), self.frames))

    def play(self) -> None:
        self.playing = True

    def stop(self) -> None:
        self.playing = False

    def advance(self) -> list[str]:
        """One step of the clock. Returns the hooks (HOOKS) the playhead reached since the last call"""
        if self.fresh:
            self.fresh = False
        elif self.playing and self.frames > 1:
            self.enter(1 if self.frame >= self.frames else self.frame + 1)
        hooks, self.hooks = self.hooks, []
        return hooks
