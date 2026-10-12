// The slug's state as bytes, for the world's fingerprint and its snapshot. This file imports nothing, so world.js can
// use it without an import loop (slug.js itself needs the world's constants and the particle engine).
//
// Layout, little-endian. No slug is the single byte 0. A slug is SLUG_BYTES long:
//   0  present u8 = 1          1  shape number k u8        2  rolling right u8 (1) or left (0)
//   3  wall bits u8 (1 left, 2 right, 4 top, 8 bottom: what its points touched last step)
//   4  scale i32 (1000ths)     8  power i32 (10000ths)     12 deaths u32
//   16 ring radius at birth i32 (256ths of a cell)
//   20 SLUG_POINTS records of (x, y, last x, last y) i32 in 256ths of a cell, the centre point first
// The springs' rest lengths are not stored: they follow from k and the ring radius.

export const SLUG_POINTS = 33;
const HEAD = 20;
export const SLUG_BYTES = HEAD + SLUG_POINTS * 16;

/** The slug (or null) as bytes */
export function packSlug(slug) {
  if (slug === null) {
    return new Uint8Array(1);
  }
  const bytes = new Uint8Array(SLUG_BYTES);
  const view = new DataView(bytes.buffer);
  view.setUint8(0, 1);
  view.setUint8(1, slug.k);
  view.setUint8(2, slug.right);
  view.setUint8(3, slug.wall);
  view.setInt32(4, slug.scale, true);
  view.setInt32(8, slug.power, true);
  view.setUint32(12, slug.deaths, true);
  view.setInt32(16, slug.radius, true);
  for (let p = 0; p < SLUG_POINTS; p++) {
    const at = HEAD + p * 16;
    view.setInt32(at, slug.x[p], true);
    view.setInt32(at + 4, slug.y[p], true);
    view.setInt32(at + 8, slug.lx[p], true);
    view.setInt32(at + 12, slug.ly[p], true);
  }
  return bytes;
}

/** Reads a slug written by packSlug from bytes at offset. Returns { slug, next }, next being the byte after it */
export function unpackSlug(bytes, offset) {
  const view = new DataView(bytes.buffer, bytes.byteOffset + offset);
  if (view.getUint8(0) === 0) {
    return { slug: null, next: offset + 1 };
  }
  const slug = {
    k: view.getUint8(1),
    right: view.getUint8(2),
    wall: view.getUint8(3),
    scale: view.getInt32(4, true),
    power: view.getInt32(8, true),
    deaths: view.getUint32(12, true),
    radius: view.getInt32(16, true),
    x: new Int32Array(SLUG_POINTS),
    y: new Int32Array(SLUG_POINTS),
    lx: new Int32Array(SLUG_POINTS),
    ly: new Int32Array(SLUG_POINTS),
    rest: null,
  };
  for (let p = 0; p < SLUG_POINTS; p++) {
    const at = HEAD + p * 16;
    slug.x[p] = view.getInt32(at, true);
    slug.y[p] = view.getInt32(at + 4, true);
    slug.lx[p] = view.getInt32(at + 8, true);
    slug.ly[p] = view.getInt32(at + 12, true);
  }
  return { slug, next: offset + SLUG_BYTES };
}
