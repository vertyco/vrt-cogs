// The casino's sound: recorded table sounds (chips, cards, dice), a few made from tones on the fly, and the lounge
// music looped with a crossfade. Scenes call sound.play(name) with a name from EFFECT_NAMES.
const MUSIC_URL = "music/lounge.mp3";
const MUSIC_VOLUME = 0.3;
const EFFECTS_VOLUME = 0.7;
// The song's last seconds fade into its start, so the loop has no gap or jump
const CROSSFADE = 2;
// Every game on the hub shares one storage, so the keys carry the game's name
const MUSIC_KEY = "casino:music";
const EFFECTS_KEY = "casino:sfx";

// Recorded sounds (Kenney's Casino Audio, CC0, in sounds/). Each play picks one of the takes at random
const SAMPLES = {
  chip: ["chip-lay-1", "chip-lay-2", "chip-lay-3"],
  bet: ["chips-stack-1", "chips-stack-2", "chips-stack-3"],
  collect: ["chips-handle-1", "chips-handle-2"],
  deal: ["card-place-1", "card-place-2", "card-place-3", "card-place-4"],
  slide: ["card-slide-1", "card-slide-2", "card-slide-3"],
  shuffle: ["card-shuffle"],
  shake: ["dice-shake-1", "dice-shake-2"],
  throw: ["dice-throw-1", "dice-throw-2", "dice-throw-3"],
};

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Casino: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Casino: couldn't save a sound setting", e);
  }
}

function tone(ctx, out, { frequency, to = null, start, length, type = "sine", level = 0.3 }) {
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
  osc.connect(gain).connect(out);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

function noise(ctx, out, { start, length, level = 0.2, cutoff = 1500, type = "lowpass" }) {
  const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * length), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  }
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  const filter = ctx.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = cutoff;
  const gain = ctx.createGain();
  gain.gain.value = level;
  source.connect(filter).connect(gain).connect(out);
  source.start(start);
}

// Sounds the pack doesn't have, made from tones
const TONES = {
  click(ctx, out, t) {
    tone(ctx, out, { frequency: 1800, to: 900, start: t, length: 0.04, type: "square", level: 0.05 });
  },
  tick(ctx, out, t) {
    tone(ctx, out, { frequency: 1250, start: t, length: 0.05, type: "triangle", level: 0.12 });
  },
  coin(ctx, out, t) {
    tone(ctx, out, { frequency: 2637, start: t, length: 0.5, type: "sine", level: 0.18 });
    tone(ctx, out, { frequency: 3951, start: t + 0.01, length: 0.35, type: "sine", level: 0.08 });
  },
  land(ctx, out, t) {
    noise(ctx, out, { start: t, length: 0.08, level: 0.35, cutoff: 900 });
    tone(ctx, out, { frequency: 2093, start: t + 0.02, length: 0.25, type: "sine", level: 0.08 });
  },
  cups(ctx, out, t) {
    noise(ctx, out, { start: t, length: 0.35, level: 0.12, cutoff: 700 });
  },
  lever(ctx, out, t) {
    noise(ctx, out, { start: t, length: 0.12, level: 0.4, cutoff: 500 });
    tone(ctx, out, { frequency: 140, to: 70, start: t, length: 0.18, type: "square", level: 0.12 });
  },
  reel(ctx, out, t) {
    for (let i = 0; i < 18; i += 1) {
      tone(ctx, out, { frequency: 900 + (i % 3) * 120, start: t + i * 0.09, length: 0.03, type: "square", level: 0.04 });
    }
  },
  stop(ctx, out, t) {
    noise(ctx, out, { start: t, length: 0.06, level: 0.3, cutoff: 1200 });
  },
  win(ctx, out, t) {
    [523.25, 659.25, 783.99, 1046.5].forEach((frequency, i) => {
      tone(ctx, out, { frequency, start: t + i * 0.09, length: 0.25, type: "triangle", level: 0.2 });
    });
  },
  bigwin(ctx, out, t) {
    [523.25, 659.25, 783.99, 1046.5, 1318.5, 1568].forEach((frequency, i) => {
      tone(ctx, out, { frequency, start: t + i * 0.08, length: 0.35, type: "triangle", level: 0.2 });
    });
    for (let i = 0; i < 10; i += 1) {
      tone(ctx, out, { frequency: 2637 + (i % 4) * 200, start: t + 0.5 + i * 0.07, length: 0.2, level: 0.06 });
    }
  },
  lose(ctx, out, t) {
    tone(ctx, out, { frequency: 392, start: t, length: 0.2, type: "triangle", level: 0.16 });
    tone(ctx, out, { frequency: 311.13, start: t + 0.18, length: 0.35, type: "triangle", level: 0.16 });
  },
  push(ctx, out, t) {
    tone(ctx, out, { frequency: 587.33, start: t, length: 0.18, type: "triangle", level: 0.14 });
    tone(ctx, out, { frequency: 587.33, start: t + 0.16, length: 0.2, type: "triangle", level: 0.12 });
  },
};

export const EFFECT_NAMES = [...Object.keys(SAMPLES), ...Object.keys(TONES)];

export class Sound {
  constructor() {
    this.ctx = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.musicOn = readSetting(MUSIC_KEY);
    this.sfxOn = readSetting(EFFECTS_KEY);
    this.song = null;
    this.loading = null;
    this.samples = {};
    this.voices = [];
    this.nextTimer = null;
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
      this.loadSamples();
    }
    this.update();
  }

  output(volume) {
    const gain = this.ctx.createGain();
    gain.gain.value = volume;
    gain.connect(this.ctx.destination);
    return gain;
  }

  // The recorded sounds are small, so they all load once, the first time the player touches the page
  loadSamples() {
    for (const takes of Object.values(SAMPLES)) {
      for (const take of takes) {
        fetch(`sounds/${take}.mp3`)
          .then((resp) => (resp.ok ? resp.arrayBuffer() : Promise.reject(new Error(`answered ${resp.status}`))))
          .then((data) => this.ctx.decodeAudioData(data))
          .then((buffer) => {
            this.samples[take] = buffer;
          })
          .catch((e) => console.warn(`Casino: couldn't load the sound ${take}`, e));
      }
    }
  }

  // Pauses everything while the page is hidden, and starts or stops the music to match its switch
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
      console.warn("Casino: couldn't start or pause the sound", e);
      return;
    }
    if (this.musicOn) {
      this.startMusic();
    } else {
      this.stopMusic();
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
  }

  play(name) {
    if (!this.sfxOn || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    if (TONES[name]) {
      TONES[name](this.ctx, this.effectsOut, this.ctx.currentTime);
      return;
    }
    const takes = (SAMPLES[name] || []).filter((take) => this.samples[take]);
    if (!takes.length) {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = this.samples[takes[Math.floor(Math.random() * takes.length)]];
    source.connect(this.effectsOut);
    source.start();
  }

  async startMusic() {
    if (this.voices.length || this.nextTimer !== null) {
      return;
    }
    try {
      this.song = this.song || (await this.loadSong());
    } catch (e) {
      console.warn("Casino: couldn't load the music", e);
      return;
    }
    // Two calls can wait on the same download; only the first starts the song
    if (this.musicOn && !this.voices.length && this.nextTimer === null) {
      this.playSong(this.ctx.currentTime);
    }
  }

  loadSong() {
    if (!this.loading) {
      this.loading = fetch(MUSIC_URL)
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`The music file answered ${resp.status}`);
          }
          return resp.arrayBuffer();
        })
        .then((data) => this.ctx.decodeAudioData(data));
      // A failed download is tried again next time
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
      this.ctx.close().catch((e) => console.warn("Casino: couldn't close the sound", e));
    }
  }
}
