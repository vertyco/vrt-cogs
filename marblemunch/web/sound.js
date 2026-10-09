// Marble Munch's sound: effects made from tones on the fly, and the background song looped with a crossfade.
const MUSIC_URL = "music/toybox.mp3";
const MUSIC_VOLUME = 0.33;
const EFFECTS_VOLUME = 0.6;
// The song's last seconds fade into its start, so the loop has no gap or jump
const CROSSFADE = 2;
// Every game on the hub shares one storage, so the keys carry the game's name
const MUSIC_KEY = "marblemunch:music";
const EFFECTS_KEY = "marblemunch:sfx";

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Marble Munch: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Marble Munch: couldn't save a sound setting", e);
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

function noise(ctx, out, { start, length, level = 0.2, cutoff = 1500 }) {
  const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * length), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  }
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  const filter = ctx.createBiquadFilter();
  filter.type = "lowpass";
  filter.frequency.value = cutoff;
  const gain = ctx.createGain();
  gain.gain.value = level;
  source.connect(filter).connect(gain).connect(out);
  source.start(start);
}

const EFFECTS = {
  chomp(ctx, out, t, loud) {
    tone(ctx, out, { frequency: 220, to: 90, start: t, length: 0.09, type: "square", level: loud ? 0.18 : 0.07 });
    noise(ctx, out, { start: t, length: 0.06, level: loud ? 0.25 : 0.1, cutoff: 1200 });
  },
  gulp(ctx, out, t) {
    tone(ctx, out, { frequency: 560, to: 210, start: t, length: 0.14, level: 0.22 });
  },
  score(ctx, out, t) {
    tone(ctx, out, { frequency: 880, start: t, length: 0.08, type: "triangle", level: 0.2 });
    tone(ctx, out, { frequency: 1320, start: t + 0.07, length: 0.12, type: "triangle", level: 0.2 });
  },
  beep(ctx, out, t) {
    tone(ctx, out, { frequency: 660, start: t, length: 0.14, type: "triangle", level: 0.25 });
  },
  go(ctx, out, t) {
    tone(ctx, out, { frequency: 990, start: t, length: 0.3, type: "triangle", level: 0.28 });
  },
  win(ctx, out, t) {
    [523.25, 659.25, 783.99, 1046.5].forEach((frequency, i) => {
      tone(ctx, out, { frequency, start: t + i * 0.1, length: 0.22, type: "triangle", level: 0.22 });
    });
  },
  end(ctx, out, t) {
    tone(ctx, out, { frequency: 523.25, start: t, length: 0.18, type: "triangle", level: 0.2 });
    tone(ctx, out, { frequency: 392, start: t + 0.16, length: 0.26, type: "triangle", level: 0.2 });
  },
};

export class Sound {
  constructor() {
    this.ctx = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.musicOn = readSetting(MUSIC_KEY);
    this.sfxOn = readSetting(EFFECTS_KEY);
    this.song = null;
    this.loading = null;
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
    }
    this.update();
  }

  output(volume) {
    const gain = this.ctx.createGain();
    gain.gain.value = volume;
    gain.connect(this.ctx.destination);
    return gain;
  }

  // Pauses everything while the page is hidden, and starts or stops the music to match its toggle
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
      console.warn("Marble Munch: couldn't start or pause the sound", e);
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

  play(name, loud = true) {
    if (!this.sfxOn || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    EFFECTS[name](this.ctx, this.effectsOut, this.ctx.currentTime, loud);
  }

  async startMusic() {
    if (this.voices.length || this.nextTimer !== null) {
      return;
    }
    try {
      this.song = this.song || (await this.loadSong());
    } catch (e) {
      console.warn("Marble Munch: couldn't load the music", e);
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
      this.ctx.close().catch((e) => console.warn("Marble Munch: couldn't close the sound", e));
    }
  }
}
