// The panels over the casino: House rules, a player's stats, the memberships, and (for admins) the settings.
// Each one asks the bot for what it shows when it opens, so it is never out of date.
import { avatar, button, duration, make, money, tierColor } from "./format.js";
import { settingsTabs } from "./settings.js";

const CREDIT = "Rebuilt for ActivityHub from Redjumpman's Casino";
const CREDIT_URL = "https://github.com/Redjumpman/Jumper-Plugins";
const TIERS_EXPLAINED =
  "Memberships are given automatically to players who meet their requirements. A player who meets several gets " +
  "the one with the highest access level. A membership given by hand stays until it is revoked.";

// Each game's rules in a few sentences, with the table's own multiplier filled in
const RULES = {
  allin: () =>
    "Pick a whole-number multiplier, 2 or higher, and bet your whole balance. You win with a chance of 1 in " +
    "(multiplier + 2), and a win pays your balance times your multiplier. Memberships don't add a bonus here. " +
    "Only you see your machine.",
  blackjack: (m) =>
    "Get closer to 21 than the dealer without going over. Aces count 1 or 11, and face cards 10. Hit, Stay, or " +
    "Double: a second bet of the same size for exactly one more card. The dealer takes one card on a hand with an " +
    `Ace that isn't 21, then draws while under 17. A win pays your bet x ${m}, and a tie is a push: your bet ` +
    "comes back. Up to 5 seats.",
  coin: (m) => `Call heads or tails. One flip for the table, and a right call pays your bet x ${m}.`,
  cups: (m) => `A coin hides under one of three cups, then they shuffle. Pick a cup: the right one pays your bet x ${m}.`,
  dice: (m) => `Two dice for the table. A total of 2, 7, 11 or 12 pays your bet x ${m}.`,
  hilo: (m) =>
    `Bet on Low (under 7), High (over 7) or Seven. Low or High pays your bet x ${m}, and Seven pays your bet x 5 x ${m}.`,
  craps: (m) =>
    `The shooter rolls two dice for everyone who bet. On the first roll, 7 pays your bet x 3 x ${m}, 11 pays your ` +
    `bet x ${m}, and 2, 3 or 12 loses. Any other total becomes the point, and the shooter rolls once more: the ` +
    `point pays your bet x ${m}, anything else loses. The dice pass to the next player after each round.`,
  war: (m) =>
    `You and the dealer each get one card, and aces are high. A higher card pays your bet x ${m}, and a lower one ` +
    "loses. On a tie, surrender to get half your bet back, or go to war with a second bet the same size: the " +
    `dealer burns 3 cards and deals again, and an equal or higher card pays your first bet x ${m} plus your war ` +
    "bet back.",
  double: () =>
    "Everyone at the table rides the same coin. Heads doubles everyone's amount, and tails takes it all. After " +
    "each heads, cash out or double again. Cashing out pays what you have, and memberships don't add a bonus here.",
};

let context = null;

function $(id) {
  return document.getElementById(id);
}

// context: api(name, data), hub(), toast(text)
export function setup(given) {
  context = given;
  $("panel-close").addEventListener("click", close);
}

// Opens the panel with a title, and returns its emptied body
export function open(title) {
  $("panel-title").textContent = title;
  $("panel-tabs").hidden = true;
  $("panel-tabs").replaceChildren();
  $("panel-body").replaceChildren(make("p", "dim", "Loading..."));
  if (!$("panel").open) {
    $("panel").showModal();
  }
  return $("panel-body");
}

export function close() {
  $("panel").close();
}

// Asks the bot; on a refusal the panel shows the reason and this returns null
export async function ask(name, data = {}) {
  try {
    return await context.api(name, data);
  } catch (e) {
    $("panel-body").replaceChildren(make("p", "error", e.message));
    return null;
  }
}

// A yes or no question over the panel. Resolves true for yes
export function confirmBox(text) {
  const box = $("confirm");
  $("confirm-text").textContent = text;
  box.showModal();
  return new Promise((resolve) => {
    const finish = (answer) => {
      $("confirm-yes").removeEventListener("click", yes);
      $("confirm-no").removeEventListener("click", no);
      box.removeEventListener("cancel", no);
      box.close();
      resolve(answer);
    };
    const yes = () => finish(true);
    const no = () => finish(false);
    $("confirm-yes").addEventListener("click", yes);
    $("confirm-no").addEventListener("click", no);
    box.addEventListener("cancel", no);
  });
}

export function facts(pairs) {
  const list = make("dl", "facts");
  for (const [label, value] of pairs) {
    list.append(make("dt", "", label), make("dd", "", String(value)));
  }
  return list;
}

export function grid(headers, rows, numeric = []) {
  const table = make("table", "grid");
  const head = make("tr");
  headers.forEach((text, i) => head.append(make("th", numeric.includes(i) ? "num" : "", text)));
  table.append(head);
  for (const row of rows) {
    const line = make("tr");
    row.forEach((cell, i) => {
      const td = make("td", numeric.includes(i) ? "num" : "");
      if (cell instanceof Node) {
        td.append(cell);
      } else {
        td.textContent = String(cell);
      }
      line.append(td);
    });
    table.append(line);
  }
  const wrap = make("div", "scroll-x");
  wrap.append(table);
  return wrap;
}

// ---------- House rules ----------

function payoutOf(game) {
  return game.multiplier === null ? "-" : `${game.multiplier}x`;
}

export async function showRules() {
  const body = open("House rules");
  const info = await ask("rules");
  if (!info) {
    return;
  }
  const rows = Object.values(info.games).map((game) => [
    game.name,
    game.open ? "Open" : "Closed",
    game.access,
    money(game.min),
    money(game.max),
    payoutOf(game),
    duration(game.cooldown),
  ]);
  body.replaceChildren(
    make("h3", "", "Games"),
    grid(["Game", "Open", "Access", "Min", "Max", "Payout", "Cooldown"], rows, [2, 3, 4, 5]),
    make("h3", "", `${info.name} Casino`),
    facts([
      ["Open", info.open ? "Yes" : "No"],
      ["Mode", info.global ? "Global: one casino for every server" : "This server"],
      ["Payout limit", info.limit_on ? `${money(info.limit_amount)} ${info.currency}` : "Off"],
    ]),
    make("p", "dim", "Wins over the payout limit are held until an admin releases them."),
    make("h3", "", "How to play"),
  );
  for (const [key, game] of Object.entries(info.games)) {
    body.append(make("h4", "", game.name), make("p", "", RULES[key](game.multiplier)));
  }
  body.append(make("h3", "", "About"), make("p", "", `${CREDIT}: ${CREDIT_URL}`));
  const hub = context.hub();
  if (hub && hub.discord) {
    body.append(button("Open Redjumpman's repo", "button small", () => openLink(hub)));
  }
}

async function openLink(hub) {
  try {
    await hub.discord.commands.openExternalLink({ url: CREDIT_URL });
  } catch (e) {
    console.warn("Casino: couldn't open the link", e);
    context.toast("Discord didn't open the link.");
  }
}

// ---------- Stats ----------

// The player's own stats when id is null, or another player's
export async function showStats(id) {
  const body = open(id ? "Player stats" : "My stats");
  const stats = id ? await ask("player_stats", { user_id: id }) : await ask("profile");
  if (stats) {
    body.replaceChildren(statsView(stats));
  }
}

export function statsView(stats) {
  const view = make("div");
  const who = make("div", "who");
  const name = make("b", "", stats.name);
  const tier = make("span", "tier", stats.membership.name);
  tier.style.setProperty("--tier-color", tierColor(stats.membership.color));
  who.append(avatar(stats.avatar), name, tier);
  const pairs = [
    ["Membership", stats.membership.name],
    ["Access level", stats.access],
    ["Cooldown reduction", duration(stats.reduction)],
    ["Bonus multiplier", `${stats.bonus}x`],
  ];
  if (stats.pending) {
    pairs.push(["Held winnings", money(stats.pending)]);
  }
  const rows = stats.games.map((game) => [
    game.name,
    money(game.played),
    money(game.won),
    game.ready_in > 0 ? duration(game.ready_in) : "Ready to play!",
  ]);
  view.append(
    who,
    facts(pairs),
    make("h3", "", "Games"),
    grid(["Game", "Played", "Won", "Ready"], rows, [1, 2]),
    make("p", "dim", "Wins don't count pushes or surrenders."),
  );
  return view;
}

// ---------- Memberships ----------

export function tierCard(tier) {
  const card = make("div", "tier-card");
  card.style.setProperty("--tier-color", tierColor(tier.color));
  const needs = [];
  if (tier.req_credits) {
    needs.push(`${money(tier.req_credits)} credits`);
  }
  if (tier.req_role_id) {
    needs.push(`the ${tier.req_role || "missing"} role`);
  }
  if (tier.req_days) {
    needs.push(`${tier.req_days} days`);
  }
  card.append(
    make("h4", "", tier.name),
    facts([
      ["Access level", tier.access],
      ["Cooldown reduction", duration(tier.reduction)],
      ["Bonus multiplier", `${tier.bonus}x`],
      ["Needs", needs.length ? needs.join(", ") : "Nothing: open to everyone"],
      ["Games", tier.games.length ? tier.games.join(", ") : "None"],
    ]),
  );
  return card;
}

export async function showTiers() {
  const body = open("Memberships");
  const result = await ask("memberships");
  if (!result) {
    return;
  }
  body.replaceChildren(make("p", "", TIERS_EXPLAINED));
  if (!result.tiers.length) {
    body.append(make("p", "dim", "There are no memberships yet. Everyone plays as Basic."));
  }
  for (const tier of result.tiers) {
    body.append(tierCard(tier));
  }
}

// ---------- Settings ----------

export async function showSettings() {
  open("Settings");
  const settings = await ask("settings");
  if (settings) {
    // Settings forms stay on screen when the bot refuses a change, so their requests throw instead of replacing them
    const api = (name, data) => context.api(name, data);
    settingsTabs(settings, { ask: api, confirmBox, facts, grid, statsView, tierCard, toast: context.toast });
  }
}
