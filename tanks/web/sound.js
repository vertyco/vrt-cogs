// Tanks' sound: the original's effects, played through the Web Audio API so several can overlap.
const VOLUME = 0.7;
// Every game on the hub shares one storage, so the key carries the game's name
const SOUND_KEY = "tanks:sound";
// The events the page plays sounds for, and the original's sound for each
const FILES = {
  turret: "turret",
  click: "click",
  shop: "shop",
  tank_death: "tank_death",
  boom_small: "boom_small",
  boom_medium: "boom_medium",
  boom_big: "boom_big",
};
// The barrel's turning sound restarts at most this often while it keeps turning
const TURRET_GAP_MS = 120;

function readSetting() {
  try {
    return localStorage.getItem(SOUND_KEY) !== "off";
  } catch (e) {
    console.warn("Tanks: couldn't read the sound setting", e);
    return true;
  }
}

function saveSetting(on) {
  try {
    localStorage.setItem(SOUND_KEY, on ? "on" : "off");
  } catch (e) {
    console.warn("Tanks: couldn't save the sound setting", e);
  }
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.out = null;
    this.on = readSetting();
    this.buffers = new Map();
    this.loading = null;
    this.turretAt = 0;
    // Browsers only allow sound after the player touches the page
    const unlock = () => this.unlock();
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    document.addEventListener("visibilitychange", () => this.update());
    window.addEventListener("pagehide", () => this.close());
  }

  unlock() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.out = this.ctx.createGain();
      this.out.gain.value = VOLUME;
      this.out.connect(this.ctx.destination);
      this.loading = this.load();
    }
    this.update();
  }

  async load() {
    const names = [...new Set(Object.values(FILES))];
    await Promise.all(
      names.map(async (name) => {
        try {
          const resp = await fetch(`sounds/${name}.mp3`);
          if (!resp.ok) {
            throw new Error(`The sound file answered ${resp.status}`);
          }
          this.buffers.set(name, await this.ctx.decodeAudioData(await resp.arrayBuffer()));
        } catch (e) {
          console.warn(`Tanks: couldn't load the ${name} sound`, e);
        }
      }),
    );
  }

  // Pauses the sound while the page is hidden
  async update() {
    if (!this.ctx || this.ctx.state === "closed") {
      return;
    }
    try {
      await (document.hidden ? this.ctx.suspend() : this.ctx.resume());
    } catch (e) {
      console.warn("Tanks: couldn't start or pause the sound", e);
    }
  }

  setOn(on) {
    this.on = on;
    saveSetting(on);
  }

  play(event) {
    if (!this.on || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    if (event === "turret") {
      if (performance.now() - this.turretAt < TURRET_GAP_MS) {
        return;
      }
      this.turretAt = performance.now();
    }
    const buffer = this.buffers.get(FILES[event]);
    if (!buffer) {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.out);
    source.start();
  }

  close() {
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Tanks: couldn't close the sound", e));
    }
  }
}
