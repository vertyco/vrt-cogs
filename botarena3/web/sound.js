// Bot Arena 3's sound, built like the original's two sound holders: one for the music (its "mholder") and one for
// the effects (its "sholder"). Each has the player's volume, kept on this device, and a fade that the screens start
// and stop, stepped on the timelines' clock. Everything plays through the Web Audio API, so effects can overlap.
export const MUSIC = ["dnb", "ambi", "rave", "shop"];
export const EFFECTS = [
  "biglaser",
  "cash",
  "cons",
  "cshot",
  "dismount",
  "dit",
  "fwork",
  "gun01",
  "gun02",
  "gun03",
  "gun04",
  "heal01",
  "heal02",
  "laser",
  "mount",
  "pact",
  "pdown",
  "plas",
  "pup",
  "rico1",
  "rico2",
  "rico3",
  "rico4",
  "rico5",
  "rico6",
  "rico7",
  "snipe",
  "splode",
];
// Every game on the hub shares one storage, so the keys carry the game's name
const SOUND_KEY = "botarena3.sound";
const MUSIC_KEY = "botarena3.music";
// The original's starting volumes, out of 100 (its sndset.sndvol and sndset.musvol)
const SOUND_VOLUME = 70;
const MUSIC_VOLUME = 35;
// The original's sound settings, each kind of effect on or off: all on (its sndset)
const KINDS = ["true_shot", "true_hit", "true_miss", "false_shot", "false_hit", "false_miss", "misc", "music"];
// How quickly a gain follows a new volume, in seconds, so stepping it 33 times a second doesn't click
const SMOOTHING = 0.015;

function readVolume(key, fallback) {
  try {
    const saved = localStorage.getItem(key);
    const value = saved === null ? NaN : Number(saved);
    return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : fallback;
  } catch (e) {
    console.warn("Bot Arena 3: couldn't read a volume", e);
    return fallback;
  }
}

function saveVolume(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch (e) {
    console.warn("Bot Arena 3: couldn't save a volume", e);
  }
}

// One of the original's sound holders: a volume out of 100 that fades by `speed` each frame toward 0 or 100
class Holder {
  constructor() {
    // The original sets both holders to 0 before its first screen fades them in
    this.percent = 0;
    this.speed = 0;
  }

  step() {
    if (!this.speed) {
      return;
    }
    this.percent += this.speed;
    if (this.percent <= 0 || this.percent >= 100) {
      this.percent = Math.max(0, Math.min(100, this.percent));
      this.speed = 0;
    }
  }
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.soundVolume = readVolume(SOUND_KEY, SOUND_VOLUME);
    this.musicVolume = readVolume(MUSIC_KEY, MUSIC_VOLUME);
    this.kinds = Object.fromEntries(KINDS.map((kind) => [kind, true]));
    this.musicHolder = new Holder();
    this.soundHolder = new Holder();
    // name -> Promise of the decoded sound, once the audio has started
    this.buffers = new Map();
    this.wanted = null;
    this.playingMusic = null;
    this.sources = new Set();
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
      this.musicOut = this.ctx.createGain();
      this.effectsOut = this.ctx.createGain();
      this.musicOut.connect(this.ctx.destination);
      this.effectsOut.connect(this.ctx.destination);
      this.applyVolumes();
      for (const name of [...MUSIC, ...EFFECTS]) {
        this.buffer(name);
      }
      if (this.wanted) {
        this.startMusic(this.wanted);
      }
    }
    this.update();
  }

  buffer(name) {
    if (!this.buffers.has(name)) {
      const loaded = fetch(`sounds/${name}.mp3`)
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`The sound file answered ${resp.status}`);
          }
          return resp.arrayBuffer();
        })
        .then((bytes) => this.ctx.decodeAudioData(bytes))
        .catch((e) => {
          console.warn(`Bot Arena 3: couldn't load sound ${name}`, e);
          return null;
        });
      this.buffers.set(name, loaded);
    }
    return this.buffers.get(name);
  }

  // Pauses everything while the page is hidden
  async update() {
    if (!this.ctx || this.ctx.state === "closed") {
      return;
    }
    try {
      await (document.hidden ? this.ctx.suspend() : this.ctx.resume());
    } catch (e) {
      console.warn("Bot Arena 3: couldn't start or pause the sound", e);
    }
  }

  // ---------- Volumes ----------

  // The player's volumes, out of 100, as the settings screen's sliders set them
  setVolumes(sound, music) {
    if (sound !== this.soundVolume) {
      this.soundVolume = sound;
      saveVolume(SOUND_KEY, sound);
    }
    if (music !== this.musicVolume) {
      this.musicVolume = music;
      saveVolume(MUSIC_KEY, music);
    }
    this.applyVolumes();
  }

  applyVolumes() {
    if (!this.ctx) {
      return;
    }
    const now = this.ctx.currentTime;
    this.musicOut.gain.setTargetAtTime((this.musicHolder.percent / 100) * (this.musicVolume / 100), now, SMOOTHING);
    this.effectsOut.gain.setTargetAtTime((this.soundHolder.percent / 100) * (this.soundVolume / 100), now, SMOOTHING);
  }

  // The original's mholder.fadein(speed) and sholder.fadein(speed): both holders rise by speed each frame
  fadeIn(speed) {
    this.musicHolder.speed = speed;
    this.soundHolder.speed = speed;
  }

  fadeOut(speed) {
    this.musicHolder.speed = -speed;
    this.soundHolder.speed = -speed;
  }

  // One frame of the timelines' clock
  step() {
    if (!this.musicHolder.speed && !this.soundHolder.speed) {
      return;
    }
    this.musicHolder.step();
    this.soundHolder.step();
    this.applyVolumes();
  }

  // ---------- Playing ----------

  // The original's playsound(name, "music"): one of its four tracks, looping
  music(name) {
    this.stopMusic();
    this.wanted = name;
    if (this.ctx) {
      this.startMusic(name);
    }
  }

  async startMusic(name) {
    const buffer = await this.buffer(name);
    if (!buffer || this.wanted !== name || this.playingMusic || this.ctx.state === "closed") {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.connect(this.musicOut);
    source.start();
    this.playingMusic = source;
  }

  stopMusic() {
    this.wanted = null;
    if (this.playingMusic) {
      this.playingMusic.stop();
      this.playingMusic.disconnect();
      this.playingMusic = null;
    }
  }

  // The original's playsound(name, kind) for an effect: plays when that kind of sound is on. Names the game has no
  // file for (the silent ricochets) play nothing
  effect(name, kind) {
    if (!this.kinds[kind] || !this.ctx || this.ctx.state !== "running" || !EFFECTS.includes(name)) {
      return;
    }
    this.buffer(name).then((buffer) => {
      if (!buffer || this.ctx.state !== "running") {
        return;
      }
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(this.effectsOut);
      source.addEventListener("ended", () => this.sources.delete(source));
      this.sources.add(source);
      source.start();
    });
  }

  // The original's stopAllSounds()
  stopAll() {
    this.stopMusic();
    for (const source of this.sources) {
      source.stop();
    }
    this.sources.clear();
  }

  close() {
    this.stopAll();
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Bot Arena 3: couldn't close the sound", e));
    }
  }
}
