// Plays a shot back at the original's 25 steps a second. The bot worked the whole shot out at once and sent it as
// a script: each shell's path, one point per step, and what happened on which step (blasts, ground, tanks,
// deaths, teleports). Every screen plays the same script on the same clock, so everyone sees the same shot.

// The same number as tanks/common/physics.py (tests/test_page.py checks they match)
const STEP_RATE = 25;
const STEP_MS = 1000 / STEP_RATE;

export class Playback {
  constructor(script, now) {
    this.script = script;
    this.start = now;
    this.next = 0;
  }

  // Draws the shot as it is at `now`. True once it has finished
  update(now, scene) {
    const step = (now - this.start) / STEP_MS;
    this.runEvents(Math.floor(step), scene);
    if (step >= this.script.steps) {
      scene.setShells([]);
      return true;
    }
    scene.setShells(this.shellsAt(step));
    return false;
  }

  // Jumps to the end, for a screen that fell behind
  finish(scene) {
    this.runEvents(Infinity, scene);
    scene.setShells([]);
  }

  runEvents(upTo, scene) {
    const events = this.script.events;
    while (this.next < events.length && events[this.next][0] <= upTo) {
      scene.shotEvent(events[this.next]);
      this.next += 1;
    }
  }

  // Every shell in the air at `step`, slid between its two nearest points
  shellsAt(step) {
    const shells = [];
    this.script.shells.forEach(([start, flat], index) => {
      const at = step - start;
      const count = flat.length / 2;
      if (at < 0 || at > count - 1) {
        return;
      }
      const i = Math.floor(at);
      const j = Math.min(i + 1, count - 1);
      const t = at - i;
      const x = flat[2 * i] + (flat[2 * j] - flat[2 * i]) * t;
      const y = flat[2 * i + 1] + (flat[2 * j + 1] - flat[2 * i + 1]) * t;
      shells.push({ index, x, y });
    });
    return shells;
  }
}
