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
    "Pick a whole-number multiplier, 2 or higher, and bet your whole balance on one spin of the wheel. The gold " +
    "slice is your chance: 1 in (multiplier + 2), so it gets thinner as the multiplier grows. Land on it and you " +
    "win your balance times your multiplier. Memberships don't add a bonus here. Only you see your wheel.",
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
  // One paragraph per line. Players bet against each other, so there is no multiplier
  holdem: (m, game) =>
    "Texas Hold'em is poker. You play against the other people at the table, not the casino, and the best hand " +
    "wins the pot: all the chips bet in that hand.\n" +
    "Everyone gets 2 private cards that only they can see. Five shared cards then come out face up in the middle, " +
    "and anyone can use them. Your hand is the best 5 cards you can make from those 7 (your 2 plus the 5 shared).\n" +
    "There are four rounds of betting: before any shared card, after the first 3 (the flop), after the 4th (the " +
    "turn), and after the 5th (the river). On your turn you can fold (give up your hand), check (pass, when nobody " +
    "has bet), call (match the bet to stay in), or raise (bet more, so the others must match it or fold). You " +
    "can bet any amount up to all your chips. Betting all of them is going all in: you stay in the hand to the " +
    "end, and can only win as much from each player as you put in.\n" +
    "Two players put in forced bets called blinds before the cards are dealt: the small blind, and the big blind, " +
    "twice as much. The dealer button moves around the table each hand, and the blinds move with it. That way " +
    "there is always something to win. If everyone else folds, you win the pot " +
    "without showing your cards. If more than one player is left after the last round, everyone shows their " +
    "cards (the showdown) and the best hand wins. The chart below shows what beats what.\n" +
    `The casino keeps ${+game.cut}% of each pot that reaches the flop, at most 3 big blinds. A hand that ends ` +
    "before the flop costs nothing. The first player to sit practices free against CPUs with play chips. Once " +
    "someone buys in, hands are for real: your buy-in comes out of your credits and goes back when you stand up.",
  // One paragraph per line. The pay table chart follows
  slots: () =>
    "Pick a bet and pull the lever down. Only the middle row counts.\n" +
    "2% of every bet grows the jackpot. 7-7-7 wins the share of it that matches your bet: a max bet wins it all, " +
    "and half the max wins half. The jackpot never drops below 60 times the max bet.\n" +
    "Memberships don't add a bonus here. Only you see your machine.",
};

// What each line on the middle row pays, bet included, and how often it comes up: 1 in this many spins
const PAY_TABLE = [
  ["7 7 7", "Jackpot share", 10648],
  ["3 diamonds", "50x", 1331],
  ["3 coins", "25x", 394],
  ["3 bells", "14x", 85],
  ["3 cherries", "8x", 166],
  ["2 cherries", "3x", 12],
  ["1 cherry", "Bet back", 3],
];

// The kinds of hand, best first, named as the table names them. A card is its rank then its suit symbol
const RANKINGS = [
  ["Royal flush", "A♠ K♠ Q♠ J♠ 10♠", "The best straight flush: A K Q J 10, all one suit"],
  ["Straight flush", "9♥ 8♥ 7♥ 6♥ 5♥", "Five in a row, all one suit"],
  ["Four of a kind", "8♣ 8♦ 8♥ 8♠ K♠", "Four cards of the same rank"],
  ["Full house", "Q♠ Q♥ Q♦ 4♣ 4♠", "Three of one rank and two of another"],
  ["Flush", "K♦ J♦ 9♦ 6♦ 3♦", "Any five cards of one suit"],
  ["Straight", "10♣ 9♥ 8♠ 7♦ 6♣", "Five in a row, mixed suits"],
  ["Three of a kind", "7♠ 7♥ 7♦ K♣ 2♠", "Three cards of the same rank"],
  ["Two pair", "J♠ J♦ 4♥ 4♣ A♠", "Two different pairs"],
  ["Pair", "10♥ 10♠ A♦ 8♣ 3♠", "Two cards of the same rank"],
  ["High card", "A♠ J♦ 8♣ 6♥ 3♦", "None of the above: your highest card counts"],
];

// What beats what: the hands best first, each with a small example drawn as cards
function rankChart() {
  const list = make("ol", "rank-chart");
  for (const [name, example, about] of RANKINGS) {
    const info = make("div", "rank-info");
    info.append(make("b", "rank-name", name), make("span", "rank-about", about));
    const hand = make("div", "rank-cards");
    for (const text of example.split(" ")) {
      hand.append(make("span", /[♥♦]/.test(text) ? "mini-card red" : "mini-card", text));
    }
    const row = make("li");
    row.append(info, hand);
    list.append(row);
  }
  return list;
}

// Slots' pay table, best first, in the rank chart's look
function payChart() {
  const list = make("ol", "rank-chart pay-chart");
  for (const [line, pays, every] of PAY_TABLE) {
    const info = make("div", "rank-info");
    info.append(make("b", "rank-name", line), make("span", "rank-about", `1 in ${money(every)}`));
    const row = make("li");
    row.append(info, make("b", "pay-amount", pays));
    list.append(row);
  }
  return list;
}

let context = null;
// Counts panel openings and closings, so an answer that arrives after its panel was closed or replaced is dropped
// instead of filling the panel opened since
let opened = 0;

function $(id) {
  return document.getElementById(id);
}

// context: api(name, data), hub(), currency(), toast(text)
export function setup(given) {
  context = given;
  $("panel-close").addEventListener("click", close);
}

// Opens the panel with a title, and returns its emptied body
export function open(title) {
  opened += 1;
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
  opened += 1;
  $("panel").close();
}

// Asks the bot; on a refusal the panel shows the reason and this returns null. Also null when the panel that asked
// was closed or replaced before the answer came
export async function ask(name, data = {}) {
  const mine = opened;
  try {
    const answer = await context.api(name, data);
    return mine === opened ? answer : null;
  } catch (e) {
    if (mine === opened) {
      $("panel-body").replaceChildren(make("p", "error", e.message));
    }
    return null;
  }
}

// A yes or no question over the panel. Resolves true for yes
export function confirmBox(text, yes = "Yes") {
  const box = $("confirm");
  $("confirm-text").textContent = text;
  $("confirm-yes").textContent = yes;
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

function payoutOf(key, game) {
  if (game.blinds) {
    return `Cut ${+game.cut}%`;
  }
  if (key === "slots") {
    return "Pay table";
  }
  return game.multiplier === null ? "-" : `${game.multiplier}x`;
}

// Hold'em's own numbers in one line: the buy-in range, the blinds and the casino's cut
function holdemLine(game) {
  const [small, big] = game.blinds;
  return `Buy-in ${money(game.min)} to ${money(game.max)} · Blinds ${money(small)}/${money(big)} · Cut ${+game.cut}%`;
}

// Slots' own numbers in one line: the bet range and the jackpot now
function slotsLine(game) {
  return `Bets ${money(game.min)} to ${money(game.max)} · Jackpot ${money(game.jackpot)}`;
}

export async function showRules() {
  const body = open("House rules");
  const info = await ask("rules");
  if (!info) {
    return;
  }
  const rows = Object.entries(info.games).map(([key, game]) => [
    game.name,
    game.open ? "Open" : "Closed",
    game.access,
    money(game.min),
    money(game.max),
    payoutOf(key, game),
    game.blinds ? "-" : duration(game.cooldown),
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
    body.append(make("h4", "", game.name));
    if (game.blinds) {
      body.append(make("p", "house-line", holdemLine(game)));
    }
    if (key === "slots") {
      body.append(make("p", "house-line", slotsLine(game)));
    }
    for (const line of RULES[key](game.multiplier, game).split("\n")) {
      body.append(make("p", "", line));
    }
    if (game.blinds) {
      body.append(
        make("h4", "", "What beats what"),
        make("p", "dim", "Best at the top. Hands of the same kind are settled by their higher cards."),
        rankChart(),
        make("p", "dim", "An Ace can also be low, so A 2 3 4 5 is the lowest straight."),
      );
    }
    if (key === "slots") {
      body.append(
        make("h4", "", "Pay table"),
        make("p", "dim", "What each line on the middle row pays, bet included, and how often it comes up."),
        payChart(),
      );
    }
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
    console.warn("Vegas: couldn't open the link", e);
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
    ["Max bet multiplier", `${stats.bet_boost}x`],
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
    needs.push(`${money(tier.req_credits)} ${context.currency()}`);
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
      ["Max bet multiplier", `${tier.bet_boost}x`],
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
