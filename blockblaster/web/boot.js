// Holds phones upright while the game is open, then starts the game's page
import { connect } from "activityhub";

// Discord's orientation lock values (OrientationLockStateTypeObject in its toolkit)
const UNLOCKED = 1;
const PORTRAIT = 2;

// Discord holds the Activity upright while the page is open, and lets it turn freely again when the page closes, so
// the lock never carries into the menu or another game
async function lockPortrait() {
  const hub = await connect();
  if (hub.platform !== "mobile" || !hub.discord) {
    return;
  }
  const lock = (state) =>
    hub.discord.commands.setOrientationLockState({ lock_state: state, picture_in_picture_lock_state: state });
  window.addEventListener("pagehide", () => {
    lock(UNLOCKED).catch((e) => console.warn("Block Blaster: couldn't unlock the screen's turning", e));
  });
  await lock(PORTRAIT);
}
lockPortrait().catch((e) => console.warn("Block Blaster: couldn't hold the phone upright", e));

await import("./game.js");
