// Warfare 1917's sound, built like the original's three: one-off effects (playSound, F5:253-262), effect loops named
// by an id (playSoundLoop, F5:263-274) and music named by an id (playMusicLoop, F5:275-284). A loop or a piece of music
// is a voice with a volume out of 100 that tween.js can fade (volumeTo) and a stop(), the way the original's Sound
// objects were. Music starts silent, as the original's does, and fades up. Everything plays through the Web Audio API,
// so effects overlap.
//
// Sound effects and music each have an on/off switch kept on this device. Off only keeps new sounds from starting, as
// the original's flags do; sounds already playing carry on, except that music switched off stops. Browsers only allow
// sound after the player touches the page, so voices asked for before that start with the first touch. Sound files are
// decoded the first time they are needed; preload() decodes a list ahead of time.
import { volumeTo } from "./tween.js";

const EFFECTS_KEY = "warfare1917:effects";
const MUSIC_KEY = "warfare1917:music";
// The original starts its loops with 9999 repeats
const FOREVER = 9999;
// Effects playing at once, beyond which new ones are dropped, so a huge battle can't bury the phone
const MOST_EFFECTS = 40;
// How quickly a gain follows a new volume, in seconds, so a fade stepped 60 times a second doesn't click
const SMOOTHING = 0.015;
const MENU_MUSIC = "sound_menuMusic";
const MENU_MUSIC_ID = "menuMusic";
const MENU_FADE_IN = 3;
const MENU_FADE_OUT = 5;

let ctx = null;
let effectsOut = null;
let musicOut = null;
let effects = readFlag(EFFECTS_KEY);
let music = readFlag(MUSIC_KEY);
// Sound name -> file, from the art library, or null before the page has given it
let files = null;
// Sound name -> Promise of the decoded sound
const buffers = new Map();
const wanted = new Set();
const voices = new Set();
const loops = new Map();
const tracks = new Map();
// The one-off effects playing, and how many have been asked for and not yet started or dropped
const shots = new Set();
let asked = 0;
let held = false;

function readFlag(key) {
  try {
    return localStorage.getItem(key) !== "0";
  } catch (e) {
    console.warn("Warfare 1917: couldn't read a sound setting", e);
    return true;
  }
}

function saveFlag(key, on) {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch (e) {
    console.warn("Warfare 1917: couldn't save a sound setting", e);
  }
}

// ---------- Starting up ----------

// Gives the sounds' names and files, from the art library's list
export function setSounds(map) {
  files = new Map(Object.entries(map));
}

function unlock() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    effectsOut = ctx.createGain();
    musicOut = ctx.createGain();
    effectsOut.connect(ctx.destination);
    musicOut.connect(ctx.destination);
    for (const name of wanted) {
      buffer(name);
    }
    for (const voice of voices) {
      begin(voice);
    }
  }
  syncContext();
}

// The sound runs while the page is showing and not held
async function syncContext() {
  if (!ctx || ctx.state === "closed") {
    return;
  }
  try {
    await (held || document.hidden ? ctx.suspend() : ctx.resume());
  } catch (e) {
    console.warn("Warfare 1917: couldn't start or pause the sound", e);
  }
}

function close() {
  stopAll();
  if (ctx && ctx.state !== "closed") {
    ctx.close().catch((e) => console.warn("Warfare 1917: couldn't close the sound", e));
  }
}

window.addEventListener("pointerdown", unlock);
window.addEventListener("keydown", unlock);
document.addEventListener("visibilitychange", syncContext);
window.addEventListener("pagehide", close);

function buffer(name) {
  if (!buffers.has(name)) {
    const file = files ? files.get(name) : `${name}.mp3`;
    const loaded = !file
      ? Promise.resolve(null)
      : fetch(`sounds/${file}`)
          .then((resp) => {
            if (!resp.ok) {
              throw new Error(`The sound file answered ${resp.status}`);
            }
            return resp.arrayBuffer();
          })
          .then((bytes) => ctx.decodeAudioData(bytes))
          .catch((e) => {
            console.warn(`Warfare 1917: couldn't load sound ${name}`, e);
            return null;
          });
    if (!file) {
      console.warn(`Warfare 1917: no sound called ${name}`);
    }
    buffers.set(name, loaded);
  }
  return buffers.get(name);
}

// Decodes these sounds now, so their first play isn't late
export function preload(names) {
  for (const name of names) {
    wanted.add(name);
    if (ctx) {
      buffer(name);
    }
  }
}

// ---------- Voices ----------

// One looping sound or piece of music. volume is out of 100
class Voice {
  constructor(name, count, kind, volume) {
    this.name = name;
    this.count = count;
    this.kind = kind;
    this.level = volume;
    this.stopped = false;
    this.source = null;
    this.gain = null;
    voices.add(this);
  }

  get volume() {
    return this.level;
  }

  set volume(value) {
    this.level = Math.max(0, Math.min(100, value));
    if (this.gain) {
      this.gain.gain.setTargetAtTime(this.level / 100, ctx.currentTime, SMOOTHING);
    }
  }

  stop() {
    this.stopped = true;
    voices.delete(this);
    if (this.source) {
      this.source.onended = null;
      try {
        this.source.stop();
      } catch (e) {
        console.warn("Warfare 1917: couldn't stop a sound", e);
      }
      this.source.disconnect();
      this.gain.disconnect();
      this.source = null;
    }
    for (const registry of [loops, tracks]) {
      for (const [id, voice] of registry) {
        if (voice === this) {
          registry.delete(id);
        }
      }
    }
  }
}

async function begin(voice) {
  const sound = await buffer(voice.name);
  if (!sound || voice.stopped || voice.source || ctx.state === "closed") {
    return;
  }
  const gain = ctx.createGain();
  gain.gain.value = voice.level / 100;
  const source = ctx.createBufferSource();
  source.buffer = sound;
  source.loop = voice.count > 1;
  source.connect(gain);
  gain.connect(voice.kind === "music" ? musicOut : effectsOut);
  source.start();
  if (voice.count > 1 && voice.count < FOREVER) {
    source.stop(ctx.currentTime + sound.duration * voice.count);
  }
  source.onended = () => voice.stop();
  voice.gain = gain;
  voice.source = source;
}

function makeVoice(name, count, kind, volume) {
  const voice = new Voice(name, count, kind, volume);
  if (ctx) {
    begin(voice);
  }
  return voice;
}

function fadeOut(voice, seconds) {
  if (seconds > 0) {
    volumeTo(voice, 0, seconds, "easeOutSine", 0, () => voice.stop());
  } else {
    voice.stop();
  }
}

// ---------- Effects ----------

// playSound: a sound that plays once, when sound effects are on
export function play(name) {
  if (!effects || !ctx || ctx.state !== "running" || asked + shots.size >= MOST_EFFECTS) {
    return;
  }
  if (files && !files.has(name)) {
    console.warn(`Warfare 1917: no sound called ${name}`);
    return;
  }
  asked += 1;
  buffer(name).then((sound) => {
    asked -= 1;
    if (!sound || ctx.state !== "running" || !effects) {
      return;
    }
    const source = ctx.createBufferSource();
    source.buffer = sound;
    source.connect(effectsOut);
    source.onended = () => {
      shots.delete(source);
      source.disconnect();
    };
    shots.add(source);
    source.start();
  });
}

// playSoundLoop: a sound that repeats (9999 times by default) until stopped, found again by its id. Null when sound
// effects are off
export function loop(name, id, count = FOREVER) {
  if (!effects) {
    return null;
  }
  loops.get(id)?.stop();
  const voice = makeVoice(name, count, "effects", 100);
  loops.set(id, voice);
  return voice;
}

export function loopVoice(id) {
  return loops.get(id) ?? null;
}

// The loop stops now, or fades out over some seconds first
export function stopLoop(id, fadeSeconds = 0) {
  const voice = loops.get(id);
  if (voice) {
    fadeOut(voice, fadeSeconds);
  }
}

// ---------- Music ----------

// playMusicLoop followed by volumeTo(100, fadeIn): a piece of music that plays `count` times (the menu's once), found
// again by its id, silent at first and fading up over fadeIn seconds. Null when music is off
export function playMusic(name, id = name, count = 1, fadeIn = 0) {
  if (!music) {
    return null;
  }
  tracks.get(id)?.stop();
  const voice = makeVoice(name, count, "music", 0);
  tracks.set(id, voice);
  volumeTo(voice, 100, fadeIn);
  return voice;
}

// The music with that id stops now, or fades out first. With no id, all music does
export function stopMusic(id = null, fadeSeconds = 0) {
  const ids = id === null ? [...tracks.keys()] : [id];
  for (const each of ids) {
    const voice = tracks.get(each);
    if (voice) {
      fadeOut(voice, fadeSeconds);
    }
  }
}

// loadMenu's music (F5:298-299), fading up over fadeIn seconds. The Options screen's music ON starts it at full
// volume at once (F5:906-908)
export function menuMusic(fadeIn = MENU_FADE_IN) {
  return playMusic(MENU_MUSIC, MENU_MUSIC_ID, 1, fadeIn);
}

// hideMenu's and moveMenu's (F5:313-332)
export function stopMenuMusic(fadeSeconds = MENU_FADE_OUT) {
  stopMusic(MENU_MUSIC_ID, fadeSeconds);
}

// ---------- Settings and holds ----------

export function effectsOn() {
  return effects;
}

export function musicOn() {
  return music;
}

export function setEffects(on) {
  effects = on;
  saveFlag(EFFECTS_KEY, on);
}

// Turning music off stops what plays. Turning it on starts nothing: the screen decides what to play
export function setMusic(on) {
  music = on;
  saveFlag(MUSIC_KEY, on);
  if (!on) {
    for (const voice of [...tracks.values()]) {
      voice.stop();
    }
  }
}

// Holds every sound where it is (a paused battle), or lets them go on
export function pauseAll(on) {
  held = on;
  syncContext();
}

// stopAllSounds (F5:6674): every sound and every piece of music stops
export function stopAll() {
  for (const voice of [...voices]) {
    voice.stop();
  }
  for (const source of shots) {
    source.onended = null;
    source.stop();
    source.disconnect();
  }
  shots.clear();
}

// What is playing, for checking from outside
export function soundState() {
  return {
    context: ctx ? ctx.state : null,
    shots: shots.size,
    loops: [...loops].map(([id, voice]) => [id, voice.name, Math.round(voice.volume), Boolean(voice.source)]),
    tracks: [...tracks].map(([id, voice]) => [id, voice.name, Math.round(voice.volume), Boolean(voice.source)]),
  };
}
