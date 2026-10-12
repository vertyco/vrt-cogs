// Sandfall's sound. Effects are made on the fly from tones and filtered noise: a hiss, a pour or a crackle while the
// player paints, and a bed that follows what the world reports (fire, steam, explosions, sparks). Music is four calm
// tracks played one at a time with long quiet gaps between them. Nothing here ever writes to the world.
import { EL, ELEMENTS } from "./sim/index.js";

const TRACKS = [
  { name: "Dune Light", url: "music/dune-light.mp3" },
  { name: "Glass Tide", url: "music/glass-tide.mp3" },
  { name: "Ember Hours", url: "music/ember-hours.mp3" },
  { name: "Settling Dust", url: "music/settling-dust.mp3" },
];
// The first track starts this long after the page opens, and each track is followed by a quiet gap in this range
const FIRST_DELAY_MS = 20000;
const QUIET_MIN_MS = 60000;
const QUIET_MAX_MS = 180000;
// Turning the music on by hand starts a track within this long, instead of waiting out the quiet gap
const SWITCH_ON_MS = 2000;
const TRACK_FADE_S = 3;
const TICK_MS = 500;

const MUSIC_LEVEL = 0.5;
const EFFECTS_LEVEL = 0.8;
// After the limiter: the compressor adds its own make-up gain, so this brings the ceiling down to the music's level
const LIMITER_TRIM = 0.5;
const DEFAULT_VOLUME = 70;
const MUSIC_KEY = "sandfall:music";
const EFFECTS_KEY = "sandfall:sfx";
const VOLUME_KEY = "sandfall:volume";

// The world is read at most this often, so a burst of caught-up batches doesn't pile up sounds
const WORLD_GAP_MS = 40;
// Fire cells at which the crackle reaches its full level
const FIRE_FULL = 400;
const MAX_CLICKS = 6;
const SIZZLE_GAP_MS = 140;
const BOOM_GAP_MS = 250;
const ZAP_GAP_MS = 110;
const BOLT_GAP_MS = 350;

// How loud each painting sound is while it plays, and the filter that shapes it
const PAINT_LAYERS = {
  powder: { type: "bandpass", frequency: 4200, q: 0.7, level: 0.06 },
  liquid: { type: "bandpass", frequency: 650, q: 1.1, level: 0.16 },
};
const LIQUID_BURBLE_HZ = 6;

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Sandfall: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Sandfall: couldn't save a sound setting", e);
  }
}

function readVolume() {
  try {
    const stored = localStorage.getItem(VOLUME_KEY);
    const volume = Number(stored);
    if (stored === null || !Number.isFinite(volume)) {
      return DEFAULT_VOLUME;
    }
    return Math.min(100, Math.max(0, Math.round(volume)));
  } catch (e) {
    console.warn("Sandfall: couldn't read the volume", e);
    return DEFAULT_VOLUME;
  }
}

function saveVolume(volume) {
  try {
    localStorage.setItem(VOLUME_KEY, String(volume));
  } catch (e) {
    console.warn("Sandfall: couldn't save the volume", e);
  }
}

/** The painting sound for the element under the brush: "powder", "liquid", "fire", or null for silence */
export function paintingKind(element) {
  if (element === EL.fire || element === EL.torch) {
    return "fire";
  }
  const kind = ELEMENTS[element]?.kind;
  return kind === "powder" || kind === "liquid" ? kind : null;
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.noiseBuffer = null;
    this.layers = {};
    this.volume = readVolume();
    this.musicOn = readSetting(MUSIC_KEY);
    this.sfxOn = readSetting(EFFECTS_KEY);
    this.painted = null;
    this.crackleTimer = null;
    this.playing = null;
    this.last = null;
    this.nextAt = performance.now() + FIRST_DELAY_MS;
    this.lastWorldAt = 0;
    this.lastPlayed = { sizzle: 0, boom: 0, zap: 0, bolt: 0 };
    this.levels = { fire: 0, sizzle: 0, boom: 0, zap: 0, bolt: 0 };
    // Browsers only allow sound after the player touches the page
    const unlock = () => this.unlock();
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    document.addEventListener("visibilitychange", () => this.update());
    window.addEventListener("pagehide", () => this.close());
    setInterval(() => this.tick(), TICK_MS);
  }

  /** Starts the audio engine. Browsers only allow this inside a touch or key press */
  unlock() {
    if (!this.ctx) {
      try {
        this.build();
      } catch (e) {
        console.warn("Sandfall: this browser can't play sound", e);
        this.ctx = null;
        return;
      }
    }
    this.update();
  }

  build() {
    const ctx = new AudioContext();
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = this.gainFor(this.volume);
    this.master.connect(ctx.destination);
    this.musicOut = ctx.createGain();
    this.musicOut.gain.value = MUSIC_LEVEL;
    this.musicOut.connect(this.master);
    // The one limiter on every effect: however much is happening, the total stays under this ceiling
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -16;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    const trim = ctx.createGain();
    trim.gain.value = LIMITER_TRIM;
    limiter.connect(trim).connect(this.master);
    this.effectsOut = ctx.createGain();
    this.effectsOut.gain.value = EFFECTS_LEVEL;
    this.effectsOut.connect(limiter);
    this.noiseBuffer = this.makeNoise(2);
    this.buildLayers();
    this.applyPainting();
  }

  makeNoise(seconds) {
    const buffer = this.ctx.createBuffer(1, Math.ceil(this.ctx.sampleRate * seconds), this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i += 1) {
      data[i] = Math.random() * 2 - 1;
    }
    return buffer;
  }

  // One endless filtered noise per painting sound, silent until painting asks for it
  buildLayers() {
    const ctx = this.ctx;
    for (const [name, spec] of Object.entries(PAINT_LAYERS)) {
      const source = ctx.createBufferSource();
      source.buffer = this.noiseBuffer;
      source.loop = true;
      const filter = ctx.createBiquadFilter();
      filter.type = spec.type;
      filter.frequency.value = spec.frequency;
      filter.Q.value = spec.q;
      const gain = ctx.createGain();
      gain.gain.value = 0;
      if (name === "liquid") {
        // A slow wobble in the loudness, so the pour burbles instead of hissing. It shapes the sound before the
        // level gain, so a silent layer stays silent
        const wobbled = ctx.createGain();
        wobbled.gain.value = 0.55;
        const wobble = ctx.createOscillator();
        wobble.frequency.value = LIQUID_BURBLE_HZ;
        const depth = ctx.createGain();
        depth.gain.value = 0.45;
        wobble.connect(depth).connect(wobbled.gain);
        wobble.start();
        source.connect(filter).connect(wobbled).connect(gain).connect(this.effectsOut);
      } else {
        source.connect(filter).connect(gain).connect(this.effectsOut);
      }
      source.start();
      this.layers[name] = { gain, level: spec.level };
    }
  }

  gainFor(volume) {
    // Loudness is felt on a curve, so the slider's low end isn't all the same quiet
    return (volume / 100) ** 2;
  }

  /** Whether sound can come out right now */
  live() {
    return this.ctx !== null && this.ctx.state === "running";
  }

  // Pauses everything while the page is hidden, and starts or stops the music to match its toggle
  async update() {
    if (!this.ctx || this.ctx.state === "closed") {
      return;
    }
    try {
      if (document.hidden) {
        this.playing?.audio.pause();
        await this.ctx.suspend();
        return;
      }
      await this.ctx.resume();
      await this.playing?.audio.play();
    } catch (e) {
      console.warn("Sandfall: couldn't start or pause the sound", e);
    }
    if (!this.musicOn) {
      this.stopTrack();
    }
  }

  setMusic(on) {
    this.musicOn = on;
    saveSetting(MUSIC_KEY, on);
    if (on) {
      this.nextAt = Math.min(this.nextAt, performance.now() + SWITCH_ON_MS);
    } else {
      this.stopTrack();
    }
  }

  setSfx(on) {
    this.sfxOn = on;
    saveSetting(EFFECTS_KEY, on);
    this.applyPainting();
  }

  setVolume(volume) {
    this.volume = Math.min(100, Math.max(0, Math.round(volume)));
    saveVolume(this.volume);
    if (this.master) {
      this.master.gain.setTargetAtTime(this.gainFor(this.volume), this.ctx.currentTime, 0.03);
    }
  }

  /** The kind of sound the brush is making now ("powder", "liquid", "fire"), or null when it is not painting */
  painting(kind) {
    this.painted = kind;
    this.applyPainting();
  }

  applyPainting() {
    const kind = this.sfxOn ? this.painted : null;
    if (this.ctx) {
      for (const [name, layer] of Object.entries(this.layers)) {
        layer.gain.gain.setTargetAtTime(name === kind ? layer.level : 0, this.ctx.currentTime, 0.05);
      }
    }
    if (kind === "fire" && this.crackleTimer === null) {
      this.crackleTimer = setInterval(() => this.crackle(0.5), 50);
    } else if (kind !== "fire" && this.crackleTimer !== null) {
      clearInterval(this.crackleTimer);
      this.crackleTimer = null;
    }
  }

  // A short filtered burst of the shared noise from a random spot in it
  burst({ start, length, level, type = "highpass", frequency = 2000, q = 0.7 }) {
    const ctx = this.ctx;
    const source = ctx.createBufferSource();
    source.buffer = this.noiseBuffer;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    filter.Q.value = q;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.linearRampToValueAtTime(level, start + 0.004);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
    source.connect(filter).connect(gain).connect(this.effectsOut);
    source.start(start, Math.random() * (this.noiseBuffer.duration - length - 0.05), length + 0.05);
  }

  tone({ frequency, to = null, start, length, type = "sine", level = 0.2 }) {
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, start);
    if (to) {
      osc.frequency.exponentialRampToValueAtTime(to, start + length);
    }
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(level, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
    osc.connect(gain).connect(this.effectsOut);
    osc.start(start);
    osc.stop(start + length + 0.02);
  }

  /** Little pops of fire: on average level * 4 of them for each call, never more than MAX_CLICKS */
  crackle(level) {
    if (!this.sfxOn || !this.live()) {
      return;
    }
    const now = this.ctx.currentTime;
    const clicks = Math.min(MAX_CLICKS, Math.floor(level * 4 + Math.random()));
    for (let k = 0; k < clicks; k += 1) {
      this.burst({
        start: now + Math.random() * 0.05,
        length: 0.012 + Math.random() * 0.03,
        level: (0.03 + Math.random() * 0.05) * (0.5 + level),
        frequency: 1800 + Math.random() * 3500,
      });
    }
  }

  /**
   * Called once per batch with what happened in it: `events` counts steams, explosions and sparks, `tally` is how many
   * cells of each element the world held
   */
  world(events, tally) {
    const now = performance.now();
    if (now - this.lastWorldAt < WORLD_GAP_MS) {
      return;
    }
    this.lastWorldAt = now;
    const fire = tally[EL.fire] + tally[EL.torch];
    this.levels = {
      fire: Math.min(1, Math.sqrt(fire / FIRE_FULL)),
      sizzle: Math.min(1, events.sizzle / 6),
      boom: Math.min(1, events.boom / 3),
      zap: Math.min(1, events.zap / 4),
      bolt: Math.min(1, events.bolt),
    };
    if (!this.sfxOn || !this.live()) {
      return;
    }
    this.crackle(this.levels.fire);
    const t = this.ctx.currentTime;
    if (this.levels.sizzle > 0 && this.ready("sizzle", now, SIZZLE_GAP_MS)) {
      this.burst({ start: t, length: 0.28, level: 0.04 + 0.1 * this.levels.sizzle, frequency: 3000 });
    }
    if (this.levels.boom > 0 && this.ready("boom", now, BOOM_GAP_MS)) {
      this.rumble(t, this.levels.boom);
    }
    if (this.levels.bolt > 0 && this.ready("bolt", now, BOLT_GAP_MS)) {
      this.burst({ start: t, length: 0.35, level: 0.22, frequency: 1200 });
      this.tone({ frequency: 3200, to: 120, start: t, length: 0.25, type: "sawtooth", level: 0.12 });
    } else if (this.levels.zap > 0 && this.ready("zap", now, ZAP_GAP_MS)) {
      const level = 0.06 + 0.05 * this.levels.zap;
      this.tone({ frequency: 1600, to: 180, start: t, length: 0.09, type: "sawtooth", level });
    }
  }

  // True (and noted) when the named sound has been quiet for at least `gap` milliseconds
  ready(name, now, gap) {
    if (now - this.lastPlayed[name] < gap) {
      return false;
    }
    this.lastPlayed[name] = now;
    return true;
  }

  rumble(t, level) {
    this.burst({ start: t, length: 0.9, level: 0.25 + 0.2 * level, type: "lowpass", frequency: 180, q: 0.5 });
    this.tone({ frequency: 70, to: 28, start: t, length: 0.7, level: 0.25 + 0.2 * level });
  }

  // Starts the next track when it is due and nothing else is playing
  tick() {
    if (!this.musicOn || !this.live() || document.hidden || this.playing !== null) {
      return;
    }
    if (performance.now() >= this.nextAt) {
      this.startTrack();
    }
  }

  startTrack() {
    const choices = TRACKS.filter((track) => track !== this.last);
    const track = choices[Math.floor(Math.random() * choices.length)];
    this.last = track;
    const audio = new Audio(track.url);
    audio.preload = "auto";
    const source = this.ctx.createMediaElementSource(audio);
    const gain = this.ctx.createGain();
    gain.gain.value = 0;
    source.connect(gain).connect(this.musicOut);
    const playing = { track, audio, source, gain };
    this.playing = playing;
    // The track fades in over its first seconds and out over its last
    audio.addEventListener("timeupdate", () => {
      const left = (audio.duration || Infinity) - audio.currentTime;
      const target = Math.min(1, audio.currentTime / TRACK_FADE_S, left / TRACK_FADE_S);
      gain.gain.setTargetAtTime(Math.max(0, target), this.ctx.currentTime, 0.3);
    });
    audio.addEventListener("ended", () => this.finishTrack(playing));
    audio.addEventListener("error", () => {
      console.warn("Sandfall: couldn't play the track", track.name, audio.error);
      this.finishTrack(playing);
    });
    audio.play().catch((e) => {
      console.warn("Sandfall: the browser wouldn't start the music", e);
      this.finishTrack(playing);
    });
  }

  release(playing) {
    playing.audio.pause();
    playing.source.disconnect();
    playing.gain.disconnect();
  }

  // The track is over: a quiet gap of one to three minutes, then another track
  finishTrack(playing) {
    if (this.playing !== playing) {
      return;
    }
    this.release(playing);
    this.playing = null;
    this.nextAt = performance.now() + QUIET_MIN_MS + Math.random() * (QUIET_MAX_MS - QUIET_MIN_MS);
  }

  stopTrack() {
    const playing = this.playing;
    if (playing === null) {
      return;
    }
    this.playing = null;
    playing.gain.gain.cancelScheduledValues(this.ctx.currentTime);
    playing.gain.gain.setTargetAtTime(0, this.ctx.currentTime, 0.1);
    setTimeout(() => this.release(playing), 400);
  }

  /** What the sound is doing now, for checks. `nextAt` is a performance.now() time; `track` is null in the quiet */
  state() {
    return {
      musicOn: this.musicOn,
      sfxOn: this.sfxOn,
      track: this.playing?.track.name ?? null,
      nextAt: this.nextAt,
      nextIn: Math.round(this.nextAt - performance.now()),
      volume: this.volume,
      context: this.ctx?.state ?? "locked",
      painting: this.painted,
      levels: { ...this.levels },
    };
  }

  close() {
    clearInterval(this.crackleTimer);
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Sandfall: couldn't close the sound", e));
    }
  }
}
