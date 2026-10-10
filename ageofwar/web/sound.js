// Age of War's sound: the original's effects, started by the animation frames that started them in the original,
// and its battle music. Effects play through the Web Audio API so many can overlap.
const VOLUME = 0.6;
const MUSIC_VOLUME = 0.45;
// Every game on the hub shares one storage, so the keys carry the game's name
const SOUND_KEY = "ageofwar:sound";
const MUSIC_KEY = "ageofwar:music";
const MUSIC = 1035;
// The original's effects, by sound id (web/sounds/<id>.mp3)
const EFFECTS = [
  234, 235, 239, 240, 241, 242, 243, 269, 314, 316, 342, 347, 382, 451, 470, 480, 496, 524, 591, 656, 680, 733, 745,
  843, 972,
];
// A big fight starts the same sound many times in one frame: this many at once is plenty
const MOST_AT_ONCE = 3;
const OVERLAP_MS = 60;

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Age of War: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Age of War: couldn't save a sound setting", e);
  }
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.out = null;
    this.on = readSetting(SOUND_KEY);
    this.musicOn = readSetting(MUSIC_KEY);
    this.buffers = new Map();
    this.playing = new Map();
    this.music = new Audio(`sounds/${MUSIC}.mp3`);
    this.music.loop = true;
    this.music.volume = MUSIC_VOLUME;
    this.music.preload = "none";
    // The music plays during a battle, like the original's, and only once the player has touched the page
    this.wantMusic = false;
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
      this.load();
    }
    this.update();
  }

  load() {
    for (const id of EFFECTS) {
      fetch(`sounds/${id}.mp3`)
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`The sound file answered ${resp.status}`);
          }
          return resp.arrayBuffer();
        })
        .then((bytes) => this.ctx.decodeAudioData(bytes))
        .then((buffer) => this.buffers.set(id, buffer))
        .catch((e) => console.warn(`Age of War: couldn't load sound ${id}`, e));
    }
  }

  // Pauses everything while the page is hidden
  async update() {
    this.updateMusic();
    if (!this.ctx || this.ctx.state === "closed") {
      return;
    }
    try {
      await (document.hidden ? this.ctx.suspend() : this.ctx.resume());
    } catch (e) {
      console.warn("Age of War: couldn't start or pause the sound", e);
    }
  }

  updateMusic() {
    const play = this.wantMusic && this.musicOn && this.ctx !== null && !document.hidden;
    if (play && this.music.paused) {
      this.music.play().catch((e) => console.warn("Age of War: couldn't start the music", e));
    } else if (!play && !this.music.paused) {
      this.music.pause();
    }
  }

  setOn(on) {
    this.on = on;
    saveSetting(SOUND_KEY, on);
  }

  setMusicOn(on) {
    this.musicOn = on;
    saveSetting(MUSIC_KEY, on);
    this.updateMusic();
  }

  // The battle started or ended: its music starts from the top each battle
  battle(on) {
    if (on && !this.wantMusic) {
      this.music.currentTime = 0;
    }
    this.wantMusic = on;
    this.updateMusic();
  }

  play(id) {
    if (!this.on || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    const buffer = this.buffers.get(id);
    if (!buffer) {
      return;
    }
    const now = performance.now();
    const recent = (this.playing.get(id) || []).filter((at) => now - at < OVERLAP_MS);
    if (recent.length >= MOST_AT_ONCE) {
      return;
    }
    recent.push(now);
    this.playing.set(id, recent);
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.out);
    source.start();
  }

  close() {
    this.music.pause();
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Age of War: couldn't close the sound", e));
    }
  }
}
