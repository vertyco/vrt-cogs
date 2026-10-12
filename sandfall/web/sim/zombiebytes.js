// The zombies' and the Hand tool's state as bytes, for the world's fingerprint and its snapshot. This file imports
// nothing, so world.js can use it without an import loop.
//
// Zombies, little-endian: count u8, then count records of ZOMBIE_BYTES:
//   0  arm length f u16 (256ths, 2..3)     2  leg length f2 u16 (256ths, 4..5)
//   4  scale i32 (1000ths, below 0 means it is about to be reborn)
//   8  walk phase u8 (0..200)              9  standing on something u8 (1) or not (0)
//   10 the zombie point glued to the slug u8 (255: none)    11 the slug point it is glued to u8
//   12 ZOMBIE_POINTS records of (x, y, last x, last y) i32 in 256ths of a cell
// The springs' rest lengths are not stored: they follow from f and f2.
//
// Grabs (the Hand tool), in the order they were made: count u8, then per grab:
//   player id length u8, the id's UTF-8 bytes, point count u8, that many point refs u16,
//   from x i32, from y i32, to x i32, to y i32 (256ths), step k u8, steps n u8
// A point ref below SLUG_REFS is a slug point; SLUG_REFS + z * ZOMBIE_POINTS + q is zombie z's point q.

export const ZOMBIE_POINTS = 11;
export const ZOMBIE_MAX = 30;
export const GRAB_MAX = 20;
export const SLUG_REFS = 64;
const HEAD = 12;
export const ZOMBIE_BYTES = HEAD + ZOMBIE_POINTS * 16;

/** The zombies as bytes */
export function packZombies(zombies) {
  const bytes = new Uint8Array(1 + zombies.length * ZOMBIE_BYTES);
  const view = new DataView(bytes.buffer);
  view.setUint8(0, zombies.length);
  for (let z = 0; z < zombies.length; z++) {
    const zombie = zombies[z];
    const at = 1 + z * ZOMBIE_BYTES;
    view.setUint16(at, zombie.f, true);
    view.setUint16(at + 2, zombie.f2, true);
    view.setInt32(at + 4, zombie.scale, true);
    view.setUint8(at + 8, zombie.walk);
    view.setUint8(at + 9, zombie.on);
    view.setUint8(at + 10, zombie.glue);
    view.setUint8(at + 11, zombie.to);
    for (let p = 0; p < ZOMBIE_POINTS; p++) {
      const pt = at + HEAD + p * 16;
      view.setInt32(pt, zombie.x[p], true);
      view.setInt32(pt + 4, zombie.y[p], true);
      view.setInt32(pt + 8, zombie.lx[p], true);
      view.setInt32(pt + 12, zombie.ly[p], true);
    }
  }
  return bytes;
}

/** Reads zombies written by packZombies from bytes at offset. Returns { zombies, next } */
export function unpackZombies(bytes, offset) {
  const view = new DataView(bytes.buffer, bytes.byteOffset + offset);
  const count = view.getUint8(0);
  const zombies = [];
  for (let z = 0; z < count; z++) {
    const at = 1 + z * ZOMBIE_BYTES;
    const zombie = {
      f: view.getUint16(at, true),
      f2: view.getUint16(at + 2, true),
      scale: view.getInt32(at + 4, true),
      walk: view.getUint8(at + 8),
      on: view.getUint8(at + 9),
      glue: view.getUint8(at + 10),
      to: view.getUint8(at + 11),
      x: new Int32Array(ZOMBIE_POINTS),
      y: new Int32Array(ZOMBIE_POINTS),
      lx: new Int32Array(ZOMBIE_POINTS),
      ly: new Int32Array(ZOMBIE_POINTS),
    };
    for (let p = 0; p < ZOMBIE_POINTS; p++) {
      const pt = at + HEAD + p * 16;
      zombie.x[p] = view.getInt32(pt, true);
      zombie.y[p] = view.getInt32(pt + 4, true);
      zombie.lx[p] = view.getInt32(pt + 8, true);
      zombie.ly[p] = view.getInt32(pt + 12, true);
    }
    zombies.push(zombie);
  }
  return { zombies, next: offset + 1 + count * ZOMBIE_BYTES };
}

/** The grabs (a Map from player id to grab) as bytes */
export function packGrabs(grabs) {
  const encoder = new TextEncoder();
  const parts = [];
  let size = 1;
  for (const [player, grab] of grabs) {
    const id = encoder.encode(player).slice(0, 255);
    parts.push([id, grab]);
    size += 1 + id.length + 1 + grab.refs.length * 2 + 18;
  }
  const bytes = new Uint8Array(size);
  const view = new DataView(bytes.buffer);
  view.setUint8(0, parts.length);
  let at = 1;
  for (const [id, grab] of parts) {
    view.setUint8(at, id.length);
    bytes.set(id, at + 1);
    at += 1 + id.length;
    view.setUint8(at, grab.refs.length);
    at += 1;
    for (const ref of grab.refs) {
      view.setUint16(at, ref, true);
      at += 2;
    }
    view.setInt32(at, grab.fx, true);
    view.setInt32(at + 4, grab.fy, true);
    view.setInt32(at + 8, grab.tx, true);
    view.setInt32(at + 12, grab.ty, true);
    view.setUint8(at + 16, grab.k);
    view.setUint8(at + 17, grab.n);
    at += 18;
  }
  return bytes;
}

/** Reads grabs written by packGrabs from bytes at offset. Returns { grabs, next } */
export function unpackGrabs(bytes, offset) {
  const decoder = new TextDecoder();
  const view = new DataView(bytes.buffer, bytes.byteOffset);
  const grabs = new Map();
  const count = view.getUint8(offset);
  let at = offset + 1;
  for (let g = 0; g < count; g++) {
    const length = view.getUint8(at);
    const player = decoder.decode(bytes.subarray(at + 1, at + 1 + length));
    at += 1 + length;
    const refCount = view.getUint8(at);
    at += 1;
    const refs = [];
    for (let r = 0; r < refCount; r++) {
      refs.push(view.getUint16(at, true));
      at += 2;
    }
    grabs.set(player, {
      refs,
      fx: view.getInt32(at, true),
      fy: view.getInt32(at + 4, true),
      tx: view.getInt32(at + 8, true),
      ty: view.getInt32(at + 12, true),
      k: view.getUint8(at + 16),
      n: view.getUint8(at + 17),
    });
    at += 18;
  }
  return { grabs, next: at };
}
