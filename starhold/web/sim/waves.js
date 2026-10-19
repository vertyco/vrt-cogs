// Waves: how big, which robots, and when. A wave's entries come in one at a time; when its last robot has entered,
// the countdown to the next wave starts, so a slow player faces overlapping waves.
import { COLOSSUS, ROBOTS, WAVES } from "./rules.js";
import { emit } from "./events.js";
import { spawn } from "./robots.js";

/** Wave n has 6 + n robots, up to 60 */
export function waveSize(n) {
  return Math.min(WAVES.base + n, WAVES.most);
}

/** The robot types wave n draws from, each listed as often as its weight */
function unlocked(n) {
  const pool = [];
  ROBOTS.forEach((info, type) => {
    if (info.weight > 0 && info.from >= 1 && info.from <= n) {
      for (let i = 0; i < info.weight; i++) {
        pool.push(type);
      }
    }
  });
  return pool;
}

/**
 * Wave n's entries in the order they come in, drawn with the run's dice. A Skitter draw is a bunch whose members come
 * close together and count toward the wave's size; every 10th wave the Colossus comes last
 */
export function buildWave(run, n) {
  const pool = unlocked(n);
  const size = waveSize(n);
  const entries = [];
  let count = 0;
  while (count < size) {
    const type = pool[run.dice.roll(pool.length)];
    const bunch = ROBOTS[type].bunch || 1;
    for (let i = 1; i <= bunch; i++) {
      entries.push({ type, gap: i < bunch ? WAVES.bunchGap : WAVES.entryGap });
    }
    count += bunch;
  }
  if (n % WAVES.bossEvery === 0) {
    entries.push({ type: COLOSSUS, gap: WAVES.entryGap });
  }
  return entries;
}

/** The next wave starts: its entries queue up, and the first comes in on this same step */
export function startWave(run) {
  run.wave += 1;
  run.queue = buildWave(run, run.wave);
  run.entryIn = 0;
  run.countdown = -1;
  emit(run, "wave", { n: run.wave });
}

/** One step of the wave clock: the countdown to the next wave, then the next entry if one is due */
export function runWaves(run) {
  if (run.countdown > 0) {
    run.countdown -= 1;
    if (run.countdown === 0) {
      startWave(run);
    }
  }
  if (run.queue.length === 0) {
    return;
  }
  if (run.entryIn > 0) {
    run.entryIn -= 1;
  }
  if (run.entryIn > 0) {
    return;
  }
  const entry = run.queue.shift();
  spawn(run, entry.type, run.wave, 0);
  run.entryIn = entry.gap;
  if (run.queue.length === 0) {
    run.countdown = WAVES.countdown;
  }
}
