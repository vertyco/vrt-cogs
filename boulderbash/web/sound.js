// Boulder Bash's sound: effects from files and a few voices made on the fly, and two songs (menus and play) that
// crossfade into each other. The Sound sign cycles music and effects the way the original's did.
const SONGS = { menu: "music/canyon-stomp.mp3", play: "music/rock-breaker.mp3" };
const FILES = [
  "click",
  "select",
  "crash",
  "stomp",
  "drop",
  "slide",
  "level",
  "rise",
  "overflow",
  "boom",
  "wipe",
  "refill",
  "bonus",
  "wild",
  "hold",
  "morph",
  "goal",
  "popup",
  "clack-1",
  "clack-2",
];
const MUSIC_VOLUME = 0.32;
const EFFECTS_VOLUME = 0.7;
// Each song's last seconds fade into its own start, and moving between menus and play crossfades the two songs
const CROSSFADE = 2;
const EFFECTS_FADE = 1;
const SHUFFLE_FADE = 1;
// Every game on the hub shares one storage, so the keys carry the game's name
const MUSIC_KEY = "boulderbash:music";
const SOUND_KEY = "boulderbash:sound";

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Boulder Bash: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Boulder Bash: couldn't save a sound setting", e);
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
  gain.gain.exponentialRampToValueAtTime(level, start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(out);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

function noise(ctx, out, { start, length, level = 0.2, cutoff = 1500 }) {
  const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * length), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 2;
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

// The voices: made here rather than recorded, so they are easy to swap for real recordings later
const VOICES = {
  // The mammoth (Undo) and the hidden caveman
  roar(ctx, out, t) {
    tone(ctx, out, { frequency: 150, to: 70, start: t, length: 0.9, type: "sawtooth", level: 0.22 });
    tone(ctx, out, { frequency: 230, to: 110, start: t + 0.05, length: 0.7, type: "square", level: 0.08 });
    noise(ctx, out, { start: t, length: 0.8, level: 0.3, cutoff: 700 });
  },
  // The triceratops' giggle
  laugh(ctx, out, t) {
    [0, 0.13, 0.26, 0.39, 0.52].forEach((when, i) => {
      tone(ctx, out, { frequency: 520 - i * 25, to: 380 - i * 20, start: t + when, length: 0.11, type: "triangle", level: 0.2 });
    });
  },
  // The pterodactyl (Shuffle)
  squawk(ctx, out, t) {
    tone(ctx, out, { frequency: 900, to: 1500, start: t, length: 0.18, type: "square", level: 0.08 });
    tone(ctx, out, { frequency: 1400, to: 700, start: t + 0.2, length: 0.35, type: "square", level: 0.09 });
  },
  // The flock crossing the sky
  flock(ctx, out, t) {
    [0, 0.35, 0.6, 1.1].forEach((when, i) => {
      tone(ctx, out, { frequency: 1300 + i * 120, to: 900, start: t + when, length: 0.22, type: "triangle", level: 0.06 });
    });
  },
  // A Countdown's last seconds
  warning(ctx, out, t) {
    tone(ctx, out, { frequency: 1046, start: t, length: 0.12, type: "square", level: 0.09 });
  },
};

export class Sound {
  constructor() {
    this.ctx = null;
    this.musicOut = null;
    this.effectsOut = null;
    this.musicOn = readSetting(MUSIC_KEY);
    this.sfxOn = readSetting(SOUND_KEY);
    this.scene = "menu";
    this.buffers = {};
    this.songs = {};
    this.loading = {};
    // The song playing now: its name, its copies (each fading into the next) and the timer that books the next copy
    this.track = null;
    this.wanted = null;
    this.shuffleTimer = null;
    const unlock = () => this.unlock();
    // Browsers only allow sound after the player touches the page
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    document.addEventListener("visibilitychange", () => this.update());
    window.addEventListener("pagehide", () => this.close());
  }

  unlock() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.musicOut = this.output(this.musicOn ? MUSIC_VOLUME : 0);
      this.effectsOut = this.output(this.sfxOn ? EFFECTS_VOLUME : 0);
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

  async loadEffects() {
    await Promise.all(
      FILES.map(async (name) => {
        try {
          const resp = await fetch(`sounds/${name}.mp3`);
          if (!resp.ok) {
            throw new Error(`The sound file answered ${resp.status}`);
          }
          this.buffers[name] = await this.ctx.decodeAudioData(await resp.arrayBuffer());
        } catch (e) {
          console.warn(`Boulder Bash: couldn't load the ${name} sound`, e);
        }
      }),
    );
  }

  // Pauses everything while the page is hidden, and keeps the right song playing
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
      console.warn("Boulder Bash: couldn't start or pause the sound", e);
      return;
    }
    this.startSong(this.scene);
  }

  // The Sound sign's label names what it does next: music off, then sound off, then music on, then sound on
  get nextAction() {
    if (this.musicOn) {
      return this.sfxOn ? "Turn music off" : "Turn sound on";
    }
    return this.sfxOn ? "Turn sound off" : "Turn music on";
  }

  cycle() {
    if (this.musicOn && this.sfxOn) {
      this.setMusic(false);
    } else if (this.sfxOn) {
      this.setSfx(false);
    } else if (!this.musicOn) {
      this.setMusic(true);
    } else {
      this.setSfx(true);
    }
  }

  setMusic(on) {
    this.musicOn = on;
    saveSetting(MUSIC_KEY, on);
    this.fade(this.musicOut, on ? MUSIC_VOLUME : 0, CROSSFADE);
  }

  setSfx(on) {
    this.sfxOn = on;
    saveSetting(SOUND_KEY, on);
    this.fade(this.effectsOut, on ? EFFECTS_VOLUME : 0, EFFECTS_FADE);
  }

  fade(out, volume, seconds) {
    if (!this.ctx) {
      return;
    }
    const now = this.ctx.currentTime;
    out.gain.cancelScheduledValues(now);
    out.gain.setValueAtTime(out.gain.value, now);
    out.gain.linearRampToValueAtTime(volume, now + seconds);
  }

  // Menus and play each have their own song, crossfaded over 2 seconds
  setScene(scene) {
    this.scene = scene;
    if (this.ctx) {
      this.startSong(scene);
    }
  }

  play(name, { volume = 1, pan = 0 } = {}) {
    if (!this.sfxOn || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    const t = this.ctx.currentTime;
    let out = this.effectsOut;
    if (volume !== 1 || pan !== 0) {
      const gain = this.ctx.createGain();
      gain.gain.value = volume;
      const panner = this.ctx.createStereoPanner();
      panner.pan.value = pan;
      gain.connect(panner).connect(this.effectsOut);
      out = gain;
    }
    if (VOICES[name]) {
      VOICES[name](this.ctx, out, t);
      return;
    }
    const buffer = this.buffers[name];
    if (!buffer) {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(out);
    source.start(t);
  }

  // The Bomb: one boom, the file and a low rumble together
  boom() {
    this.play("boom");
    if (this.sfxOn && this.ctx && this.ctx.state === "running") {
      noise(this.ctx, this.effectsOut, { start: this.ctx.currentTime, length: 1.0, level: 0.5, cutoff: 400 });
    }
  }

  // Stones clattering while the Shuffle swaps them, faded out once the swapping ends
  startShuffle() {
    this.stopShuffle(0);
    if (!this.ctx) {
      return;
    }
    const gain = this.ctx.createGain();
    gain.connect(this.effectsOut);
    const clack = () => {
      const buffer = this.buffers[Math.random() < 0.5 ? "clack-1" : "clack-2"];
      if (buffer && this.sfxOn && this.ctx.state === "running") {
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        source.playbackRate.value = 0.8 + Math.random() * 0.5;
        source.connect(gain);
        source.start();
      }
    };
    this.shuffleTimer = { gain, interval: setInterval(clack, 70) };
  }

  stopShuffle(seconds = SHUFFLE_FADE) {
    const shuffle = this.shuffleTimer;
    if (!shuffle) {
      return;
    }
    this.shuffleTimer = null;
    const now = this.ctx.currentTime;
    shuffle.gain.gain.setValueAtTime(shuffle.gain.gain.value, now);
    shuffle.gain.gain.linearRampToValueAtTime(0, now + seconds);
    setTimeout(() => clearInterval(shuffle.interval), seconds * 1000);
  }

  async loadSong(name) {
    if (!this.loading[name]) {
      this.loading[name] = fetch(SONGS[name])
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`The music file answered ${resp.status}`);
          }
          return resp.arrayBuffer();
        })
        .then((data) => this.ctx.decodeAudioData(data));
      // A failed download is tried again next time
      this.loading[name].catch(() => {
        delete this.loading[name];
      });
    }
    return this.loading[name];
  }

  // The new song loads first, so the old one keeps playing until the two can crossfade
  async startSong(name) {
    this.wanted = name;
    if (this.track?.name === name) {
      return;
    }
    try {
      this.songs[name] = this.songs[name] || (await this.loadSong(name));
    } catch (e) {
      console.warn("Boulder Bash: couldn't load the music", e);
      return;
    }
    // The scene may have changed while it loaded
    if (this.wanted !== name || this.track?.name === name) {
      return;
    }
    this.endTrack();
    const track = { name, voices: [], timer: null };
    this.track = track;
    this.playCopy(track, this.ctx.currentTime);
  }

  // One copy of the song, fading in while the copy before it fades out. The next copy is booked just before it starts
  playCopy(track, when) {
    const song = this.songs[track.name];
    const source = this.ctx.createBufferSource();
    source.buffer = song;
    const gain = this.ctx.createGain();
    const end = when + song.duration;
    gain.gain.setValueAtTime(0, when);
    gain.gain.linearRampToValueAtTime(1, when + CROSSFADE);
    gain.gain.setValueAtTime(1, end - CROSSFADE);
    gain.gain.linearRampToValueAtTime(0, end);
    source.connect(gain).connect(this.musicOut);
    source.start(when);
    source.stop(end);
    const voice = { source, gain };
    track.voices.push(voice);
    source.addEventListener("ended", () => {
      track.voices = track.voices.filter((other) => other !== voice);
    });
    const next = end - CROSSFADE;
    track.timer = setTimeout(
      () => {
        if (this.track === track) {
          this.playCopy(track, Math.max(next, this.ctx.currentTime));
        }
      },
      Math.max(0, (next - this.ctx.currentTime - 1) * 1000),
    );
  }

  // The old song fades out over the crossfade while the new one fades in
  endTrack() {
    const track = this.track;
    this.track = null;
    if (!track || !this.ctx) {
      return;
    }
    clearTimeout(track.timer);
    const now = this.ctx.currentTime;
    for (const { source, gain } of track.voices) {
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(0, now + CROSSFADE);
      source.stop(now + CROSSFADE + 0.05);
    }
  }

  close() {
    if (this.track) {
      clearTimeout(this.track.timer);
    }
    if (this.shuffleTimer) {
      clearInterval(this.shuffleTimer.interval);
    }
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Boulder Bash: couldn't close the sound", e));
    }
  }
}
