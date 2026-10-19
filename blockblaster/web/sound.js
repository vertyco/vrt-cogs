// Block Blaster's sound effects: recorded files from the original, played through Web Audio. Other modules call
// play(name) with a short name from SOUNDS below. The effects switch (setEffects) silences them at once. Music is a
// separate switch whose songs come later (setMusic only remembers the choice until then).
// Every call that gets past the rate limits is written to `played` as [name, ms, muted], even with the sound off, so a
// check can read what the page tried to play without listening.
// Each entry: `files` (one is picked each time, never the one before), `together` (play every file at once), `big`
// (files for play(name, {big: true}), e.g. a larger cube), `volume`, `gap` (shortest wait in ms between two plays of
// the name) and `voices` (most copies of the name sounding at once).
const SOUNDS = {
  tap: { files: ["pig2_trimmed"], volume: 0.8, gap: 40, voices: 3 },
  hop: { files: ["pig3_trimmed"], volume: 0.6, gap: 40, voices: 3 },
  slot: { files: ["first_settle2_trimmed"], volume: 0.7, gap: 60, voices: 3 },
  pop: { files: ["pop2"], volume: 0.7, gap: 60, voices: 2 },
  vanish: { files: ["disapper_trimmed"], volume: 0.7, gap: 80, voices: 3 },
  // 46 shots a second would pile up, so these are thinned to a patter
  shot: { files: ["shoot_whoosh_04_trimmed"], volume: 0.3, gap: 90, voices: 3 },
  hit: { files: ["shoot_hit", "hit_05"], volume: 0.35, gap: 70, voices: 3 },
  metal: { files: ["metal_hit"], volume: 0.5, gap: 70, voices: 3 },
  break: {
    files: ["grid_breaking_1", "grid_breaking_2"],
    big: ["grid_breaking_6", "grid_breaking_7"],
    volume: 0.5,
    gap: 60,
    voices: 4,
  },
  clear: { files: ["final_break02", "stagebreak3"], together: true, volume: 0.8, gap: 500, voices: 1 },
  win: { files: ["game_success", "endgame_win"], together: true, volume: 0.6, gap: 1000, voices: 1 },
  fail: { files: ["game_over"], volume: 0.7, gap: 1000, voices: 1 },
  retry: { files: ["try_again"], volume: 0.7, gap: 500, voices: 1 },
  click: { files: ["click"], volume: 0.5, gap: 80, voices: 2 },
  button: { files: ["button_tap_pop", "tap_cartoon_pop_mouth_002"], volume: 0.8, gap: 60, voices: 2 },
  count: { files: ["coin_counting"], volume: 0.5, gap: 70, voices: 3 },
  coins: { files: ["coins_collect_several_at_once_001"], volume: 0.7, gap: 500, voices: 1 },
  appear: { files: ["booster_appear"], volume: 0.7, gap: 500, voices: 1 },
  unlock: { files: ["unlock"], volume: 0.8, gap: 500, voices: 1 },
  purchase: { files: ["purchase"], volume: 0.8, gap: 500, voices: 1 },
  tray: { files: ["raise_03_trimmed"], volume: 0.8, gap: 200, voices: 1 },
  revive: { files: ["sparkle1"], volume: 0.7, gap: 500, voices: 1 },
  reveal: { files: ["pop_sparkle"], volume: 0.6, gap: 100, voices: 2 },
  shuffle: { files: ["whoosh2_gem"], volume: 0.7, gap: 300, voices: 1 },
  bomb: { files: ["bomb"], volume: 0.9, gap: 300, voices: 1 },
  volley: { files: ["booster_shooting"], volume: 0.8, gap: 500, voices: 1 },
  select: { files: ["selection"], volume: 0.7, gap: 100, voices: 1 },
  pick: { files: ["pop_sparkle"], volume: 0.7, gap: 100, voices: 1 },
  lock_open: { files: ["opening_metal_slide2"], volume: 0.8, gap: 120, voices: 2 },
  gate_pull: { files: ["pull_01", "pull_02"], volume: 0.35, gap: 90, voices: 2 },
  gate_open: { files: ["pulley_01_trimmed"], volume: 0.7, gap: 200, voices: 2 },
  snake_pull: { files: ["ivy_whoosh_close"], volume: 0.35, gap: 120, voices: 2 },
  snake_gone: { files: ["ivy_whoosh_open"], volume: 0.6, gap: 200, voices: 2 },
  egg_change: { files: ["egg_break_change_trimmed"], volume: 0.55, gap: 70, voices: 3 },
  egg_break: { files: ["egg_full_break_trimmed"], volume: 0.7, gap: 60, voices: 3 },
  pipe_out: { files: ["tap_cartoon_pop_mouth_009_trimmed"], volume: 0.7, gap: 70, voices: 3 },
  ice_hit: { files: ["ice_break_14765_trimmed", "ice_break_14765_trimmed_trimmed"], volume: 0.35, gap: 120, voices: 2 },
  ice_shatter: { files: ["ice_shatter_trimmed", "ice_shatter_3"], volume: 0.8, gap: 150, voices: 2 },
  hammer_swing: { files: ["sport_baseball_bat_foam_swipe_001"], volume: 0.6, gap: 80, voices: 3 },
  hammer_hit: { files: ["industrial_impacts_hammer_wood_fixed_beam_002_trimmed_trimmed"], volume: 0.7, gap: 80, voices: 3 },
  wood_hit: { files: ["wood_stage1"], volume: 0.6, gap: 80, voices: 2 },
  wood_break: { files: ["wood_stage2"], volume: 0.8, gap: 150, voices: 2 },
  door_hit: { files: ["pm_fssf_door_mid_3", "pm_fssf_door_mid_7"], volume: 0.35, gap: 90, voices: 3 },
  door_open: { files: ["opening_metal_slide2", "door_close"], volume: 0.8, gap: 200, voices: 2 },
  biscuit_hit: { files: ["biscuit_hit_no_click"], volume: 0.45, gap: 70, voices: 3 },
  biscuit_break: { files: ["berry_explode_2"], volume: 0.7, gap: 120, voices: 2 },
  // The rocket's sounds as its prefab pairs them: the rear (start) part's hit, the front (end) part's hit, the merge,
  // the lift-off and the boost (Split Object Feature's AudioFx lists; hits at most once every 0.04 s)
  rocket_rear_hit: { files: ["rocket_hit_fire"], volume: 0.4, gap: 40, voices: 3 },
  rocket_front_hit: { files: ["rocket_hit"], volume: 0.4, gap: 40, voices: 3 },
  rocket_merge: { files: ["rocket_merge"], volume: 0.8, gap: 200, voices: 2 },
  rocket_lift_off: { files: ["rocket_lift_off_trimmed"], volume: 0.9, gap: 200, voices: 2 },
  rocket_boost: { files: ["rocket_boost"], volume: 0.5, gap: 200, voices: 2 },
  unicorn_ready: { files: ["unicorn_button_ready"], volume: 0.8, gap: 500, voices: 1 },
  unicorn_exit: { files: ["unicorn_exit_trimmed"], volume: 0.8, gap: 500, voices: 1 },
};
const EFFECTS_VOLUME = 0.8;
// The record keeps this many of the latest entries
const PLAYED_LIMIT = 400;

// [name, ms since the page opened, muted]
export const played = [];

const audio = {
  ctx: null,
  out: null,
  effects: true,
  music: true,
  buffers: new Map(),
  last: new Map(),
  lastFile: new Map(),
  voices: new Map(),
};

function filesOf(entry) {
  return [...entry.files, ...(entry.big || [])];
}

async function loadFile(file) {
  try {
    const response = await fetch(`sounds/${file}.ogg`);
    if (!response.ok) {
      throw new Error(`The sound file answered ${response.status}`);
    }
    audio.buffers.set(file, await audio.ctx.decodeAudioData(await response.arrayBuffer()));
  } catch (e) {
    console.warn(`Block Blaster: couldn't load the ${file} sound`, e);
  }
}

// Browsers only allow sound after the player touches the page, so the sound starts then
function unlock() {
  if (!audio.ctx) {
    try {
      audio.ctx = new AudioContext();
    } catch (e) {
      console.warn("Block Blaster: couldn't start the sound", e);
      return;
    }
    audio.out = audio.ctx.createGain();
    audio.out.gain.value = audio.effects ? EFFECTS_VOLUME : 0;
    audio.out.connect(audio.ctx.destination);
    const files = new Set(Object.values(SOUNDS).flatMap(filesOf));
    files.forEach(loadFile);
  }
  update();
}

// The sound pauses while the page is hidden
async function update() {
  const { ctx } = audio;
  if (!ctx || ctx.state === "closed") {
    return;
  }
  try {
    await (document.hidden ? ctx.suspend() : ctx.resume());
  } catch (e) {
    console.warn("Block Blaster: couldn't start or pause the sound", e);
  }
}

export function initSound() {
  window.addEventListener("pointerdown", unlock);
  window.addEventListener("keydown", unlock);
  document.addEventListener("visibilitychange", update);
}

export function setEffects(on) {
  audio.effects = on;
  if (audio.out) {
    const now = audio.ctx.currentTime;
    audio.out.gain.cancelScheduledValues(now);
    audio.out.gain.setValueAtTime(on ? EFFECTS_VOLUME : 0, now);
  }
}

// The songs come later; the switch is kept so they can follow it
export function setMusic(on) {
  audio.music = on;
}

export function effectsOn() {
  return audio.effects;
}

export function musicOn() {
  return audio.music;
}

function pick(files, name) {
  if (files.length === 1) {
    return files[0];
  }
  const before = audio.lastFile.get(name);
  const others = files.filter((file) => file !== before);
  const file = others[Math.floor(Math.random() * others.length)];
  audio.lastFile.set(name, file);
  return file;
}

function start(file, name, volume) {
  const buffer = audio.buffers.get(file);
  if (!buffer || !audio.ctx || audio.ctx.state !== "running") {
    return;
  }
  const source = audio.ctx.createBufferSource();
  source.buffer = buffer;
  const gain = audio.ctx.createGain();
  gain.gain.value = volume;
  source.connect(gain).connect(audio.out);
  audio.voices.set(name, (audio.voices.get(name) || 0) + 1);
  source.addEventListener("ended", () => audio.voices.set(name, audio.voices.get(name) - 1));
  source.start();
}

// Play a sound by its short name. `options.big` picks the larger variant where the sound has one; `options.volume`
// scales it. Plays closer together than the sound's gap, or past its voice limit, are dropped and never recorded
export function play(name, options = {}) {
  const entry = SOUNDS[name];
  if (!entry) {
    throw new Error(`Block Blaster has no sound called ${name}`);
  }
  const now = performance.now();
  if (now - (audio.last.get(name) ?? -Infinity) < entry.gap || (audio.voices.get(name) || 0) >= entry.voices) {
    return;
  }
  audio.last.set(name, now);
  played.push([name, Math.round(now), !audio.effects]);
  if (played.length > PLAYED_LIMIT) {
    played.shift();
  }
  if (!audio.effects) {
    return;
  }
  const volume = entry.volume * (options.volume ?? 1);
  const files = options.big && entry.big ? entry.big : entry.files;
  if (entry.together) {
    files.forEach((file) => start(file, name, volume));
  } else {
    start(pick(files, name), name, volume);
  }
}
