// A world as bytes and back, for saving, sharing, undo and the fingerprint. Everything that outlives a step is in
// here, so a world unpacked from these bytes runs on exactly like the one that was packed.
//
// Layout, little-endian:
//   0  "SAND"                  4  version u8 = 1           5  flags u8 (bit 0 solid floor)
//   6  width u16 = 320         8  height u16 = 180         10 step u32
//   14 seed u32                18 strokeCount u32          22 slug mode u8
//   23 zombies u8              24 backdrop u8              25 reserved u8 = 0
//   26 spigots: 4 x (element u8, size u8)
//   34 el[N] u8, shade[N] u8, heat[N] i16, life[N] u16
//      particle count u16, then count x PART_FIELDS i32
//      creatures length u32, then the slug, zombie and grab bytes
// The text form is that, deflated (zlib-wrapped) and base64'd.
import { ELEMENT_COUNT } from "./elements.js";
import { packSlug, unpackSlug } from "./slugbytes.js";
import { createWorld, H, N, PART_FIELDS, PART_MAX, W } from "./world.js";
import { packGrabs, packZombies, unpackGrabs, unpackZombies } from "./zombiebytes.js";

const MAGIC = [83, 65, 78, 68];
const VERSION = 1;
const HEAD = 34;
const PLANES = N * 6;
// btoa takes a string; building it this many bytes at a time keeps each String.fromCharCode call small
const CHUNK = 0x8000;

function creatureBytes(w) {
  const slug = packSlug(w.slug);
  const zombies = packZombies(w.zombies);
  const grabs = packGrabs(w.grabs);
  const bytes = new Uint8Array(slug.length + zombies.length + grabs.length);
  bytes.set(slug, 0);
  bytes.set(zombies, slug.length);
  bytes.set(grabs, slug.length + zombies.length);
  return bytes;
}

function writeHeader(view, w) {
  MAGIC.forEach((b, k) => view.setUint8(k, b));
  view.setUint8(4, VERSION);
  view.setUint8(5, w.settings.floor & 1);
  view.setUint16(6, W, true);
  view.setUint16(8, H, true);
  view.setUint32(10, w.step, true);
  view.setUint32(14, w.seed, true);
  view.setUint32(18, w.strokeCount, true);
  view.setUint8(22, w.settings.slug);
  view.setUint8(23, w.settings.zombies);
  view.setUint8(24, w.settings.backdrop);
  view.setUint8(25, 0);
  w.spigots.forEach(([element, size], k) => {
    view.setUint8(26 + k * 2, element);
    view.setUint8(27 + k * 2, size);
  });
}

/** The world as raw bytes (the snapshot layout above) */
export function packWorld(w) {
  const creatures = creatureBytes(w);
  const partBytes = w.parts.n * PART_FIELDS * 4;
  const bytes = new Uint8Array(HEAD + PLANES + 2 + partBytes + 4 + creatures.length);
  const view = new DataView(bytes.buffer);
  writeHeader(view, w);
  let at = HEAD;
  bytes.set(w.el, at);
  at += N;
  bytes.set(w.shade, at);
  at += N;
  for (let i = 0; i < N; i++, at += 2) {
    view.setInt16(at, w.heat[i], true);
  }
  for (let i = 0; i < N; i++, at += 2) {
    view.setUint16(at, w.life[i], true);
  }
  view.setUint16(at, w.parts.n, true);
  at += 2;
  const rec = w.parts.rec;
  for (let k = 0; k < w.parts.n * PART_FIELDS; k++, at += 4) {
    view.setInt32(at, rec[k], true);
  }
  view.setUint32(at, creatures.length, true);
  bytes.set(creatures, at + 4);
  return bytes;
}

function checkHeader(bytes, view) {
  if (bytes.length < HEAD + PLANES + 6 || MAGIC.some((b, k) => bytes[k] !== b)) {
    throw new Error("That isn't a Sandfall world.");
  }
  if (view.getUint8(4) !== VERSION) {
    throw new Error("That world was saved by a different version of Sandfall.");
  }
  if (view.getUint16(6, true) !== W || view.getUint16(8, true) !== H) {
    throw new Error("That world is the wrong size.");
  }
}

function readHeader(view) {
  const w = createWorld({ seed: view.getUint32(14, true) });
  w.step = view.getUint32(10, true);
  w.strokeCount = view.getUint32(18, true);
  w.settings.floor = view.getUint8(5) & 1;
  w.settings.slug = view.getUint8(22);
  w.settings.zombies = view.getUint8(23);
  w.settings.backdrop = view.getUint8(24);
  for (let k = 0; k < 4; k++) {
    w.spigots[k][0] = view.getUint8(26 + k * 2);
    w.spigots[k][1] = view.getUint8(27 + k * 2);
  }
  return w;
}

function readPlanes(w, bytes, view) {
  let at = HEAD;
  w.el.set(bytes.subarray(at, at + N));
  for (let i = 0; i < N; i++) {
    if (w.el[i] >= ELEMENT_COUNT) {
      throw new Error("That world holds a material Sandfall doesn't know.");
    }
  }
  at += N;
  w.shade.set(bytes.subarray(at, at + N));
  at += N;
  for (let i = 0; i < N; i++, at += 2) {
    w.heat[i] = view.getInt16(at, true);
  }
  for (let i = 0; i < N; i++, at += 2) {
    w.life[i] = view.getUint16(at, true);
  }
  return at;
}

function readParticles(w, bytes, view, at) {
  const n = view.getUint16(at, true);
  at += 2;
  if (n > PART_MAX || at + n * PART_FIELDS * 4 + 4 > bytes.length) {
    throw new Error("That world's saved explosions are broken.");
  }
  w.parts.n = n;
  for (let k = 0; k < n * PART_FIELDS; k++, at += 4) {
    w.parts.rec[k] = view.getInt32(at, true);
  }
  return at;
}

function readCreatures(w, bytes, view, at) {
  const length = view.getUint32(at, true);
  at += 4;
  if (at + length !== bytes.length) {
    throw new Error("That world's saved creatures are broken.");
  }
  const slug = unpackSlug(bytes, at);
  const zombies = unpackZombies(bytes, slug.next);
  const grabs = unpackGrabs(bytes, zombies.next);
  if (grabs.next !== bytes.length) {
    throw new Error("That world's saved creatures are broken.");
  }
  w.slug = slug.slug;
  w.zombies = zombies.zombies;
  w.grabs = grabs.grabs;
}

/** A world from bytes made by packWorld. Throws an Error with a plain message when the bytes aren't a world */
export function unpackWorld(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  checkHeader(bytes, view);
  const w = readHeader(view);
  let at = readPlanes(w, bytes, view);
  at = readParticles(w, bytes, view, at);
  try {
    readCreatures(w, bytes, view, at);
  } catch (e) {
    if (e instanceof RangeError) {
      // A DataView read past the end: the creature bytes were cut short
      throw new Error("That world's saved creatures are broken.", { cause: e });
    }
    throw e;
  }
  return w;
}

async function streamBytes(bytes, transform) {
  const stream = new Blob([bytes]).stream().pipeThrough(transform);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function toBase64(bytes) {
  let text = "";
  for (let at = 0; at < bytes.length; at += CHUNK) {
    text += String.fromCharCode.apply(null, bytes.subarray(at, at + CHUNK));
  }
  return btoa(text);
}

function fromBase64(text) {
  const raw = atob(text);
  const bytes = new Uint8Array(raw.length);
  for (let k = 0; k < raw.length; k++) {
    bytes[k] = raw.charCodeAt(k);
  }
  return bytes;
}

/** The world as snapshot text: packed, deflated, base64'd */
export async function encodeWorld(w) {
  return toBase64(await streamBytes(packWorld(w), new CompressionStream("deflate")));
}

/** A world from snapshot text made by encodeWorld. Rejects with a plain message when the text isn't a world */
export async function decodeWorld(text) {
  let bytes;
  try {
    bytes = await streamBytes(fromBase64(text), new DecompressionStream("deflate"));
  } catch (e) {
    throw new Error("That world couldn't be read.", { cause: e });
  }
  return unpackWorld(bytes);
}

/** An 8-hex-digit fingerprint (FNV-1a 32) of the world's snapshot bytes, so it covers exactly what a snapshot carries */
export function hashWorld(w) {
  const bytes = packWorld(w);
  let h = 0x811c9dc5;
  for (let k = 0; k < bytes.length; k++) {
    h = Math.imul(h ^ bytes[k], 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}
