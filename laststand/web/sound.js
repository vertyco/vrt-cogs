// The game's sound, built the way the original's three calls work: one-off effects (playSound, F4:625-661) that take a
// volume and a pan out of 100, effect loops named by an id (playSoundLoop, F4:662-680) and music (playMusicLoop,
// F4:681-709). Everything plays through the Web Audio API, so effects overlap.
//
// An effect aimed at a place in the world (x) is louder the nearer it is to the player and leans toward the side it
// comes from (distSound and panSound, F4:754-793). The original counts the distance from the player, not the camera.
// Effects take turns in 33 channels, so the 34th sound cuts off the first. Music fades in on a new track while the old
// one fades out. Whether effects and music are on is part of the save (story.settings), so loading a slot sets it.
//
// Browsers only allow sound after the player touches the page. Music asked for before that starts with the first
// touch; effects asked for before it are lost, as they are for any sound the player could not have heard. Sound files
// are decoded the first time they are needed, and preload() decodes a list ahead of time.
import { data } from "./data.js";
import { story } from "./story.js";
import { world } from "./world.js";

// The original's effect channels: a new effect takes the next one and cuts off whatever still plays there
const CHANNELS = 33;
// Repeats the original asks for when a loop or a piece of music should go on until stopped
const FOREVER = 999999;
const LOOP_REPEATS = 9999;
// Fade of stopAllMusic (F4:710-722), in seconds
const STOP_FADE = 2;
// The calls kept for checks
const LOG_SIZE = 200;
const FULL = 100;

// Sound name -> file in sounds/, from flash.json
let files = new Map();
let ctx = null;
let effectsOut = null;
let musicOut = null;
let held = false;
// Sound name -> Promise of the decoded sound (null when it could not load)
const buffers = new Map();
const wanted = new Set();
const missing = new Set();
// Everything that is a voice: loops and music, played or waiting for the first touch
const voices = new Set();
const loops = new Map();
// The effect channels, in turn, and the one the next effect takes
const channels = new Array(CHANNELS).fill(null);
let nextChannel = 0;
// Sounds the animations start, which have no channel
const timeline = new Set();
// The piece of music that plays now
let current = null;
const calls = [];
// Used while no story holds the settings (the menus)
const menuSettings = { soundOn: true, musicOn: true };

function constant(name) {
  return data.actors.constants[name];
}

function settings() {
  return story.settings ?? menuSettings;
}

function record(entry) {
  calls.push({ t: Math.round(performance.now()), ...entry });
  if (calls.length > LOG_SIZE) {
    calls.shift();
  }
}

// ---------- Starting up ----------

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

// The sound runs while the page is showing and nothing holds it
async function syncContext() {
  if (!ctx || ctx.state === "closed") {
    return;
  }
  try {
    await (held || document.hidden ? ctx.suspend() : ctx.resume());
  } catch (e) {
    console.warn("Union City: couldn't start or pause the sound", e);
  }
}

function close() {
  stopAll();
  if (ctx && ctx.state !== "closed") {
    ctx.close().catch((e) => console.warn("Union City: couldn't close the sound", e));
  }
}

window.addEventListener("pointerdown", unlock);
window.addEventListener("keydown", unlock);
document.addEventListener("visibilitychange", syncContext);
window.addEventListener("pagehide", close);

// Gives the sounds' names and files (flash.json's sounds)
function setSounds(map) {
  files = new Map(Object.entries(map));
}

function buffer(name) {
  if (!buffers.has(name)) {
    const file = files.get(name);
    if (!file && !missing.has(name)) {
      missing.add(name);
      console.warn(`Union City: no sound called ${name}`);
    }
    buffers.set(
      name,
      file
        ? fetch(`sounds/${file}`)
            .then((resp) => {
              if (!resp.ok) {
                throw new Error(`The sound file answered ${resp.status}`);
              }
              return resp.arrayBuffer();
            })
            .then((bytes) => ctx.decodeAudioData(bytes))
            .catch((e) => {
              console.warn(`Union City: couldn't load sound ${name}`, e);
              return null;
            })
        : Promise.resolve(null),
    );
  }
  return buffers.get(name);
}

// Decodes these sounds now, so their first play isn't late
function preload(names) {
  for (const name of names) {
    wanted.add(name);
    if (ctx) {
      buffer(name);
    }
  }
}

// ---------- Voices ----------

// One looping sound or piece of music. Its volume is out of 100 and moves in straight lines (volumeTo "linear")
class Voice {
  constructor(name, kind, repeats, volume) {
    this.name = name;
    this.kind = kind;
    this.repeats = repeats;
    this.id = null;
    this.stopped = false;
    this.source = null;
    this.gain = null;
    this.timer = null;
    // The fade under way: from where, to where, when it began and how long it takes (milliseconds)
    this.fade = { from: volume, to: volume, begun: 0, ms: 0 };
    voices.add(this);
  }

  // The volume now, out of 100
  get level() {
    const { from, to, begun, ms } = this.fade;
    const done = ms > 0 ? Math.min(1, (performance.now() - begun) / ms) : 1;
    return from + (to - from) * done;
  }

  // Moves to `to` over some seconds, then runs `then` (stopping, usually)
  fadeTo(to, seconds, then = null) {
    clearTimeout(this.timer);
    this.fade = { from: this.level, to, begun: performance.now(), ms: seconds * 1000 };
    this.ramp();
    if (then) {
      this.timer = setTimeout(then, seconds * 1000);
    }
  }

  // Hands the fade to the audio clock, which keeps it smooth between frames
  ramp() {
    if (!this.gain) {
      return;
    }
    const param = this.gain.gain;
    const now = ctx.currentTime;
    const left = this.fade.ms - (performance.now() - this.fade.begun);
    param.cancelScheduledValues(now);
    param.setValueAtTime(this.level / FULL, now);
    if (left > 0) {
      param.linearRampToValueAtTime(this.fade.to / FULL, now + left / 1000);
    }
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    voices.delete(this);
    if (loops.get(this.id) === this) {
      loops.delete(this.id);
    }
    if (current === this) {
      current = null;
    }
    if (this.source) {
      this.source.onended = null;
      try {
        this.source.stop();
      } catch (e) {
        console.warn("Union City: couldn't stop a sound", e);
      }
      this.source.disconnect();
      this.gain.disconnect();
      this.source = null;
      this.gain = null;
    }
  }
}

async function begin(voice) {
  const sound = await buffer(voice.name);
  if (!sound || voice.stopped || voice.source || ctx.state === "closed") {
    return;
  }
  const gain = ctx.createGain();
  const source = ctx.createBufferSource();
  source.buffer = sound;
  source.loop = voice.repeats > 1;
  source.connect(gain);
  gain.connect(voice.kind === "music" ? musicOut : effectsOut);
  source.start();
  if (voice.repeats > 1 && voice.repeats < FOREVER) {
    source.stop(ctx.currentTime + sound.duration * voice.repeats);
  }
  source.onended = () => voice.stop();
  voice.gain = gain;
  voice.source = source;
  voice.ramp();
}

function startVoice(voice) {
  if (ctx) {
    begin(voice);
  }
  return voice;
}

// ---------- Effects ----------

// distSound (F4:754-768): out of 100 by how far the sound is from the player; under the cut-off it is 0
function distance(x) {
  const away = Math.abs(sound.listener() - x);
  const volume = Math.round(((constant("distSoundRange") - away) / constant("distSoundRange")) * FULL);
  return volume < constant("volCutOff") ? 0 : volume;
}

// panSound (F4:769-793): -100 hard left to 100 hard right, by how far to either side of the player the sound is
function panOf(x) {
  const across = x - sound.listener();
  const pan = Math.round((Math.abs(across) / constant("distSoundRange")) * FULL);
  return across < 0 ? -pan : pan;
}

// playSound: a sound that plays once, when effects are on. x puts it in the world (volume and pan follow from the
// distance); volume and pan, out of 100, say them outright; with none it plays at full volume in the middle. Heard
// only above the cut-off volume
function play(name, { x, volume, pan } = {}) {
  if (!settings().soundOn) {
    return;
  }
  const level = volume ?? (x === undefined ? FULL : distance(x));
  const side = pan ?? (x === undefined ? 0 : panOf(x));
  const heard = level > constant("volCutOff");
  record({ kind: "effect", name, volume: level, pan: side, heard });
  if (!heard || !ctx || ctx.state !== "running") {
    return;
  }
  const channel = {
    source: null,
    cancelled: false,
    cancel() {
      this.cancelled = true;
      this.source?.stop();
    },
  };
  channels[nextChannel]?.cancel();
  channels[nextChannel] = channel;
  nextChannel = (nextChannel + 1) % CHANNELS;
  const parts = [];
  buffer(name).then((sounds) => {
    if (!sounds || channel.cancelled || ctx.state !== "running") {
      return;
    }
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    const panner = ctx.createStereoPanner();
    source.buffer = sounds;
    gain.gain.value = level / FULL;
    panner.pan.value = side / FULL;
    source.connect(gain);
    gain.connect(panner);
    panner.connect(effectsOut);
    parts.push(source, gain, panner);
    source.onended = () => {
      for (const part of parts) {
        part.disconnect();
      }
      if (channels.includes(channel)) {
        channels[channels.indexOf(channel)] = null;
      }
    };
    channel.source = source;
    source.start();
  });
}

// A sound an animation starts on a frame (lib.onSound). points is the volume it was given, [[seconds, volume 0 to 1],
// ...] with straight lines between, or nothing for full volume
function startTimeline(name, points = null) {
  if (!settings().soundOn) {
    return;
  }
  record({ kind: "timeline", name, volume: points?.[0]?.[1] === undefined ? FULL : points[0][1] * FULL, pan: 0 });
  if (!ctx || ctx.state !== "running") {
    return;
  }
  buffer(name).then((sounds) => {
    if (!sounds || ctx.state !== "running") {
      return;
    }
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = sounds;
    source.connect(gain);
    gain.connect(effectsOut);
    if (points?.length) {
      const now = ctx.currentTime;
      gain.gain.setValueAtTime(points[0][1], now);
      for (const [seconds, volume] of points) {
        gain.gain.linearRampToValueAtTime(volume, now + seconds);
      }
    }
    source.onended = () => {
      timeline.delete(source);
      source.disconnect();
      gain.disconnect();
    };
    timeline.add(source);
    source.start();
  });
}

// playSoundLoop: a sound that repeats until stopped, found again by its id. Nothing starts while a loop with that id
// plays, or while effects are off
function loop(name, id, repeats = LOOP_REPEATS) {
  if (!settings().soundOn || loops.has(id)) {
    return;
  }
  const voice = new Voice(name, "effects", repeats, FULL);
  voice.id = id;
  loops.set(id, voice);
  record({ kind: "loop", name, volume: FULL, pan: 0 });
  startVoice(voice);
}

function stopLoop(id) {
  loops.get(id)?.stop();
}

// ---------- Music ----------

// playMusicLoop: the new piece starts silent and fades up to `volume` over `fade` seconds while the one before fades out
// over the same time and stops. Nothing plays while music is off
function music(name, options = {}) {
  if (!settings().musicOn) {
    return null;
  }
  const fade = options.fade ?? constant("musicFadeTimeBase");
  const volume = options.volume ?? constant("musicVolumeBase");
  const repeats = options.loops ?? FOREVER;
  const old = current;
  const voice = new Voice(name, "music", repeats, 0);
  current = voice;
  voice.fadeTo(volume, fade);
  record({ kind: "music", name, volume, pan: 0, fade });
  if (old) {
    record({ kind: "musicOut", name: old.name, volume: 0, pan: 0, fade });
    old.fadeTo(0, fade, () => old.stop());
  }
  return startVoice(voice);
}

// stopAllMusic: every piece of music fades out over some seconds and stops. With 0 they stop at once
function stopMusic(fade = STOP_FADE) {
  for (const voice of [...voices]) {
    if (voice.kind !== "music") {
      continue;
    }
    record({ kind: "musicOut", name: voice.name, volume: 0, pan: 0, fade });
    if (fade > 0) {
      voice.fadeTo(0, fade, () => voice.stop());
    } else {
      voice.stop();
    }
  }
}

// ---------- Settings and holds ----------

function setEffects(on) {
  story.settings ??= menuSettings;
  story.settings.soundOn = on;
}

// Turning music off stops what plays. Turning it on starts nothing: the music director picks the next piece
function setMusic(on) {
  story.settings ??= menuSettings;
  story.settings.musicOn = on;
  if (!on) {
    stopMusic(0);
  }
}

// Holds every sound where it is, or lets them go on
function pauseAll(on) {
  held = on;
  syncContext();
}

// Every sound and piece of music stops
function stopAll() {
  for (const voice of [...voices]) {
    voice.stop();
  }
  for (const channel of channels) {
    channel?.cancel();
  }
  channels.fill(null);
  for (const source of [...timeline]) {
    source.onended = null;
    source.stop();
    source.disconnect();
  }
  timeline.clear();
}

// The name of the piece of music that plays now, or null
function currentMusic() {
  return current ? current.name : null;
}

// What is playing now, for checks
function state() {
  return {
    context: ctx ? ctx.state : null,
    music: [...voices]
      .filter((voice) => voice.kind === "music")
      .map((voice) => ({
        name: voice.name,
        level: Math.round(voice.level * 100) / 100,
        started: Boolean(voice.source),
      })),
    loops: [...loops.keys()],
    channels: channels.filter(Boolean).length,
  };
}

export const sound = {
  play,
  music,
  current: currentMusic,
  stopMusic,
  loop,
  stopLoop,
  setEffects,
  setMusic,
  pauseAll,
  stopAll,
  preload,
  setSounds,
  startTimeline,
  state,
  // Where the listener stands, in the world's x: the player, as the original measures from
  listener: () => world.player?.x ?? 0,
  log: calls,
};
