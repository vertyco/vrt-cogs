// Penguin Wars' sounds, made on the fly with the browser's audio, so there are no files to load. A page can't make
// sound until a person has pressed something, so nothing plays until unlock() has run from a press.

const rand = (low, high) => low + Math.random() * (high - low);
// The loudness at full volume. The sound panel's slider, 0 to 100, scales it along a curve, so the lower half of the
// slider still has room to set a quiet level
const LOUDNESS = 0.55;

function levelFor(volume) {
  return LOUDNESS * (volume / 100) ** 2;
}

function envelope(gain, at, peak, length) {
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(peak, at + 0.008);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
}

// Each sound gets the audio context, the moment to start at and how strong it is, from 0 to 1
const SOUNDS = {
  flick: (s, at, k) => s.noise(at, 0.22, "bandpass", 500, 2600, 0.2 + 0.25 * k, 1.2),
  heavy: (s, at) => {
    s.noise(at, 0.3, "bandpass", 300, 1400, 0.35, 1);
    s.tone(at, 0.3, "sawtooth", 140, 60, 0.1);
  },
  bonk: (s, at, k) => {
    s.tone(at, 0.14, "sine", 380 + 140 * k, 90, 0.55);
    s.tone(at, 0.05, "triangle", 900, 400, 0.18);
  },
  bounce: (s, at) => {
    s.tone(at, 0.1, "sine", 180, 560, 0.4);
    s.tone(at + 0.09, 0.16, "sine", 560, 200, 0.25);
    s.noise(at, 0.08, "highpass", 3500, 2500, 0.15);
  },
  brace: (s, at) => {
    s.noise(at, 0.12, "highpass", 3000, 1500, 0.2);
    s.tone(at, 0.1, "triangle", 700, 480, 0.15);
  },
  gulp: (s, at) => {
    s.tone(at, 0.08, "sine", 420, 820, 0.3);
    s.tone(at + 0.09, 0.08, "sine", 600, 1100, 0.25);
  },
  seal: (s, at) => {
    s.tone(at, 0.12, "square", 340, 220, 0.08);
    s.tone(at + 0.16, 0.12, "square", 310, 200, 0.07);
  },
  bubble: (s, at) => {
    for (let i = 0; i < 4; i += 1) {
      s.tone(at + i * 0.07, 0.05, "sine", rand(800, 1300), rand(1300, 1800), 0.06);
    }
  },
  splash: (s, at) => {
    s.noise(at, 0.55, "lowpass", 2400, 300, 0.45);
    s.tone(at, 0.22, "sine", 320, 70, 0.3);
  },
  crack: (s, at) => {
    for (let i = 0; i < 3; i += 1) {
      s.noise(at + i * 0.045, 0.05, "highpass", 2800, 2000, 0.12);
    }
  },
  sink: (s, at) => s.noise(at, 0.6, "lowpass", 700, 150, 0.15),
  // A crate whistling down, thumping onto the ice, and being opened
  crate: (s, at) => s.tone(at, 1.1, "sine", 1500, 420, 0.1),
  land: (s, at) => {
    s.tone(at, 0.18, "sine", 170, 60, 0.5);
    s.noise(at, 0.1, "lowpass", 1200, 400, 0.25);
  },
  open: (s, at) => [659, 880, 1175].forEach((pitch, i) => s.tone(at + i * 0.06, 0.14, "triangle", pitch, pitch, 0.16)),
  // What came out of it: a shield going up, and bursting later, a frost, and a pile of fish
  shield: (s, at) => s.tone(at, 0.3, "sine", 300, 900, 0.2),
  pop: (s, at) => {
    s.noise(at, 0.09, "highpass", 2600, 1200, 0.3);
    s.tone(at, 0.08, "sine", 900, 300, 0.2);
  },
  frost: (s, at) => {
    s.noise(at, 0.5, "highpass", 5200, 2600, 0.22);
    s.tone(at, 0.4, "triangle", 1900, 1100, 0.08);
  },
  feast: (s, at) => [420, 520, 640].forEach((pitch, i) => s.tone(at + i * 0.08, 0.08, "sine", pitch, pitch * 1.9, 0.26)),
  // The wind picking up as a warning, then a gust blowing for its two seconds, as three swells run together
  gustwarn: (s, at) => {
    s.noise(at, 0.6, "bandpass", 500, 1700, 0.16, 2);
    s.tone(at, 0.5, "sine", 520, 900, 0.04);
  },
  gust: (s, at) =>
    [0, 0.55, 1.1].forEach((later, i) => {
      s.noise(at + later, 0.95, "bandpass", 500 + 220 * i, 1300 - 280 * i, 0.24, 0.9);
    }),
  // The walrus rearing up with a grunt, and coming down on the ice
  rear: (s, at) => {
    s.tone(at, 0.5, "sawtooth", 80, 150, 0.13);
    s.tone(at + 0.12, 0.38, "square", 120, 190, 0.04);
  },
  slam: (s, at) => {
    s.tone(at, 0.3, "sine", 130, 40, 0.6);
    s.noise(at, 0.25, "lowpass", 900, 200, 0.4);
  },
  // A watcher's snowball leaving, and bursting where it lands
  throw: (s, at) => s.noise(at, 0.3, "bandpass", 900, 2600, 0.12, 3),
  snowhit: (s, at) => {
    s.noise(at, 0.16, "lowpass", 1800, 500, 0.35);
    s.tone(at, 0.09, "sine", 240, 110, 0.2);
  },
  // A party round's 3-2-1 beginning
  party: (s, at) =>
    [523, 659, 784, 659, 1047].forEach((pitch, i) => s.tone(at + i * 0.09, 0.12, "square", pitch, pitch, 0.07)),
  // The 3-2-1's beeps, and the higher one that starts the round
  beep: (s, at) => s.tone(at, 0.14, "square", 660, 660, 0.07),
  go: (s, at) => {
    s.tone(at, 0.4, "square", 1320, 1320, 0.07);
    s.tone(at, 0.4, "sine", 660, 660, 0.12);
  },
  // A button on a card, the bar or a dialog being pressed
  tap: (s, at) => s.tone(at, 0.06, "triangle", 520, 760, 0.1),
  // Play unlocked a new look
  unlock: (s, at) => [784, 988, 1319].forEach((pitch, i) => s.tone(at + i * 0.08, 0.2, "triangle", pitch, pitch, 0.14)),
  // The round's last knockout going into slow motion: a deep boom under a falling note
  final: (s, at) => {
    s.tone(at, 1, "sine", 150, 42, 0.55);
    s.noise(at, 0.8, "lowpass", 1400, 180, 0.28);
    s.tone(at + 0.04, 0.9, "triangle", 880, 330, 0.1);
  },
  win: (s, at) => [523, 659, 784, 1047].forEach((pitch, i) => s.tone(at + i * 0.1, 0.16, "square", pitch, pitch, 0.08)),
  lose: (s, at) => s.tone(at, 0.6, "triangle", 440, 140, 0.2),
};

export class Sound {
  constructor() {
    // The sound panel (panels.js) keeps these in step with the saved choices
    this.muted = false;
    this.volume = 100;
    this.ac = null;
    this.master = null;
    this.noiseBuffer = null;
    // A hidden page's audio is paused, and everything played into a paused engine would sound at once on resume
    document.addEventListener("visibilitychange", () => this.follow());
    window.addEventListener("pagehide", () => this.close());
  }

  // Safe to call on every press: it makes the engine the first time, and brings it back whenever it isn't running
  unlock() {
    try {
      if (this.ac?.state === "closed") {
        this.ac = null;
      }
      if (!this.ac) {
        this.ac = new (window.AudioContext || window.webkitAudioContext)();
        this.master = this.ac.createGain();
        this.master.gain.value = levelFor(this.volume);
        this.master.connect(this.ac.destination);
        this.noiseBuffer = this.ac.createBuffer(1, this.ac.sampleRate, this.ac.sampleRate);
        const data = this.noiseBuffer.getChannelData(0);
        for (let i = 0; i < data.length; i += 1) {
          data[i] = Math.random() * 2 - 1;
        }
      }
      if (this.ac.state !== "running") {
        this.ac.resume().catch((e) => console.warn("Penguin Wars: couldn't start the sound", e));
      }
    } catch (e) {
      console.warn("Penguin Wars: sound is unavailable", e);
      this.ac = null;
    }
  }

  // Pauses with the page and starts again when it comes back
  follow() {
    if (!this.ac || this.ac.state === "closed") {
      return;
    }
    const change = document.hidden ? this.ac.suspend() : this.ac.resume();
    change.catch((e) => console.warn("Penguin Wars: couldn't pause or start the sound", e));
  }

  close() {
    if (this.ac && this.ac.state !== "closed") {
      this.ac.close().catch((e) => console.warn("Penguin Wars: couldn't close the sound", e));
    }
  }

  // Takes effect at once, on sounds already playing too
  setVolume(volume) {
    this.volume = volume;
    if (this.master) {
      this.master.gain.value = levelFor(volume);
    }
  }

  play(kind, strength = 1) {
    if (!this.ac || this.muted || this.ac.state !== "running") {
      return;
    }
    try {
      SOUNDS[kind](this, this.ac.currentTime, strength);
    } catch (e) {
      console.warn("Penguin Wars: a sound failed", kind, e);
    }
  }

  noise(at, length, type, from, to, peak, q = 1) {
    const { ac } = this;
    const source = ac.createBufferSource();
    const filter = ac.createBiquadFilter();
    const gain = ac.createGain();
    source.buffer = this.noiseBuffer;
    filter.type = type;
    filter.Q.value = q;
    filter.frequency.setValueAtTime(from, at);
    filter.frequency.exponentialRampToValueAtTime(to, at + length);
    envelope(gain, at, peak, length);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    source.start(at);
    source.stop(at + length + 0.05);
  }

  tone(at, length, type, from, to, peak) {
    const { ac } = this;
    const oscillator = ac.createOscillator();
    const gain = ac.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(from, at);
    oscillator.frequency.exponentialRampToValueAtTime(to, at + length);
    envelope(gain, at, peak, length);
    oscillator.connect(gain);
    gain.connect(this.master);
    oscillator.start(at);
    oscillator.stop(at + length + 0.05);
  }
}
