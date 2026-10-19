// The feature looks, called in feature-number order. A look module exports `NUMBER` and `create(scene, picture)`
// (`picture` is picture.js's handle, for looks that move cubes), which loads what it draws with and returns an object
// with any of: `build(state)` (a new level), `clear()` (the level is left), `onEvents(events, state)`,
// `frame(alpha, state)` (every drawn frame), `begin(state)` and `end()` (around the pigs' placing each frame) and
// `shape(id, pig, pose)` (dress one pig, between the two). Looks change only what is drawn.
import * as biscuit from "./biscuit.js";
import * as connected from "./connected.js";
import * as eggBox from "./egg_box.js";
import * as frozenPig from "./frozen_pig.js";
import * as gate from "./gate.js";
import * as hardPixels from "./hard_pixels.js";
import * as hungryDoor from "./hungry_door.js";
import * as iceBlock from "./ice_block.js";
import * as locksKeys from "./locks_keys.js";
import * as pigPipe from "./pig_pipe.js";
import * as pixelPipe from "./pixel_pipe.js";
import * as rocket from "./rocket.js";
import * as snake from "./snake.js";
import * as surprisePig from "./surprise_pig.js";
import * as surprisePixel from "./surprise_pixel.js";
import * as wall from "./wall.js";
import * as woodHammer from "./wood_hammer.js";

const MODULES = [
  surprisePig,
  connected,
  hardPixels,
  locksKeys,
  gate,
  pixelPipe,
  surprisePixel,
  snake,
  wall,
  eggBox,
  pigPipe,
  iceBlock,
  woodHammer,
  frozenPig,
  hungryDoor,
  biscuit,
  rocket,
];

class Looks {
  constructor(looks) {
    this.looks = looks;
  }

  call(name, ...args) {
    for (const look of this.looks) {
      if (look[name]) {
        look[name](...args);
      }
    }
  }

  build(state) {
    this.call("build", state);
  }

  clear() {
    this.call("clear");
  }

  onEvents(events, state) {
    this.call("onEvents", events, state);
  }

  frame(alpha, state) {
    this.call("frame", alpha, state);
  }

  begin(state) {
    this.call("begin", state);
  }

  shape(id, pig, pose) {
    this.call("shape", id, pig, pose);
  }

  end() {
    this.call("end");
  }
}

// Make every look for a scene, loading them together
export async function createLooks(scene, picture) {
  return new Looks(await Promise.all(MODULES.map((module) => module.create(scene, picture))));
}
