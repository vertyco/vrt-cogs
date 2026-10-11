// FarmCord's sound: the recorded effects listed in sounds/sounds.json, rain looping while it rains, and the farm song
// looped with a crossfade. The effects switch covers effects and rain; the music switch covers the song.
const LIST_URL = "sounds/sounds.json";
const MUSIC_VOLUME = 0.3;
const EFFECTS_VOLUME = 0.7;
const RAIN_VOLUME = 0.45;
// The song's last seconds fade into its start, so the loop has no gap or jump
const CROSSFADE = 2;
// Rain fades in and out over this many seconds
const RAIN_FADE = 1;
// Every game on the hub shares one storage, so the keys carry the game's name
const MUSIC_KEY = "farmcord:music";
const EFFECTS_KEY = "farmcord:sound";

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("FarmCord: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("FarmCord: couldn't save a sound setting", e);
  }
}

async function download(ctx, url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`${url} answered ${resp.status}`);
  }
  return ctx.decodeAudioData(await resp.arrayBuffer());
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.musicOn = readSetting(MUSIC_KEY);
    this.sfxOn = readSetting(EFFECTS_KEY);
    this.list = null;
    this.buffers = {};
    this.song = null;
    this.loading = null;
    this.voices = [];
    this.nextTimer = null;
    this.raining = false;
    this.rain = null;
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
      this.musicOut = this.output(MUSIC_VOLUME);
      this.effectsOut = this.output(EFFECTS_VOLUME);
      this.loadEffects();
    }
    this.update();
  }

  output(volume) {
    const gain = this.ctx.createGain();
    gain.gain.value = volume;
    gain.connect(this.ctx.destination);
    return gain;
  }

  // The effects are small, so they all load once, the first time the player touches the page
  async loadEffects() {
    try {
      const resp = await fetch(LIST_URL);
      if (!resp.ok) {
        throw new Error(`The sound list answered ${resp.status}`);
      }
      this.list = await resp.json();
    } catch (e) {
      console.warn("FarmCord: couldn't load the sound list", e);
      return;
    }
    for (const [name, file] of Object.entries(this.list)) {
      if (name === "music") {
        continue;
      }
      download(this.ctx, `sounds/${file}`)
        .then((buffer) => {
          this.buffers[name] = buffer;
          if (name === "rain") {
            this.update();
          }
        })
        .catch((e) => console.warn(`FarmCord: couldn't load the sound ${name}`, e));
    }
    this.update();
  }

  // Pauses everything while the page is hidden, and starts or stops the music and the rain to match their switches
  async update() {
    if (!this.ctx || this.ctx.state === "closed") {
      return;
    }
    try {
      if (document.hidden) {
        await this.ctx.suspend();
        return;
      }
      await this.ctx.resume();
    } catch (e) {
      console.warn("FarmCord: couldn't start or pause the sound", e);
      return;
    }
    if (this.musicOn) {
      this.startMusic();
    } else {
      this.stopMusic();
    }
    if (this.raining && this.sfxOn) {
      this.startRain();
    } else {
      this.stopRain();
    }
  }

  setMusic(on) {
    this.musicOn = on;
    saveSetting(MUSIC_KEY, on);
    this.update();
  }

  setSfx(on) {
    this.sfxOn = on;
    saveSetting(EFFECTS_KEY, on);
    this.update();
  }

  // Rain loops while the farmer is outside on a rainy day
  setRain(on) {
    if (on !== this.raining) {
      this.raining = on;
      this.update();
    }
  }

  play(name) {
    const buffer = this.buffers[name];
    if (!this.sfxOn || !buffer || this.ctx.state !== "running") {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.effectsOut);
    source.start();
  }

  startRain() {
    if (this.rain || !this.buffers.rain) {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = this.buffers.rain;
    source.loop = true;
    const gain = this.ctx.createGain();
    const now = this.ctx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(RAIN_VOLUME, now + RAIN_FADE);
    source.connect(gain).connect(this.effectsOut);
    source.start();
    this.rain = { source, gain };
  }

  stopRain() {
    if (!this.rain) {
      return;
    }
    const { source, gain } = this.rain;
    const now = this.ctx.currentTime;
    gain.gain.cancelScheduledValues(now);
    gain.gain.setValueAtTime(gain.gain.value, now);
    gain.gain.linearRampToValueAtTime(0, now + RAIN_FADE);
    source.stop(now + RAIN_FADE + 0.05);
    this.rain = null;
  }

  async startMusic() {
    if (this.voices.length || this.nextTimer !== null || !this.list) {
      return;
    }
    try {
      this.song = this.song || (await this.loadSong());
    } catch (e) {
      console.warn("FarmCord: couldn't load the music", e);
      return;
    }
    // Two calls can wait on the same download; only the first starts the song
    if (this.musicOn && !this.voices.length && this.nextTimer === null) {
      this.playSong(this.ctx.currentTime);
    }
  }

  loadSong() {
    if (!this.loading) {
      this.loading = download(this.ctx, `music/${this.list.music.file}`);
      // A failed download is tried again next time. startMusic() logs why it failed
      this.loading.catch(() => {
        this.loading = null;
      });
    }
    return this.loading;
  }

  // One copy of the song, fading in while the copy before it fades out. The next copy is booked just before it starts
  playSong(when) {
    const source = this.ctx.createBufferSource();
    source.buffer = this.song;
    const gain = this.ctx.createGain();
    const end = when + this.song.duration;
    gain.gain.setValueAtTime(0, when);
    gain.gain.linearRampToValueAtTime(1, when + CROSSFADE);
    gain.gain.setValueAtTime(1, end - CROSSFADE);
    gain.gain.linearRampToValueAtTime(0, end);
    source.connect(gain).connect(this.musicOut);
    source.start(when);
    source.stop(end);
    const voice = { source, gain };
    this.voices.push(voice);
    source.addEventListener("ended", () => {
      this.voices = this.voices.filter((other) => other !== voice);
    });
    const next = end - CROSSFADE;
    const delay = Math.max(0, (next - this.ctx.currentTime - 1) * 1000);
    this.nextTimer = setTimeout(() => {
      this.nextTimer = null;
      if (this.musicOn) {
        this.playSong(Math.max(next, this.ctx.currentTime));
      }
    }, delay);
  }

  stopMusic() {
    clearTimeout(this.nextTimer);
    this.nextTimer = null;
    const now = this.ctx.currentTime;
    for (const { source, gain } of this.voices) {
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(0, now + 0.3);
      source.stop(now + 0.35);
    }
    // Forgotten at once, so turning the music back on straight away starts a fresh copy
    this.voices = [];
  }

  close() {
    clearTimeout(this.nextTimer);
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("FarmCord: couldn't close the sound", e));
    }
  }
}
