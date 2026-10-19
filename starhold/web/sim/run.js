// One run of Starhold: the state the page draws, the moves that change it, and one step of time. The page and the
// bot's check drive a run only through createRun, apply and tick, so they always agree.
import { Dice } from "./dice.js";
import { div } from "./num.js";
import { BUILD, CALL, FORM, MAP, PARK, SELL, START, STASIS, STEPS, STRIKE, UPGRADE, WAVES } from "./rules.js";
import { emit } from "./events.js";
import { moveRobots, removeGone } from "./robots.js";
import { runWaves, startWave } from "./waves.js";
import { build, finalForm, fireTowers, landShells, sell, upgrade } from "./towers.js";
import { parkDrones, runDrones, wallLines } from "./drones.js";
import { stasis, strike } from "./powers.js";

export function createRun(seed) {
  return {
    seed,
    dice: new Dice(seed),
    step: 0,
    money: START.money,
    lives: START.lives,
    score: 0,
    wave: 0,
    over: false,
    countdown: START.countdown,
    queue: [],
    entryIn: 0,
    robots: [],
    towers: MAP.spots.map(() => null),
    shells: [],
    strikeReady: 0,
    stasisReady: 0,
    nextId: 1,
    events: null,
  };
}

/** Calling the next wave early: a bonus for each whole second left on the countdown, and the wave starts now */
function callWave(run) {
  if (run.countdown <= 0) {
    return false;
  }
  const bonus = WAVES.callBonus * div(run.countdown, STEPS);
  run.money += bonus;
  emit(run, "call", { bonus });
  startWave(run);
  return true;
}

// What each move kind does, and how many numbers a move of that kind has ([step, kind, ...details])
const MOVES = [];
const SIZES = [];
MOVES[BUILD] = (run, move) => build(run, move[2], move[3]);
SIZES[BUILD] = 4;
MOVES[UPGRADE] = (run, move) => upgrade(run, move[2]);
SIZES[UPGRADE] = 3;
MOVES[FORM] = (run, move) => finalForm(run, move[2], move[3]);
SIZES[FORM] = 4;
MOVES[SELL] = (run, move) => sell(run, move[2]);
SIZES[SELL] = 3;
// Drone parking comes in whole map units along the road
MOVES[PARK] = (run, move) => parkDrones(run, move[2], move[3] * 100);
SIZES[PARK] = 4;
MOVES[CALL] = (run) => callWave(run);
SIZES[CALL] = 2;
MOVES[STRIKE] = (run, move) => strike(run, move[2], move[3]);
SIZES[STRIKE] = 4;
MOVES[STASIS] = (run, move) => stasis(run, move[2], move[3]);
SIZES[STASIS] = 4;

/** Apply one move at the run's current step. A move that can't happen (too dear, bad spot, not ready) answers false */
export function apply(run, move) {
  if (run.over || !Array.isArray(move) || !move.every(Number.isInteger)) {
    return false;
  }
  const kind = move[1];
  if (MOVES[kind] === undefined || move.length !== SIZES[kind]) {
    return false;
  }
  return MOVES[kind](run, move);
}

/** One step of time */
export function tick(run) {
  if (run.over) {
    return;
  }
  runWaves(run);
  moveRobots(run, wallLines(run));
  runDrones(run);
  fireTowers(run);
  landShells(run);
  removeGone(run);
  run.step += 1;
}

export function summary(run) {
  return { score: run.score, wave: run.wave, lives: run.lives, step: run.step, over: run.over };
}
