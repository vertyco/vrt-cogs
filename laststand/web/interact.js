// Interaction: what the player could use, the bracket and prompt that show it, and what E does with it.
//
// Everything usable is a "thing": a marker the room's art placed (doors, stairs, links, entrances and exits), a pickup
// on the floor, or whatever a source adds (NPCs, containers, beds, notes, shop pedestals come from later systems). A
// kind of thing is registered with register(kind, { prompt, use, look, leaves, available }):
//   prompt(thing)    the words the HUD shows when the thing is in reach, a { text, grey } for an unusable one, or null
//   use(thing, said) what E does; said is what prompt returned
//   look             how the bracket is drawn: { frame (false hides the corner brackets), icon (the highlight clip's
//                    child to show), flip (true when the thing in the left half of the room mirrors it), dress(clip,
//                    thing) for anything else }
//   leaves           true when using it takes the player out of the room, so a companion who is down stops them first
//   available(thing) false for a marker that offers nothing (a decor entrance with no building behind it)
//
// On a desktop the thing under the mouse is the one the player would use (it is bracketed dim while out of reach and
// bright, with its words, when in reach). On a touch screen there is no pointer: the things in reach are listed nearest
// first and the player steps through them. Reach is checked fresh at every use, so E never fires from out of range.
import { companions } from "./companions.js";
import { data } from "./data.js";
import { drops } from "./drops.js";
import { hud } from "./hud.js";
import { input } from "./input.js";
import { enterRoom, layers, onRoom, room, toScreen, toWorld } from "./rooms.js";
import { rng } from "./rng.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

// Used until the converted constants load (F4:27515-27526)
const DEFAULT_INTERACT_RANGE = 80;
// The bracket is this much bigger than the thing, all round (F4:15260)
const FRAME_MARGIN = 5;
const BRACKET_IN_REACH = 1;
const BRACKET_OUT_OF_REACH = 0.5;
const MOST_LOGGED = 100;
const DIALOG_PAUSE = "dialog";
// The icons on the highlight clip, one of which a kind shows
const ICONS = [
  "mapIcon",
  "arrowIcon",
  "dropIcon",
  "inspectIcon",
  "shopIcon",
  "doorIcon",
  "stairUp",
  "stairDown",
  "talkIcon",
  "enter",
  "exit",
  "arrowUp",
];
const ID_PARTS = /^l(\d+)_s(\d+)_b(\d+)_f(\d+)_r(\d+)$/;
// The wording the prompts and alerts use (F4:15437-15690, 14899)
const TEXT = {
  open: "[E] OPEN",
  pick: "[E] PICK LOCK",
  useKey: "[E] USE KEY",
  needsKey: "REQUIRES KEY",
  blocked: "DOOR IS BLOCKED",
  keyRequired: "KEY REQUIRED TO OPEN THIS DOOR",
  unlocked: "DOOR UNLOCKED",
};

let page = null;
// The highlight clip and which thing it was dressed for
let highlight = null;
let highlightKey = null;
let artReady = false;
let choice = 0;
let changing = false;
let serial = 0;
const kinds = new Map();
const sources = [];

export const interact = {
  // What E would use now: { kind, key, name, x, y, w, h, marker | pickup | actor, prompt, grey, label, gPrompt,
  // inRange }, or null. label is the prompt without its "[E] " (what a touch button says)
  target: null,
  // The thing under the mouse (desktop), in reach or not, or null
  hover: null,
  // The G prompt for a companion in reach, shown with no E target hovered on a desktop and always on touch
  gPrompt: "",
  // On touch: how many things are in reach and which one the action button shows (0 and 0 on a desktop)
  count: 0,
  index: 0,
  // The dialog waiting for the dialog panel: { kind: "companionDown", heading, body, ok } or null
  dialog: null,
  // What a later system plugs in: lockpick({ kind, name, diff, unlock }) opens the lockpick screen, map() the city map
  hooks: { lockpick: null, map: null },
  // { kind, name, frame } for each thing used or step it ran, newest last, for checks
  log: [],
};

// The functions of the interface (declared below)
Object.assign(interact, {
  register,
  addSource,
  things,
  candidates,
  refresh,
  cycle,
  useTarget,
  answerDialog,
  showDialog,
  unlockDoor,
  tryDoor,
});

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

function note(kind, name, extra = {}) {
  interact.log.push({ kind, name, frame: world.frame, ...extra });
  if (interact.log.length > MOST_LOGGED) {
    interact.log.shift();
  }
}

// ---------- Registering ----------

// Registers a kind of thing (see the top of the file)
export function register(kind, def) {
  kinds.set(kind, def);
}

// Registers fn() returning more things: { kind, key, name, x, y, w, h, ...whatever its use needs }
export function addSource(fn) {
  sources.push(fn);
}

// ---------- The things in the room ----------

function parseId(id) {
  const [l, s, b, f, r] = ID_PARTS.exec(id).slice(1).map(Number);
  return { l, s, b, f, r };
}

function idOf({ l, s, b, f, r }) {
  return `l${l}_s${s}_b${b}_f${f}_r${r}`;
}

function markerThings() {
  return Object.values(room.markers)
    .filter((marker) => kinds.has(marker.kind))
    .map((marker) => ({
      kind: marker.kind,
      key: `m:${marker.name}`,
      name: marker.name,
      x: marker.x,
      y: marker.y,
      w: marker.w,
      h: marker.h,
      marker,
    }));
}

// Each landed pickup, sized by its picture
function pickupThings() {
  return drops.pickups
    .filter((piece) => !piece.node.destroyed)
    .map((piece) => {
      if (!piece.interactId) {
        // A landed pickup keeps its size, so its picture is measured once
        const box = piece.node.getLocalBounds();
        piece.interactId = serial += 1;
        piece.interactSize = {
          w: Math.max(1, box.width * Math.abs(piece.node.scale.x)),
          h: Math.max(1, box.height * Math.abs(piece.node.scale.y)),
        };
      }
      return {
        kind: "pickup",
        key: `p:${piece.interactId}`,
        name: piece.name,
        x: piece.node.x,
        y: piece.node.y,
        ...piece.interactSize,
        pickup: piece,
      };
    });
}

// Everything usable in the room, in the order the original builds its list: the room's markers, then what drops and the
// other sources add. A later entry wins where two overlap under the mouse
export function things() {
  if (!room.id) {
    return [];
  }
  const found = [...markerThings(), ...pickupThings(), ...sources.flatMap((fn) => fn())];
  return found.filter((thing) => kinds.get(thing.kind)?.available?.(thing) !== false);
}

// ---------- Reach and words ----------

function reach(thing) {
  return thing.w + constant("interactRange", DEFAULT_INTERACT_RANGE);
}

function distance(thing) {
  return Math.abs(world.player.x - thing.x);
}

// The player is close enough to use the thing. Worked out from where both are now, every time it is asked
function inRange(thing) {
  return Boolean(world.player) && distance(thing) < reach(thing);
}

// The thing as the HUD and the touch button see it, or null when it has nothing to say
function describe(thing) {
  const said = kinds.get(thing.kind)?.prompt(thing);
  if (!said) {
    return null;
  }
  const { text, grey = false } = typeof said === "string" ? { text: said } : said;
  const label = text.replace(/^\[E\]\s*/, "");
  return { ...thing, prompt: text, grey, label, gPrompt: companions.near?.text ?? null };
}

// Whether the player's body lets them use things: not shooting, held, in the air or climbing (F4:15003, 15245)
function free() {
  const body = world.player;
  const busy = body?.firing || body?.struggling || body?.jumping || body?.falling || body?.climbing;
  return Boolean(body) && body.alive !== false && !busy;
}

// Everything in reach with something to say, nearest first. A touch screen's action button steps through these
export function candidates() {
  if (!free()) {
    return [];
  }
  return things()
    .filter(inRange)
    .map(describe)
    .filter(Boolean)
    .sort((a, b) => distance(a) - distance(b));
}

// The thing whose box holds the mouse, the last one in the list first as the original finds it
function hovered() {
  const point = toWorld(input.mouse.x, input.mouse.y);
  const list = things();
  for (let place = list.length - 1; place >= 0; place -= 1) {
    const thing = list[place];
    if (Math.abs(point.x - thing.x) < thing.w / 2 && Math.abs(point.y - thing.y) < thing.h / 2) {
      return thing;
    }
  }
  return null;
}

// ---------- The bracket ----------

function dropHighlight() {
  if (highlight && !highlight.destroyed) {
    highlight.destroy({ children: true });
  }
  highlight = null;
  highlightKey = null;
}

// Dresses the highlight for a thing: the corner brackets sized to it, and the one icon its kind shows (F4:15256-15430)
function dressHighlight(clip, thing, look) {
  const frame = clip.child("frame");
  if (frame) {
    const box = frame.getLocalBounds();
    frame.visible = look.frame !== false;
    frame.scale.set((thing.w + FRAME_MARGIN) / (box.width || 1), (thing.h + FRAME_MARGIN) / (box.height || 1));
  }
  for (const name of ICONS) {
    const icon = clip.child(name);
    if (icon) {
      icon.visible = name === look.icon;
    }
  }
  clip.scale.x = look.flip && thing.x < room.width / 2 ? -1 : 1;
  look.dress?.(clip, thing);
}

function showHighlight(thing, inReach) {
  if (!artReady) {
    return;
  }
  if (!highlight || highlight.destroyed || highlightKey !== thing.key) {
    dropHighlight();
    highlight = page.lib.makeExported("searchHighlight");
    highlight.eventMode = "none";
    highlight.x = thing.x;
    highlight.y = thing.y;
    layers.effects.addChild(highlight);
    highlightKey = thing.key;
    dressHighlight(highlight, thing, kinds.get(thing.kind).look ?? {});
  }
  highlight.x = thing.x;
  highlight.y = thing.y;
  highlight.alpha = inReach ? BRACKET_IN_REACH : BRACKET_OUT_OF_REACH;
}

// ---------- What the player would use ----------

function clear() {
  interact.target = null;
  interact.hover = null;
  interact.gPrompt = "";
  interact.count = 0;
  interact.index = 0;
  dropHighlight();
  hud.prompt("");
  hud.gPrompt("");
}

// Works out the target, the bracket and the prompt lines from where the player and the mouse are now
export function refresh() {
  if (!free() || !room.id) {
    clear();
    return null;
  }
  let hover = null;
  let target = null;
  if (page.touch) {
    const list = candidates();
    choice = Math.min(choice, Math.max(0, list.length - 1));
    target = list[choice] ?? null;
    hover = target;
    interact.count = list.length;
    interact.index = choice;
  } else {
    hover = hovered();
    target = hover && inRange(hover) ? describe(hover) : null;
  }
  interact.hover = hover;
  interact.target = target;
  interact.gPrompt = hover && !page.touch ? "" : (companions.near?.text ?? "");
  if (hover && kinds.has(hover.kind)) {
    showHighlight(hover, Boolean(target));
  } else {
    dropHighlight();
  }
  hud.prompt(target?.prompt ?? "", target);
  hud.gPrompt(interact.gPrompt);
  return target;
}

// On a touch screen: steps the action button to the next (1) or the previous (-1) thing in reach
export function cycle(step = 1) {
  const count = candidates().length;
  choice = count ? (choice + step + count) % count : 0;
  return refresh();
}

// ---------- Using ----------

// A box for the dialog panel to draw: { kind, heading, body, ok }. The world stops until the player answers it
export function showDialog(kind, dialog) {
  interact.dialog = { kind, ...dialog };
  world.pause(DIALOG_PAUSE);
  note("dialog", kind);
}

// The "COMPANION DOWN!" box: it stops the player leaving a down companion, and its OK lets the next try through
function warnCompanionDown() {
  showDialog("companionDown", companions.downDialog);
}

// The box's OK: the player has been told, and the door will open the next time they use it
export function answerDialog() {
  if (interact.dialog?.kind === "companionDown") {
    companions.ackDown();
  }
  interact.dialog = null;
  world.resume(DIALOG_PAUSE);
}

// E on a thing (or the touch button): uses it if the player can use things and it is in reach right now. Returns
// whether anything was done
export function useTarget(target = interact.target) {
  if (!target || !free() || world.paused || changing) {
    return false;
  }
  const thing = things().find((each) => each.key === target.key);
  if (!thing || !inRange(thing)) {
    return false;
  }
  const said = describe(thing);
  const def = kinds.get(thing.kind);
  if (!said) {
    return false;
  }
  if (def.leaves && companions.leaveWarning()) {
    warnCompanionDown();
    return true;
  }
  note("use", thing.name, { thing: thing.kind });
  def.use(thing, said);
  return true;
}

function useKey() {
  refresh();
  if (input.usePressed) {
    useTarget(interact.target);
  }
}

// ---------- Locks ----------

function doorKey(name) {
  return `${room.id}_${name}`;
}

// The lock on a door of this room that is still shut: { needsKey, blocked, diff }, or null for a door with none
function lockOf(name) {
  const entry = room.def?.lockedDoors?.find((each) => each.marker === name);
  if (!entry || story.doors?.[doorKey(name)] === false) {
    return null;
  }
  return { needsKey: entry.needsKey === true, blocked: entry.isBlocked === true, diff: entry.diff };
}

// The row in the backpack that is the key to this door, or -1
function keyIndex(name) {
  const door = doorKey(name);
  return story.inventory.findIndex((row) => data.items.quest?.[row.ref]?.door === door);
}

// The door opens for good (unlockDoor F4:14803)
export function unlockDoor(name) {
  story.doors ??= {};
  story.doors[doorKey(name)] = false;
  sound.play("sound_security_complete");
  hud.alert(TEXT.unlocked, "white");
}

// E on a shut door: the key it needs is used up and opens it, a door with no key to find opens the lockpick screen at
// that door's own difficulty (attemptUnlockDoor F4:14829)
function tryUnlock(thing, lock) {
  const held = keyIndex(thing.name);
  if (held >= 0) {
    story.inventory.splice(held, 1);
    unlockDoor(thing.name);
    return;
  }
  if (lock.needsKey) {
    hud.alert(TEXT.keyRequired);
    sound.play("sound_doorLocked");
    return;
  }
  const hook = interact.hooks.lockpick;
  note("lockpick", thing.name, { diff: lock.diff });
  hook?.({ kind: "door", name: thing.name, diff: lock.diff, unlock: () => unlockDoor(thing.name) });
}

// E on a door of this room by its name, as the lock system asks for it: its key, its refusal or the lockpick screen.
// Returns "key", "refused", "pick", or null for a door with no lock still shut
export function tryDoor(name) {
  const lock = lockOf(name);
  if (!lock) {
    return null;
  }
  const held = keyIndex(name) >= 0;
  tryUnlock({ name }, lock);
  if (held) {
    return "key";
  }
  return lock.needsKey ? "refused" : "pick";
}

// What a door-like thing says: its open words, or what its lock needs. withKey shows "[E] USE KEY" for a carried key
function doorWords(thing, open, withKey) {
  const lock = lockOf(thing.name);
  if (!lock) {
    return open;
  }
  let text = lock.needsKey ? TEXT.needsKey : TEXT.pick;
  if (lock.blocked) {
    text = TEXT.blocked;
  }
  return withKey && keyIndex(thing.name) >= 0 ? TEXT.useKey : text;
}

// ---------- Moving between rooms ----------

function roomExists(id) {
  return Boolean(data.world.rooms[id]);
}

function doorSound() {
  sound.play(`sound_door${rng.random(2) + 1}`);
}

function stepSound() {
  sound.play("sound_step_baseLeft1");
  sound.play("sound_step_baseLeft2");
}

// Which way a thing on the room's left or right half leads: the left one goes to the lower room or street number
function sideOf(thing) {
  return thing.x < room.width / 2 ? -1 : 1;
}

function numberOf(thing) {
  return Number(thing.name.slice(4));
}

// Where each kind goes: the room it leads to, the marker (or edge) the player appears at, and the sound of leaving
// (changeRooms F4:14463-14960). here is the room's numbers
const GOES = {
  door: (thing, here) => ({
    to: { ...here, r: here.r + sideOf(thing) },
    arrive: sideOf(thing) < 0 ? "end" : "start",
    sound: doorSound,
  }),
  room: (thing, here) => ({ to: { ...here, r: numberOf(thing) }, arrive: `room${here.r}`, sound: doorSound }),
  uprm: (thing, here) => ({ to: { ...here, r: numberOf(thing) }, arrive: `dnrm${here.r}` }),
  dnrm: (thing, here) => ({ to: { ...here, r: numberOf(thing) }, arrive: `uprm${here.r}` }),
  ltrm: (thing, here) => ({ to: { ...here, r: here.r - 1 }, arrive: "end" }),
  rtrm: (thing, here) => ({ to: { ...here, r: here.r + 1 }, arrive: "start" }),
  entr: (thing, here) => ({
    to: { ...here, b: numberOf(thing), f: 1, r: 1 },
    arrive: `exit${numberOf(thing)}`,
    sound: doorSound,
  }),
  exit: (thing, here) => ({
    to: { ...here, b: 0, f: 0, r: 1 },
    arrive: numberOf(thing) === 0 ? "start" : `entr${numberOf(thing)}`,
    sound: doorSound,
  }),
  sup: (thing, here) => ({
    to: { ...here, f: here.f + 1 },
    arrive: "sdwn",
    sound: () => sound.play("sound_stairsUp"),
  }),
  sdwn: (thing, here) => ({
    to: { ...here, f: here.f - 1 },
    arrive: "sup",
    sound: () => sound.play("sound_stairsDown"),
  }),
  drop: (thing, here) => ({ to: { ...here, f: here.f - 1 }, arrive: "drop", sound: stepSound }),
  strt: (thing, here) => ({
    to: { ...here, s: here.s + sideOf(thing), b: 0, f: 0, r: 1 },
    arrive: sideOf(thing) < 0 ? "end" : "start",
  }),
};
// What using a thing does when the room it leads to is not there: the doors and links are locked and say so, the
// stairs, drops and streets do nothing
const DEAD_END_SOUND = new Set(["door", "room", "uprm", "dnrm", "ltrm", "rtrm", "entr"]);

// Takes the player through a door, stairs, link, entrance, exit or street end
function pass(thing) {
  const go = GOES[thing.kind](thing, parseId(room.id));
  const id = idOf(go.to);
  if (!roomExists(id)) {
    if (DEAD_END_SOUND.has(thing.kind)) {
      sound.play("sound_doorLocked");
    }
    return;
  }
  go.sound?.();
  changing = true;
  enterRoom(id, go.arrive)
    .catch((e) => console.warn(`Union City: couldn't go through ${thing.name}`, e))
    .finally(() => {
      changing = false;
    });
}

// A door-like thing that can be locked: shut, it tries its lock; open, it takes the player through
function openOrUnlock(thing) {
  const lock = lockOf(thing.name);
  if (lock) {
    tryUnlock(thing, lock);
  } else {
    pass(thing);
  }
}

// Whether the entrance has a building behind it. Many entrances in the art are only decoration
function hasBuilding(thing) {
  const here = parseId(room.id);
  return roomExists(idOf({ ...here, b: numberOf(thing), f: 1, r: 1 }));
}

// The wording of an entrance: a safe house building, or a safe room the entrance's side of this floor leads to
function enterWords(thing) {
  const here = parseId(room.id);
  const building = data.world.locations?.[`l${here.l}`]?.streets?.[`s${here.s}`]?.buildings?.[`b${numberOf(thing)}`];
  let text = building?.safeHouse === true ? "[E] ENTER SAFEHOUSE" : "[E] ENTER";
  const next = { ...here, r: here.r + (thing.x > 200 ? 1 : -1) };
  if (roomExists(idOf(next)) && data.world.rooms[idOf(next)].safeHouse === true) {
    text = "[E] ENTER SAFEROOM";
  }
  return text;
}

function openMap() {
  savePoint("map");
  note("map", "area");
  interact.hooks.map?.();
}

// ---------- The kinds this file owns ----------

function registerDoorKinds() {
  register("door", {
    prompt: (thing) => doorWords(thing, TEXT.open, true),
    use: openOrUnlock,
    leaves: true,
    look: {
      frame: false,
      icon: "doorIcon",
      dress(clip, thing) {
        const icon = clip.child("doorIcon");
        icon.x = 0;
        icon.scale.x = thing.x < 100 ? -1 : 1;
      },
    },
  });
  register("room", {
    prompt: (thing) => doorWords(thing, TEXT.open, true),
    use: openOrUnlock,
    leaves: true,
    look: {
      icon: "doorIcon",
      dress(clip) {
        clip.child("doorIcon").x = 7;
      },
    },
  });
}

function registerLinkKinds() {
  const links = { frame: false, icon: "arrowIcon", flip: true };
  register("uprm", { prompt: () => "[E] ENTER", use: pass, leaves: true, look: { frame: false, icon: "arrowUp" } });
  register("dnrm", { prompt: () => "[E] ENTER", use: pass, leaves: true, look: { frame: false, icon: "dropIcon" } });
  register("ltrm", { prompt: () => "[E] NEXT AREA", use: pass, leaves: true, look: links });
  register("rtrm", { prompt: () => "[E] NEXT AREA", use: pass, leaves: true, look: links });
  register("strt", { prompt: () => "[E] NEXT AREA", use: pass, leaves: true, look: links });
}

function registerBuildingKinds() {
  register("entr", {
    prompt: (thing) => doorWords(thing, enterWords(thing), false),
    use: openOrUnlock,
    available: hasBuilding,
    leaves: true,
    look: { icon: "enter" },
  });
  register("exit", {
    prompt: (thing) => doorWords(thing, "[E] EXIT", false),
    use: openOrUnlock,
    leaves: true,
    look: { icon: "exit" },
  });
  register("sup", {
    prompt: (thing) => doorWords(thing, "[E] UP STAIRS", false),
    use: openOrUnlock,
    leaves: true,
    look: { frame: false, icon: "stairUp", flip: true },
  });
  register("sdwn", {
    prompt: (thing) => doorWords(thing, "[E] DOWN STAIRS", false),
    use: openOrUnlock,
    leaves: true,
    look: { frame: false, icon: "stairDown", flip: true },
  });
  register("drop", {
    prompt: () => "[E] DROP DOWN",
    use: pass,
    leaves: true,
    look: { frame: false, icon: "dropIcon" },
  });
  register("area", {
    prompt: () => "[E] EXIT TO MAP",
    use: openMap,
    leaves: true,
    look: { frame: false, icon: "mapIcon", flip: true },
  });
  register("pickup", {
    prompt: (thing) => `[E] PICK UP ${thing.name.toUpperCase()}`,
    use: (thing) => drops.takePickup(thing.pickup),
    look: {},
  });
}

// ---------- Setup ----------

export function initInteract(owner) {
  page = owner;
  registerDoorKinds();
  registerLinkKinds();
  registerBuildingKinds();
  page.lib
    .need([page.lib.exported("searchHighlight")])
    .then(() => {
      artReady = true;
    })
    .catch((e) => console.warn("Union City: the interaction bracket's art didn't load", e));
  // The bracket's thing is gone with its room
  onRoom("leave", () => {
    choice = 0;
    clear();
  });
  world.onReset(() => {
    choice = 0;
    changing = false;
    interact.dialog = null;
    interact.log.length = 0;
    clear();
  });
  world.stage("controls", useKey);
}

// Helpers for page.py checks
export const interactDebug = {
  // Moves the mouse to the middle of a thing in the room, by its name ("door1") or by its kind, so hovering and E
  // act on it as if the mouse were there, dx and dy pixels off its middle. Returns where it put the mouse (stage
  // pixels), or null
  pointAt(name, dx = 0, dy = 0) {
    const thing = things().find((each) => each.name === name || each.kind === name);
    if (!thing) {
      return null;
    }
    const at = toScreen(thing.x + dx, thing.y + dy);
    input.mouse.x = at.x;
    input.mouse.y = at.y;
    input.aim.x = at.x;
    input.aim.y = at.y;
    return { x: Math.round(at.x), y: Math.round(at.y) };
  },

  // The things in the room: what each is, where, and what it says now
  things() {
    return things().map((thing) => ({
      kind: thing.kind,
      name: thing.name,
      x: Math.round(thing.x),
      y: Math.round(thing.y),
      w: Math.round(thing.w),
      h: Math.round(thing.h),
      says: describe(thing)?.prompt ?? null,
      inRange: Boolean(world.player) && inRange(thing),
    }));
  },

  // What the player would use now, and what the prompt lines say
  state() {
    const target = interact.target;
    return {
      target: target && {
        kind: target.kind,
        name: target.name,
        prompt: target.prompt,
        label: target.label,
        grey: target.grey,
      },
      hover: interact.hover && { kind: interact.hover.kind, name: interact.hover.name },
      gPrompt: interact.gPrompt,
      prompts: { interact: hud.interactText, survivor: hud.survivorText },
      bracket:
        highlight && !highlight.destroyed
          ? { key: highlightKey, alpha: highlight.alpha, flip: highlight.scale.x < 0 }
          : null,
      candidates: candidates().map((each) => each.prompt),
      dialog: interact.dialog && interact.dialog.kind,
      changing,
    };
  },

  // The player stands at x on the floor (a stand-in for walking there)
  stand(x) {
    world.player.x = x;
    return world.player.x;
  },

  useTarget,
  answerDialog,
  unlockDoor,
  cycle,
};
