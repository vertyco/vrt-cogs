// The state every simulation module shares: pig records, timers and events.
// Every other module in this folder imports this one and none imports it back, so any module loads on its own.
// common/sim/base.py mirrors this file function for function.
// The state is plain data: timers are records [tick, seq, kind, args] looked up by kind, never closures.

// Where a pig is. "exit" is the line at the belt's exit where pigs wait for a free slot
export const PLACES = ["queue", "slot", "belt", "rescue", "gone", "held", "exit"];

// The fixed order inside one tick (taps are applied before the tick starts, in phase 1)
export const PHASE_TAPS = 1;
export const PHASE_BELT = 2;
export const PHASE_SHOOT = 3;
export const PHASE_FEATURES = 4;
export const PHASE_SHOTS = 5;
export const PHASE_CHECKS = 6;
export const PHASE_RELEASE = 7;

// Every feature module, in feature-number order. The core calls their hooks in this order and skips missing ones
export const MODULES = [];

export const FNV_START = 2166136261;
const FNV_PRIME = 16777619;

// timer kind -> [phase it fires in, handler(state, args)]
export const TIMER_KINDS = new Map();

// A pig record. place is one of PLACES. nextFire: beat its next shot is due (ShootersOffenseController's next-fire
// table; 0 for none). reserved: [target id, cell] with a shot of this pig in flight. freeAt: the first tick it can be
// tapped after hopping into a slot (Shooter.IsMoving until then)
export function makePig(id, color, ammo, place) {
  return { id, color, ammo, place, tags: [], nextFire: 0, reserved: [], freeAt: 0 };
}

export function registerTimer(kind, phase, handler) {
  TIMER_KINDS.set(kind, [phase, handler]);
}

// Run the kind's handler with args in its phase of tick state.tick + delayTicks
export function schedule(state, delayTicks, kind, args) {
  state.timers.push([state.tick + delayTicks, state.seq, kind, args]);
  state.seq += 1;
}

// Drop every pending timer of this kind
export function cancel(state, kind) {
  state.timers = state.timers.filter((timer) => timer[2] !== kind);
}

// Every due timer of this phase, by (tick, seq), including ones a handler schedules for now
export function fireTimers(state, phase) {
  for (;;) {
    let best = -1;
    state.timers.forEach((timer, index) => {
      if (timer[0] > state.tick || TIMER_KINDS.get(timer[2])[0] !== phase) {
        return;
      }
      const chosen = state.timers[best];
      if (best < 0 || timer[0] < chosen[0] || (timer[0] === chosen[0] && timer[1] < chosen[1])) {
        best = index;
      }
    });
    if (best < 0) {
      return;
    }
    const [timer] = state.timers.splice(best, 1);
    TIMER_KINDS.get(timer[2])[1](state, timer[3]);
  }
}

// Tell the features, and record it for the page
export function emit(state, name, data) {
  state.events.push({ k: name, ...data });
  for (const module of MODULES) {
    if (module.onEvent) {
      module.onEvent(state, name, data);
    }
  }
}

export function callHooks(state, name) {
  for (const module of MODULES) {
    if (module[name]) {
      module[name](state);
    }
  }
}

// The level is lost at this tick. The first fail stands
export function fail(state, kind, name) {
  if (state.over === null) {
    state.over = { result: "failed", tick: state.tick, kind, name };
    emit(state, "failed", { kind, name });
  }
}

// Pigs still in play: in a queue, a slot, on the belt, in the rescue queue, waiting at the exit or held inside a
// feature (ShooterProvider's list, which the win check and the auto-finisher count, keeps nested shooters)
export function livePigCount(state) {
  return Object.values(state.pigs).filter((pig) => pig.place !== "gone").length;
}

// One step of 32-bit FNV-1a over a whole number
export function mix(h, value) {
  return Math.imul(h ^ value, FNV_PRIME) >>> 0;
}

export function mixText(h, text) {
  h = mix(h, text.length);
  for (let i = 0; i < text.length; i++) {
    h = mix(h, text.charCodeAt(i));
  }
  return h;
}
