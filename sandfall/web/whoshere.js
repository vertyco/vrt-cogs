// Who's here: the status line everyone in the Activity window sees beside this player's name. It says what the player
// is painting with in their own world (shared or not), whose world they are visiting, or that they are browsing the
// server's gallery. Sandfall has no round to lose and
// saves itself, so it never marks the player busy.
import { ELEMENTS } from "./sim/index.js";

const CHECK_MS = 500;
// What the player is doing with each tool that doesn't build with an element
const DOING = {
  eraser: "Erasing",
  heat: "Heating things up",
  cool: "Cooling things down",
  shove: "Shoving things around",
  hand: "Using the hand",
  lightning: "Calling lightning",
};

/** Starts telling the hub what the player is doing. Only changes are sent */
export function watchPeople(state) {
  const { hub, shared, painter } = state;
  if (!hub.status || hub.offline) {
    return;
  }
  let told = "";

  function activity() {
    if (shared.lost) {
      return ["Not connected", null];
    }
    if (state.gallery?.open) {
      return ["Browsing the gallery", { world: shared.inWorld }];
    }
    // Visiting a world someone else runs
    if (shared.inWorld !== null && !shared.ownsWorld && !shared.isOwner) {
      return [`In ${shared.ownerName}'s world`, { world: shared.inWorld }];
    }
    const what = DOING[painter.tool] ?? `Building · ${ELEMENTS[painter.element]?.name ?? "Sand"}`;
    return [what, { world: shared.inWorld }];
  }

  function report() {
    const [text, data] = activity();
    const look = JSON.stringify([text, data]);
    if (look !== told) {
      told = look;
      hub.status(text, data);
    }
  }

  shared.onChange(report);
  setInterval(report, CHECK_MS);
  report();
}
