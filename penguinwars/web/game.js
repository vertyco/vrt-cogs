// Penguin Wars' page: the live connection, the screen around the game and what it tells the hub.
// The bot runs the game. This page sends sit, stand and start, and shows what the bot sends back.
import { backToMenu, connect } from "activityhub";
import { bindInput } from "./input.js";
import { SEAT_COLORS } from "./models.js";
import { callOut, clearMoments, showFinal } from "./moments.js";
import { decided } from "./motion.js";
import {
  bindExtras,
  bindSettings,
  bindShop,
  bindSound,
  bindTuning,
  openProfile,
  openShop,
  showExtras,
} from "./panels.js";
import { createScene } from "./scene.js";
import { Sound } from "./sound.js";
import { characters, fieldName, isolate, nameStyleOf, styledName } from "./tags.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Penguin Wars again.",
  1011: "Couldn't join the game.",
  4003: "Penguin Wars was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
// The seated card's line for someone alone, whose round starts when they tap
const SOLO_LINE = "Start when you're ready";
// Names on the card and under the end card's heading are cut to this many characters
const NAME_MAX = 12;
const WINNER_NAME_MAX = 16;
const ICE_NAMES = 4;
const WATCHER_FACES = 6;
const BOARD_NAME_MAX = 16;
// How long "Go!" shows as the round starts
const GO_MS = 800;
// Each number of the 3-2-1 lands a little big and settles
const COUNT_POP = [
  { transform: "scale(1.35)", opacity: 0.5 },
  { transform: "scale(1)", opacity: 1 },
];
const COUNT_POP_MS = 220;
// The round's call-outs under the bar have left this long after a round starts, or after this page joins one. A
// knockout's line shows in their place, so one that comes sooner waits for them to go
const CALLS_MS = 2900;
// The cards wait for the last knockout's slow motion, and then this long more, so the winner's cheer is seen to begin.
// They never wait longer than the limit, whatever becomes of the slow motion
const CARDS_AFTER_MS = 600;
const CARDS_LIMIT_MS = 4000;
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
// What the title card's big button sends, by what it says. Joining and leaving the line say which, so a second tap
// before the first is answered changes nothing
const GO_SENDS = { sit: { sit: true }, join: { line: true }, leave: { line: false } };
const page = {
  hub: null,
  conn: null,
  state: null,
  // The latest frame or snapshot board: where every penguin is
  board: null,
  mySeat: null,
  // The stage and round the shop last sent a stand for, so one state change sends one
  standKey: null,
  updates: 0,
  toastTimer: null,
  // What the screen last showed, so an identical list or frame leaves its elements alone. For the people on the ice
  // and the faces watching, it is who has an element: what an element says changes in place, so a press on it lands
  watchLook: null,
  iceLook: null,
  endLook: null,
  barLook: null,
  hintLook: "",
  // The moves this player has made, each of which drops its line from the hint
  learned: { slide: false, brace: false, seal: false },
  // The status last given to the hub, and whether the game's connection has closed for good
  reported: null,
  closed: false,
  // The round whose win has been cheered
  cheered: null,
  // The round and number of the 3-2-1 last beeped, so a snapshot that repeats the number stays quiet
  beat: null,
  goTimer: null,
  // The names of the looks this player's last round unlocked, for the end card
  unlocked: [],
  // The id of this player's nemesis, as the bot last said it, or null
  nemesis: null,
  // When the round's call-outs under the bar have left, on the page's own clock
  callsUntil: 0,
  // Whether the cards wait for the last knockout's slow motion, and the timer that lets them show
  holdCards: false,
  cardTimer: null,
  // Whether the profile card on show was opened from the leaderboard, which comes back once the card closes
  boardNext: false,
};

function $(id) {
  return document.getElementById(id);
}

const sound = new Sound();
const scene = createScene($("game"), $("tags"), sound);
const controls = bindInput($("game"), scene, {
  slide: (dx, dz, power) => sendMove("slide", { slide: [dx, dz, power] }),
  brace: () => sendMove("brace", { brace: true }),
  splash: (angle) => sendMove("seal", { splash: angle }),
});

scene.onEvent(hearEvent);

// ---------- Starting ----------

async function start() {
  bindButtons();
  try {
    page.hub = await connect();
  } catch (e) {
    showMessage(e.message);
    return;
  }
  // Older hubs have no people button
  if (page.hub.peopleButton) {
    $("mute").after(page.hub.peopleButton());
  }
  page.hub.onPeople?.(renderWatchers);
  if (page.hub.offline) {
    showPreview();
    return;
  }
  bindSettings(page.hub);
  bindTuning(page.hub);
  // A press on the crate button or a party button must not fire a slide from a finger still down on the ice. The
  // snowball button hands the taps of someone with no seat to whatever throws their snowballs
  bindExtras(
    page.hub,
    toast,
    () => controls.cancelDrag(),
    (thrower) => controls.setThrow(thrower),
  );
  setInterval(showRate, 1000);
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showMessage(CLOSED_BECAUSE[e.status] || e.message);
    leaveRound();
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    controls.cancelDrag();
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    showMessage(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
    leaveRound();
  });
}

function showPreview() {
  $("title").hidden = false;
  $("go").hidden = true;
  $("note").textContent = "Open Penguin Wars in Discord to play.";
  $("note").hidden = false;
}

function showMessage(text) {
  // A dialog left open would cover the message, and a modal one would leave its button dead
  page.boardNext = false;
  for (const id of ["shop", "profile", "board", "party", "settings", "tuning", "sound-panel"]) {
    $(id).close();
  }
  const cleared = ["title", "end", "count", "twist-call", "map-call", "hint", "watch-shop", "drop-crate", "throw-snow"];
  for (const id of cleared) {
    $(id).hidden = true;
  }
  // No card waiting on a slow motion comes up over the message later
  clearTimeout(page.cardTimer);
  page.holdCards = false;
  clearMoments();
  $("message-text").textContent = text;
  $("message").hidden = false;
}

// ---------- Messages from the bot ----------

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  if (data.state) {
    applyState(data.state);
  } else if ("f" in data) {
    applyFrame(data);
  } else if (typeof data.notice === "string") {
    toast(data.notice);
  } else if (Array.isArray(data.unlocked)) {
    showUnlocked(data.unlocked);
  } else if ("nemesis" in data) {
    setNemesis(data.nemesis);
  }
}

// The bot says who this player's nemesis is as they join, and again when a round changes it: the id of the person who
// has knocked them out most, or null. That person's name tag is marked on this page
function setNemesis(id) {
  page.nemesis = typeof id === "string" ? id : null;
  if (page.state) {
    scene.setSeats(page.state.seats, page.mySeat, page.nemesis);
  }
}

// What the drawing has just reached, among the bot's events and the scene's own two. A fall is said in words. The
// round's last knockout gets its banner, and holds the cards back until its slow motion is over
const MOMENTS = {
  fall(seat, by, how, name) {
    const wait = Math.max(0, page.callsUntil - performance.now());
    callOut({ seat, by, how, name }, page.state.seats, page.mySeat, page.nemesis, wait);
  },
  final() {
    page.holdCards = true;
    showFinal(true);
    showCardsIn(CARDS_LIMIT_MS);
  },
  final_done() {
    showFinal(false);
    showCardsIn(CARDS_AFTER_MS);
  },
};

function hearEvent([kind, ...values]) {
  if (page.state && Object.hasOwn(MOMENTS, kind)) {
    MOMENTS[kind](...values);
  }
}

function showCardsIn(ms) {
  clearTimeout(page.cardTimer);
  page.cardTimer = setTimeout(showCards, ms);
}

// Lets the cards show again, at once for whichever of them the state calls for
function showCards() {
  clearTimeout(page.cardTimer);
  showFinal(false);
  if (page.holdCards) {
    page.holdCards = false;
    renderCards(page.state);
  }
}

// Play just unlocked these looks. The end card says so, or a toast for someone who gets no end card, and the Looks
// buttons carry a dot until the wardrobe is opened. An end card still waiting for the slow motion says it when it
// comes up
function showUnlocked(names) {
  page.unlocked = names.filter((name) => typeof name === "string");
  if (!page.unlocked.length) {
    return;
  }
  document.body.classList.add("new-looks");
  sound.play("unlock");
  if (!$("end").hidden) {
    renderUnlocked();
  } else if (!(page.holdCards && playedRound(page.state))) {
    toast(unlockedLine());
  }
}

function unlockedLine() {
  return `Unlocked: ${page.unlocked.join(", ")}`;
}

function renderUnlocked() {
  $("end-unlocked").hidden = !page.unlocked.length;
  if (page.unlocked.length) {
    setText("end-unlocked", unlockedLine());
  }
}

function applyState(state) {
  const before = page.state?.stage;
  page.state = state;
  page.board = state.board;
  page.mySeat = findMySeat(state.seats);
  document.body.dataset.stage = state.stage;
  // A round never runs under the leaderboard, so it closes as the 3-2-1 begins and again as the round starts, which
  // leaves it open for someone who opened it from the title card during the 3-2-1 until then. The prices dialog
  // stays, as an admin opens it on purpose
  if ((state.stage === "starting" || state.stage === "playing") && state.stage !== before) {
    $("board").close();
    // Nor under a profile card for someone with a penguin in it. The card covers the game
    page.boardNext = false;
    if (page.mySeat !== null) {
      $("profile").close();
    }
    // What the last round unlocked has been said by now
    page.unlocked = [];
  }
  // A party round opens its 3-2-1 with a fanfare
  if (state.stage === "starting" && before !== "starting" && state.twist) {
    sound.play("party");
  }
  followMoments(state, before);
  keepShopSeatless(state);
  liveControls();
  scene.setRules(state.rules);
  scene.setSeats(state.seats, page.mySeat, page.nemesis);
  scene.reset(state.board, state.round);
  renderCards(state);
  renderCount(state, before);
  renderBar();
  renderHint();
  showExtras(state, page.mySeat !== null);
  renderWatchers();
  report(state);
}

// A round's words belong to it. Its call-outs under the bar show from its start, or from when this page joins it, and
// a knockout's line waits for them to go. Once the round and its results are gone, so are its words, and the cards no
// longer wait for its slow motion
function followMoments(state, before) {
  if (state.stage === "playing" && before !== "playing") {
    page.callsUntil = performance.now() + CALLS_MS;
  }
  const over = state.stage === "waiting" || state.stage === "starting";
  if (over && state.stage !== before) {
    clearMoments();
    showCards();
  }
}

// The shop covers the screen, so whoever has it open must not hold a seat. The bot only drops a seat between rounds,
// so a stand can miss: then the shop closes once a round is on, and between rounds the stand goes again
function keepShopSeatless(state) {
  if (!$("shop").open || page.mySeat === null) {
    page.standKey = null;
    return;
  }
  if (state.stage === "starting" || state.stage === "playing") {
    $("shop").close();
    return;
  }
  // A stand that couldn't go out, as while the connection comes back, goes again with the next state
  const key = `${state.stage}:${state.round}`;
  if (page.standKey !== key && send({ stand: true })) {
    page.standKey = key;
  }
}

function applyFrame(frame) {
  page.updates += 1;
  page.board = frame;
  liveControls();
  renderBar();
  report(page.state);
  // A frame can beat the first snapshot here, and the scene starts from a snapshot
  if (page.state) {
    scene.push(frame);
    renderHint();
  }
}

// Moves count while a round is played, until it is decided. Then the bot takes no more of them
function liveControls() {
  const { state, board } = page;
  const live = state?.stage === "playing" && Boolean(board) && !decided(board.p);
  controls.setLive(live);
  // A mouse over the ice shows a hand while this player has something to drag
  document.body.classList.toggle("can-move", live && page.mySeat !== null);
}

function findMySeat(seats) {
  const index = seats.findIndex((seat) => seat.kind === "human" && seat.id === page.hub.player.id);
  return index === -1 ? null : index;
}

// The update rate next to the hub's frame rate counter, only while a round streams updates
function showRate() {
  page.hub.stat(page.state?.stage === "playing" ? `${page.updates} TPS` : "");
  page.updates = 0;
}

// ---------- Cards ----------

// Whether someone without a seat can still take a CPU's penguin: during the 3-2-1, with nobody waiting in line
function canHopIn(state) {
  return (
    state.stage === "starting" &&
    page.mySeat === null &&
    state.line.length === 0 &&
    state.seats.some((seat) => seat.kind === "cpu")
  );
}

// Whether the results on show are of a round this player played, which gets them the end card
function playedRound(state) {
  const seat = page.mySeat;
  return (
    Boolean(state) && seat !== null && state.stage === "results" && state.seats[seat].played && Boolean(state.results)
  );
}

// Which card a person sees: the end card for those who played the round on show, the title card (with their seat
// when they have one) between rounds, and none during a round. Someone without a seat keeps the title card through
// the 3-2-1 while a penguin can be taken, so a friend's Play a moment after the round started still gets them in. The
// results' cards wait for the last knockout's slow motion, which a card would cover
function renderCards(state) {
  const seat = page.mySeat;
  const between = state.stage === "waiting" || state.stage === "results" || canHopIn(state);
  const played = playedRound(state);
  const held = page.holdCards && state.stage === "results";
  $("title").hidden = !between || played || held;
  $("end").hidden = !played || held;
  if (held) {
    return;
  }
  if (played) {
    renderEnd(state);
  } else if (between) {
    renderTitle(state, seat !== null);
  }
}

// The 3-2-1 beeps once per number, and the round starts with "Go!" and a higher beep. The title card covers the
// numbers for someone who can still hop in, but they hear them
function renderCount(state, before) {
  const count = $("count");
  if (state.stage === "starting") {
    clearTimeout(page.goTimer);
    count.classList.remove("go");
    setText("count", String(state.left));
    count.hidden = !$("title").hidden;
    const beat = `${state.round}:${state.left}`;
    if (page.beat !== beat) {
      page.beat = beat;
      sound.play("beep");
      if (!REDUCED) {
        count.animate?.(COUNT_POP, { duration: COUNT_POP_MS, easing: "cubic-bezier(0.2, 1.4, 0.4, 1)" });
      }
    }
  } else if (state.stage === "playing" && before === "starting") {
    setText("count", "Go!");
    count.classList.add("go");
    count.hidden = false;
    sound.play("go");
    page.goTimer = setTimeout(() => {
      count.hidden = true;
      count.classList.remove("go");
    }, GO_MS);
  } else if (state.stage !== "playing") {
    clearTimeout(page.goTimer);
    count.hidden = true;
  }
}

// This player's place in the line: 1 is next, null when not waiting
function linePlace(state) {
  const index = state.line.indexOf(page.hub.player.id);
  return index === -1 ? null : index + 1;
}

function placeText(place) {
  return place === 1 ? "You're next" : `${ordinal(place)} in line`;
}

function setText(id, text) {
  if ($(id).textContent !== text) {
    $(id).textContent = text;
  }
}

function renderTitle(state, seated) {
  const place = linePlace(state);
  const free = state.seats.some((seat) => seat.kind !== "human");
  // A line that exists gets the free spots first, so Play only shows when nobody is waiting
  const canSit = free && state.line.length === 0 && place === null;
  // The rules are for people who haven't asked to play yet. After that, the card holds the countdown and the others
  $("title").classList.toggle("seated", seated || place !== null);
  $("go").hidden = seated;
  $("go").dataset.send = place !== null ? "leave" : canSit ? "sit" : "join";
  setText("go", place !== null ? "Leave the line" : canSit ? "Play" : "Join the line");
  $("start").hidden = !seated;
  $("stand").hidden = !seated;
  $("starting").hidden = !seated && place === null && state.stage !== "starting";
  $("ice").hidden = !seated;
  // Whoever the last swap sat out is told why, for as long as they wait
  const out = place !== null && state.out.includes(page.hub.player.id);
  $("note").hidden = !out;
  // The swap comes as the results end, so the round about to start is the one they miss
  if (out) {
    setText("note", state.stage === "results" ? "You sat out that round" : "You're sitting out this round");
  }
  if (!seated) {
    if (place !== null) {
      setText("starting", placeText(place));
    } else if (state.stage === "starting") {
      setText("starting", `Starting in ${state.left}`);
    }
    return;
  }
  // The bot sends no seconds while nothing counts down, which is when this player is alone
  const counting = state.stage === "results" ? state.left !== null : state.countdown !== null;
  if (!counting) {
    $("starting").textContent = SOLO_LINE;
  } else if (state.stage === "results") {
    $("starting").textContent = `Next round in ${state.left}`;
  } else {
    $("starting").textContent = `Starting in ${state.countdown}`;
  }
  renderIce(state.seats);
}

// A button that opens a person's profile card, by their Discord id as text
function whoButton(id) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "who";
  button.addEventListener("click", () => showProfile(id));
  return button;
}

// Who is on the ice, in seat order. Only the first few names fit, the rest are counted. A name opens that person's
// card. States come several times a second, so the list is only built again when other people are in it, and a name
// or an away mark changes in place
function renderIce(seats) {
  const people = seats.filter((seat) => seat.kind === "human");
  const shown = people.slice(0, ICE_NAMES);
  const look = JSON.stringify([shown.map((seat) => seat.id), people.length]);
  if (look !== page.iceLook) {
    page.iceLook = look;
    const items = shown.map((seat) => {
      const item = document.createElement("li");
      item.append(whoButton(seat.id));
      return item;
    });
    if (people.length > ICE_NAMES) {
      const more = document.createElement("li");
      more.className = "more";
      more.textContent = `+${people.length - ICE_NAMES}`;
      items.push(more);
    }
    $("ice").replaceChildren(...items);
  }
  shown.forEach((seat, place) => {
    const item = $("ice").children[place];
    // Names come from Discord, so they only ever go in as text
    const name = fieldName(seat.name, NAME_MAX);
    if (item.firstChild.textContent !== name) {
      item.firstChild.textContent = name;
    }
    item.classList.toggle("away", seat.away);
    // In yellow, as the player's own name tag is on the ice
    item.classList.toggle("you", seat.id === page.hub.player.id);
  });
}

function ordinal(n) {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
}

function clock(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// The end card's heading: `words`, or with a `state` the winner's name and "wins". The name is in the style its player
// wears, when the seat is still theirs, and a person's name opens their card. States come several times a second, so
// the heading is only built again when it says something else, and a press on the name lands
function nameWinner(state, words) {
  const winner = state?.seats[state.results.winner];
  const theirs = Boolean(winner) && winner.name === state.results.name;
  const style = theirs ? nameStyleOf(winner.looks) : null;
  const id = theirs && winner.kind === "human" ? winner.id : null;
  const look = JSON.stringify([words, state?.results.name, style, id]);
  if (look === page.endLook) {
    return;
  }
  page.endLook = look;
  if (!state) {
    $("end-head").textContent = words;
    return;
  }
  const name = styledName(fieldName(state.results.name, WINNER_NAME_MAX), style, true);
  const button = id === null ? null : whoButton(id);
  button?.append(name);
  $("end-head").replaceChildren(button ?? name, " wins");
}

function renderEnd(state) {
  const { results } = state;
  const seat = page.mySeat;
  const won = results.winner === seat;
  if (won && page.cheered !== page.state.round) {
    page.cheered = page.state.round;
    sound.play("win");
  }
  $("end").classList.toggle("won", won);
  if (won) {
    nameWinner(null, "You win!");
  } else if (results.name) {
    nameWinner(state, "");
  } else {
    nameWinner(null, "Nobody made it");
  }
  // With no winner, "Nobody made it" already says it, and a place would contradict it
  $("end-text").hidden = results.winner === null;
  $("end-text").textContent = won
    ? "Last penguin on the ice."
    : `You came ${ordinal(results.places[seat] || 1)} of ${results.places.length}.`;
  $("end-stats").textContent = `Round ${clock(results.seconds)} · Knockouts: ${results.knocked[seat]}`;
  // The bot sends no seconds while the card waits for this player's tap, which is when they are alone
  $("end-next").hidden = state.left === null;
  if (state.left !== null) {
    setText("end-next", `Next round in ${state.left}`);
  }
  renderUnlocked();
}

// ---------- The bar ----------

// How the bar can look, roomiest first: as it is, without the words of the count, with small buttons, then both. It
// takes the first that fits on its row, so the count never wraps and no button is pushed off the screen
const BAR_FITS = [[], ["short"], ["small"], ["small", "short"]];

function fitBar() {
  const bar = $("bar");
  for (const looks of BAR_FITS) {
    bar.classList.remove("small", "short");
    bar.classList.add(...looks);
    if (bar.scrollWidth <= bar.clientWidth) {
      return;
    }
  }
}

// The bar's room changes with the screen and its safe area, and with the buttons, count and faces in it. Its own
// classes are not watched, so fitting it never sets off another fit
function watchBar() {
  new ResizeObserver(fitBar).observe(document.querySelector(".hud"));
  new MutationObserver(fitBar).observe($("bar"), {
    subtree: true,
    childList: true,
    characterData: true,
    attributeFilter: ["hidden"],
  });
  document.fonts?.addEventListener("loadingdone", fitBar);
}

function buildDots() {
  $("dots").replaceChildren(
    ...SEAT_COLORS.map((color) => {
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = color;
      return dot;
    }),
  );
}

function aliveSeats(board) {
  return board.p.map((row) => (row[2] & 1) === 1);
}

// The dots and the count of penguins still on the ice, only while a round exists
function renderBar() {
  const board = page.board;
  const live = Boolean(board && page.state) && page.state.stage !== "waiting";
  const alive = live ? aliveSeats(board) : [];
  const look = JSON.stringify([alive, page.mySeat]);
  if (look === page.barLook) {
    return;
  }
  page.barLook = look;
  $("round").hidden = !live;
  if (!live) {
    return;
  }
  const dots = $("dots").children;
  alive.forEach((isAlive, seat) => {
    dots[seat].classList.toggle("out", !isAlive);
    dots[seat].classList.toggle("you", seat === page.mySeat);
  });
  $("left").textContent = `${alive.filter(Boolean).length} left`;
}

// What the hint says: why someone watching has no Play button, or the next move a player hasn't made yet
function hintText(state) {
  const { learned, mySeat } = page;
  if (mySeat === null) {
    if ((state.stage !== "starting" && state.stage !== "playing") || canHopIn(state)) {
      return "";
    }
    const place = linePlace(state);
    if (place === null) {
      return "Watching. Tap to join the line";
    }
    if (state.out.includes(page.hub.player.id)) {
      return `Sitting out this round. ${placeText(place)}. Tap to leave`;
    }
    return `Watching. ${placeText(place)}. Tap to leave`;
  }
  if (state.stage !== "playing" || !page.board) {
    return "";
  }
  if (aliveSeats(page.board)[mySeat]) {
    if (!learned.slide) {
      return "Drag back anywhere, let go to slide";
    }
    return learned.brace ? "" : "Tap to brace when someone slides at you";
  }
  const sealUp = scene.pens[mySeat].seal.state !== "off";
  return sealUp && !learned.seal ? "You're a seal now. Tap near the edge to splash" : "";
}

// Only a watcher's chip takes presses, to join or leave the line. A seated player's lets drags through. Someone
// watching a round gets the Shop button beside it, and toasts above the two
function renderHint() {
  const text = hintText(page.state);
  const { stage } = page.state;
  const watching = page.mySeat === null && (stage === "playing" || (stage === "starting" && !canHopIn(page.state)));
  const look = `${text}|${page.mySeat === null}|${watching}`;
  if (look !== page.hintLook) {
    page.hintLook = look;
    $("watch-shop").hidden = !watching;
    $("toast").classList.toggle("raised", watching);
    const tap = Boolean(text) && page.mySeat === null;
    $("hint").classList.toggle("tap", tap);
    // A watcher's chip is a button to the keyboard and screen readers as well
    if (tap) {
      $("hint").tabIndex = 0;
      $("hint").setAttribute("role", "button");
    } else {
      $("hint").removeAttribute("tabindex");
      $("hint").removeAttribute("role");
    }
    // The last words stay on while the chip fades away
    if (text) {
      $("hint").textContent = text;
    }
    $("hint").classList.toggle("gone", !text);
  }
}

// A move that reached the connection drops its line from the hint
function sendMove(move, data) {
  const sent = send(data);
  if (sent) {
    page.learned[move] = true;
    renderHint();
  }
  return sent;
}

// ---------- Who's here ----------

// What the rest of the window sees this player doing, and whether a round is on for them
function activity(state) {
  const seat = page.mySeat;
  if (seat === null) {
    const place = linePlace(state);
    return [place === null ? "Watching" : place === 1 ? "Next up" : "In line", false];
  }
  const live = state.stage === "playing" || state.stage === "starting";
  if (!live || !page.board) {
    return ["Waiting for a round", false];
  }
  const alive = aliveSeats(page.board);
  const left = alive.filter(Boolean).length;
  return [alive[seat] ? `Round ${state.round} · ${left} left` : `Seal · ${left} left`, true];
}

// The hub passes on whatever it is told, even when nothing changed, so only changes go to it
function tell(text, busy) {
  const look = JSON.stringify([text, busy]);
  if (look === page.reported) {
    return;
  }
  page.reported = look;
  page.hub.status(text);
  page.hub.busy(busy);
}

function report(state) {
  if (page.hub.status && state && !page.closed) {
    tell(...activity(state));
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveRound() {
  page.closed = true;
  controls.setLive(false);
  if (page.hub.status) {
    tell("Not connected", false);
  }
}

// The people here who aren't on the ice, from the hub's list
function renderWatchers() {
  const state = page.state;
  if (!state) {
    return;
  }
  const people = page.hub.people || [];
  const seated = new Set(state.seats.filter((seat) => seat.kind === "human").map((seat) => seat.id));
  const watchers = people.filter((person) => person.here && !seated.has(person.id));
  // The hub's list counts people. The bot's number counts connections, so someone with the game open on two
  // devices is two there. It stands in only while the hub has no list
  const count = people.length ? watchers.length : state.watching;
  const shown = watchers.slice(0, WATCHER_FACES);
  // Lists arrive several times a second, and a face built again between a press and its release loses the tap. So the
  // row is only built again when other people or pictures are in it, and an away mark changes in place
  const look = JSON.stringify([count, shown.map((p) => [p.id, p.name, p.avatar, p.you])]);
  const box = $("watching");
  if (look !== page.watchLook) {
    page.watchLook = look;
    box.hidden = !count;
    const faces = shown.map(watcherFace);
    const more = count - faces.length;
    if (more > 0 && faces.length) {
      const extra = document.createElement("span");
      extra.className = "more";
      extra.textContent = `+${more}`;
      faces.push(extra);
    }
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = `${count} watching`;
    box.replaceChildren(...(count ? [...faces, label] : []));
  }
  shown.forEach((person, place) => box.children[place]?.classList.toggle("away", Boolean(person.away)));
}

// A watcher's picture. Hovering shows their name, and a tap opens their card. Someone with a penguin in a round is
// only told the name, as the card would cover their game
function watcherFace(person) {
  const face = document.createElement("button");
  face.type = "button";
  face.className = "face";
  const name = person.you ? "You" : person.name;
  face.title = name;
  face.setAttribute("aria-label", name);
  const letter = document.createTextNode(characters(name)[0]?.toUpperCase() ?? "");
  if (person.avatar) {
    const img = document.createElement("img");
    img.alt = "";
    img.addEventListener("error", () => img.replaceWith(letter));
    img.src = person.avatar;
    face.append(img);
  } else {
    face.append(letter);
  }
  face.addEventListener("click", () => {
    const { stage } = page.state;
    if (page.mySeat !== null && (stage === "starting" || stage === "playing")) {
      toast(`${isolate(person.name)} is watching.`);
    } else {
      showProfile(person.id);
    }
  });
  return face;
}

// Opens a person's profile card, by their Discord id as text, or this player's own with null. `after` runs once the
// card has closed
function showProfile(id, after = null) {
  // A finger still down on the ice must not fire a slide under the card
  controls.cancelDrag();
  openProfile(page.hub, id, after);
}

function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 2500);
}

// ---------- Leaderboard ----------

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

async function openBoard() {
  $("leaders").replaceChildren();
  $("invite").hidden = true;
  setText("you", "Loading...");
  $("board").showModal();
  if (!page.hub || page.hub.offline) {
    setText("you", "Open Penguin Wars in Discord to see the leaderboard.");
    return;
  }
  try {
    renderBoard(await page.hub.api("leaderboard"));
  } catch (e) {
    setText("you", e.message);
  }
}

function renderBoard(board) {
  $("leaders").replaceChildren(...board.top.map(boardRow));
  if (board.dm) {
    setText("you", "The leaderboard works in servers. Open Penguin Wars in a server to see it.");
  } else if (!board.top.length) {
    setText("you", "No rounds yet. Play with a friend to start the board.");
    // The hub's list counts you too, so only others in the window mean you aren't solo
    const others = (page.hub.people || []).filter((person) => !person.you && person.here);
    $("invite").hidden = others.length > 0;
  } else if (board.you) {
    setText("you", `You: #${board.you.rank} with ${plural(board.you.wins, "win")}`);
  } else {
    setText("you", "Play a round with a friend to get on the board.");
  }
}

// The leaderboard makes way for a profile card, which draws on the game's canvas, and comes back when the card closes
function profileFromBoard(id) {
  $("board").close();
  page.boardNext = true;
  showProfile(id, () => {
    if (page.boardNext) {
      page.boardNext = false;
      $("board").showModal();
    }
  });
}

// A row is one button, which opens that player's card
function boardRow(row) {
  const item = document.createElement("li");
  item.classList.toggle("mine", row.id === page.hub.player?.id);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "row";
  button.addEventListener("click", () => profileFromBoard(row.id));
  const place = document.createElement("span");
  place.className = "place";
  place.textContent = `#${row.rank}`;
  const name = document.createElement("span");
  name.className = "name";
  // Names come from Discord, so they only ever go in as text
  name.textContent = fieldName(row.name, BOARD_NAME_MAX);
  const numbers = document.createElement("span");
  numbers.className = "numbers";
  numbers.textContent = `${plural(row.wins, "win")} · ${plural(row.knockouts, "knockout")} · ${plural(row.rounds, "round")}`;
  button.append(place, name, numbers);
  item.append(button);
  return item;
}

// ---------- Buttons ----------

function bindButtons() {
  buildDots();
  watchBar();
  // Browsers only allow sound after a press, and the first one can land on the cards or the bar as well as the ice
  for (const press of ["pointerdown", "pointerup", "touchend", "click", "keydown"]) {
    window.addEventListener(press, () => sound.unlock(), { capture: true });
  }
  // iPhones draw a pressed button's :active look only on a page that listens for touches
  window.addEventListener("touchstart", () => {}, { passive: true });
  // Every button ticks as it is pressed. Captured, so it sounds before the press closes or swaps the button
  document.addEventListener(
    "click",
    (e) => {
      if (e.target.closest?.("button, .hint.tap")) {
        sound.play("tap");
      }
    },
    true,
  );
  $("back").addEventListener("click", () => backToMenu());
  $("message-back").addEventListener("click", () => backToMenu());
  $("hint").addEventListener("click", () => {
    if ($("hint").classList.contains("tap")) {
      send({ line: linePlace(page.state) === null });
    }
  });
  $("hint").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      $("hint").click();
    }
  });
  $("go").addEventListener("click", () => send(GO_SENDS[$("go").dataset.send]));
  $("start").addEventListener("click", () => send({ start: true }));
  $("stand").addEventListener("click", () => send({ stand: true }));
  $("again").addEventListener("click", () => send({ start: true }));
  $("open-board").addEventListener("click", openBoard);
  $("open-profile").addEventListener("click", () => showProfile(null));
  bindShop(scene);
  // Opening the wardrobe gives up this player's seat and place in the line, so the others carry on without them
  for (const id of ["open-shop", "end-shop", "watch-shop"]) {
    $(id).addEventListener("click", () => {
      document.body.classList.remove("new-looks");
      send({ stand: true });
      openShop(page.hub);
    });
  }
  // The gear opens at any time, and a finger still down on the ice must not fire a slide under the dialog
  $("open-settings").addEventListener("click", () => controls.cancelDrag());
  $("close-board").addEventListener("click", () => $("board").close());
  $("invite").addEventListener("click", () => {
    $("board").close();
    page.hub.openPeople?.();
  });
  // Like the gear, the sound button opens a panel over the ice, so a finger still down there must not fire a slide
  bindSound(sound, () => controls.cancelDrag());
}

function send(data) {
  return page.conn ? page.conn.send(data) : false;
}

start();
