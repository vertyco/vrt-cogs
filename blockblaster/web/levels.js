// Level packs: 26 files of 100 levels each, fetched when a level is first needed.
// The hub sends the .gz files with Content-Encoding: gzip, so fetch(...).json() already gets plain JSON.

const PACK_SIZE = 100;
const LEVEL_COUNT = 2600;
const PACK_COUNT = LEVEL_COUNT / PACK_SIZE;
// Once a level is this far into its pack (the 90th of 100), the next pack starts loading in the background
const PREFETCH_FROM = 90;

// pack number -> Promise of {level number: compact level}
const packs = new Map();

async function fetchPack(packNo) {
  const name = String(packNo).padStart(2, "0");
  const response = await fetch(`levels/pack-${name}.json.gz`);
  if (!response.ok) {
    throw new Error(`level pack ${name} came back ${response.status}`);
  }
  const data = await response.json();
  const byNumber = new Map();
  for (const level of data.levels) {
    byNumber.set(level.n, level);
  }
  return byNumber;
}

function openPack(packNo) {
  if (!packs.has(packNo)) {
    const pending = fetchPack(packNo);
    packs.set(packNo, pending);
    // A failed fetch must not stay cached, or every later try would fail the same way
    pending.catch((e) => {
      console.warn("Block Blaster: couldn't load a level pack", e);
      packs.delete(packNo);
    });
  }
  return packs.get(packNo);
}

// The compact level number n (1 to 2,600). Expand it with sim/level.js
export async function loadLevel(n) {
  if (!Number.isInteger(n) || n < 1 || n > LEVEL_COUNT) {
    throw new Error(`Level ${n} does not exist, levels run from 1 to ${LEVEL_COUNT}`);
  }
  const packNo = Math.floor((n - 1) / PACK_SIZE) + 1;
  const pack = await openPack(packNo);
  if ((n - 1) % PACK_SIZE >= PREFETCH_FROM - 1 && packNo < PACK_COUNT) {
    openPack(packNo + 1).catch((e) => console.warn("Block Blaster: the next level pack didn't load", e));
  }
  return pack.get(n);
}
