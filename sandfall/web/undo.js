// Undo for a private world: a copy of the world (its snapshot bytes) is kept from just before each stroke, the last
// LIMIT of them, and Undo puts the newest back. A shared world has none, since one player's undo would also wipe out
// what everyone else did since.
import { onKey } from "./keys.js";
import { packWorld, unpackWorld } from "./sim/index.js";
import { addBarButton } from "./ui/bar.js";
import { icon } from "./ui/icons.js";

const LIMIT = 20;

/** Builds state.undo = { push(), undo(), clear(), available, button }. setWorld(world) swaps the page's world */
export function buildUndo(state, setWorld) {
  const copies = [];
  const button = addBarButton({ id: "undo", label: "Undo", icon: icon("undo"), order: 20, onClick: () => undo() });

  function refresh() {
    button.disabled = copies.length === 0;
  }

  function push() {
    if (state.shared?.inWorld) {
      return;
    }
    copies.push(packWorld(state.world));
    if (copies.length > LIMIT) {
      copies.shift();
    }
    refresh();
  }

  function undo() {
    if (state.shared?.inWorld || copies.length === 0) {
      return;
    }
    setWorld(unpackWorld(copies.pop()));
    refresh();
  }

  function clear() {
    copies.length = 0;
    refresh();
  }

  onKey("z", () => undo());
  onKey("Z", () => undo());
  refresh();
  return {
    push,
    undo,
    clear,
    button,
    get available() {
      return copies.length > 0;
    },
  };
}
