// The payout settings dialog, for the people who may change them: server admins, or only the bot owner when the
// bank is global. The gear on the title shows only for them, and the bot checks again on every save.
import { click, plainError } from "./panels.js";

// The dialog's last numbers from the bot, or null for players who can't change them
let state = null;

function $(id) {
  return document.getElementById(id);
}

function plural(count, word) {
  return `${count.toLocaleString()} ${count === 1 ? word : `${word}s`}`;
}

export function bindSettings(page) {
  click("open-payouts", () => {
    $("payouts-status").textContent = "";
    $("payouts").showModal();
    loadPayouts(page);
  });
  click("close-payouts", () => $("payouts").close());
  click("save-payouts", () => savePayouts(page));
  click("reset-payouts", () => {
    fillPayouts(state.defaults);
    $("payouts-status").textContent = "Reset. Save to keep it.";
  });
  for (const id of ["payouts-cap", "payouts-plays"]) {
    $(id).addEventListener("input", showDailyMost);
  }
}

export async function loadPayouts(page) {
  if (!page.hub || page.hub.offline) {
    return;
  }
  try {
    showPayouts(await page.hub.api("payouts"));
  } catch (e) {
    console.warn("Starhold: couldn't load the payout settings", e);
  }
}

// Players who can't change the settings get none, and never see the gear
function showPayouts(answer) {
  state = answer.settings ? answer : null;
  $("open-payouts").hidden = !state;
  if (!state) {
    return;
  }
  $("payouts-global").hidden = !answer.global;
  const currency = answer.currency;
  $("payouts-rate-label").textContent = `${currency[0].toUpperCase()}${currency.slice(1)} per point`;
  fillPayouts(answer.settings);
  const today = answer.today;
  const players = plural(today.players, "player");
  $("payouts-today").textContent = `Today: ${today.paid.toLocaleString()} ${currency} paid to ${players}.`;
}

function fillPayouts(settings) {
  $("payouts-on").checked = settings.on;
  for (const name of ["rate", "cap", "plays"]) {
    $(`payouts-${name}`).value = String(settings[name]);
  }
  showDailyMost();
}

function showDailyMost() {
  const cap = Number($("payouts-cap").value);
  const plays = Number($("payouts-plays").value);
  const currency = state?.currency || "credits";
  $("payouts-day").textContent =
    cap > 0 && plays > 0 ? `A player can earn at most ${(cap * plays).toLocaleString()} ${currency} a day.` : "";
}

// An empty box goes as null, which the bot refuses with a message saying what it needs
function numberIn(id) {
  const value = $(id).value;
  return value === "" ? null : Number(value);
}

async function savePayouts(page) {
  const settings = {
    on: $("payouts-on").checked,
    rate: numberIn("payouts-rate"),
    cap: numberIn("payouts-cap"),
    plays: numberIn("payouts-plays"),
  };
  $("payouts-status").textContent = "Saving...";
  try {
    showPayouts(await page.hub.api("save_payouts", { settings }));
    $("payouts-status").textContent = "Saved.";
  } catch (e) {
    console.warn("Starhold: couldn't save the payout settings", e);
    $("payouts-status").textContent = plainError(e);
  }
}
