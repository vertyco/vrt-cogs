// Menu sounds for the Orb theme. Move, select and back are soft bell tones built on the fly; the menu whoosh
// and the background loop are files.

// A level that jumps up at once and dies away smoothly, the way a struck bell does
function strike(ctx, out, when, peak, length) {
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(peak, when + 0.004);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + length);
  gain.connect(out);
  return gain;
}

function tone(ctx, out, frequency, level, when, length) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = frequency;
  gain.gain.value = level;
  osc.connect(gain).connect(out);
  osc.start(when);
  osc.stop(when + length + 0.02);
  return osc;
}

// A pure note with two faint overtones, so it rings like a small glass bell instead of beeping
function bell(ctx, out, frequency, when, peak, length) {
  const body = strike(ctx, out, when, peak, length);
  tone(ctx, body, frequency, 1, when, length);
  tone(ctx, body, frequency * 2, 0.2, when, length);
  tone(ctx, body, frequency * 3, 0.05, when, length);
}

// A droplet tick: one high note that slides down a little as it dies away, quick enough to scroll through
function move(ctx, out, when) {
  const body = strike(ctx, out, when, 0.3, 0.07);
  const osc = tone(ctx, body, 1700, 1, when, 0.07);
  osc.detune.setValueAtTime(500, when);
  osc.detune.setTargetAtTime(0, when, 0.012);
}

// Two bell notes going up, over a soft low thump that gives a launch some weight
function select(ctx, out, when) {
  const thump = strike(ctx, out, when, 0.35, 0.18);
  const low = tone(ctx, thump, 110, 1, when, 0.18);
  low.detune.setValueAtTime(1200, when);
  low.detune.setTargetAtTime(0, when, 0.03);
  bell(ctx, out, 880, when, 0.28, 0.45);
  bell(ctx, out, 1318.5, when + 0.075, 0.24, 0.6);
}

// Two quieter, shorter notes going down
function back(ctx, out, when) {
  bell(ctx, out, 1174.7, when, 0.3, 0.3);
  bell(ctx, out, 784, when + 0.07, 0.26, 0.4);
}

export const SOUNDS = { move, select, back };

const FILES = {
  menu: new URL("sounds/menu.mp3", import.meta.url).href,
  ambient: new URL("sounds/ambient.mp3", import.meta.url).href,
};
const VOLUME = 0.3;
const AMBIENT_VOLUME = 0.45;

function activated() {
  return !navigator.userActivation || navigator.userActivation.hasBeenActive;
}

export class MenuSounds {
  constructor() {
    this.enabled = false;
    this.inMenu = true;
    this.ctx = null;
    this.volume = null;
    this.buffers = {};
    this.ambientOn = false;
    this.ambientElement = null;
    this.ambientNode = null;
    // Browsers only let a page make sound after the player clicks, taps or presses a key,
    // unless the frame around it allows autoplay
    for (const type of ["pointerdown", "keydown"]) {
      document.addEventListener(type, () => this.unlock(), { capture: true });
    }
    document.addEventListener("visibilitychange", () => this.updateAmbient());
  }

  setEnabled(on) {
    this.enabled = on;
    if (on) {
      this.prepare();
    }
    this.updateAmbient();
  }

  // The background loop plays only while the menu shows; a game brings its own sound
  setInMenu(on) {
    this.inMenu = on;
    this.updateAmbient();
  }

  prepare() {
    if (this.ctx) {
      return;
    }
    this.ctx = new AudioContext();
    this.volume = this.ctx.createGain();
    this.volume.gain.value = VOLUME;
    this.volume.connect(this.ctx.destination);
    this.ctx.addEventListener("statechange", () => this.updateAmbient());
  }

  unlock() {
    if (!this.enabled) {
      return;
    }
    this.prepare();
    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch((e) => console.error(e));
    }
  }

  // Before the first click a hover makes no sound, rather than every hover sounding at once on that click
  run(start) {
    if (!this.enabled) {
      return;
    }
    this.unlock();
    if (this.ctx.state === "running") {
      start();
    } else if (activated()) {
      this.ctx.resume().then(start, (e) => console.error(e));
    }
  }

  play(name) {
    this.run(() => SOUNDS[name](this.ctx, this.volume, this.ctx.currentTime + 0.005));
  }

  playFile(name) {
    this.run(() => {
      this.load(name).then(
        (buffer) => {
          const source = this.ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(this.volume);
          source.start();
        },
        (e) => console.error(e),
      );
    });
  }

  load(name) {
    if (!this.buffers[name]) {
      this.buffers[name] = fetch(FILES[name])
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`Couldn't load the ${name} sound (${resp.status})`);
          }
          return resp.arrayBuffer();
        })
        .then((data) => this.ctx.decodeAudioData(data))
        .catch((e) => {
          // A failed load is tried again next time instead of silencing the sound for the whole visit
          delete this.buffers[name];
          throw e;
        });
    }
    return this.buffers[name];
  }

  // The loop streams from an audio element instead of being decoded whole, which would take a lot of a
  // phone's memory; it still runs through the volume control, since phones ignore an element's own volume
  updateAmbient() {
    const want = this.enabled && this.inMenu && !document.hidden && this.ctx && this.ctx.state === "running";
    if (want && !this.ambientOn) {
      if (!this.ambientNode) {
        this.ambientElement = new Audio(FILES.ambient);
        this.ambientElement.loop = true;
        this.ambientNode = this.ctx.createGain();
        this.ctx.createMediaElementSource(this.ambientElement).connect(this.ambientNode).connect(this.volume);
      }
      this.ambientOn = true;
      const now = this.ctx.currentTime;
      this.ambientNode.gain.cancelScheduledValues(now);
      this.ambientNode.gain.setValueAtTime(0, now);
      this.ambientNode.gain.linearRampToValueAtTime(AMBIENT_VOLUME, now + 1.5);
      this.ambientElement.play().catch((e) => console.error(e));
    } else if (!want && this.ambientOn) {
      this.ambientOn = false;
      this.ambientElement.pause();
    }
  }
}
