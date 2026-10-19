// The director: how many zombies a room may hold and when more come (F4:1454-1964). Once a second it works out the
// threat budget and the zombie limit for the room being played (setMaxThreat F4:1559), and then runs its loop
// (directorLoop F4:1477): a break from spawning after enough zombies, a rush when the time since the last one has run
// out, and outdoors a zombie now and then just off the camera. Entering a room may fill it (directorAddZombiesRoom
// F4:1663) when nobody is there and it was cleared long enough ago.
//
// During a rush, indoors, zombies drop one by one through a hole torn in the roof (directorSpawnRoofZombies F4:1798,
// showRoofHoleEffect F4:10496); outdoors they run in from just off the camera. Every spawn waits on the game clock and
// is dropped when the player changes rooms. On Union Island the ending rush sends sprinters from behind the player
// without end, and zombies ignore companions while it lasts.
//
// The music director rides on the same loop (musicDirectorLoop F4:1896): a new track every 60 game minutes, rush music
// that follows how bad the rush is, and the normal tracks back after it.
import { Rectangle, Sprite } from "./vendor/pixi.min.mjs";
import { data } from "./data.js";
import { effects } from "./effects.js";
import { player } from "./player.js";
import { rng } from "./rng.js";
import { layers, onRoom, room, toWorld } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { START_TIME, world } from "./world.js";
import { roomDanger, spawnPlace, spawnZombie, zombieType } from "./zombies.js";

// Used until the converted constants load (F4:26107-26160, 26674-26710)
const DEFAULTS = {
  absMaxZombies: 5,
  repopTime: 90,
  smallRoomWidth: 600,
  spawnRoofZomDelay: 600,
  randZomTrigger: 3,
  breakLengthBase: 0.75,
  breakThreshold: 3,
  baseRushTime: 3,
  rushLengthBase: 2,
  rushLengthMax: 15,
  threatMultiplier: 25,
  threatAddition: 30,
  maxZombieAdd: 1,
  maxZombieDiv: 2,
  levelCap: 30,
  musicVolumeBase: 8,
  musicFadeTimeBase: 10,
  musicChangeTime: 60,
  rushMusicVolume: 22,
  rushMusicChangeTime: 4,
  rushLevel2: 20,
  rushLevel3: 50,
  rushLevel4: 90,
  rushLevel5: 98,
  moveEdgeBuffer: 50,
  depth_world_holeTop: 95500,
  depth_world_player: 115000,
};
// The stage the camera shows (Stage.width, Stage.height)
const STAGE_W = 760;
const STAGE_H = 400;
// Union Island: no room fills, no trickle, and the ending rush (locationNumber 7)
const UNION_ISLAND = "l7";
// The threat budget drops 5 for each of these health percents the player is under, and 2 for each medical item
const HEALTH_STEPS = [90, 70, 50, 30, 10];
const HEALTH_STEP_COST = 5;
const MEDS_COST = 2;
// Outdoors a room refills after half the wait
const OUTSIDE_REPOP = 0.5;
// A room fill's count: random(round(threatMax / 10)) indoors, random(round(threatMax / 3)) outdoors
const INSIDE_FILL_DIV = 10;
const OUTSIDE_FILL_DIV = 3;
// How many types a room fill or a place on the floor gets to fit before it gives up
const FIT_TRIES = 10;
// A rush waits 10 more minutes for each of these that holds
const RUSH_DELAY = 10;
const RECENT_RUSH = 30;
const LOW_HEALTH = 50;
// Just off the camera: past the screen's edge by 50 to 149 px, with 200 px of street beyond the screen on that side
const OFF_CAMERA_MIN = 50;
const OFF_CAMERA_SPREAD = 100;
const OFF_CAMERA_ROOM = 200;
// A roof hole is torn at least 180 px from the player and 150 px inside the room's ends, in at most 200 tries
const HOLE_PLAYER_GAP = 180;
const HOLE_EDGE = 150;
const HOLE_TRIES = 200;
// The hole's art sits at this y; the copy of the ceiling torn out is 300 x 120, from 60 px above the room's top
const HOLE_Y = 33;
const SLAB_W = 300;
const SLAB_H = 120;
const SLAB_TOP = 60;
const ROOF_PIECES = 8;
const ROOF_PIECE_MS = 200;
const ROOF_PIECE_FIRST = 50;
// Rush zombies land up to 50 px either side of the hole or the run-in place
const RUSH_SPREAD = 100;
// The roof's art starts loading with the director
const HOLE_ART = ["roofHole", "roofHoleTop", "roofHoleMask", "particle_roof"];
// Types that can't drop through a roof
const NO_ROOF = new Set(["zombieCrawl", "zombieDog", "zombieRiser"]);
// The ending rush's types and where they come from: 760 px behind the player, no nearer the street's start than 50
const ENDING_POOL = [
  "zombieDog",
  "zombieHammerSprint",
  "zombieCleaverSprint",
  "zombieHatchetSprint",
  "zombieArmySprint",
  "zombieFatSprint",
  "zombieSprint",
];
const ENDING_BEHIND = 760;
const ENDING_MIN_X = 50;
const ENDING_LENGTH = 999999;
const RUSH_START_VOLUME = 30;
// The tracks a rush picks from, weakest first, and the rush strength (constants rushLevel2 to rushLevel5) each starts at
const RUSH_TRACKS = ["music_rush1", "music_rush2", "music_rush3", "music_rush4", "music_rush5"];
const MENU_TRACK = "music_menu";
const MENU_LOOPS = 5;
// The same track is never picked again within this many tries (the original gives up after 10)
const TRACK_TRIES = 10;
// Rush strength is worked out at once when a rush starts
const RUSH_MUSIC_NOW = Infinity;

let page = null;
let holeArt = false;
// Pending rush spawns: world timers that the room change cancels
let pending = [];
// The roof hole torn in this room: its x and the copies of the ceiling it made
let hole = null;
const listeners = { rushStart: [], rushEnd: [] };
// The music director's memory: when it last changed track (game minutes), the last two normal tracks, the rush track
// playing, the rush strength it was picked for and how many loops ago that was worked out
const music = { lastChange: 0, current: null, secondLast: null, rushTrack: null, rushLevel: 0, rushChange: 0 };

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function frames(ms) {
  return Math.round((ms / 1000) * (page?.lib?.fps ?? 30));
}

function notify(event) {
  for (const fn of listeners[event]) {
    try {
      fn();
    } catch (e) {
      console.warn(`Union City: a director ${event} listener failed`, e);
    }
  }
}

// ---------- The room ----------

function safeHouse() {
  return room.def?.safeHouse === true;
}

function outside() {
  return room.def?.outside === true;
}

function onUnionIsland() {
  return room.def?.loc === UNION_ISLAND;
}

// Enemies on screen: the zombies and the hostile people
function enemies() {
  return world.zombies.length + world.humans.filter((each) => each.side === "enemy" && each.alive === true).length;
}

// The threat the zombies in the room use up, each its type's
function threatHere() {
  return world.zombies.reduce((sum, each) => sum + (each.threat ?? 0), 0);
}

function inNoSpawn(x) {
  const zone = room.markers.noSpawn;
  return Boolean(zone) && x > zone.left && x < zone.left + zone.w;
}

// The zombie types a room of that danger picks from (zLevel F4:9539)
function typesFor(danger) {
  const levels = data.actors?.zombieLevels ?? {};
  const top = Math.max(0, ...Object.keys(levels).map(Number));
  return levels[Math.min(danger, top)] ?? [];
}

function randomType(danger = roomDanger()) {
  return rng.pick(typesFor(danger));
}

function fits(type) {
  return (zombieType(type)?.threat ?? 0) + threatHere() <= director.threatMax;
}

// ---------- The budget ----------

function healthCost() {
  const percent = Math.round((player.health / player.healthMax) * 100);
  return HEALTH_STEPS.filter((step) => percent < step).length * HEALTH_STEP_COST;
}

function medsCost() {
  return (story.inventory ?? []).filter((row) => row.type === "meds").length * MEDS_COST;
}

// The threat budget, the zombie limit and the rush's length for the room being played (setMaxThreat F4:1559)
function setMaxThreat() {
  const danger = roomDanger();
  const wanted = Math.round(danger / constant("maxZombieDiv") + constant("maxZombieAdd"));
  let limit = Math.min(constant("absMaxZombies"), wanted);
  if (director.onBreak) {
    limit = 0;
  }
  if (room.width <= constant("smallRoomWidth")) {
    limit = Math.ceil(limit / 3);
  }
  director.rushLength = Math.min(constant("rushLengthMax"), constant("rushLengthBase") * danger);
  if (director.endingRushOn) {
    director.rushLength = ENDING_LENGTH;
  }
  let threat = Math.round(constant("threatMultiplier") * danger + constant("threatAddition"));
  if (danger === 0) {
    threat = 0;
    limit = 0;
  }
  if (story.player) {
    threat -= healthCost() + medsCost();
  }
  director.threatMax = Math.max(0, threat);
  director.zombieLimit = limit;
}

// ---------- Spawning ----------

// One zombie through the director: none while on a break or with the room at its limit (setupZombie F4:8599-8607).
// Every zombie made counts toward the next break
function spawn(type, x, options) {
  if (director.onBreak || world.zombies.length >= director.zombieLimit || !type) {
    return null;
  }
  const zombie = spawnZombie(type, x, options);
  if (zombie) {
    director.sinceBreak += 1;
  }
  return zombie;
}

// A place on the floor off to one side of where the player came in, outside the room's no-spawn stretch
function floorPlace() {
  let x = spawnPlace();
  for (let i = 1; i < FIT_TRIES && inNoSpawn(x); i += 1) {
    x = spawnPlace();
  }
  return inNoSpawn(x) ? null : x;
}

// Just off the camera's left or right, with room in the street beyond the screen: a side picked at random when both
// have room, none when neither does (directorAddRandomZombies F4:1730-1774)
function offCamera() {
  const centre = toWorld(STAGE_W / 2, STAGE_H / 2).x;
  const away = rng.random(OFF_CAMERA_SPREAD) + OFF_CAMERA_MIN;
  const right = centre + STAGE_W / 2 + OFF_CAMERA_ROOM < room.width;
  const left = centre - STAGE_W / 2 - OFF_CAMERA_ROOM > 0;
  let side = right ? 1 : 0;
  if (left) {
    side = right && rng.random(2) === 0 ? 1 : -1;
  }
  if (!side) {
    return null;
  }
  const x = centre + side * (STAGE_W / 2 + away);
  return inNoSpawn(x) ? null : x;
}

// A rush's run-in place outdoors: just off the camera, or, in a street too short for that, the end further from the
// player
function runInPlace() {
  const x = offCamera();
  if (x !== null) {
    return x;
  }
  const edge = constant("moveEdgeBuffer");
  return player.x > room.width / 2 ? edge : room.width - edge;
}

// Entering a room fills it when nobody is there, it is no safe house, nobody lives there, it is not on Union Island
// and it was last cleared long enough ago: a random count up to the limit, each a type that fits the threat budget
// (directorAddZombiesRoom F4:1663). Returns the zombies made
function onRoomEnter() {
  if (enemies() > 0 || safeHouse() || onUnionIsland() || (room.def?.npcs?.length ?? 0) > 0) {
    return [];
  }
  const saved = story.rooms?.[room.id]?.lastTime;
  const wait = constant("repopTime") * (outside() ? OUTSIDE_REPOP : 1);
  if (saved !== undefined && world.time - saved <= wait) {
    return [];
  }
  markCleared();
  const div = outside() ? OUTSIDE_FILL_DIV : INSIDE_FILL_DIV;
  const count = Math.min(rng.random(Math.round(director.threatMax / div)), director.zombieLimit);
  const made = [];
  for (let i = 0; i < count; i += 1) {
    const zombie = fillOne();
    if (zombie) {
      made.push(zombie);
    }
  }
  return made;
}

// One zombie of a room fill: a fresh type is rolled until one fits the budget
function fillOne() {
  for (let i = 0; i < FIT_TRIES; i += 1) {
    const type = randomType();
    if (type && fits(type)) {
      const x = floorPlace();
      return x === null ? null : spawn(type, x);
    }
  }
  return null;
}

// The room's cleared-at time: kept by room, so each street of a location has its own (F4:14487)
function markCleared() {
  story.rooms ??= {};
  story.rooms[room.id] = { ...story.rooms[room.id], lastTime: world.time };
}

// Every few seconds outdoors one zombie of a fitting type appears just off the camera (directorAddRandomZombies
// F4:1715)
function trickle() {
  if (world.zombies.length >= director.zombieLimit || !outside()) {
    return null;
  }
  const type = randomType();
  const x = offCamera();
  if (!type || x === null || !fits(type)) {
    return null;
  }
  return spawn(type, x);
}

// ---------- Breaks ----------

function level() {
  return story.player?.level ?? 1;
}

// After enough zombies the director rests for a few game minutes, never in a rush or a kill quest (F4:1479-1489)
function checkBreak() {
  const threshold = Math.round(level() * constant("breakThreshold") + rng.random(level()));
  if (!director.rushActive && !director.onBreak && !director.killQuestActive && director.sinceBreak > threshold) {
    const base = constant("breakLengthBase");
    director.sinceBreak = 0;
    director.onBreak = true;
    director.breakLength = Math.round(rng.random((constant("levelCap") - level()) * base) + base);
    director.breakStart = world.time;
  }
  if (director.onBreak && world.time - director.breakStart > director.breakLength) {
    director.onBreak = false;
  }
}

// ---------- Rushes ----------

// Low on ammo: the gun in the hands has no more rounds of its kind left than an average magazine
function lowOnAmmo() {
  const type = player.weapon && data.items?.weapons?.[player.weapon]?.ammoType;
  const ammo = type && data.items?.ammo?.[type];
  return Boolean(ammo) && (story.ammo?.[type] ?? 0) <= ammo.avgMag;
}

function permPercent() {
  return story.player ? (story.player.permHealth / story.player.healthMax) * 100 : 100;
}

// How many game minutes must pass between rushes (F4:1490-1516)
function rushTimeRange() {
  let range = Math.round(constant("baseRushTime") * (constant("levelCap") - level()));
  if (world.time - director.lastRushTime < RECENT_RUSH) {
    range += RUSH_DELAY;
  }
  if (permPercent() < LOW_HEALTH) {
    range += RUSH_DELAY;
  }
  if (lowOnAmmo()) {
    range += RUSH_DELAY;
  }
  return range + enemies();
}

function beginRush() {
  director.lastRushTime = world.time;
  director.rushStart = world.time;
  director.rushActive = true;
  sound.play("sound_rushStart", { volume: RUSH_START_VOLUME });
  music.rushTrack = null;
  music.rushChange = RUSH_MUSIC_NOW;
  musicDirector.loop(true);
  notify("rushStart");
}

function finishRush() {
  director.lastRushTime = world.time;
  director.rushActive = false;
  music.rushTrack = null;
  musicDirector.loop(true);
  notify("rushEnd");
}

// A rush starts when its wait has run out and the room has space, sends zombies while it lasts, and ends when its
// length has passed. None of it runs in a safe house (F4:1515-1547)
function runRush() {
  if (safeHouse()) {
    return;
  }
  const range = rushTimeRange();
  director.rushTimeRange = range;
  const free = world.zombies.length < director.zombieLimit;
  if (Math.abs(director.lastRushTime - world.time) > range && free && !director.rushActive && !director.onBreak) {
    beginRush();
  }
  if (director.rushActive && world.time < director.rushStart + director.rushLength) {
    sendRush();
  }
  if (director.rushActive && world.time > director.rushStart + director.rushLength) {
    finishRush();
  }
}

function spawnsPending() {
  pending = pending.filter((timer) => !timer.dead);
  return pending.length > 0;
}

// Zombies for the rush, one every 600 ms of game time, as many as the room has space for. A new batch waits until the
// last has come
function sendRush() {
  if (spawnsPending()) {
    return;
  }
  if (outside()) {
    runInZombies();
  } else {
    roofZombies();
  }
}

function later(index, fn) {
  pending.push(world.later(index * frames(constant("spawnRoofZomDelay")), fn, { room: true }));
}

// Indoors they drop through the room's roof hole, torn the first time (F4:1805-1856). Types that can't drop are
// skipped
function roofZombies() {
  const x = hole?.x ?? tearRoof();
  const limit = director.zombieLimit;
  for (let i = 0; i <= limit; i += 1) {
    if (i + world.zombies.length < limit) {
      const type = randomType();
      if (type && !NO_ROOF.has(type)) {
        later(i, () => spawn(type, x + (rng.random(RUSH_SPREAD) - RUSH_SPREAD / 2), { fromRoof: true }));
      }
    }
  }
}

// Outdoors they run in from just off the camera, awake; in the ending rush, sprinters from behind the player
// (F4:1858-1880)
function runInZombies() {
  const limit = director.zombieLimit;
  for (let i = 0; i < limit; i += 1) {
    if (i + world.zombies.length < limit) {
      later(i, director.endingRushOn ? endingZombie : runInZombie);
    }
  }
}

function runInZombie() {
  spawn(randomType(), runInPlace() + (rng.random(RUSH_SPREAD) - RUSH_SPREAD / 2), { alerted: true });
}

function endingZombie() {
  spawn(rng.pick(ENDING_POOL), Math.max(ENDING_MIN_X, player.x - ENDING_BEHIND), { alerted: true });
}

// ---------- The roof hole ----------

// A place for the hole: away from the player, inside the room's ends (F4:1814-1838)
function holePlace() {
  let x = 0;
  for (let tries = 0; tries < HOLE_TRIES; tries += 1) {
    x = rng.random(room.width);
    if (Math.abs(x - player.x) > HOLE_PLAYER_GAP && !inNoSpawn(x)) {
      break;
    }
  }
  return Math.min(room.width - HOLE_EDGE, Math.max(HOLE_EDGE, x));
}

// A copy of the ceiling around x, drawn over the zombies and cut to the hole's mask, so a zombie comes out of the
// opening and not through the ceiling (showRoofHoleEffect F4:10496-10538)
function ceilingSlab(source, x, z) {
  if (!source || !page.app) {
    return null;
  }
  // The copy is taken from the same room pixels it covers, so it lines up with the ceiling under it
  const left = x - SLAB_W / 2;
  const top = SLAB_TOP - SLAB_H;
  const frame = new Rectangle(left - source.x, top - source.y, SLAB_W, SLAB_H);
  const texture = page.app.renderer.generateTexture({ target: source, frame });
  const slab = new Sprite(texture);
  slab.x = left;
  slab.y = top;
  slab.zIndex = z;
  slab.eventMode = "none";
  const mask = page.lib.makeExported("roofHoleMask");
  mask.x = x;
  mask.y = HOLE_Y;
  layers.actors.addChild(mask, slab);
  slab.mask = mask;
  return slab;
}

// The hole's pictures: the dark opening behind everything that moves, the ceiling copies and the broken rim over
// them, then pieces of roof falling and the crash
function drawHole(x) {
  const base = constant("depth_world_holeTop") - constant("depth_world_player");
  const opening = page.lib.makeExported("roofHole");
  opening.x = x;
  opening.y = HOLE_Y;
  layers.back.addChildAt(opening, 0);
  const named = room.clip?.named ?? {};
  hole.slabs = [ceilingSlab(named.bgBrick, x, base + 100), ceilingSlab(named.bg, x, base + 170)].filter(Boolean);
  const rim = page.lib.makeExported("roofHoleTop");
  rim.x = x;
  rim.y = HOLE_Y;
  rim.zIndex = base + 111;
  layers.actors.addChild(rim);
}

// Tears the room's roof open at a place away from the player. Returns the hole's x
function tearRoof() {
  const x = holePlace();
  hole = { x, slabs: [] };
  if (holeArt) {
    try {
      drawHole(x);
    } catch (e) {
      console.warn("Union City: couldn't draw the roof hole", e);
    }
  }
  const owner = { x, y: HOLE_Y, facing: 1, name: "roofHole" };
  for (let i = 0; i < ROOF_PIECES; i += 1) {
    world.later(frames(i * rng.random(ROOF_PIECE_MS) + ROOF_PIECE_FIRST), () => effects.bounce("roof", owner), {
      room: true,
    });
  }
  sound.play("sound_roofBreak");
  return x;
}

// ---------- Music ----------

// A random normal track that is neither of the last two, at the normal volume, fading over the old one
function playNormalTrack() {
  music.lastChange = world.time;
  const tracks = data.actors?.lists?.allMusic ?? [];
  if (tracks.length === 0) {
    return;
  }
  let name = rng.pick(tracks);
  for (let tries = 1; tries < TRACK_TRIES && (name === music.current || name === music.secondLast); tries += 1) {
    name = rng.pick(tracks);
  }
  music.secondLast = music.current;
  music.current = name;
  sound.music(name, { volume: constant("musicVolumeBase"), fade: constant("musicFadeTimeBase") });
}

// How hard the rush hits the player decides its track: the less health and the more zombies, the harder the track
function rushTrackFor(level) {
  const starts = [constant("rushLevel2"), constant("rushLevel3"), constant("rushLevel4"), constant("rushLevel5")];
  return RUSH_TRACKS[starts.filter((start) => level >= start).length];
}

// The strength is worked out again every few loops; a track that is not already playing takes over at once at the rush
// volume (S14, Z15: the original only picked once, at the rush's start)
function playRushTrack() {
  music.rushChange += 1;
  if (music.rushChange >= constant("rushMusicChangeTime")) {
    music.rushLevel = Math.round(100 - permPercent() + 1 + world.zombies.length * 4);
    music.rushChange = 0;
  }
  const name = rushTrackFor(music.rushLevel);
  if (name !== music.rushTrack) {
    music.rushChange = 0;
    music.rushTrack = name;
    sound.music(name, { volume: constant("rushMusicVolume"), fade: 0 });
  }
}

// ---------- The loop ----------

// Once a second: the budget, a break, a rush, and outdoors every fourth second a zombie off the camera
function tick() {
  if (!story.player || !room.id) {
    return;
  }
  setMaxThreat();
  checkBreak();
  runRush();
  if (!director.rushActive && !onUnionIsland()) {
    director.trickleCount += 1;
    if (director.trickleCount > constant("randZomTrigger")) {
      director.trickleCount = 0;
      trickle();
    }
  }
  musicDirector.loop();
}

// Leaving a room with no enemies left marks it cleared (F4:14485-14489), and its roof hole's copies go
function leave() {
  if (room.id && story.player && enemies() === 0) {
    markCleared();
  }
  for (const slab of hole?.slabs ?? []) {
    slab.texture.destroy(true);
  }
  hole = null;
  pending = [];
}

// A new room: the ending rush stops (newRoomReset F4:1138), zombies brought back from the room's memory count toward a
// break, and the budget is worked out for this room before it fills
function build() {
  if (director.endingRushOn) {
    director.endingRush(false);
  }
  director.sinceBreak += world.zombies.length;
  if (!story.player) {
    return;
  }
  setMaxThreat();
  onRoomEnter();
}

function reset() {
  Object.assign(director, {
    rushActive: false,
    rushStart: 0,
    onBreak: false,
    breakStart: 0,
    breakLength: 0,
    sinceBreak: 0,
    trickleCount: 0,
    killQuestActive: false,
  });
  Object.assign(music, { lastChange: 0, current: null, secondLast: null, rushTrack: null, rushLevel: 0, rushChange: 0 });
  director.endingRush(false);
  pending = [];
  hole = null;
}

export const director = {
  threatMax: 0,
  zombieLimit: 0,
  rushActive: false,
  rushStart: 0,
  rushLength: 0,
  rushTimeRange: 0,
  onBreak: false,
  breakStart: 0,
  breakLength: 0,
  sinceBreak: 0,
  trickleCount: 0,
  endingRushOn: false,
  // Set by the quests while a kill quest is the active one: no breaks then
  killQuestActive: false,

  // The game minute the last rush started or ended. It is part of the save, and a new story starts it with the clock
  get lastRushTime() {
    return story.lastRushTime ?? START_TIME;
  },

  set lastRushTime(value) {
    story.lastRushTime = value;
  },

  // A rush as soon as the room has space (startRush F4:1454): the break ends and the wait is zeroed
  startRush() {
    director.onBreak = false;
    director.rushActive = false;
    director.lastRushTime = 0;
  },

  endRush() {
    if (director.rushActive) {
      finishRush();
    }
    pending.forEach((timer) => timer.cancel());
    pending = [];
  },

  // Sleeping or waiting restarts the wait for the next rush (F4:22921)
  restartRushTimer() {
    director.lastRushTime = world.time;
  },

  // The ending rush on Union Island (startEndingRush F4:1460): endless sprinters, and zombies leave companions alone
  endingRush(on) {
    director.endingRushOn = Boolean(on);
    world.endingRush = director.endingRushOn;
    if (on) {
      director.startRush();
    } else {
      director.rushActive = false;
    }
  },

  onRoomEnter,
  setMaxThreat,
  spawn,
  tick,

  // fn() runs when a rush starts ("rushStart") or ends ("rushEnd")
  on(event, fn) {
    listeners[event].push(fn);
  },
};

// The music: loop() runs with the director's loop, and forced picks a track now (a rush starting or ending, a death);
// menu() starts the menu's music; stop() fades every track out
export const musicDirector = {
  loop(forced = false) {
    if (director.rushActive) {
      playRushTrack();
    } else if (forced || world.time - music.lastChange > constant("musicChangeTime")) {
      playNormalTrack();
    }
  },

  menu() {
    sound.stopMusic();
    music.current = null;
    music.secondLast = null;
    music.rushTrack = null;
    sound.music(MENU_TRACK, {
      volume: constant("musicVolumeBase"),
      fade: constant("musicFadeTimeBase"),
      loops: MENU_LOOPS,
    });
  },

  stop() {
    sound.stopMusic();
  },
};

export function initDirector(owner) {
  page = owner;
  onRoom("leave", leave);
  onRoom("build", build);
  world.onReset(reset);
  world.stage("slow", tick);
  page.lib
    .need(HOLE_ART.map((name) => page.lib.exported(name)).filter(Boolean))
    .then(() => {
      holeArt = true;
    })
    .catch((e) => console.warn("Union City: the roof hole's art couldn't load", e));
}

// Helpers for page.py checks
export const directorDebug = {
  // The director's numbers now
  directorState() {
    return {
      threatMax: director.threatMax,
      zombieLimit: director.zombieLimit,
      threat: threatHere(),
      zombies: world.zombies.length,
      rushActive: director.rushActive,
      rushStart: director.rushStart,
      rushLength: director.rushLength,
      rushTimeRange: director.rushTimeRange,
      lastRushTime: director.lastRushTime,
      onBreak: director.onBreak,
      breakLength: director.breakLength,
      sinceBreak: director.sinceBreak,
      pending: pending.filter((timer) => !timer.dead).length,
      hole: hole?.x ?? null,
      cleared: story.rooms?.[room.id]?.lastTime ?? null,
      endingRush: director.endingRushOn,
      music: { ...music, playing: sound.current() },
    };
  },

  // Works out the budget for the room being played and returns it
  threat() {
    setMaxThreat();
    return { threatMax: director.threatMax, zombieLimit: director.zombieLimit };
  },

  // Runs the director's once-a-second loop n times
  directorTick(n = 1) {
    for (let i = 0; i < n; i += 1) {
      tick();
    }
    return directorDebug.directorState();
  },

  // Starts a rush at once: the wait and the count toward a break are zeroed and the loop runs
  forceRush() {
    director.sinceBreak = 0;
    director.startRush();
    tick();
    return directorDebug.directorState();
  },
};
