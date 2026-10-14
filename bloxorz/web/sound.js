// Bloxorz's sound: the original's effects, which timelines start with their own volume curves, and its two looping
// tracks (menu and ambient). Everything plays through the Web Audio API so effects can overlap. The one Toggle Sound
// switch mutes it all, music included, and is kept on this device.
// Every game on the hub shares one storage, so the key carries the game's name
const MUTED_KEY = "bloxorz:muted";
// How many names `played` keeps, for checks
const PLAYED_KEPT = 50;

function readMuted() {
  try {
    return localStorage.getItem(MUTED_KEY) === "1";
  } catch (e) {
    console.warn("Bloxorz: couldn't read the sound setting", e);
    return false;
  }
}

function saveMuted(muted) {
  try {
    localStorage.setItem(MUTED_KEY, muted ? "1" : "0");
  } catch (e) {
    console.warn("Bloxorz: couldn't save the sound setting", e);
  }
}

export class Sound {
  constructor() {
    this.muted = readMuted();
    // The last PLAYED_KEPT sound names started, newest last. Recorded even when nothing can be heard (muted, or the
    // player has not touched the page yet), so a check can read what the game asked for
    this.played = [];
    // Sound name -> file in sounds/, from the art's data
    this.files = {};
    this.ctx = null;
    this.master = null;
    // name -> Promise of the decoded sound, once the audio has started
    this.buffers = new Map();
    // The track the game wants ({ name, volume }) and the one playing now ({ name, source })
    this.wanted = null;
    this.track = null;
    this.sources = new Set();
    // Browsers only allow sound after the player touches the page
    const unlock = () => this.unlock();
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    document.addEventListener("visibilitychange", () => this.update());
    window.addEventListener("pagehide", () => this.close());
  }

  load(files) {
    this.files = files;
  }

  unlock() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.muted ? 0 : 1;
      this.master.connect(this.ctx.destination);
      for (const name of Object.keys(this.files)) {
        this.buffer(name);
      }
      if (this.wanted) {
        this.startTrack(this.wanted);
      }
    }
    this.update();
  }

  buffer(name) {
    if (!this.buffers.has(name)) {
      const file = this.files[name];
      const loaded = fetch(`sounds/${file}`)
        .then((resp) => {
          if (!resp.ok) {
            throw new Error(`The sound file answered ${resp.status}`);
          }
          return resp.arrayBuffer();
        })
        .then((bytes) => this.ctx.decodeAudioData(bytes))
        .catch((e) => {
          console.warn(`Bloxorz: couldn't load sound ${name}`, e);
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
      console.warn("Bloxorz: couldn't start or pause the sound", e);
    }
  }

  note(name) {
    this.played.push(name);
    if (this.played.length > PLAYED_KEPT) {
      this.played.splice(0, this.played.length - PLAYED_KEPT);
    }
  }

  // ---------- Toggle Sound ----------

  // The original's button: muted and unmuted. Returns whether sound is now muted
  toggle() {
    this.muted = !this.muted;
    saveMuted(this.muted);
    if (this.master) {
      this.master.gain.setTargetAtTime(this.muted ? 0 : 1, this.ctx.currentTime, 0.015);
    }
    return this.muted;
  }

  // ---------- Playing ----------

  // A timeline's sound. fade: the volume the original set on this start, [[seconds, volume], ...] with straight
  // ramps between them, or nothing for full volume
  play(name, fade = null) {
    this.note(name);
    if (this.muted || !this.ctx || this.ctx.state !== "running" || !this.files[name]) {
      return;
    }
    this.buffer(name).then((buffer) => {
      if (!buffer || this.ctx.state !== "running") {
        return;
      }
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      if (fade?.length) {
        const gain = this.ctx.createGain();
        const start = this.ctx.currentTime;
        gain.gain.setValueAtTime(fade[0][1], start);
        for (const [at, volume] of fade) {
          gain.gain.linearRampToValueAtTime(volume, start + at);
        }
        source.connect(gain);
        gain.connect(this.master);
      } else {
        source.connect(this.master);
      }
      source.addEventListener("ended", () => this.sources.delete(source));
      this.sources.add(source);
      source.start();
    });
  }

  // The original's backs.attachSound / backs.start loop (R20, R46): the track named loops at that volume (0 to 1). The
  // track already playing is left alone; changing track first stops every sound, like its stopAllSounds()
  music(name, volume = 1) {
    if (this.wanted?.name === name) {
      return;
    }
    this.stopAll();
    this.note(name);
    this.wanted = { name, volume };
    if (this.ctx) {
      this.startTrack(this.wanted);
    }
  }

  async startTrack(wanted) {
    const buffer = await this.buffer(wanted.name);
    if (!buffer || this.wanted !== wanted || this.track || this.ctx.state === "closed") {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    const gain = this.ctx.createGain();
    gain.gain.value = wanted.volume;
    source.connect(gain);
    gain.connect(this.master);
    source.start();
    this.track = { source, gain };
  }

  // The original's stopAllSounds(): the track and every effect still sounding
  stopAll() {
    this.wanted = null;
    if (this.track) {
      this.track.source.stop();
      this.track.gain.disconnect();
      this.track = null;
    }
    for (const source of this.sources) {
      source.stop();
    }
    this.sources.clear();
  }

  close() {
    this.stopAll();
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Bloxorz: couldn't close the sound", e));
    }
  }
}
