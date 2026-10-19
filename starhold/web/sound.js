// Starhold's sound: effects mixed from recordings, played with small random changes in pitch and volume so repeats
// never sound identical; robots' footsteps on their own beats; and two songs (menus and battle) that crossfade into
// each other. The Sound button cycles music and effects the way Boulder Bash's does.
import { findRobot } from "./sim/robots.js";
import { BLASTER, BUZZER, MAP, MISSILE, ROBOTS, TESLA, WAVES } from "./sim/rules.js";

const SONGS = { menu: "music/title.mp3", play: "music/battle.mp3" };
const FILES = [
  "tap",
  "build",
  "upgrade",
  "form",
  "sell",
  "park",
  "turn",
  "shot-blaster",
  "shot-gatling",
  "shot-railgun",
  "shot-missile",
  "shot-swarm",
  "shot-mortar",
  "zap",
  "zap-storm",
  "zap-disruptor",
  "hit",
  "hit-armor",
  "blast",
  "blast-big",
  "grab",
  "drone-down",
  "drone-back",
  "step-scrapper",
  "step-skitter",
  "step-brute",
  "step-splitter",
  "step-colossus",
  "rotor-buzzer",
  "die-scrapper",
  "die-skitter",
  "die-buzzer",
  "die-brute",
  "die-splitter",
  "die-colossus",
  "split",
  "leak",
  "life",
  "wave",
  "wave-boss",
  "call",
  "strike-charge",
  "strike-blast",
  "stasis",
  "over",
  "cashin",
];
const MUSIC_VOLUME = 0.3;
const EFFECTS_VOLUME = 0.75;
const ROTOR_VOLUME = 0.4;
const ROTOR_FADE = 0.3;
// Each song's last seconds fade into its own start, and moving between menus and play crossfades the two songs
const CROSSFADE = 2;
const EFFECTS_FADE = 1;
// Every game on the hub shares one storage, so the keys carry the game's name
const MUSIC_KEY = "starhold:music";
const SOUND_KEY = "starhold:sound";
// Repeats of one sound: at most this many playing at once, and never two starting closer together than MIN_GAP
// seconds. A Gatling volley or a Swarm salvo otherwise turns to mush and only gets louder
const MOST_AT_ONCE = { hit: 5, "hit-armor": 4, "shot-gatling": 4, "shot-blaster": 4, "shot-swarm": 2, turn: 2 };
const MOST_DEFAULT = 3;
const MIN_GAP = 0.03;
// After a song fails to download, seconds before another try
const SONG_RETRY = 30;
const PITCH_SPREAD = 0.06;
const VOLUME_SPREAD = 0.12;
// Sounds are placed left or right by where they happen, at most this far
const PAN_WIDTH = 0.6;
// Seconds between one robot type's footsteps while any of them walk
const STEP_EVERY = { scrapper: 0.45, skitter: 0.2, brute: 0.75, splitter: 0.5, colossus: 1.1 };
// The shot each tower makes: its level shot, then its two final forms'
const TOWER_SHOTS = {
  [BLASTER]: ["shot-blaster", "shot-gatling", "shot-railgun"],
  [MISSILE]: ["shot-missile", "shot-swarm", "shot-mortar"],
  [TESLA]: ["zap", "zap-storm", "zap-disruptor"],
};
// Events whose sound never depends on anything else
const PLAIN = {
  build: "build",
  upgrade: "upgrade",
  form: "form",
  sell: "sell",
  park: "park",
  call: "call",
  grab: "grab",
  droneDown: "drone-down",
  droneBack: "drone-back",
  stasis: "stasis",
  split: "split",
  over: "over",
};

function readSetting(key) {
  try {
    return localStorage.getItem(key) !== "off";
  } catch (e) {
    console.warn("Starhold: couldn't read a sound setting", e);
    return true;
  }
}

function saveSetting(key, on) {
  try {
    localStorage.setItem(key, on ? "on" : "off");
  } catch (e) {
    console.warn("Starhold: couldn't save a sound setting", e);
  }
}

function spotX(spot) {
  return MAP.spots[spot][0] * 100;
}

function panFor(x) {
  return x === undefined || x === null ? 0 : ((x / (MAP.width * 100)) * 2 - 1) * PAN_WIDTH;
}

function towerShot(run, spot) {
  const tower = run.towers[spot];
  const shots = tower ? TOWER_SHOTS[tower.kind] : null;
  return shots ? shots[tower.form + 1] : null;
}

// A tower's shot, with a turret whine first when it swung to a new target. A null target (the Railgun's beam event
// carries no robot) never whines
function aimed(sound, spot, target, name) {
  if (!name) {
    return [];
  }
  const x = spotX(spot);
  const turned = target !== null && sound.aim.get(spot) !== target;
  sound.aim.set(spot, target);
  return turned ? [["turn", x], [name, x]] : [[name, x]];
}

// Each event that needs more than a name: returns [sound name, x] pairs
const HANDLERS = {
  shot: (sound, e, run) => aimed(sound, e.spot, e.id, towerShot(run, e.spot)),
  rail: (sound, e, run) => aimed(sound, e.spot, null, towerShot(run, e.spot)),
  zap: (sound, e, run) => aimed(sound, e.spot, e.ids[0], towerShot(run, e.spot)),
  launch: (sound, e, run) => {
    // The strike's own event plays its charge; only towers' missiles get a launch sound
    if (e.shell.kind === "strike") {
      return [];
    }
    return aimed(sound, e.spot, e.shell.target, towerShot(run, e.spot));
  },
  hit: (sound, e, run) => {
    const robot = findRobot(run, e.id);
    return [[robot && ROBOTS[robot.type].armored ? "hit-armor" : "hit", robot ? robot.x : null]];
  },
  boom: (sound, e) => [[e.strike ? "strike-blast" : e.big ? "blast-big" : "blast", e.x]],
  die: (sound, e) => [[`die-${ROBOTS[e.type].key}`, e.x]],
  leak: () => [
    ["leak", MAP.core[0] * 100],
    ["life", MAP.core[0] * 100],
  ],
  wave: (sound, e) => [[e.n % WAVES.bossEvery === 0 ? "wave-boss" : "wave", null]],
  strike: (sound, e) => [["strike-charge", e.x]],
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
    this.failedAt = {};
    this.track = null;
    this.wanted = null;
    // How many copies of each sound play now, and when each last started
    this.playing = new Map();
    this.lastAt = new Map();
    // Per run: each tower's last target, for the turret whine
    this.run = null;
    this.aim = new Map();
    this.nextStep = [];
    this.rotor = null;
    const unlock = () => this.unlock();
    // Browsers only allow sound after the player touches the page
    // (a finger's pointerdown doesn't count on iPhones, its pointerup and touchend do)
    for (const name of ["pointerdown", "pointerup", "touchend"]) {
      window.addEventListener(name, unlock);
    }
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
          console.warn(`Starhold: couldn't load the ${name} sound`, e);
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
      console.warn("Starhold: couldn't start or pause the sound", e);
      return;
    }
    this.startSong(this.scene);
  }

  // The Sound button's label names what it does next: music off, then sound off, then music on, then sound on
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

  // One effect. x (hundredths of a map unit) places it left or right; steady skips the random variation (UI sounds)
  play(name, { x = null, volume = 1, steady = false } = {}) {
    if (!this.sfxOn || !this.ctx || this.ctx.state !== "running") {
      return;
    }
    const buffer = this.buffers[name];
    if (!buffer || !this.room(name)) {
      return;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.value = steady ? 1 : 1 + (Math.random() * 2 - 1) * PITCH_SPREAD;
    const gain = this.ctx.createGain();
    gain.gain.value = steady ? volume : volume * (1 - Math.random() * VOLUME_SPREAD);
    const panner = this.ctx.createStereoPanner();
    panner.pan.value = panFor(x);
    source.connect(gain).connect(panner).connect(this.effectsOut);
    this.playing.set(name, (this.playing.get(name) || 0) + 1);
    this.lastAt.set(name, this.ctx.currentTime);
    source.addEventListener("ended", () => this.playing.set(name, this.playing.get(name) - 1));
    source.start();
  }

  room(name) {
    const most = MOST_AT_ONCE[name] ?? MOST_DEFAULT;
    const last = this.lastAt.get(name) ?? -Infinity;
    return (this.playing.get(name) || 0) < most && this.ctx.currentTime - last >= MIN_GAP;
  }

  // The run's events since the last frame, each turned into its sounds. A new run starts with no remembered aims
  events(list, run) {
    if (run !== this.run) {
      this.run = run;
      this.aim.clear();
    }
    for (const event of list) {
      for (const [name, x] of this.soundsFor(event, run)) {
        this.play(name, { x });
      }
    }
  }

  // One event's sounds as [name, x] pairs, placed at the event's spot or position
  soundsFor(event, run) {
    const plain = PLAIN[event.kind];
    if (plain) {
      return [[plain, event.spot === undefined ? event.x : spotX(event.spot)]];
    }
    const handler = HANDLERS[event.kind];
    return handler ? handler(this, event, run) : [];
  }

  // Called each frame with how many robots of each type are walking (by ROBOTS index; zeros while paused). Each type
  // steps on its own beat, a little louder the more there are, and the Buzzers' rotors hum while any fly
  walk(counts) {
    if (!this.ctx || this.ctx.state !== "running") {
      return;
    }
    const now = this.ctx.currentTime;
    ROBOTS.forEach((robot, type) => {
      const every = STEP_EVERY[robot.key];
      if (!every || !counts[type] || now < (this.nextStep[type] ?? 0)) {
        return;
      }
      this.nextStep[type] = now + every;
      this.play(`step-${robot.key}`, { volume: Math.min(1, 0.35 + 0.08 * counts[type]) });
    });
    this.hum(counts[BUZZER] > 0);
  }

  hum(on) {
    const buffer = this.buffers["rotor-buzzer"];
    if (on && !this.rotor && buffer) {
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.loop = true;
      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0, this.ctx.currentTime);
      gain.gain.linearRampToValueAtTime(ROTOR_VOLUME, this.ctx.currentTime + ROTOR_FADE);
      source.connect(gain).connect(this.effectsOut);
      source.start();
      this.rotor = { source, gain };
    } else if (!on && this.rotor) {
      const { source, gain } = this.rotor;
      this.rotor = null;
      const now = this.ctx.currentTime;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(0, now + ROTOR_FADE);
      source.stop(now + ROTOR_FADE + 0.05);
    }
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
    }
    try {
      return await this.loading[name];
    } catch (e) {
      delete this.loading[name];
      this.failedAt[name] = this.ctx.currentTime;
      throw e;
    }
  }

  // The new song loads first, so the old one keeps playing until the two can crossfade
  async startSong(name) {
    this.wanted = name;
    if (this.track?.name === name) {
      return;
    }
    if (this.ctx.currentTime - (this.failedAt[name] ?? -Infinity) < SONG_RETRY) {
      return;
    }
    try {
      this.songs[name] = this.songs[name] || (await this.loadSong(name));
    } catch (e) {
      console.warn("Starhold: couldn't load the music", e);
      return;
    }
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
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch((e) => console.warn("Starhold: couldn't close the sound", e));
    }
  }
}
