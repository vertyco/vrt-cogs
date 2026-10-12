// Keeps the player's private world on the bot. Opening the game brings the saved world back (a first-time player gets
// the starter scene). Changes are saved 30 seconds after the last one, and when the page is hidden or going away.
import { note } from "./notes.js";
import { isSnowStroke } from "./runner.js";
import { decodeWorld, encodeWorld, starterWorld } from "./sim/index.js";

const SAVE_DELAY_MS = 30000;
// The browser refuses a keepalive request over 64 KB, so a bigger world goes as a normal request
const KEEPALIVE_MAX = 60000;
const CANT_LOAD = "Couldn't load your world, so here's a fresh one.";
const CANT_SAVE = "Couldn't save your world. It's still here; try again in a moment.";

function freshWorld() {
  return starterWorld(Math.floor(Math.random() * 0x100000000));
}

async function loadWorld(hub) {
  let text;
  try {
    ({ snap: text } = await hub.api("load_world", {}));
  } catch (e) {
    console.warn("Sandfall: couldn't load the saved world", e);
    note(CANT_LOAD);
    return freshWorld();
  }
  if (text === null) {
    return freshWorld();
  }
  try {
    return await decodeWorld(text);
  } catch (e) {
    console.warn("Sandfall: the saved world is broken", e);
    note(CANT_LOAD);
    return freshWorld();
  }
}

/**
 * Loads the player's world into the page and starts saving it. Resolves once the world is in place, with
 * `{ saveNow(options), changed() }`: changed() says the world changed (strokes, undo), saveNow() saves right away.
 */
export async function startSaving(state) {
  const { hub } = state;
  // The browser preview has no bot to keep a world, so it plays the starter scene and saves nothing
  if (hub.offline) {
    state.setWorld(freshWorld());
    return { saveNow: () => Promise.resolve(false), changed() {} };
  }
  state.setWorld(await loadWorld(hub));

  let dirty = false;
  let timer = null;
  let queue = Promise.resolve(true);

  // The player's own world: the one on screen, or the private one waiting while they visit a shared world
  const ownWorld = () => state.shared?.ownWorld() ?? state.world;
  const owns = () => state.shared?.ownsWorld ?? true;

  // Saves one after another, so an older world never lands after a newer one
  async function write(keepalive, world) {
    // Cleared before the packing starts, so a change made while it runs still gets its own save
    dirty = false;
    let text;
    try {
      text = await encodeWorld(world ?? ownWorld());
    } catch (e) {
      console.warn("Sandfall: couldn't pack the world to save it", e);
      dirty = true;
      note(CANT_SAVE);
      return false;
    }
    try {
      await hub.api("save_world", { snap: text }, { keepalive: keepalive && text.length <= KEEPALIVE_MAX });
      return true;
    } catch (e) {
      console.warn("Sandfall: couldn't save the world", e);
      dirty = true;
      note(CANT_SAVE);
      return false;
    }
  }

  /** Saves the player's own world now. `world` pins which world, for a save made just before it leaves the screen */
  function saveNow({ keepalive = false, world = null } = {}) {
    clearTimeout(timer);
    timer = null;
    queue = queue.then(() => write(keepalive, world));
    return queue;
  }

  function changed() {
    // Someone else's shared world belongs to its owner's page and is never saved as this player's own
    if (!owns()) {
      return;
    }
    dirty = true;
    clearTimeout(timer);
    timer = setTimeout(() => saveNow(), SAVE_DELAY_MS);
  }

  // The Christmas snow rides in every batch, so it doesn't count as a change or the save timer would never run out
  state.runner.onBatch((batch) => {
    if (batch[2].some(([, stroke]) => !isSnowStroke(stroke))) {
      changed();
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && dirty) {
      saveNow();
    }
  });
  window.addEventListener("pagehide", () => {
    if (dirty) {
      saveNow({ keepalive: true });
    }
  });
  return { saveNow, changed };
}
