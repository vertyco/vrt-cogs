// Replaying a run from its seed and moves: the bot's check, and the page picking a closed run back up.
import { apply, createRun, summary, tick } from "./run.js";

/**
 * The run as it stood at step `end`, or at game over if that came first. Each move is applied at its own step, before
 * that step's tick, the way the page applied it. Moves at the final step are applied too, so a run picked back up
 * there matches the page that sent them. A move whose step has already passed is skipped.
 */
export function replay(seed, moves, end) {
  const run = createRun(seed);
  let next = 0;
  while (!run.over) {
    while (next < moves.length && moves[next][0] <= run.step) {
      if (moves[next][0] === run.step) {
        apply(run, moves[next]);
      }
      next += 1;
    }
    if (run.step >= end) {
      break;
    }
    tick(run);
  }
  return run;
}

/** The bot's check: what a run's moves really scored */
export function check(input) {
  return summary(replay(input.seed, input.moves, input.end));
}
