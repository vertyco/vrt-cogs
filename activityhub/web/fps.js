// The frame rate counter in the corner, over the menu and over a game. A game's frame shares the menu's thread,
// so a game that can't keep up slows the menu's own frames too, and counting them here works for every game.
const SAMPLE_MS = 500;

export class FrameRate {
  constructor() {
    this.node = document.createElement("div");
    this.node.className = "fps";
    this.node.setAttribute("aria-hidden", "true");
    this.node.hidden = true;
    document.body.append(this.node);
    this.request = null;
    this.frames = 0;
    this.since = 0;
    this.fps = null;
    // The open game's round trip to the bot in milliseconds, while it has a live connection
    this.latency = null;
    // A game's own figure after the frame rate, like "30 TPS", from hub.stat()
    this.stat = "";
    this.tick = this.tick.bind(this);
    // The browser stops drawing a hidden page, so the first count after coming back would cover that gap
    document.addEventListener("visibilitychange", () => this.restart());
  }

  setEnabled(on) {
    if (on === (this.request !== null)) {
      return;
    }
    this.node.hidden = !on;
    cancelAnimationFrame(this.request);
    this.request = null;
    if (on) {
      this.fps = null;
      this.node.textContent = "";
      this.restart();
      this.request = requestAnimationFrame(this.tick);
    }
  }

  setLatency(ms) {
    this.latency = ms;
    this.show();
  }

  setStat(text) {
    this.stat = text;
    this.show();
  }

  show() {
    if (this.fps === null) {
      return;
    }
    const parts = [`${this.fps} FPS`];
    if (this.latency !== null) {
      parts.push(`${this.latency} ms`);
    }
    if (this.stat) {
      parts.push(this.stat);
    }
    this.node.textContent = parts.join(" · ");
  }

  restart() {
    this.frames = 0;
    this.since = performance.now();
  }

  tick(now) {
    this.frames += 1;
    if (now - this.since >= SAMPLE_MS) {
      this.fps = Math.round((this.frames * 1000) / (now - this.since));
      this.show();
      this.restart();
    }
    this.request = requestAnimationFrame(this.tick);
  }
}
