// The original's art, loaded in groups. flash.json's atlas lists every page and which pages each group and each room
// needs (atlas.groups, atlas.roomPages), so the page fetches only what the screen in front of the player draws:
// loadGroup for the menus and the world's shared art, roomArt for one room. Room art is released again as the player
// moves on, so a long play does not run a phone out of graphics memory.
import { Graphics, ImageSource, Texture } from "./vendor/pixi.min.mjs";

// Pages fetched and decoded at once, and how many of those a background prefetch may hold, so a prefetch never
// keeps a room the player is walking into waiting
const MOST_AT_ONCE = 6;
const MOST_PREFETCH = 2;
// Groups the world and the menus keep for good. Pages of these are never released, even when a room lists one
const KEPT_GROUPS = ["core", "ui", "map", "intro", "ending"];
// The original's load screen fades in over half a second and out over a second and a half (F4:14468, F4:22391)
const FADE_IN_SECONDS = 0.5;
const FADE_OUT_SECONDS = 1.5;

let lib = null;
let veil = null;
let veilFade = null;
// Pages waiting for a free slot, most urgent first
const waiting = { urgent: [], prefetch: [] };
let active = 0;
let activePrefetch = 0;
// Pages a prefetch asked for, so loadPage queues them behind everything else
const prefetching = new Set();

export async function download(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    throw new Error(`${url}: ${resp.status}`);
  }
  return resp;
}

// Fetches and decodes one atlas page into a texture
async function fetchPage(index, prefetch) {
  const blob = await (
    await download(`art/${lib.data.atlas.pages[index]}`, { priority: prefetch ? "low" : "auto" })
  ).blob();
  // Browsers don't premultiply a decoded bitmap's colors on upload, so it is decoded premultiplied, which is how
  // Pixi blends; the art's see-through parts would otherwise draw solid
  const bitmap = await createImageBitmap(blob, { premultiplyAlpha: "premultiply" });
  return new Texture({ source: new ImageSource({ resource: bitmap, alphaMode: "premultiplied-alpha" }) });
}

function runNext() {
  while (active < MOST_AT_ONCE) {
    const job = waiting.urgent.shift() ?? (activePrefetch < MOST_PREFETCH ? waiting.prefetch.shift() : undefined);
    if (!job) {
      return;
    }
    active += 1;
    activePrefetch += job.prefetch ? 1 : 0;
    fetchPage(job.index, job.prefetch)
      .then(job.resolve, job.reject)
      .finally(() => {
        active -= 1;
        activePrefetch -= job.prefetch ? 1 : 0;
        runNext();
      });
  }
}

// The Library's loadPage: queues the page behind the ones already fetching
export function loadPage(index) {
  const prefetch = prefetching.delete(index);
  return new Promise((resolve, reject) => {
    (prefetch ? waiting.prefetch : waiting.urgent).push({ index, prefetch, resolve, reject });
    runNext();
  });
}

// A room the player is waiting for needs a page a prefetch queued: the page moves up to the urgent line
function promote(index) {
  const at = waiting.prefetch.findIndex((job) => job.index === index);
  if (at >= 0) {
    const [job] = waiting.prefetch.splice(at, 1);
    job.prefetch = false;
    waiting.urgent.push(job);
  }
}

// ---------- Groups and rooms ----------

function pagesOf(ids) {
  return new Set(ids.flatMap((id) => lib.data.atlas.roomPages[id] ?? []));
}

// Resolves once every page of the group has loaded
export function loadGroup(name) {
  const pages = lib.data.atlas.groups[name];
  if (!pages) {
    return Promise.reject(new Error(`Union City: no art group called ${name}`));
  }
  return Promise.all(pages.map((index) => lib.page(index)));
}

// The world draws nothing until the shared art is in; the page loads it behind the menus
export function coreLoaded() {
  return loadGroup("core");
}

// Names of the groups with pages, all of them loaded
export function loadedGroups() {
  return Object.entries(lib.data.atlas.groups)
    .filter(([, pages]) => pages.length > 0 && pages.every((index) => lib.textures[index]))
    .map(([name]) => name);
}

// Resolves once every page the room draws from has loaded
export function roomArt(roomId) {
  const pages = lib.data.atlas.roomPages[roomId];
  if (!pages) {
    return Promise.reject(new Error(`Union City: no art for room ${roomId}`));
  }
  pages.forEach(promote);
  return Promise.all(pages.map((index) => lib.page(index)));
}

// Loads the art of rooms the player may walk into next (the rooms through the current room's doors and links), after
// everything the player is waiting for
export function prefetchRooms(ids) {
  for (const index of pagesOf(ids)) {
    if (!lib.textures[index] && !lib.loading[index]) {
      prefetching.add(index);
      lib.page(index).catch((e) => console.warn(`Union City: couldn't fetch art page ${index} ahead`, e));
    }
  }
}

// Frees every room page that no kept room draws from. Clips built from a freed page must be gone first. A page still
// loading is left alone; it is freed by a later call
export function releaseRooms(keepIds) {
  const atlas = lib.data.atlas;
  const keep = pagesOf(keepIds);
  for (const name of KEPT_GROUPS) {
    atlas.groups[name].forEach((index) => keep.add(index));
  }
  for (const index of pagesOf(Object.keys(atlas.roomPages))) {
    if (!keep.has(index)) {
      lib.forgetPage(index);
    }
  }
}

// ---------- The load screen ----------

// The original's load screen is a full black picture over the world. This fades it in or out; off hides it when done.
// The fade eases out like a room change's, or runs straight with linear (sleeping)
export function showLoading(on, seconds = on ? FADE_IN_SECONDS : FADE_OUT_SECONDS, { linear = false } = {}) {
  veil.visible = true;
  veilFade = { from: veil.alpha, to: on ? 1 : 0, steps: Math.max(1, Math.round(seconds * lib.fps)), at: 0, linear };
}

function stepVeil() {
  if (!veilFade) {
    return;
  }
  veilFade.at += 1;
  const t = Math.min(1, veilFade.at / veilFade.steps);
  const share = veilFade.linear ? t : Math.sin((t * Math.PI) / 2);
  veil.alpha = veilFade.from + (veilFade.to - veilFade.from) * share;
  if (t >= 1) {
    veil.visible = veilFade.to > 0;
    veilFade = null;
  }
}

// Hooks the loader to the page: the library whose pages it loads, and the load screen on the root
export function initArt(page, depth) {
  lib = page.lib;
  veil = new Graphics().rect(0, 0, page.width, page.height).fill(0x000000);
  veil.label = "loading";
  veil.zIndex = depth;
  veil.alpha = 0;
  veil.visible = false;
  veil.eventMode = "none";
  page.root.addChild(veil);
  page.steppers.push(stepVeil);
}

export const art = { loadGroup, coreLoaded, loadedGroups, roomArt, prefetchRooms, releaseRooms, showLoading };
