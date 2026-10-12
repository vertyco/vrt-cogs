import { backToMenu, connect } from "activityhub";

const status = document.getElementById("status");
document.getElementById("back").addEventListener("click", backToMenu);

let hub;
try {
  hub = await connect();
} catch (e) {
  // Discord didn't accept the login. The Back button still works
  status.textContent = e.message;
  throw e;
}
status.textContent = hub.offline ? "Open this from Discord to earn credits." : `Hi ${hub.player.displayName}!`;

document.getElementById("click").addEventListener("click", async () => {
  try {
    const result = await hub.api("click");
    status.textContent = `Clicks today: ${result.clicks}. Balance: ${result.balance}`;
  } catch (e) {
    status.textContent = e.message;
  }
});
