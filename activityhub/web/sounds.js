// Menu sounds for the Orb theme. Move, select and back are built from tones and noise on the fly; the menu
// whoosh and the background loop are files.

function envelope(ctx, when, attack, hold, release, peak) {
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0, when);
  gain.gain.linearRampToValueAtTime(peak, when + attack);
  gain.gain.setValueAtTime(peak, when + attack + hold);
  gain.gain.linearRampToValueAtTime(0, when + attack + hold + release);
  return gain;
}

function tone(ctx, out, frequency, level, when, length) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = frequency;
  gain.gain.value = level;
  osc.connect(gain).connect(out);
  osc.start(when);
  osc.stop(when + length);
  return gain;
}

// A short bright tick: three close tones that beat against each other, opened by a burst of hiss
function move(ctx, out, when) {
  const body = envelope(ctx, when, 0.002, 0.009, 0.022, 0.5);
  body.connect(out);
  tone(ctx, body, 2665, 0.6, when, 0.04);
  tone(ctx, body, 2518, 0.25, when, 0.04);
  tone(ctx, body, 2214, 0.15, when, 0.04);
  const noise = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * 0.005), ctx.sampleRate);
  const samples = noise.getChannelData(0);
  for (let i = 0; i < samples.length; i++) {
    samples[i] = Math.random() * 2 - 1;
  }
  const hiss = ctx.createBufferSource();
  hiss.buffer = noise;
  const filter = ctx.createBiquadFilter();
  filter.type = "highpass";
  filter.frequency.value = 500;
  const click = envelope(ctx, when, 0.0005, 0.001, 0.0035, 0.2);
  hiss.connect(filter).connect(click).connect(out);
  hiss.start(when);
}

// A steady round tone over a soft wobbling undertone, then a quick fade. Back is the same, a third lower.
function chime(ctx, out, when, pitch) {
  const body = envelope(ctx, when, 0.005, 0.235, 0.105, 1);
  body.connect(out);
  tone(ctx, body, 431 * pitch, 0.5, when, 0.36);
  tone(ctx, body, 703 * pitch, 0.008, when, 0.36);
  tone(ctx, body, 896 * pitch, 0.008, when, 0.36);
  const under = tone(ctx, body, 158 * pitch, 0.1, when, 0.36);
  const wobble = ctx.createOscillator();
  const depth = ctx.createGain();
  wobble.frequency.value = 33;
  depth.gain.value = 0.04;
  wobble.connect(depth).connect(under.gain);
  wobble.start(when);
  wobble.stop(when + 0.36);
}

export const SOUNDS = {
  move,
  select: (ctx, out, when) => chime(ctx, out, when, 1),
  back: (ctx, out, when) => chime(ctx, out, when, 0.8),
};

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
        .then((resp) => resp.arrayBuffer())
        .then((data) => this.ctx.decodeAudioData(data));
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
