// The screens and dialogs around the map: the title, How to play, High Scores, the pause menu, the game over card
// with its cash-in box, and the Play again warning. main.js runs the game and passes its actions in; this file only
// shows the page's state.
const ORPHAN = "This run can't be cashed in or saved, because the connection to the bot was lost.";
// The bot's own sentences for a cash-in that can't pay, so the card says what a press would have answered
const NONE_LEFT = "You've used every cash-in for today. They come back at midnight UTC.";
const NOTHING_EARNED = "That score isn't worth anything yet. Score more to earn some.";
export const NOT_CONNECTED = "Not connected to the bot yet. Try again in a moment.";
const IN_SERVERS = "High scores and cash-ins work in servers.";
const SCORES_OFFLINE = "Open Starhold in Discord to see the high scores.";
// The bot's answer when the run it was asked to cash in isn't one it can pay (it was replaced, or never ended)
const NOTHING_TO_CASH = "Nothing to cash in. Finish a run first.";
// Sent when a payment broke partway, with no fresh card: whether it paid is unknown, so it is never offered again
const CASH_FAILED = "Something went wrong while cashing in this run, so it can't be cashed in again.";
const CHECKING = "Checking...";
// In place of a request's error that has no sentence for a player, like the hub's "Request failed (500)"
const UNREACHABLE = "Starhold couldn't reach the bot. Try again in a moment.";
const BARE_STATUS = /^Request failed \(\d+\)$/;
const TOAST_MS = 3000;
// A long sentence stays up long enough to read
const TOAST_MS_PER_LETTER = 60;
let toastTimer = null;
// A cash-in has been sent and the bot hasn't answered yet
let cashing = false;
// The page's Sound, for the Sound button
let sound = null;
// Resolves the Play again warning while it is open
let confirmAnswer = null;

function $(id) {
  return document.getElementById(id);
}

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function plural(count, word) {
  return `${count.toLocaleString()} ${count === 1 ? word : `${word}s`}`;
}

// Every page button goes through here
export function click(id, handler) {
  $(id).addEventListener("click", (event) => {
    event.currentTarget.blur();
    sound?.play("tap", { steady: true });
    handler(event);
  });
}

// Whether a cash-in is still waiting on the bot
export function isCashing() {
  return cashing;
}

export function bindPanels(page, actions) {
  sound = actions.sound;
  click("play-button", () => actions.play());
  click("again", () => actions.play());
  click("how-button", () => actions.show("help"));
  click("help-close", () => actions.back());
  click("back", () => actions.back());
  click("resume", () => actions.resume());
  click("end-run", () => actions.endRun());
  click("scores-button", () => openScores(page));
  click("over-scores", () => openScores(page));
  click("close-scores", () => $("scores").close());
  click("cashin-button", () => cashIn(actions));
  click("sound-button", () => {
    sound.cycle();
    showToggles();
  });
  click("message-close", () => {
    $("message").hidden = true;
  });
  click("confirm-yes", () => answer(true));
  click("confirm-no", () => answer(false));
  // Escape closes the dialog too, which counts as no
  $("confirm").addEventListener("close", () => answer(false));
  showToggles();
}

function showToggles() {
  $("sound-button").textContent = sound.nextAction;
}

// A failed request as a sentence a player can read: the bot's own words, or a plain one when the bot broke or never
// answered
export function plainError(e) {
  const message = e?.message || "";
  return e?.status >= 500 || !message || BARE_STATUS.test(message) ? UNREACHABLE : message;
}

export function showMessage(text) {
  $("message-text").textContent = text;
  $("message").hidden = false;
}

export function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(
    () => {
      node.hidden = true;
    },
    Math.max(TOAST_MS, text.length * TOAST_MS_PER_LETTER),
  );
}

// ---------- Game over ----------

export function renderResult(page) {
  const final = page.final || { score: 0, wave: 0 };
  const result = page.result;
  // Once the bot has replayed the run, its score is the one that counts
  const score = result?.checked ? result.score : final.score;
  $("final-score").textContent = score.toLocaleString();
  $("final-wave").textContent = final.wave > 0 ? `Reached wave ${final.wave}` : "Ended before wave 1";
  $("standing").replaceChildren();
  $("cashin").hidden = true;
  cashing = false;
  if (page.orphan) {
    $("standing").textContent = ORPHAN;
  } else if (!result) {
    return;
  } else if (result.dm) {
    $("standing").textContent = IN_SERVERS;
  } else if (result.refused) {
    $("standing").textContent = result.refused;
  } else {
    showStanding(result);
    showOffer(result.offer);
  }
}

function showStanding(result) {
  if (result.newBest && result.rank) {
    $("standing").append(make("span", "new", "New best! "), `#${result.rank} on this server`);
  } else if (result.best) {
    $("standing").textContent = `Your best: ${result.best.toLocaleString()} · #${result.rank} on this server`;
  }
}

// What the run is worth where this server pays out. Starting another run gives it up, so players choose which runs
// to spend their few cash-ins a day on
function showOffer(offer) {
  const button = $("cashin-button");
  $("cashin").hidden = !offer;
  if (!offer) {
    return;
  }
  button.disabled = false;
  button.hidden = offer.left <= 0 || offer.worth <= 0;
  if (offer.left <= 0) {
    $("cashin-text").textContent = NONE_LEFT;
  } else if (offer.worth <= 0) {
    $("cashin-text").textContent = NOTHING_EARNED;
  } else {
    const worth = `${offer.worth.toLocaleString()} ${offer.currency}`;
    $("cashin-text").textContent = `This run is worth ${worth} · ${offer.left} of ${offer.plays} cash-ins left today`;
    button.textContent = `Cash in ${offer.worth.toLocaleString()}`;
  }
}

// The bot checks the run by replaying it before it pays, which can take a moment
function cashIn(actions) {
  if (actions.cashIn()) {
    const button = $("cashin-button");
    cashing = true;
    button.disabled = true;
    button.textContent = CHECKING;
  } else {
    showMessage(NOT_CONNECTED);
  }
}

export function onCashed(page, cashed) {
  sound?.play("cashin", { steady: true });
  const paid = `${cashed.paid.toLocaleString()} ${cashed.currency}`;
  // The card of the run on screen only: a late answer for an earlier run still toasts, but never rewrites this card
  const shown = page.claim ? page.claim[1] : page.result?.score;
  if (!page.result || cashed.claim !== shown) {
    toast(`+${paid}`);
    return;
  }
  Object.assign(page.result, { offer: null, score: cashed.score, checked: true, best: cashed.best, rank: cashed.rank });
  renderResult(page);
  $("cashin").hidden = false;
  $("cashin-button").hidden = true;
  // An honest page always matches the bot's replay; a changed one is paid for what its moves really scored
  $("cashin-text").textContent =
    cashed.score !== cashed.claim
      ? `Paid ${paid} for a checked score of ${cashed.score.toLocaleString()}`
      : `Paid ${paid} · ${plural(cashed.left, "cash-in")} left today`;
  toast(`+${paid}`);
}

// A short message from the bot. While a cash-in waits on the bot, it is why the cash-in couldn't pay this time
// (payouts off, a full balance), so it goes in the box and the button comes back. Final answers arrive as a fresh
// result first, whose card has no box, so their notice is a toast
export function notice(page, text) {
  const waiting = page.screen === "over" && !$("cashin").hidden && cashing;
  cashing = false;
  if (!waiting) {
    toast(text);
  } else if (text === NOTHING_TO_CASH || text === CASH_FAILED) {
    $("cashin").hidden = true;
    toast(text);
  } else {
    showOffer(page.result?.offer);
    $("cashin-text").textContent = text;
  }
}

// ---------- The Play again warning ----------

export function askConfirm(text) {
  $("confirm-text").textContent = text;
  return new Promise((resolve) => {
    confirmAnswer = resolve;
    $("confirm").showModal();
  });
}

function answer(yes) {
  const resolve = confirmAnswer;
  confirmAnswer = null;
  if ($("confirm").open) {
    $("confirm").close();
  }
  resolve?.(yes);
}

// ---------- High scores ----------

export async function openScores(page) {
  $("leaders").replaceChildren();
  $("you").textContent = "Loading...";
  if (!$("scores").open) {
    $("scores").showModal();
  }
  if (!page.hub || page.hub.offline) {
    $("you").textContent = SCORES_OFFLINE;
    return;
  }
  try {
    renderScores(page, await page.hub.api("scores"));
  } catch (e) {
    console.warn("Starhold: couldn't load the high scores", e);
    $("you").textContent = plainError(e);
  }
}

function renderScores(page, table) {
  $("leaders").replaceChildren(...table.top.map((row) => scoreRow(page, row)));
  if (table.dm) {
    $("you").textContent = "High scores are kept per server.";
  } else if (!table.top.length) {
    $("you").textContent = "No runs yet. Be the first!";
  } else if (table.you) {
    $("you").textContent = `You: #${table.you.rank} with ${table.you.best.toLocaleString()}`;
  } else {
    $("you").textContent = "Finish a run to get on the table.";
  }
}

function scoreRow(page, row) {
  const item = document.createElement("li");
  item.classList.toggle("mine", row.id === page.hub.player?.id);
  // Names come from Discord, so they only ever go in as text
  const name = make("span", "name", row.name);
  item.append(make("span", "place", `#${row.rank}`), name, make("span", "best", row.best.toLocaleString()));
  return item;
}
