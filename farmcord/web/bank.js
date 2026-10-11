// The Market's bank counter: FarmCoins become this server's credits, Neopets style. The server sets what a FarmCoin
// pays, the most one cash-in pays and the cash-ins a day; the bot works out every offer and pays every conversion.
// Players who may change those settings get a gear here, opening the payout settings dialog copied from Marble Munch's
// page.
import { HubError } from "activityhub";

// How long the amount box waits for typing to stop before asking the bot what that many FarmCoins pay
const OFFER_WAIT_MS = 300;
// The bot's own words for refusals the offer already shows coming
const NONE_LEFT = "You've used every cash-in for today. They come back at midnight UTC.";
const NO_COINS = "You have no FarmCoins to convert.";
const PICK_COINS = "Pick how many FarmCoins to convert.";
const TOO_FEW = "That many FarmCoins aren't worth a credit yet. Convert more.";
// The bot takes amounts up to this
const MOST_COINS = 10 ** 12;
const GEAR = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>`;

const bank = {
  // The counter's parts while it is open
  parts: null,
  // Counts the offers asked for, so only the latest one's answer shows
  asked: 0,
  timer: null,
  // The payout settings as the bot last sent them: { settings, defaults, global, currency }
  payouts: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- The counter ----------

export function openBank(ctx) {
  ctx.sound.play("tap");
  const body = ctx.hud.openPanel("Bank");
  bank.parts = build(ctx);
  body.append(bank.parts.root);
  // The box starts at the most one cash-in takes, or all the player's FarmCoins if fewer: the bot cuts it to that
  return askOffer(ctx, ctx.state().player.coins, true);
}

function build(ctx) {
  const { make } = ctx.hud;
  const parts = { root: make("div", "bank") };
  const top = make("div", "bank-top");
  parts.intro = make("p", "bank-intro", "Turn your FarmCoins into this server's credits.");
  top.append(parts.intro);
  if (ctx.info().canSetPayouts) {
    top.append(gearButton(ctx));
  }
  parts.why = make("p", "bank-why");
  parts.why.id = "bank-why";
  parts.why.hidden = true;
  parts.form = make("div", "bank-form");
  parts.form.hidden = true;
  parts.amount = make("input");
  Object.assign(parts.amount, { id: "bank-amount", type: "number", inputMode: "numeric", min: "0", step: "1" });
  const label = make("label", "bank-amount");
  label.append(make("span", "", "FarmCoins to convert"), parts.amount);
  parts.offer = make("p", "bank-offer");
  parts.offer.id = "bank-offer";
  parts.most = make("p", "dim bank-most");
  parts.left = make("p", "bank-left");
  parts.left.id = "bank-left";
  parts.convert = make("button", "button primary", "Convert");
  Object.assign(parts.convert, { id: "bank-convert", type: "button" });
  parts.convertWhy = make("p", "shop-why");
  parts.convertWhy.id = "bank-convert-why";
  parts.form.append(label, parts.offer, parts.most, parts.left, parts.convert, parts.convertWhy);
  parts.root.append(top, parts.why, parts.form);
  parts.amount.addEventListener("input", ctx.safe("the amount box", () => offerSoon(ctx)));
  parts.convert.addEventListener("click", ctx.safe("the Convert button", () => convert(ctx, parts.convert)));
  return parts;
}

// The whole number of FarmCoins in the box, as the bot takes it
function amount() {
  return Math.min(MOST_COINS, Math.max(0, Math.floor(Number(bank.parts.amount.value)) || 0));
}

function offerSoon(ctx) {
  clearTimeout(bank.timer);
  bank.timer = setTimeout(ctx.safe("asking what FarmCoins pay", () => askOffer(ctx, amount(), false)), OFFER_WAIT_MS);
}

// Asks the bot what these FarmCoins pay here. `reset` puts the amount it would really take in the box
async function askOffer(ctx, coins, reset) {
  bank.asked += 1;
  const ask = bank.asked;
  const reply = await ctx.act("offer", { coins }, { key: null, sound: null });
  if (reply && ask === bank.asked && bank.parts?.root.isConnected) {
    showOffer(ctx, reply, reset);
  }
}

// What the bot offers, or why conversions don't work here (a DM, or payouts off)
function showOffer(ctx, reply, reset) {
  const parts = bank.parts;
  parts.why.textContent = reply.reason || "";
  parts.why.hidden = !reply.reason;
  parts.form.hidden = Boolean(reply.reason);
  if (reply.reason) {
    return;
  }
  const { number } = ctx.hud;
  const { offer } = reply;
  if (reset) {
    parts.amount.value = String(offer.coins);
  }
  parts.intro.textContent = `Turn your FarmCoins into this server's ${offer.currency}.`;
  parts.offer.textContent = `${number(offer.coins)} FarmCoins become ${number(offer.worth)} ${offer.currency}`;
  parts.most.textContent = `One cash-in takes up to ${number(offer.most)} FarmCoins.`;
  parts.left.textContent = `${offer.left} of ${offer.plays} cash-ins left today`;
  let problem = "";
  if (offer.left < 1) {
    problem = NONE_LEFT;
  } else if (ctx.state().player.coins < 1) {
    problem = NO_COINS;
  } else if (offer.coins < 1) {
    problem = PICK_COINS;
  } else if (offer.worth < 1) {
    problem = TOO_FEW;
  }
  parts.convert.disabled = Boolean(problem);
  parts.convertWhy.textContent = problem;
  parts.convertWhy.hidden = !problem;
}

// Convert stays off from the press until the fresh offer after it arrives and sets it again: until then the box and
// the cash-ins left show the old numbers, and a quick second press would cash in again
async function convert(ctx, button) {
  clearTimeout(bank.timer);
  button.disabled = true;
  const reply = await ctx.act("convert", { coins: amount() });
  if (reply) {
    const { number } = ctx.hud;
    const { paid, coins, currency, balance } = reply.result;
    ctx.hud.toast(`+${number(paid)} ${currency} for ${number(coins)} FarmCoins. You have ${number(balance)} now.`);
  }
  // Fresh numbers either way: cash-ins left, and the box from what the farm holds now
  return askOffer(ctx, ctx.state().player.coins, true);
}

// ---------- Payout settings (owner, or server admins when the bank isn't global) ----------

function gearButton(ctx) {
  const button = ctx.hud.make("button", "round-button small bank-gear");
  Object.assign(button, { id: "bank-gear", type: "button", title: "Payout settings", innerHTML: GEAR });
  button.setAttribute("aria-label", "Payout settings");
  button.addEventListener("click", ctx.safe("the payout settings button", () => openSettings(ctx, button)));
  return button;
}

async function openSettings(ctx, button) {
  const reply = await ctx.actButton(button, "payouts", {}, { sound: null });
  // Players who can't change the settings get none, and never see the button again
  if (!reply?.settings) {
    button.hidden = Boolean(reply);
    return;
  }
  showSettings(reply);
  $("payouts-status").textContent = "";
  $("save-payouts").onclick = ctx.safe("saving the payouts", () => saveSettings(ctx));
  $("reset-payouts").onclick = ctx.safe("resetting the payouts", () => {
    fillSettings(bank.payouts.defaults);
    $("payouts-status").textContent = "Reset. Save to keep it.";
  });
  $("close-payouts").onclick = ctx.safe("closing the payouts", () => $("payouts").close());
  $("payouts").showModal();
}

function showSettings(reply) {
  bank.payouts = reply;
  $("payouts-global").hidden = !reply.global;
  const currency = reply.currency;
  $("payouts-rate-label").textContent = `${currency[0].toUpperCase()}${currency.slice(1)} per FarmCoin`;
  fillSettings(reply.settings);
}

function fillSettings(settings) {
  $("payouts-on").checked = settings.on;
  for (const name of ["rate", "cap", "plays"]) {
    $(`payouts-${name}`).value = String(settings[name]);
  }
}

// An empty box goes as null, which the bot refuses with a message saying what it needs
function numberIn(id) {
  const value = $(id).value;
  return value === "" ? null : Number(value);
}

// The bot's refusal shows in the dialog, like Marble Munch's. Anything else is a page bug for ctx.safe to report
async function saveSettings(ctx) {
  const settings = {
    on: $("payouts-on").checked,
    rate: numberIn("payouts-rate"),
    cap: numberIn("payouts-cap"),
    plays: numberIn("payouts-plays"),
  };
  $("payouts-status").textContent = "Saving...";
  try {
    showSettings(await ctx.hub().api("save_payouts", { settings }));
  } catch (e) {
    if (!(e instanceof HubError)) {
      throw e;
    }
    $("payouts-status").textContent = e.message;
    return;
  }
  $("payouts-status").textContent = "Saved.";
  if (bank.parts?.root.isConnected) {
    await askOffer(ctx, ctx.state().player.coins, true);
  }
}
