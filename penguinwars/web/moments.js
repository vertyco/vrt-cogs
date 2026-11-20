// The round's big moments in words: a line for everyone as each penguin goes in, a big one for whoever it was, and the
// banner over the last knockout's slow motion. The bot's fall event says who went in, who did it and how.
import { fieldName, isolate } from "./tags.js";

// Names in a line are cut to this many characters
const NAME_MAX = 13;
// The newest lines show, each for this long. The page's styles fade one out over its last moments, and show fewer
// on a small screen
const LINES = 3;
const LINE_MS = 3200;
// How long the big words stay for the player they are for. Words longer than this many characters get smaller letters
const TOLD_MS = 2200;
const TOLD_LONG = 24;
// The ways one player knocks out another. Any other way with a player behind it reads as a plain knockout
const PLAYER_WAYS = ["hit", "bounce", "shield", "seal"];
// Hazards knock penguins in for nobody
const HAZARD_WAYS = ["wind", "walrus"];

// What a line says, by the way it happened: `a` did it and `b` went in. Each is a name's element
const SAYS = {
  hit: (a, b) => [a, " knocked out ", b],
  bounce: (a, b) => [a, " bounced ", b, " into the sea"],
  shield: (a, b) => [b, " bounced off ", a, "'s shield"],
  seal: (a, b) => [a, "'s seal splashed ", b, " in"],
  snowball: (a, b) => [a, "'s snowball knocked ", b, " in"],
  wind: (a, b) => ["The wind blew ", b, " in"],
  walrus: (a, b) => ["The walrus knocked ", b, " in"],
  fell: (a, b) => [b, " fell in"],
};
// The same for whoever went in, as their own big words. `name` is who did it
const TOLD = {
  hit: (name) => `Knocked out by ${name}`,
  bounce: (name) => `Bounced off ${name}`,
  shield: (name) => `Bounced off ${name}'s shield`,
  seal: (name) => `Splashed in by ${name}`,
  snowball: (name) => `Knocked in by ${name}'s snowball`,
  wind: () => "Blown in by the wind",
  walrus: () => "Knocked in by the walrus",
  fell: () => "You fell in",
};

// The timer that takes the big words away, and how many times the words were all cleared, so a line that was waiting
// to show for a round that has gone stays away
const shown = { timer: null, clears: 0 };

function $(id) {
  return document.getElementById(id);
}

// How a fall happened, as one of the ways above, and the name of whoever did it, or null for nobody. `fall` is
// { seat, by, how, name } from the bot's event, and `seats` the seats as the bot's state lists them
function wayOf(fall, seats) {
  const doer = seats[fall.by];
  if (doer) {
    return { way: PLAYER_WAYS.includes(fall.how) ? fall.how : "hit", name: doer.name };
  }
  if (fall.how === "snowball" && typeof fall.name === "string" && fall.name) {
    return { way: "snowball", name: fall.name };
  }
  return { way: HAZARD_WAYS.includes(fall.how) ? fall.how : "fell", name: null };
}

// A name in a line, in the player's own yellow when it is theirs
function who(name, you) {
  const node = document.createElement("b");
  // Names come from Discord, so they only ever go in as text
  node.textContent = fieldName(name, NAME_MAX);
  node.classList.toggle("you", you);
  return node;
}

// Puts a line at the top of the feed for a few seconds. Only the newest few stay
function addLine(parts) {
  const feed = $("feed");
  const line = document.createElement("p");
  line.className = "feed-line";
  line.append(...parts);
  feed.prepend(line);
  while (feed.children.length > LINES) {
    feed.lastElementChild.remove();
  }
  setTimeout(() => line.remove(), LINE_MS);
}

// The big words for this player alone, with a smaller line under them when there is one
function tell(head, line, glad) {
  const box = $("told");
  $("told-head").textContent = head;
  $("told-line").textContent = line;
  $("told-line").hidden = !line;
  box.classList.toggle("glad", glad);
  box.classList.toggle("long", head.length > TOLD_LONG);
  // Hiding it first starts its way in again for words that follow the last ones closely
  box.hidden = true;
  void box.offsetWidth;
  box.hidden = false;
  clearTimeout(shown.timer);
  shown.timer = setTimeout(() => {
    box.hidden = true;
  }, TOLD_MS);
}

// Whether a seat is held by this player's nemesis, whose id the bot sent, or null for none
function isFoe(seat, nemesis) {
  return nemesis !== null && seat?.kind === "human" && seat.id === nemesis;
}

// Says a knockout: a line for everyone, and big words for the player who went in. This player's nemesis getting them
// again, and this player getting their nemesis, are said to them alone. `mine` is this player's seat, or null for
// someone watching, and the line waits `wait` milliseconds before it shows
export function callOut(fall, seats, mine, nemesis, wait = 0) {
  const victim = seats[fall.seat];
  if (!victim) {
    return;
  }
  const { way, name } = wayOf(fall, seats);
  const byMe = mine !== null && fall.by === mine;
  const doer = name === null ? null : who(name, byMe);
  const parts = SAYS[way](doer, who(victim.name, fall.seat === mine));
  const { clears } = shown;
  setTimeout(() => shown.clears === clears && addLine(parts), wait);
  if (fall.seat === mine) {
    const again = isFoe(seats[fall.by], nemesis) ? "Your nemesis got you again" : "";
    tell(TOLD[way](name === null ? "" : isolate(fieldName(name, NAME_MAX))), again, false);
  } else if (byMe && isFoe(victim, nemesis)) {
    tell("Revenge!", "You knocked out your nemesis", true);
  }
}

// The banner over the last knockout's slow motion
export function showFinal(shown) {
  $("final-call").hidden = !shown;
}

// Takes every word away, as when the round they were about is gone. A line still waiting to show never does
export function clearMoments() {
  shown.clears += 1;
  $("feed").replaceChildren();
  clearTimeout(shown.timer);
  $("told").hidden = true;
  showFinal(false);
}
