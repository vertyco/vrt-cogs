// Texas Hold'em's part of the dock: the action bar on the player's turn, the moves they can tick before it comes, the
// buy-in (sitting down, the bot's offers, topping up), standing up, and the name of their hand. The scene draws the
// table and the bot deals every card and checks every move, so this only sends what the player chose.
// Every button is in index.html from the start: table states arrive up to 4 times a second, and a button rebuilt
// between a press and its release would lose the press.
import { button, make, money } from "./format.js";
import { handNames } from "./scenes/holdem_seats.js";

// Raise sizes as a share of the pot once the player has called. Min and All in are the ask's own ends
const POT_SHARES = { half: 0.5, three: 0.75, pot: 1 };
// A long name in the dock's sentences is cut to this many visible characters, as the lobby cuts names, and to no
// fewer than NAME_LEAST (six of its letters and the "…") before a shorter way of saying it is tried
const NAME_MAX = 12;
const NAME_LEAST = 7;
// A hand's short name stands in for its whole one only while it still says the rank: "Trips Ks", "A high", never a
// bare "Pair"
const RANKED = /\b(?:[AKQJ2-9]|10|Aces|Kings|Queens|Jacks)s?\b/;
// What a person sees as single characters, so a flag or a joined emoji is never split
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;
// Measures words in the status line's font, to find the longest way of saying something that fits it
const meter = document.createElement("canvas").getContext("2d");
// The question keeps its two words together when the title wraps on a phone
const DIALOG_TITLES = {
  seat: "Buy in",
  top: "Top up",
  join: "A real game is starting. Buy in?",
  broke: "You're out of chips. Top up?",
};
// The offers the bot makes; the other dialogs are the player's own idea
const OFFERS = new Set(["join", "broke"]);
const ALL_IN = "You're all in";

// A hand's name inside a sentence: "a pair of Kings", "two pair, Kings and Sevens", "a flush, King high". A short
// name that starts with its rank keeps it as it is: "A high", "Ks full of 2s"
function phrase(name) {
  if (/^(?:[AKQJ]|\d+)s?\b/.test(name)) {
    return name;
  }
  const lower = name.charAt(0).toLowerCase() + name.slice(1);
  return /^(pair|straight|flush|full house|royal flush)/.test(lower) ? `a ${lower}` : lower;
}

// The characters a person sees in a name, so a flag or a joined emoji counts as one
function letters(name) {
  return segmenter ? Array.from(segmenter.segment(name), (part) => part.segment) : Array.from(name);
}

// A name at most this many visible characters long, cut by whole characters
function cutName(name, most) {
  const all = letters(name);
  return all.length > most ? `${all.slice(0, most - 1).join("")}…` : name;
}

// The ways to show these names, shortest last: each cut to the lobby's length, then the longest one character
// shorter at a time, so a short name stays whole while a long one gives up what the line needs, down to `least`
function nameCuts(names, least) {
  const lengths = names.map((name) => Math.min(letters(name).length, NAME_MAX));
  const cuts = [];
  for (;;) {
    cuts.push(names.map((name, index) => cutName(name, lengths[index])));
    const longest = Math.max(0, ...lengths);
    if (longest <= least) {
      return cuts;
    }
    lengths[lengths.indexOf(longest)] -= 1;
  }
}

// A hand's name in a sentence, whole (form 0) or by its short name (form 1) when it has one that keeps the rank
function handPhrase(name, form) {
  const short = handNames(name)[1];
  return phrase(form && short && RANKED.test(short) ? short : name);
}

// Every way to say how a hand ended, longest first. say(shown, form) words it with the names as shown and the hand
// whole (form 0) or by its short name (form 1). The names come whole, then cut to the lobby's length, then the hand
// takes its short name, then the longest names are cut, keeping six letters of each. Past that a line with amounts
// drops them (bare) before any name is cut further: the words saying how the hand ended always stay whole
function wordings({ names, say, bare = null }) {
  const cuts = nameCuts(names, NAME_LEAST);
  const further = nameCuts(names, 2).slice(cuts.length);
  const choices = [say(names, 0), say(cuts[0], 0), ...cuts.map((shown) => say(shown, 1))];
  if (bare) {
    choices.push(...cuts.map((shown) => bare(shown)));
  }
  choices.push(...further.map((shown) => (bare ?? say)(shown, 1)));
  return [...new Set(choices)];
}

function $(id) {
  return document.getElementById(id);
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

// What a quick size raises to: the call, then that share of the pot once called, kept inside the ask's range
export function quickSize(ask, size) {
  if (size === "min") {
    return ask.min_to;
  }
  if (size === "all") {
    return ask.max_to;
  }
  const to = ask.bet + ask.call + Math.round(POT_SHARES[size] * (ask.pot + ask.call));
  return clamp(to, ask.min_to, ask.max_to);
}

// The amounts a slider stops at: both ends exactly, and every multiple of the step between them. The range input runs
// over the stops' positions, 0 to top, so an odd end such as 1,234 can still be picked
export function ladder(low, high, step) {
  const first = (Math.floor(low / step) + 1) * step;
  const last = (Math.ceil(high / step) - 1) * step;
  const inner = last >= first ? (last - first) / step + 1 : 0;
  const top = high > low ? inner + 1 : 0;
  return {
    top,
    at: (index) => (index <= 0 ? low : index >= top ? high : first + (index - 1) * step),
    index(amount) {
      if (amount <= low) {
        return 0;
      }
      if (amount >= high) {
        return top;
      }
      if (!inner) {
        return amount - low < high - amount ? 0 : top;
      }
      return clamp(Math.round((amount - first) / step) + 1, 1, inner);
    },
  };
}

// A range input's gold track fills up to its knob (the .volume look)
function fill(slider, stops) {
  slider.style.setProperty("--level", `${stops.top ? (Number(slider.value) / stops.top) * 100 : 100}%`);
}

// The raise button's two lines: what the move is, and the amount
function raiseWords(asked, amount) {
  if (amount >= asked.max_to) {
    return ["All in", money(amount)];
  }
  return [asked.bet + asked.call === 0 ? "Bet" : "Raise to", money(amount)];
}

// The check or call button's two lines. A call that takes every chip the player has left is an all in
function callWords(asked, stack) {
  if (asked.moves.includes("check")) {
    return ["Check", ""];
  }
  return [asked.call >= stack ? "All in" : "Call", money(asked.call)];
}

function setWords(node, [verb, sum]) {
  node.querySelector(".verb").textContent = verb;
  node.querySelector(".sum").textContent = sum;
}

export class HoldemDock {
  // view: the TableView, for the table's state and the player's id, and its page for send, sound, toast, me() and
  // casino()
  constructor(view) {
    this.view = view;
    this.page = view.page;
    this.state = null;
    // The bot's open question to this player (moves, call, min_to, max_to, pot, bet), while the bar is up
    this.asked = null;
    this.raiseTo = 0;
    this.stops = ladder(0, 0, 1);
    // The move just sent, in words, shown until the table plays it
    this.pending = "";
    // The move ticked in advance: "check_fold", "check" or "call_any"
    this.advance = null;
    this.street = undefined;
    // The player's latest cards message, for the name of their hand
    this.cards = null;
    // The hand whose betting is over on screen: a showdown or a win played, and no table has said so yet
    this.settled = null;
    // While a new hand is dealt, before its table arrives: the hand the last table was about, and whether the deal
    // has given the player cards or taken their blind
    this.dealing = null;
    this.dealtIn = false;
    // The player's own latest move this betting round in words ("You called 20"), and the round's biggest bet and
    // the player's own as the table plays them
    this.myMove = "";
    this.topBet = 0;
    this.myBet = 0;
    // The hands shown at this hand's showdown, every way of saying how it ended (longest first), and how many of the
    // player's cards the scene has dealt them while a new hand is dealt (their hand's name waits for the second)
    this.shown = {};
    this.result = [];
    this.landedCards = 0;
    this.standing = false;
    // What the buy-in is open for: kind (a DIALOG_TITLES key), seat, low, high, stops, the offer's deadline, and
    // whether it shows as a strip in the dock instead of the dialog
    this.dialog = null;
    this.buyAmount = 0;
    this.bound = [];
    this.bind();
    $("holdem").hidden = false;
    // An upright screen's dock lays out for Hold'em: its bar slides in over the dock (style.css)
    $("table").classList.add("holdem-table");
  }

  listen(node, event, handler) {
    node.addEventListener(event, handler);
    this.bound.push([node, event, handler]);
  }

  bind() {
    this.listen($("hd-fold"), "click", () => this.press("fold"));
    this.listen($("hd-call"), "click", () => this.press($("hd-call").dataset.move));
    this.listen($("hd-raise"), "click", () => this.press("raise"));
    this.listen($("hd-slider"), "input", () => this.setRaise(this.stops.at(Number($("hd-slider").value)), null));
    for (const node of $("hd-sizes").children) {
      this.listen(node, "click", () => this.pickSize(node.dataset.size));
    }
    for (const node of $("hd-ticks").children) {
      this.listen(node, "click", () => this.toggle(node.dataset.advance));
    }
    this.listen($("hd-top-up"), "click", () => this.openTopUp());
    this.listen($("hd-stand"), "click", () => this.stand());
    this.listen($("hd-buyin-slider"), "input", () => this.slideBuyIn());
    this.listen($("hd-buyin-post"), "click", () => this.buyIn(true));
    this.listen($("hd-buyin-wait"), "click", () => this.buyIn(false));
    this.listen($("hd-buyin-yes"), "click", () => this.buyIn(false));
    this.listen($("hd-buyin-no"), "click", () => this.dismiss());
    // The dialog closed some other way, such as with Escape, means the same as its No button. A dialog that moved into
    // the dock, or was closed and opened again for something new, is left alone
    this.listen($("hd-buyin"), "close", () => {
      if (this.dialog && !this.dialog.strip && !$("hd-buyin").open) {
        this.dismiss();
      }
    });
  }

  close() {
    for (const [node, event, handler] of this.bound) {
      node.removeEventListener(event, handler);
    }
    this.closeDialog();
    this.asked = null;
    this.pending = "";
    this.state = null;
    this.draw();
    $("holdem").hidden = true;
    $("table").classList.remove("holdem-table", "holdem-offering");
  }

  // ---------- What the table says ----------

  render(state) {
    // A new hand that no button announced (after a reconnect, or events skipped while the page fell behind): the last
    // hand's result and shown hands are over with it
    if (this.dealing === null && this.state && state && state.hand !== this.state.hand) {
      this.shown = {};
      this.result = [];
      this.newRound(true);
    }
    if (this.dealing !== null && state?.hand !== this.dealing) {
      this.dealing = null;
      this.dealtIn = false;
    }
    this.state = state;
    if (state && state.street !== this.street) {
      this.newStreet(state.street);
    }
    this.topBet = Math.max(this.topBet, ...(state?.seats || []).map((taker) => (taker ? taker.bet : 0)));
    if (!this.view.waitingOnMe()) {
      this.asked = null;
      this.pending = "";
    }
    const seat = this.mySeat();
    if (seat) {
      this.myBet = seat.bet;
    }
    if (this.advance === "check" && this.facing() > 0) {
      this.advance = null;
    }
    if (!seat) {
      this.advance = null;
      this.standing = false;
    }
    this.recheckDialog(seat);
    this.draw();
  }

  // A new street: last street's ticks and the player's last move no longer apply. A new hand's first table only
  // confirms the deal its button began, so the blinds the player posted still stand. A table in the middle of a round
  // (after a reconnect) says what the player did last in it
  newStreet(street) {
    const opening = this.street === null && street === "preflop";
    this.street = street;
    this.advance = null;
    if (!opening) {
      this.newRound();
    }
    const seat = this.mySeat();
    if (!this.myMove && seat?.last) {
      this.topBet = this.betBefore(seat);
      this.myMove = this.moveSentence(seat.last);
    }
  }

  // The bot asks for a move. A ticked advance move is sent at once; otherwise the bar slides in
  ask(message) {
    const move = this.advanceMove(message.moves);
    this.advance = null;
    if (move) {
      this.send(move, message);
      return;
    }
    // The bar comes up over an open offer's strip, which hides and then waits for the bot to send that offer again with
    // its time started over, so it never comes back for a moment with the countdown it had. An offer that opens while
    // the bar is up shows as soon as the bar goes
    if (this.dialog?.strip) {
      this.dialog.held = true;
    }
    this.asked = message;
    this.pending = "";
    this.drawAsk();
    this.draw();
    this.view.renderStatus();
  }

  hole(message) {
    this.cards = message;
    this.dealtIn = this.dealtIn || this.dealing !== null;
    this.draw();
    this.view.renderStatus();
  }

  // The table plays an event. A move, a deal or the end of a round means the turn is over on screen, so its countdown
  // stops until the next turn's table; the player's own move lets the words standing in for it go
  played(event) {
    if (event.kind !== "seat" && event.kind !== "unseat" && this.view.deadline !== null) {
      this.view.deadline = null;
      this.view.tick();
    }
    if (event.kind === "show" || event.kind === "win") {
      this.settled = this.state?.hand ?? null;
      this.draw();
    }
    if (event.kind === "show") {
      this.shown = { ...this.shown, ...event.hands };
    }
    if (event.kind === "win") {
      this.result = this.resultSentence(event);
    }
    if (event.kind === "button") {
      // A new hand: its table comes once the cards have flown. A Top up left open closes, as the hand has begun
      this.dealing = this.state?.hand ?? null;
      this.dealtIn = false;
      this.landedCards = 0;
      this.shown = {};
      this.result = [];
      this.newRound(true);
      if (this.dialog?.kind === "top") {
        this.closeDialog();
      }
      this.draw();
    }
    if (event.kind === "sweep") {
      this.newRound();
    }
    if (event.kind === "act" && event.seat === this.mySeat()?.seat) {
      // The player's move is played, even one the bot made for them when their time ran out: the bar goes
      this.dealtIn = this.dealtIn || this.dealing !== null;
      this.myMove = this.moveSentence(event);
      this.myBet = event.amount;
      this.pending = "";
      this.asked = null;
      this.draw();
    }
    if (event.kind === "act") {
      this.topBet = Math.max(this.topBet, event.amount);
    }
    this.view.renderStatus();
  }

  // The scene has played an event: once it has dealt the player their second card, their hand's name may show
  landed(event) {
    if (event.kind === "pitch" && this.dealing !== null && event.seat === this.mySeat()?.seat) {
      this.landedCards += 1;
      this.view.renderStatus();
    }
  }

  // A new betting round: no bets yet, and the player's last move no longer applies, unless they are all in, which
  // holds through the cards still to come. A new hand clears that too
  newRound(hand = false) {
    if (hand || this.myMove !== ALL_IN) {
      this.myMove = "";
    }
    this.topBet = 0;
    this.myBet = 0;
  }

  // How the hand ended, every way of saying it for the status line, longest first (wordings): "You won 608 with a
  // pair of Kings", "Split pot: you won 304". A split is one pot shared by its winners; side pots won by different
  // players are no split
  resultSentence({ awards }) {
    const shares = {};
    for (const award of awards) {
      for (const [number, amount] of Object.entries(award.shares)) {
        shares[number] = (shares[number] || 0) + amount;
      }
    }
    const sharers = (award) => Object.keys(award.shares).filter((number) => award.shares[number] > 0);
    const split = new Set(awards.filter((award) => sharers(award).length > 1).flatMap(sharers));
    const winners = Object.keys(shares).filter((number) => shares[number] > 0);
    const mine = String(this.mySeat()?.seat);
    const found = winners.includes(mine)
      ? this.myResult(mine, money(shares[mine]), split.has(mine))
      : this.othersResult(winners, shares, split.size > 0);
    return found ? wordings(found) : [];
  }

  // The player's own result, worded as wordings() asks: "You won 608 with a pair of Kings", "Split pot: you won 304"
  myResult(mine, won, split) {
    const hand = this.shownName(mine);
    if (split) {
      return { names: [], say: () => `Split pot: you won ${won}` };
    }
    if (!hand) {
      return { names: [], say: () => `You won ${won}` };
    }
    return { names: [], say: (shown, form) => `You won ${won} with ${handPhrase(hand, form)}` };
  }

  // How the hand ended for others, worded as wordings() asks: "Manager won with a pair of Aces", "Split pot: Ann and
  // Bo", or "Ann won 300 and Bo won 500" when side pots went to different players ("Ann and Bo split the pot"
  // where that won't fit)
  othersResult(winners, shares, split) {
    const seats = this.state?.seats || [];
    const people = winners.filter((number) => seats[number]);
    if (!people.length) {
      return null;
    }
    const names = people.map((number) => seats[number].name);
    if (split) {
      return { names, say: (shown) => `Split pot: ${shown.join(" and ")}` };
    }
    if (people.length > 1) {
      const say = (shown) => shown.map((name, index) => `${name} won ${money(shares[people[index]])}`).join(" and ");
      return { names, say, bare: (shown) => `${shown.join(" and ")} split the pot` };
    }
    const [one] = people;
    const hand = this.shownName(one);
    if (!hand) {
      return { names, say: ([name]) => `${name} won ${money(shares[one])}` };
    }
    return { names, say: ([name], form) => `${name} won with ${handPhrase(hand, form)}` };
  }

  // The first of these words that fits the status line beside its clock, else the shortest. The line's own font
  // measures them, so a long name never pushes how the hand ended out of sight
  fitStatus(choices) {
    const status = $("status");
    const style = getComputedStyle($("status-text"));
    meter.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const gap = parseFloat(getComputedStyle(status).columnGap) || 0;
    const room = status.clientWidth - $("clock").offsetWidth - gap - 1;
    return choices.find((words) => meter.measureText(words).width <= room) ?? choices[choices.length - 1];
  }

  // The name of a seat's hand shown at this showdown. The latest table has it: after an all-in run-out the bot names
  // the hands again with each card, and the show event came before those cards
  shownName(number) {
    return this.state?.shown?.[number]?.name || this.shown[number]?.name || "";
  }

  // The biggest bet before the player's own move, as far as a table shows it after a reconnect: before the flop the
  // big blind, otherwise the biggest bet below theirs
  betBefore(seat) {
    const below = this.state.seats.filter((taker) => taker && taker.bet < seat.bet).map((taker) => taker.bet);
    return Math.max(this.state.street === "preflop" ? this.blinds()[1] : 0, ...below);
  }

  // The player's own move in words, as the table plays it: "You posted the big blind 20", "You called 20"
  moveSentence({ move, amount }) {
    const big = this.blinds()[1];
    const sentences = {
      blind: `You posted the ${amount >= big ? "big" : "small"} blind ${money(amount)}`,
      post: `You paid ${money(amount)} to play now`,
      check: "You checked",
      call: `You called ${money(amount)}`,
      raise: this.topBet > 0 ? `You raised to ${money(amount)}` : `You bet ${money(amount)}`,
      all_in: ALL_IN,
      return: this.myBet > amount ? `You got ${money(this.myBet - amount)} back` : "You got chips back",
    };
    return sentences[move] ?? "";
  }

  offer(message) {
    if (message.kind === null) {
      if (OFFERS.has(this.dialog?.kind)) {
        this.closeDialog();
      }
      return;
    }
    this.openDialog(message.kind, { low: message.min, high: message.max, left: message.left });
  }

  // A tap on a seat in the scene. Alone at the table it's a free practice seat; anyone else buys in
  chooseSeat(number) {
    const seats = this.state?.seats;
    if (!seats || seats[number] !== null || this.mySeat()) {
      return;
    }
    if (!seats.some((seat) => seat && !seat.cpu)) {
      this.page.send({ t: "sit", seat: number });
      return;
    }
    const game = this.page.casino()?.games?.holdem;
    if (!game) {
      return;
    }
    // Back within 30 minutes of standing up, the player must bring at least what they left with
    const floor = this.page.me()?.holdem_floor ?? 0;
    this.openDialog("seat", { low: Math.max(game.min, floor), high: Math.max(game.max, floor), seat: number });
  }

  // The people here for the dock's list: the player's own row first. Where the list keeps to its room (one row on an
  // upright screen, the rows down to the dock's bottom on a sideways phone) it shows as many whole entries as fit and
  // then "+N", which opens the hub's people panel with everyone. Null when the list already shows just this, so its
  // buttons stay put and a tap that spans a table still lands
  peopleRow(rows, list) {
    const mine = rows.filter((row) => row.classList.contains("me"));
    const ordered = [...mine, ...rows.filter((row) => !mine.includes(row))];
    const fit = Math.min(ordered.length, this.peopleRoom(list, ordered.length));
    const key = JSON.stringify([this.state?.players, this.view.myId(), fit]);
    if (key === this.peopleKey) {
      return null;
    }
    this.peopleKey = key;
    if (fit === ordered.length) {
      return ordered;
    }
    const rest = ordered.length - fit;
    const item = make("li", "more");
    // The hub's own people button in the top bar opens its list of everyone here
    const open = button(`+${rest}`, "", () => document.querySelector(".tools .hub-people-button")?.click());
    open.setAttribute("aria-label", `${rest} more here. See everyone`);
    item.append(open);
    return [...ordered.slice(0, fit), item];
  }

  // How many whole entries the people list has room for: all of them unless it keeps to its room, then as many as fit
  // with the "+N" after them, each --person long and the "+N" --more (style.css). With no room for one beside the
  // "+N", the "+N" alone stands for everyone
  peopleRoom(list, count) {
    const style = getComputedStyle(list);
    const more = parseFloat(style.getPropertyValue("--more"));
    if (!more) {
      return count;
    }
    const entry = parseFloat(style.getPropertyValue("--person"));
    const across = style.flexDirection === "row";
    const gap = parseFloat(across ? style.columnGap : style.rowGap) || 0;
    let room = list.clientWidth;
    if (!across) {
      // Down to the dock's bottom, measured as if the dock weren't scrolled, or on the player's turn down to the top of
      // the bar, which covers the dock's bottom then
      const dock = list.closest(".dock");
      const top = list.getBoundingClientRect().top + dock.scrollTop;
      const bar = $("hd-bar");
      const bottom = bar.classList.contains("up")
        ? bar.getBoundingClientRect().top + dock.scrollTop
        : dock.getBoundingClientRect().bottom - parseFloat(getComputedStyle(dock).paddingBottom);
      room = bottom - top;
    }
    if (count * (entry + gap) - gap <= room) {
      return count;
    }
    return Math.max(0, Math.floor((room - more) / (entry + gap)));
  }

  // ---------- Facts about the table ----------

  mySeat() {
    const me = this.view.myId();
    return (this.state?.seats || []).find((seat) => seat && seat.id === me) || null;
  }

  // Chips the player must add to stay in, from the bets in front of every seat
  facing() {
    const seat = this.mySeat();
    if (!seat) {
      return 0;
    }
    const top = Math.max(0, ...(this.state.seats || []).map((taker) => (taker ? taker.bet : 0)));
    return top - seat.bet;
  }

  // True while the bot may still ask this player for a move this hand: they're in and can bet, the showdown hasn't
  // begun (on the table or on screen), and someone is left to bet against them or they still owe chips. All in
  // run-outs ask nobody
  canBeAsked(seat) {
    const state = this.state;
    if (!seat || !seat.in_hand || seat.folded || seat.all_in || !state.street) {
      return false;
    }
    if (Object.keys(state.shown || {}).length || state.hand === this.settled) {
      return false;
    }
    const others = state.seats.filter((taker) => taker && taker !== seat && taker.in_hand && !taker.folded);
    return others.some((taker) => !taker.all_in) || this.facing() > 0;
  }

  blinds() {
    const stakes = this.state?.stakes;
    if (stakes) {
      return [stakes.small, stakes.big];
    }
    return this.page.casino()?.games?.holdem?.blinds || [1, 1];
  }

  // The name of the player's hand, for this hand or the one being dealt: while it is dealt, once both their cards
  // have landed face up
  handName() {
    const cards = this.cards;
    if (this.dealing !== null && this.landedCards < 2) {
      return "";
    }
    return cards && this.state && cards.hand >= this.state.hand ? cards.name : "";
  }

  // In this hand on screen: the table says so, or the deal now playing gave the player cards or took their blind
  inHand(seat) {
    return Boolean(seat?.in_hand) || (this.dealing !== null && this.dealtIn);
  }

  statusText() {
    const seat = this.mySeat();
    // Someone watching reads how the hand ended too, until the next hand starts
    if (!seat && this.result.length) {
      return this.fitStatus(this.result);
    }
    if (!seat) {
      const seats = this.state.seats || [];
      if (!seats.includes(null)) {
        return "The table is full. Watch until a seat opens.";
      }
      return seats.some((taker) => taker && !taker.cpu)
        ? "Tap an empty seat to buy in."
        : "Tap an empty seat to practice for free.";
    }
    const playing = this.inHand(seat);
    if (this.standing) {
      return playing ? "You stand up when this hand ends." : "Standing up...";
    }
    if (this.result.length) {
      return this.fitStatus(this.result);
    }
    if (playing && !seat.folded) {
      const name = this.handName();
      const lead = this.asked ? "Your turn" : this.myMove;
      return [lead, name].filter(Boolean).join(" · ") || "Good luck!";
    }
    if (playing) {
      return "You folded. Next hand soon.";
    }
    if (seat.waiting) {
      return "You join when the big blind reaches you.";
    }
    return this.state.street ? "You're dealt in next hand." : "Next hand in a moment.";
  }

  // ---------- Moves ----------

  advanceMove(moves) {
    const free = moves.includes("check");
    switch (this.advance) {
      case "check_fold":
        return free ? "check" : "fold";
      case "check":
        return free ? "check" : null;
      case "call_any":
        return moves.includes("call") ? "call" : free ? "check" : null;
      default:
        return null;
    }
  }

  press(move) {
    if (!this.asked || !this.asked.moves.includes(move)) {
      return;
    }
    this.page.sound.play("click");
    this.send(move, this.asked);
  }

  // The move goes to the bot, and the bar gives way to it in words straight away, before the bot answers
  send(move, asked) {
    const message = { t: "move", move };
    if (move === "raise") {
      message.amount = this.raiseTo;
    }
    this.page.send(message);
    let words = ["Fold"];
    if (move === "raise") {
      words = raiseWords(asked, this.raiseTo);
    } else if (move !== "fold") {
      words = callWords(asked, this.mySeat()?.stack ?? Infinity);
    }
    this.pending = words.filter(Boolean).join(" ");
    this.asked = null;
    this.draw();
    this.view.renderStatus();
  }

  pickSize(size) {
    if (!this.asked) {
      return;
    }
    this.page.sound.play("click");
    this.setRaise(quickSize(this.asked, size), size);
  }

  setRaise(amount, size) {
    if (!this.asked) {
      return;
    }
    this.raiseTo = amount;
    const slider = $("hd-slider");
    slider.value = String(this.stops.index(amount));
    fill(slider, this.stops);
    setWords($("hd-raise"), raiseWords(this.asked, amount));
    for (const node of $("hd-sizes").children) {
      node.setAttribute("aria-pressed", String(node.dataset.size === size));
    }
  }

  toggle(advance) {
    this.page.sound.play("click");
    this.advance = this.advance === advance ? null : advance;
    this.draw();
  }

  stand() {
    this.page.sound.play("click");
    this.standing = true;
    this.page.send({ t: "stand" });
    this.draw();
    this.view.renderStatus();
  }

  // ---------- Drawing ----------

  // Everything is updated in place
  draw() {
    const seat = this.mySeat();
    const acting = Boolean(this.asked);
    $("hd-deck").hidden = !seat;
    $("hd-bar").classList.toggle("up", acting);
    $("hd-wait").classList.toggle("down", acting);
    $("hd-pending").hidden = !this.pending;
    $("hd-pending").textContent = this.pending;
    this.drawTicks(seat);
    $("hd-stand").hidden = !seat;
    $("hd-stand").disabled = this.standing;
    // More credits between hands, while the stack has room under the Max
    const max = this.state?.stakes?.max ?? 0;
    const between = this.dealing === null && !this.inHand(seat);
    $("hd-top-up").hidden = !(seat && this.state.mode === "real" && between && seat.stack < max);
    // Practice chips are play chips, never credits
    $("hd-note").hidden = this.state?.mode !== "practice";
    this.drawStrip();
  }

  // An offer's strip hides while the bar is up: the bot holds its clock until the player has moved, then sends it
  // again with all its time, so it never runs down out of sight under the bar. A strip the bar came up over waits for
  // that message (ask)
  drawStrip() {
    const dialog = this.dialog;
    const strip = Boolean(dialog?.strip) && !this.asked && !dialog.held;
    $("hd-offer").hidden = !strip;
    // A sideways phone makes room for an offer's strip (style.css)
    $("table").classList.toggle("holdem-offering", strip);
    // The ticks, the move just sent and the offer change the room the people list has on a sideways phone
    this.view.renderPlayers();
  }

  // Shown while the player waits for a turn that can still come
  drawTicks(seat) {
    const waiting = !this.asked && !this.pending && !this.view.waitingOnMe();
    $("hd-ticks").hidden = !(waiting && this.canBeAsked(seat));
    const facing = this.facing();
    for (const node of $("hd-ticks").children) {
      node.setAttribute("aria-pressed", String(node.dataset.advance === this.advance));
      node.disabled = node.dataset.advance === "check" && facing > 0;
    }
  }

  // The bar's buttons for this ask, set once when it arrives
  drawAsk() {
    const asked = this.asked;
    const free = asked.moves.includes("check");
    // Fold keeps its place, greyed, when a check is free: the bot doesn't take a fold then
    $("hd-fold").disabled = !asked.moves.includes("fold");
    $("hd-call").dataset.move = free ? "check" : "call";
    setWords($("hd-call"), callWords(asked, this.mySeat()?.stack ?? Infinity));
    const raise = asked.moves.includes("raise");
    $("hd-raise").hidden = !raise;
    // With no room between the smallest raise and all in, there is nothing to slide, but the space stays so the
    // table above the dock doesn't jump
    $("hd-sizer").classList.toggle("off", !raise || asked.max_to <= asked.min_to);
    if (raise) {
      this.stops = ladder(asked.min_to, asked.max_to, Math.max(1, this.blinds()[1]));
      $("hd-slider").max = String(this.stops.top);
      this.setRaise(asked.min_to, "min");
    }
  }

  // ---------- The buy-in ----------

  openDialog(kind, { low, high, seat = null, left = null }) {
    const deadline = left === null ? null : performance.now() + left * 1000;
    const stops = ladder(low, high, Math.max(1, this.blinds()[1]));
    this.dialog = { kind, seat, low, high, deadline, stops, strip: false };
    // The most the player can pay, or the least allowed when they're short
    this.buyAmount = clamp(this.page.me()?.balance ?? 0, low, high);
    $("hd-buyin-title").textContent = DIALOG_TITLES[kind];
    $("hd-buyin-min").textContent = money(low);
    $("hd-buyin-max").textContent = money(high);
    $("hd-buyin-slider").max = String(stops.top);
    this.drawWaysIn();
    this.drawBuyIn();
    this.tick();
    this.place();
  }

  // The open buy-in still fits the table: a seat someone else took, or a top-up once the player is dealt in, closes;
  // the ways in follow the table's mode, and an offer moves into the dock once the player is dealt in
  recheckDialog(seat) {
    const dialog = this.dialog;
    if (!dialog) {
      return;
    }
    if (dialog.kind === "seat" && (seat || (this.state && this.state.seats[dialog.seat] !== null))) {
      if (!seat) {
        this.page.toast("That seat was just taken.");
      }
      this.closeDialog();
      return;
    }
    if (dialog.kind === "top" && (!seat || this.inHand(seat))) {
      this.closeDialog();
      return;
    }
    this.drawWaysIn();
    this.drawBuyIn();
    this.place();
  }

  // Where the buy-in shows. An offer to a player dealt into a hand is a strip in the dock, so the table stays free
  // while its clock runs; once there it stays. Anything else is the dialog
  place() {
    const dialog = this.dialog;
    const box = $("hd-buyin");
    if (dialog) {
      dialog.strip = dialog.strip || Boolean(OFFERS.has(dialog.kind) && this.inHand(this.mySeat()));
      const home = dialog.strip ? $("hd-offer") : box;
      if ($("hd-buyin-body").parentNode !== home) {
        home.append($("hd-buyin-body"));
      }
    }
    this.drawStrip();
    if (dialog && !dialog.strip && !box.open) {
      box.showModal();
    } else if ((!dialog || dialog.strip) && box.open) {
      box.close();
    }
  }

  // In a real game a new player picks how to join: pay a big blind now, or wait for it to come round
  drawWaysIn() {
    const { kind } = this.dialog;
    const [small, big] = this.blinds();
    const real = kind === "seat" && this.state?.mode === "real";
    $("hd-buyin-note").textContent = `Blinds ${money(small)} / ${money(big)}`;
    $("hd-buyin-post").textContent = `Pay ${money(big)} and play now`;
    $("hd-buyin-post").hidden = !real;
    $("hd-buyin-wait").hidden = !real;
    $("hd-buyin-yes").hidden = real;
    $("hd-buyin-yes").querySelector(".verb").textContent = kind === "top" || kind === "broke" ? "Top up" : "Buy in";
    // Saying no to an offer stands the player up to watch, and its button says so
    $("hd-buyin-no").textContent = OFFERS.has(kind) ? "Watch instead" : "Cancel";
  }

  openTopUp() {
    const seat = this.mySeat();
    const max = this.state?.stakes?.max ?? 0;
    if (!seat || seat.stack >= max) {
      return;
    }
    this.page.sound.play("click");
    this.openDialog("top", { low: 1, high: max - seat.stack });
  }

  drawBuyIn() {
    const { low, stops } = this.dialog;
    const balance = this.page.me()?.balance ?? 0;
    const slider = $("hd-buyin-slider");
    slider.value = String(stops.index(this.buyAmount));
    slider.disabled = stops.top === 0;
    fill(slider, stops);
    $("hd-buyin-amount").textContent = money(this.buyAmount);
    $("hd-buyin-yes").querySelector(".sum").textContent = money(this.buyAmount);
    const short = balance < low;
    let why = "";
    if (short) {
      why = `Your balance of ${money(balance)} is under the ${money(low)} minimum.`;
    } else if (this.buyAmount > balance) {
      why = `That's more than your balance of ${money(balance)}.`;
    }
    $("hd-buyin-why").hidden = !why;
    $("hd-buyin-why").textContent = why;
    // An upright screen's strip shows the reason in place of what it stops (style.css): the slider and Buy in when the
    // balance is under the minimum, only Buy in when the amount is past the balance, so the slider can come back
    $("hd-buyin-body").classList.toggle("blocked", short);
    $("hd-buyin-body").classList.toggle("over", Boolean(why) && !short);
    for (const id of ["hd-buyin-post", "hd-buyin-wait", "hd-buyin-yes"]) {
      $(id).disabled = Boolean(why);
    }
  }

  slideBuyIn() {
    this.buyAmount = this.dialog.stops.at(Number($("hd-buyin-slider").value));
    this.drawBuyIn();
    // A reason line coming or going changes the strip's height, and so the room the people list has on a sideways phone
    this.view.renderPlayers();
  }

  buyIn(post) {
    const dialog = this.dialog;
    if (!dialog) {
      return;
    }
    this.page.sound.play("chip");
    if (dialog.kind === "top") {
      this.page.send({ t: "top_up", amount: this.buyAmount });
    } else {
      this.page.send({ t: "buy_in", seat: dialog.seat, amount: this.buyAmount, post });
    }
    this.closeDialog();
  }

  // No to an offer stands the player up before the next hand; any other buy-in just closes
  dismiss() {
    if (!this.dialog) {
      return;
    }
    this.page.sound.play("click");
    if (OFFERS.has(this.dialog.kind)) {
      this.page.send({ t: "decline" });
    }
    this.closeDialog();
  }

  closeDialog() {
    this.dialog = null;
    this.place();
  }

  // An offer's countdown. When it runs out the bot has taken the silence as a no, so the buy-in closes
  tick() {
    const deadline = this.dialog?.deadline ?? null;
    $("hd-buyin-left").hidden = deadline === null;
    if (deadline === null) {
      return;
    }
    const left = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
    $("hd-buyin-left").textContent = `${left}s`;
    if (left <= 0) {
      this.closeDialog();
    }
  }
}
