// The people who stand in the rooms and talk (setupNPCs F4:23121, setupAnNPC F4:23134, the table F4:23276-24530) and
// the bubbles that say things over their heads (setupWorldSpeech F4:24531, displayWorldSpeech F4:24556).
//
// Each room lists its NPCs in world.json with an x, a pose and a facing. A room places them as it is built, half a
// second of game time apart, each dressed from its entry in story.json as a companion is, in the full-body animation
// holding the pose. A person whose story state is "off" is left out. Each NPC is an actor in world.npcs with
// a box the interaction system reads: [E] TALK TO <FIRST NAME> opens the dialog (npcs.hooks.dialog(key)).
//
// A person's story state is story.npcs[key].state (the table's number, or "off"); quests change it
// (quests.hooks.npcState) and triggers and cutscenes switch people on, off and away. story.npcs[key].place moves a
// person to another room.
//
// World speech: the lines of each person in their state (story.json "speech") join one queue as the room is built, in
// the order of the original (every person's first line, then every person's second ...). One bubble shows every six
// seconds of game time. The lines are keyed by the NPC, the queue starts empty in each room and each line comes up
// once. A bubble also shows on demand for a cutscene: say("player" | "partner" | "npc_<key>", text).
import { boxOf } from "./collide.js";
import { dressOf } from "./companions.js";
import { data } from "./data.js";
import { TextField } from "./flash.js";
import { tween } from "./hud.js";
import { addSource, register } from "./interact.js";
import { player } from "./player.js";
import { quests } from "./quests.js";
import { goto, gotoPlay, makeHuman } from "./rig.js";
import { layers, onRoom, room } from "./rooms.js";
import { fillText, story } from "./story.js";
import { world } from "./world.js";

const KIND = "talk";
const SPEECH_ART = "speechBubble";
// Used until the converted constants load (F4:36300-36302, 26111)
const DEFAULTS = { NPCsetupDelay: 500, depth_world_NPC: 115200, depth_world_player: 115000, edgeBuffer: 0 };
// A bubble comes up every six seconds (setInterval F4:36309)
const SPEECH_SECONDS = 6;
// The bubble fades in over 0.2 s, stays until 5 s have passed and fades out in 0.2 s (F4:24611-24618)
const FADE_SECONDS = 0.2;
const HOLD_SECONDS = 5;
// A bubble sits this far above the feet of a standing person and of a seated one (F4:24590-24594), and its text box is
// lifted by one and a half text heights
const ABOVE_STANDING = 135;
const ABOVE_SEATED = 70;
const TEXT_LIFT = 1.5;
// The backing is the text plus this much in width and height (F4:24572-24573)
const BACKING_MARGIN = { w: 20, h: 10 };
// The backing's size in the art, which a bubble stretches to its text
const BACKING_ART = { w: 115.5, h: 99.5 };
// A bubble near a room's edge slides its text and backing this far from the pointer (F4:24602-24609)
const EDGE_SHIFT = 50;
const EDGE_NEAR = 100;
// The arrow points at the head, 20 px to the left of it, for a person facing right (F4:24598)
const ARROW_BACK = 20;
// A text field tall enough for any line count the bubbles need
const FIELD_HEIGHT = 200;
// The NPC depths are counted to 20 and then start over (F4:23137-23140)
const MOST_NPCS = 20;
// A person seated in the "sit" pose is low (F4:23207)
const LOW_POSE = "sit";
// The box a person is talked to in: half its width and 0.6 of its head's height (F4:23216-23220)
const BOX_WIDTH_SHARE = 0.5;
const BOX_HEIGHT_SHARE = 0.6;
// The talk icon floats this much above the box (F4:15299)
const ICON_LIFT = 20;
const MOST_LOGGED = 100;

let page = null;
let numNPC = 0;
// Spawns still waiting on their delay in this room
let waiting = 0;
// The lines waiting for a bubble in this room: { key, line }
let queue = [];
// The bubble on the screen: { clip, target, follow }
let bubble = null;
// NPC key -> { room, entry } for the room that lists the person first, so a person moved to a room that does not list
// them still has a pose and a facing
const homes = new Map();
// What was placed, spoken and moved, newest last, for checks
const log = [];

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function note(kind, key, extra = {}) {
  log.push({ kind, key, frame: world.frame, ...extra });
  if (log.length > MOST_LOGGED) {
    log.shift();
  }
}

// ---------- Who is where ----------

function defOf(key) {
  return data.story?.npcs?.[key] ?? null;
}

// The person's state: what the story has recorded, or the table's start
export function stateOf(key) {
  return story.npcs?.[key]?.state ?? defOf(key)?.state;
}

function isOff(key) {
  return stateOf(key) === "off";
}

function moved(key) {
  return story.npcs?.[key]?.place ?? null;
}

function homeOf(key) {
  if (homes.size === 0) {
    for (const [id, def] of Object.entries(data.world.rooms)) {
      for (const entry of def.npcs ?? []) {
        if (!homes.has(entry.key)) {
          homes.set(entry.key, { room: id, entry });
        }
      }
    }
  }
  return homes.get(key)?.entry ?? null;
}

// The people in a room, each { key, x, pose, facing }: the ones its data lists that have not been moved elsewhere, the
// ones moved in, and none that are switched off
export function npcsForRoom(roomRef = room) {
  const id = typeof roomRef === "string" ? roomRef : roomRef.id;
  const here = [];
  for (const entry of data.world.rooms[id]?.npcs ?? []) {
    const place = moved(entry.key);
    if (!place) {
      here.push(entry);
    } else if (place.room === id) {
      here.push({ ...entry, ...place });
    }
  }
  for (const [key, each] of Object.entries(story.npcs ?? {})) {
    if (each.place?.room === id && !here.some((entry) => entry.key === key)) {
      here.push({ ...homeOf(key), key, ...each.place });
    }
  }
  return here.filter((entry) => !isOff(entry.key));
}

// The person with that key standing in the room now, or null
export function npc(key) {
  return world.npcs.find((each) => each.key === key && each.clip && !each.clip.destroyed) ?? null;
}

// ---------- Standing in the room ----------

function withinEdges(x) {
  const buffer = constant("edgeBuffer");
  return Math.min(room.edges.right - buffer, Math.max(room.edges.left + buffer, x));
}

// A name the dialog and the prompt use: the first word of the full name (F4:23163), the whole name when it is one word
function shortName(def) {
  const full = fillText(def.fullName).trim();
  const space = full.indexOf(" ");
  return space < 0 ? full : full.slice(0, space);
}

function bySex(value) {
  return value && typeof value === "object" ? value[story.player?.sex === "female" ? "f" : "m"] : value;
}

// A weapon the rig can show: "none" is bare hands
function shownRef(ref) {
  return ref && ref !== "none" && data.items?.weapons?.[ref] ? ref : "hands";
}

function toRight(facing) {
  return facing === "left" || facing === -1 ? -1 : 1;
}

// Dresses a person and puts them in the room (setupAnNPC F4:23134). Returns the actor, or null for a person who is
// switched off, already here or unknown
function placeNPC(entry) {
  const def = defOf(entry.key);
  if (!def || isOff(entry.key) || npc(entry.key)) {
    return null;
  }
  const dress = dressOf(entry.key);
  const made = makeHuman({
    sex: dress.look.sex,
    look: dress.look,
    clothes: dress.clothes,
    weapon: shownRef(dress.weapon),
    backpack: dress.backpack,
  });
  made.setAnimMode("full");
  for (const [part, pose] of [
    ["hand_frontAnim", "meleeFrontHand"],
    ["hand_backAnim", "meleeBackHand"],
  ]) {
    goto(made.clip.child(part), pose);
  }
  for (const mod of ["scope", "suppressor"]) {
    const item = made.animWeapon?.child("item")?.child(mod);
    if (item) {
      item.visible = false;
    }
  }
  const actor = {
    kind: "npc",
    key: entry.key,
    name: shortName(def),
    side: "friend",
    x: withinEdges(Number(entry.x)),
    y: room.floorY,
    facing: toRight(entry.facing),
    pose: entry.pose,
    low: entry.pose === LOW_POSE,
    alive: true,
  };
  made.bind(actor);
  made.setFacing(actor.facing);
  // A state can name its own animation, which replaces the pose the room gave (F4:23202)
  gotoPlay(made.clip, defOf(entry.key).states?.find((each) => each.n === stateOf(entry.key))?.anim ?? entry.pose);
  numNPC = numNPC >= MOST_NPCS ? 0 : numNPC + 1;
  made.clip.zIndex = constant("depth_world_NPC") - constant("depth_world_player") + numNPC;
  made.clip.x = actor.x;
  made.clip.y = actor.y;
  layers.actors.addChild(made.clip);
  fitBox(actor);
  world.npcs.push(actor);
  note("place", entry.key, { x: actor.x });
  return actor;
}

// The box E talks to a person in, and where the talk icon floats, from the pose it was placed in
function fitBox(actor) {
  const head = actor.clip.child("headAnim");
  const body = boxOf(actor.clip);
  const height = Math.abs((head?.y ?? 0) * BOX_HEIGHT_SHARE);
  actor.box = { w: (body?.w ?? 0) * BOX_WIDTH_SHARE, h: height };
  actor.headX = head?.x ?? 0;
}

function removeNPC(key) {
  const index = world.npcs.findIndex((each) => each.key === key);
  if (index < 0) {
    return false;
  }
  const [gone] = world.npcs.splice(index, 1);
  gone.clip?.destroy({ children: true });
  gone.alive = false;
  queue = queue.filter((line) => line.key !== key);
  note("remove", key);
  return true;
}

// Places the room's people, half a second of game time apart. The first stands at once
function placeRoomNPCs() {
  world.npcs.length = 0;
  waiting = 0;
  numNPC = 0;
  if (!story.player) {
    return;
  }
  const delay = (constant("NPCsetupDelay") * page.lib.fps) / 1000;
  const entries = npcsForRoom(room);
  entries.forEach((entry, i) => {
    if (i === 0) {
      placeNPC(entry);
      return;
    }
    waiting += 1;
    world.later(
      Math.round(i * delay),
      () => {
        waiting -= 1;
        placeNPC(entry);
      },
      { room: true },
    );
  });
  fillQueue(entries);
  world.every(SPEECH_SECONDS * page.lib.fps, showNext, { room: true });
}

// ---------- Story: states, switching on and off, moving ----------

// A person's state set to a number or "off". A person who is now on and belongs in the room stands in it at once
export function setNPCState(key, state) {
  story.npcs ??= {};
  story.npcs[key] = { ...story.npcs[key], state };
  note("state", key, { state });
  return refresh(key);
}

// turnOnNPC and turnOffNPC (F4:23106): the start state, or "off". The person in the room stays until removed
export function turnOnNPC(key) {
  return setNPCState(key, 1);
}

export function turnOffNPC(key) {
  return setNPCState(key, "off");
}

// A person on, belonging in this room and not here yet appears (setupAnNPCDirect F4:23130, which cutscene 6 uses)
function refresh(key) {
  const entry = room.id ? npcsForRoom(room).find((each) => each.key === key) : null;
  if (!entry || npc(key)) {
    return npc(key);
  }
  const actor = placeNPC(entry);
  if (actor) {
    queueLines(key);
  }
  return actor;
}

// Moves a person to a room and an x: gone from this room if they were in it, standing in it if that is where they go
export function moveNPC(key, roomId, x, { pose, facing } = {}) {
  const home = homeOf(key);
  story.npcs ??= {};
  story.npcs[key] = {
    ...story.npcs[key],
    place: { room: roomId, x, pose: pose ?? home?.pose ?? "idle", facing: facing ?? home?.facing ?? "left" },
  };
  note("move", key, { room: roomId, x });
  if (roomId !== room.id) {
    removeNPC(key);
    return null;
  }
  removeNPC(key);
  return refresh(key);
}

// ---------- Talking ----------

function talkPrompt(thing) {
  return `[E] TALK TO ${thing.npc.name.toUpperCase()}`;
}

function talk(thing) {
  note("talk", thing.npc.key);
  npcs.hooks.dialog?.(thing.npc.key);
}

// The icon over the head shows a quest mark when the person's state has a quest, a talk mark otherwise
function dressTalkIcon(clip, thing) {
  const icon = clip.child("talkIcon");
  if (!icon) {
    return;
  }
  const quest = defOf(thing.npc.key)?.states?.find((each) => each.n === stateOf(thing.npc.key))?.quest;
  const questMark = icon.child("quest");
  const talkMark = icon.child("talk");
  if (questMark) {
    questMark.visible = Boolean(quest);
  }
  if (talkMark) {
    talkMark.visible = !quest;
  }
  icon.x = thing.npc.headX;
  icon.y -= Math.round(thing.h / 2) + ICON_LIFT;
}

// A talking box for each person standing here
function talkThings() {
  return world.npcs
    .filter((each) => each.clip && !each.clip.destroyed)
    .map((each) => ({
      kind: KIND,
      key: `n:${each.key}`,
      name: each.key,
      x: each.x,
      y: each.y - each.box.h / 2,
      w: each.box.w,
      h: each.box.h,
      npc: each,
    }));
}

// ---------- Speech ----------

function linesOf(key) {
  return (defOf(key)?.speech?.[String(stateOf(key))] ?? []).filter((line) => line !== "");
}

// The people's lines in the order of the original: every person's first line, then every person's second ... Each entry
// names the person and which line, and what is said is the line in the person's state when its turn comes
function fillQueue(entries) {
  queue = [];
  const counts = entries.map((entry) => ({ key: entry.key, count: linesOf(entry.key).length }));
  const most = Math.max(0, ...counts.map((each) => each.count));
  for (let i = 0; i < most; i += 1) {
    for (const each of counts) {
      if (i < each.count) {
        queue.push({ key: each.key, line: i });
      }
    }
  }
}

// A person who comes into the room later adds their lines to the end
function queueLines(key) {
  linesOf(key).forEach((_, line) => queue.push({ key, line }));
}

function dropBubble() {
  if (bubble?.clip && !bubble.clip.destroyed) {
    bubble.clip.destroy({ children: true });
  }
  bubble = null;
}

// The speaker: the player, the partner, "npc_<key>" or a person standing here
function speakerOf(target) {
  if (typeof target !== "string") {
    return target;
  }
  if (target === "player") {
    return world.player ?? player;
  }
  if (target === "partner") {
    return world.companions.find((each) => each.partner) ?? null;
  }
  return npc(target.replace(/^npc_/, ""));
}

// Swaps the bubble's one-line text field for one that grows with its words, and returns it
function growText(clip, words) {
  const old = clip.child("txt");
  const [left, top, right] = old.def.bounds;
  const field = new TextField({ ...old.def, html: null, bounds: [left, top, right, top + FIELD_HEIGHT] });
  field.position.copyFrom(old.position);
  clip.addChildAt(field, clip.getChildIndex(old));
  old.visible = false;
  field.own = words;
  field.draw();
  return { field, width: right - left };
}

// Shapes the bubble to its words and sets it over the speaker's head (displayWorldSpeech F4:24556)
function dressBubble(clip, speaker, words, thought) {
  const { field, width } = growText(clip, words);
  const height = field.contentHeight;
  const back = clip.child("back");
  const backing = back.child("backing");
  const arrow = back.child("arrow");
  backing.scale.set((width + BACKING_MARGIN.w) / BACKING_ART.w, (height + BACKING_MARGIN.h) / BACKING_ART.h);
  arrow.y = height + BACKING_MARGIN.h;
  clip.x = speaker.x;
  clip.y = speaker.y - (speaker.low ? ABOVE_SEATED : ABOVE_STANDING) - height * TEXT_LIFT;
  if (speaker.x > room.width - EDGE_NEAR) {
    field.x -= EDGE_SHIFT;
    backing.x -= EDGE_SHIFT;
  }
  if (speaker.x < EDGE_NEAR) {
    field.x += EDGE_SHIFT;
    backing.x += EDGE_SHIFT;
  }
  layers.effects.addChild(clip);
  const head = speaker.clip?.child("headAnim");
  if (head && speaker.facing > 0) {
    const spot = back.toLocal(head.toGlobal({ x: head.x, y: head.y }));
    arrow.x = spot.x - ARROW_BACK;
  }
  if (thought) {
    arrow.gotoAndStop("thought");
  }
}

// A bubble over a speaker: it fades in, stays and fades out. Another bubble is replaced. follow keeps it over the
// speaker as they walk (a cutscene's lines do)
export function say(target, text, { thought = false, follow = true } = {}) {
  const speaker = speakerOf(target);
  if (!speaker || !page.lib.exported(SPEECH_ART)) {
    return null;
  }
  dropBubble();
  const clip = page.lib.makeExported(SPEECH_ART);
  clip.eventMode = "none";
  clip.alpha = 0;
  dressBubble(clip, speaker, fillText(text), thought);
  bubble = { clip, speaker, follow };
  tween(clip, "alpha", 100, FADE_SECONDS, { ease: "easeOutSine" });
  tween(clip, "alpha", 0, FADE_SECONDS, {
    ease: "easeOutSine",
    delay: HOLD_SECONDS,
    done: () => {
      if (bubble?.clip === clip) {
        dropBubble();
      }
    },
  });
  note("say", speaker.key ?? speaker.name, { text });
  return clip;
}

// The next waiting line comes up over the person who says it, if they are standing here and still have it to say
function showNext() {
  while (queue.length > 0) {
    const { key, line } = queue.shift();
    const text = linesOf(key)[line];
    if (text !== undefined && npc(key)) {
      say(key, text, { follow: false });
      return;
    }
  }
}

function followSpeaker() {
  if (bubble?.follow && bubble.clip && !bubble.clip.destroyed) {
    bubble.clip.x = bubble.speaker.x;
  }
}

function leaveRoom() {
  dropBubble();
  queue = [];
}

export const npcs = {
  forRoom: npcsForRoom,
  npc,
  move: moveNPC,
  setState: setNPCState,
  stateOf,
  turnOn: turnOnNPC,
  turnOff: turnOffNPC,
  remove: removeNPC,
  setupDirect: refresh,
  say,
  // Where the dialog panel plugs in: dialog(key) opens the talk with a person (Task 54)
  hooks: { dialog: null },
  get waiting() {
    return waiting;
  },
  get queued() {
    return queue.map((each) => ({ ...each }));
  },
  log,
};

export function initNPCs(owner) {
  page = owner;
  register(KIND, {
    prompt: talkPrompt,
    use: talk,
    look: { frame: false, icon: "talkIcon", dress: dressTalkIcon },
  });
  addSource(talkThings);
  quests.hooks.npcState = refresh;
  onRoom("leave", leaveRoom);
  onRoom("build", placeRoomNPCs);
  page.steppers.push(followSpeaker);
  world.onReset(() => {
    waiting = 0;
    queue = [];
    bubble = null;
    log.length = 0;
    homes.clear();
  });
}

// Helpers for page.py checks
export const npcsDebug = {
  // The people in the room now
  npcList() {
    return world.npcs.map((each) => ({
      key: each.key,
      name: each.name,
      x: Math.round(each.x),
      pose: each.pose,
      facing: each.facing,
      state: stateOf(each.key),
      box: { w: Math.round(each.box.w), h: Math.round(each.box.h) },
      headX: each.headX,
    }));
  },

  // The lines waiting for a bubble, and the bubble up now
  speechState() {
    return {
      queue: queue.map((each) => `${each.key}: ${linesOf(each.key)[each.line]}`),
      showing:
        bubble?.clip && !bubble.clip.destroyed
          ? { speaker: bubble.speaker.key ?? "player", alpha: bubble.clip.alpha }
          : null,
    };
  },

  npcState(key, state) {
    setNPCState(key, state);
    return npcsDebug.npcList();
  },

  npcMove(key, roomId, x) {
    moveNPC(key, roomId, x);
    return npcsDebug.npcList();
  },

  npcSay(target, text, thought) {
    say(target, text, { thought });
    return npcsDebug.speechState();
  },

  npcLog() {
    return log.map((each) => ({ ...each }));
  },
};
