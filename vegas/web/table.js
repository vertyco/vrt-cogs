// One table: its scene, the round's status and clock, the players at it, the player's own buttons, and results.
// The bot runs the round. Messages wait in a queue so each animation finishes before the next thing shows,
// the same pacing the bot keeps (PACE), so a result never shows before the cards or dice that decide it.
import { Application, Container } from "./vendor/pixi.min.mjs";
import { avatar, button, duration, make, money } from "./format.js";
import { HoldemDock } from "./holdem.js";
import { Tray } from "./tray.js";

// How long each kind of event animates, in seconds. The same numbers as PACE in vegas/common/table.py
export const PACE = {
  flip: 2.0,
  shuffle: 3.0,
  roll: 2.0,
  deal: 0.45,
  reveal: 0.6,
  burn: 1.2,
  pull: 3.0,
  // Hold'em
  seat: 0.4,
  unseat: 0.4,
  button: 0.4,
  act: 0.5,
  pitch: 0.15,
  sweep: 0.5,
  flop: 1.1,
  street: 0.7,
  runout: 1.6,
  show: 1.0,
  win: 1.8,
};
// A scene gets this much longer than its pace to finish, then the table moves on without waiting. An event that says
// how many seconds it takes (a Slots spin) is paced by that instead
const GRACE_MS = 350;
// A Slots win of this many times the bet or more gets the big win sound
const SLOTS_BIG_WIN = 14;
// More waiting messages than this means the page fell behind (it was hidden), so it skips the animations
const MAX_BEHIND = 12;
const RESULT_MS = 3500;
// A result card placed in the scene's spot for it keeps this far inside the spot's sides, and its top and bottom
const SPOT_INSET_X = 8;
const SPOT_INSET_Y = 3;
// The looks a placed result card tries, in order
const SHRINK_FIRST = [[], ["compact"], ["wrap"], ["wrap", "compact"]];
const BREAK_FIRST = [[], ["wrap"], ["compact"], ["wrap", "compact"]];
const SPINNING_WHEEL = "The wheel is spinning...";
const MOVE_LABELS = {
  hit: "Hit",
  stay: "Stay",
  double: "Double",
  war: "Go to war",
  surrender: "Surrender",
  cashout: "Cash out",
  keep: "Double",
  roll: "Roll",
};

function $(id) {
  return document.getElementById(id);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// How far down `node` the jackpot note reaches, in CSS pixels: from the note's own box while it shows, otherwise from
// where its style puts it under the top bar
export function noteReach(node) {
  const note = $("news");
  const top = node.getBoundingClientRect().top;
  if (!note.hidden) {
    return Math.max(0, note.getBoundingClientRect().bottom - top);
  }
  const style = getComputedStyle(note);
  const bar = document.querySelector(".top").getBoundingClientRect().bottom;
  return Math.max(0, bar + (parseFloat(style.marginTop) || 0) + (parseFloat(style.height) || 0) - top);
}

// The words and color for the player's own result
export function resultView(result, game) {
  const lines = [];
  if (result.held) {
    lines.push("It's over the payout limit, so it's held until an admin releases it.");
  }
  if (result.bonus > 0) {
    lines.push(`Includes a ${money(result.bonus)} membership bonus.`);
  }
  if (result.returned > 0) {
    lines.push(`Your war bet of ${money(result.returned)} came back too.`);
  }
  lines.push(`Balance: ${money(result.balance)}`);
  const small = lines.join(" ");
  switch (result.outcome) {
    case "win":
      return { tone: "win", big: `You win ${money(result.payout)}`, small };
    case "jackpot":
      // Joined so that a headline too long for one line breaks after "Jackpot!"
      return { tone: "win", big: `Jackpot! You win ${money(result.payout)}`, small, breaks: true };
    case "push":
      return {
        tone: "even",
        big: game === "slots" ? "Bet back" : "Push",
        small: `Your ${money(result.stake)} came back. Balance: ${money(result.balance)}`,
      };
    case "surrender":
      return {
        tone: "even",
        big: "Surrendered",
        small: `${money(result.payout)} of your ${money(result.stake)} came back. Balance: ${money(result.balance)}`,
      };
    case "bust":
      return { tone: "lose", big: "Bust", small };
    default:
      return { tone: "lose", big: ["allin", "slots"].includes(game) ? "No luck" : "House wins", small };
  }
}

export class TableView {
  // page: send(message), sound, casino(), me(), readyIn(game), showPlayer(id), toast(text), changed(), jackpot()
  // changed() is called whenever the bot sends the table's state, for the page to report what the player is doing.
  // jackpot() is the Slots pot in whole credits as the bot last said
  constructor(game, page) {
    this.game = game;
    this.page = page;
    this.state = null;
    this.moves = null;
    this.deadline = null;
    this.pulling = false;
    this.scene = null;
    this.app = null;
    this.queue = [];
    this.running = false;
    this.closed = false;
    this.resultTimer = null;
    // The winner's own jackpot note, held while their result card is up
    this.heldNote = null;
    this.tray = new Tray(game, {
      onBet: (message) => this.bet(message),
      onGo: () => this.page.send({ t: "go" }),
      onPreview: (value) => this.scene?.preview?.(value),
      sound: page.sound,
    });
    // Hold'em's own part of the dock: its action bar, buy-ins and seat buttons take the tray's place
    this.dock = game === "holdem" ? new HoldemDock(this) : null;
    this.sitHandler = () => this.sit();
    this.standHandler = () => this.page.send({ t: "stand" });
    $("sit").addEventListener("click", this.sitHandler);
    $("stand").addEventListener("click", this.standHandler);
    this.ticker = setInterval(() => this.tick(), 250);
    this.sceneReady = this.startScene();
    this.update();
  }

  // ---------- The scene ----------

  async startScene() {
    const host = $("scene");
    try {
      const app = new Application();
      await app.init({
        resizeTo: host,
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
      });
      if (this.closed) {
        app.destroy(true);
        return;
      }
      host.append(app.canvas);
      this.app = app;
      const root = new Container();
      app.stage.addChild(root);
      const module = await import(`./scenes/${this.game}.js`);
      const scene = await module.createScene(this.stage(app, root));
      if (this.closed) {
        scene.destroy?.();
        return;
      }
      this.scene = scene;
      this.observer = new ResizeObserver(() => this.layout());
      this.observer.observe(host);
      this.layout();
      if (this.state) {
        this.scene.show(this.state);
      }
      this.scene.preview?.(this.tray.preview());
      this.scene.jackpot?.(this.page.jackpot?.() ?? null);
    } catch (e) {
      console.error("Vegas: couldn't start the table's graphics", e);
      this.page.toast("This device couldn't draw the table, but you can still play.");
    }
  }

  // What a scene gets to draw with and to act for the player (the top of scenes/plain.js describes each part)
  stage(app, root) {
    const game = this.page.casino()?.games[this.game];
    return {
      app,
      root,
      game: this.game,
      title: game ? game.name : this.game,
      sound: this.page.sound,
      me: () => this.page.me()?.id || null,
      nameOf: (id) => this.nameOf(id),
      settings: () => this.page.casino()?.games[this.game],
      actions: {
        choose: (value) => this.tray.choose(value),
        sit: (seat) => (this.dock ? this.dock.chooseSeat(seat) : this.page.send({ t: "sit", seat })),
        stand: () => this.page.send({ t: "stand" }),
        move: (name) => this.sendMove(name),
        place: (strength) => this.tray.place(strength),
      },
    };
  }

  layout() {
    const host = $("scene");
    if (!this.scene || !this.app || !host.clientWidth || !host.clientHeight) {
      return;
    }
    this.app.resize();
    this.scene.layout(host.clientWidth, host.clientHeight, noteReach(host));
    this.placeResult();
    // Hold'em fits its people row and the words of its status line to the dock's new size
    if (this.dock) {
      this.renderPlayers();
      this.renderStatus();
    }
  }

  // ---------- Messages ----------

  receive(message) {
    // An offer counts down from when it was sent, so it shows at once instead of waiting behind the animations
    if (message.t === "offer") {
      this.dock?.offer(message);
      return;
    }
    this.queue.push(message);
    this.drain();
  }

  async drain() {
    if (this.running) {
      return;
    }
    this.running = true;
    await this.sceneReady;
    while (this.queue.length && !this.closed) {
      if (this.queue.length > MAX_BEHIND) {
        this.queue = this.queue.filter((message) => message.t !== "event");
      }
      const message = this.queue.shift();
      try {
        await this.handle(message);
      } catch (e) {
        console.error("Vegas: a table update failed", e);
      }
    }
    this.running = false;
  }

  async handle(message) {
    if (message.t === "table") {
      this.state = message;
      this.deadline = message.left === null ? null : performance.now() + message.left * 1000;
      if (!this.waitingOnMe()) {
        this.moves = null;
      }
      this.scene?.show(message);
      this.update();
      this.page.changed?.();
    } else if (message.t === "event") {
      await this.animate(message);
    } else if (message.t === "result") {
      this.showResult(message);
    } else if (message.t === "ask" && this.dock) {
      this.dock.ask(message);
    } else if (message.t === "ask") {
      this.moves = message.moves;
      this.renderMoves();
    } else if (message.t === "hole") {
      this.dock?.hole(message);
      this.scene?.hole?.(message);
    } else if (message.t === "jackpot") {
      // Queued behind the spin it belongs to, so the marquee moves once the reels have stopped. The winner's own note
      // then waits for their result card to hide, so the two never stack
      this.scene?.jackpot?.(message.amount);
      if (message.note && $("result").hidden) {
        this.page.news?.(message.note);
      } else if (message.note) {
        this.heldNote = message.note;
      }
    }
  }

  async animate(event) {
    this.dock?.played(event);
    if (!this.scene) {
      return;
    }
    const limit = (event.seconds ?? PACE[event.kind] ?? 0) * 1000 + GRACE_MS;
    let late = false;
    await Promise.race([this.scene.play(event), wait(limit).then(() => (late = true))]);
    // The bot has moved on by now, so an animation this slow falls behind the table
    if (late) {
      console.warn(`Vegas: the ${this.game} ${event.kind} animation ran past ${limit} ms`);
    }
    this.dock?.landed(event);
  }

  // A refused bet or move (the bot says why in a notice), or a reconnect that lost a pull: nothing is coming for it
  notice() {
    this.pulling = false;
    this.scene?.notice?.();
    this.update();
  }

  showResult(result) {
    this.pulling = false;
    const view = resultView(result, this.game);
    $("result").className = `result ${view.tone}`;
    $("result").classList.toggle("breaks", Boolean(view.breaks));
    $("result-big").textContent = view.big;
    $("result-small").textContent = view.small;
    $("result").hidden = false;
    this.placeResult();
    clearTimeout(this.resultTimer);
    this.resultTimer = setTimeout(() => this.hideResult(), RESULT_MS);
    this.playResult(result);
    this.scene?.result?.(result);
    this.update();
  }

  hideResult() {
    $("result").hidden = true;
    if (this.heldNote) {
      this.page.news?.(this.heldNote);
    }
    this.heldNote = null;
  }

  // A scene can say where the result card covers nothing that matters (All In, Slots): the card sits in the middle of
  // that spot, below a jackpot note that shows, in the first look that fits: its headline on one line, then the same
  // smaller, then wrapped, then wrapped and smaller. A headline with a place to break (a jackpot's, after "Jackpot!")
  // breaks there before it gets smaller. Without a spot, or when no look fits it, the card sits along the bottom of the
  // scene as at every other game
  placeResult() {
    const card = $("result");
    card.classList.remove("placed", "wrap", "compact");
    const spot = card.hidden ? null : this.scene?.resultSpot?.();
    if (!spot) {
      return;
    }
    const host = $("scene");
    const left = host.offsetLeft + spot.left + SPOT_INSET_X;
    const right = host.offsetLeft + spot.right - SPOT_INSET_X;
    const below = $("news").hidden ? 0 : noteReach(host.parentElement);
    const top = Math.max(host.offsetTop + spot.top, below) + SPOT_INSET_Y;
    const bottom = host.offsetTop + spot.bottom - SPOT_INSET_Y;
    card.style.setProperty("--spot-x", `${(left + right) / 2}px`);
    card.style.setProperty("--spot-y", `${(top + bottom) / 2}px`);
    card.style.setProperty("--spot-width", `${Math.max(0, right - left)}px`);
    const looks = card.classList.contains("breaks") ? BREAK_FIRST : SHRINK_FIRST;
    // The headline is measured, not the card: a headline too wide spills into the card's padding first, which the
    // card's own width doesn't count
    const big = $("result-big");
    for (const look of looks) {
      card.classList.remove("wrap", "compact");
      card.classList.add("placed", ...look);
      if (card.offsetHeight <= bottom - top && big.scrollWidth <= big.clientWidth) {
        return;
      }
    }
    card.classList.remove("placed", "wrap", "compact");
  }

  playResult(result) {
    const won = result.outcome === "win" || result.outcome === "jackpot";
    const bigAt = this.game === "slots" ? SLOTS_BIG_WIN : 5;
    const bigWin = won && (this.game === "allin" || result.payout >= result.stake * bigAt);
    const big = result.outcome === "jackpot" || bigWin;
    this.page.sound.play(won ? (big ? "bigwin" : "win") : result.payout > 0 ? "push" : "lose");
    if (won) {
      this.page.sound.play("collect");
    }
  }

  // ---------- The player's part ----------

  // False when the bet couldn't reach the bot. A pull that went waits for its spin
  bet(message) {
    const sent = this.page.send(message);
    if (sent && message.t === "pull") {
      this.pulling = true;
    }
    this.update();
    return sent;
  }

  sit() {
    const seats = this.state?.seats || [];
    const free = seats.findIndex((seat) => seat === null);
    if (free >= 0) {
      this.page.send({ t: "sit", seat: free });
    }
  }

  sendMove(name) {
    if (!this.moves || !this.moves.includes(name)) {
      return;
    }
    this.page.send({ t: "move", move: name });
    this.page.sound.play("click");
    this.moves = null;
    this.renderMoves();
  }

  myId() {
    return this.page.me()?.id || null;
  }

  myRow() {
    return (this.state?.players || []).find((player) => player.id === this.myId()) || null;
  }

  seated() {
    return (this.state?.seats || []).some((seat) => seat && seat.id === this.myId());
  }

  waitingOnMe() {
    return (this.state?.waiting || []).includes(this.myId());
  }

  nameOf(id) {
    const player = (this.state?.players || []).find((row) => row.id === id);
    if (player) {
      return player.name;
    }
    const seat = (this.state?.seats || []).find((row) => row && row.id === id);
    return seat ? seat.name : "A player";
  }

  // Why the player can't bet right now, checked in the bot's order, or "" when they can
  blockedReason() {
    const casino = this.page.casino();
    const me = this.page.me();
    const game = casino?.games[this.game];
    if (!casino || !game || !me) {
      return "Loading the table...";
    }
    if (!casino.open) {
      return "The casino is closed.";
    }
    if (!game.open) {
      return `${game.name} is closed.`;
    }
    if (game.access > me.access) {
      return `${game.name} needs access level ${game.access}. Yours is ${me.access}. A higher membership unlocks it.`;
    }
    if (this.game === "blackjack" && !this.seated()) {
      return "Take a seat to bet.";
    }
    return this.roundReason(game, me);
  }

  roundReason(game, me) {
    const phase = this.state ? this.state.phase : "idle";
    if (this.pulling) {
      return this.game === "allin" ? SPINNING_WHEEL : "The reels are spinning...";
    }
    if (this.myRow() && this.myRow().bet !== null) {
      return { betting: "Your bet is in.", results: "Next round in a moment." }[phase] || "You're in this round.";
    }
    if (!["idle", "betting"].includes(phase)) {
      return "Wait for the next round.";
    }
    if (this.game === "allin" && me.balance <= 0) {
      return "You need some credits to go all in.";
    }
    if (this.game !== "allin" && me.balance < (game.min ?? 0)) {
      return "You don't have enough credits for the minimum bet.";
    }
    const left = this.page.readyIn(this.game);
    if (left > 0) {
      return `${game.name} is ready again in ${duration(left)}.`;
    }
    return "";
  }

  // ---------- Drawing the dock ----------

  update() {
    if (this.closed) {
      return;
    }
    const game = this.page.casino()?.games[this.game];
    if (game) {
      // A membership can raise the player's max bet, so the tray takes their own max over the table's
      this.tray.configure({ ...game, max: this.page.me()?.max_bets?.[this.game] ?? game.max });
    }
    const state = this.state;
    $("tray").hidden = Boolean(this.dock);
    this.dock?.render(state);
    this.renderTray();
    this.renderStatus();
    this.renderPlayers();
    this.renderMoves();
    const blackjack = this.game === "blackjack";
    $("seat-buttons").hidden = !blackjack;
    $("sit").hidden = !blackjack || this.seated() || !(state?.seats || []).includes(null);
    $("stand").hidden = !blackjack || !this.seated();
  }

  statusText() {
    const state = this.state;
    if (!state) {
      return "Walking up to the table...";
    }
    if (this.dock) {
      return this.dock.statusText();
    }
    if (this.game === "slots") {
      return this.pulling ? "The reels are spinning..." : "Pick your bet, then pull the lever.";
    }
    if (this.game === "allin" && state.phase === "idle") {
      return this.pulling ? SPINNING_WHEEL : "Each spin bets your whole balance. Pick a multiplier and spin.";
    }
    if (state.phase === "idle") {
      return "Place your bets.";
    }
    if (state.phase === "betting") {
      return this.myRow()?.bet != null ? "Waiting for bets. Press Go to start now." : "Betting is open.";
    }
    if (state.phase === "results") {
      return "Results";
    }
    const waiting = state.waiting || [];
    if (waiting.includes(this.myId())) {
      return this.game === "craps" ? "You have the dice. Roll!" : "Your move.";
    }
    if (this.game === "craps" && state.shooter) {
      return `${this.nameOf(state.shooter)} has the dice.`;
    }
    if (state.turn) {
      return `${this.nameOf(state.turn)}'s turn.`;
    }
    if (waiting.length) {
      return `Waiting on ${waiting.map((id) => this.nameOf(id)).join(", ")}.`;
    }
    return "Good luck!";
  }

  renderStatus() {
    $("status-text").textContent = this.statusText();
    this.tick();
  }

  renderTray() {
    const state = this.state;
    const canGo = state?.phase === "betting" && this.myRow()?.bet != null && state.players.length > 1;
    const balance = this.page.me()?.balance ?? 0;
    this.tray.render({ blocked: this.blockedReason(), canGo, balance, spinning: this.pulling });
  }

  tick() {
    const left = this.deadline === null ? null : Math.max(0, Math.ceil((this.deadline - performance.now()) / 1000));
    // Hold'em's dock counts only the player's own turn: everyone else's time drains on their seat's ring
    const counted = !this.dock || this.waitingOnMe();
    $("clock").textContent = left === null || !counted ? "" : `${left}s`;
    this.dock?.tick();
    // A cooldown counts down on its own, so its reason is redrawn as it changes
    if (this.page.readyIn(this.game) > 0 || $("tray").classList.contains("blocked")) {
      this.renderTray();
    }
  }

  renderPlayers() {
    const rows = (this.state?.players || []).map((player) => {
      const item = make("li");
      item.classList.toggle("me", player.id === this.myId());
      item.classList.toggle("away", player.away);
      const row = button("", "");
      row.append(avatar(player.avatar), make("span", "name", player.name));
      if (player.outcome) {
        const won = player.outcome === "win";
        // A push, surrender or refund gave money back, so it isn't shown in a loss's red
        const tone = won ? "win" : ["lose", "bust"].includes(player.outcome) ? "lose" : "bet";
        row.append(make("span", tone, won ? `+${money(player.payout)}` : player.outcome));
      } else if (player.bet !== null) {
        const call = player.choice === null ? "" : ` on ${player.choice}`;
        row.append(make("span", "bet", `${money(player.bet)}${call}`));
      }
      row.addEventListener("click", () => this.page.showPlayer(player.id));
      item.append(row);
      return item;
    });
    // Hold'em puts the player's own row first and fits the list's room with "+N" for the rest, and leaves a list that
    // already shows the same alone
    const shown = this.dock ? this.dock.peopleRow(rows, $("players")) : rows;
    if (shown) {
      $("players").replaceChildren(...shown);
    }
  }

  renderMoves() {
    const moves = this.waitingOnMe() ? this.moves : null;
    $("moves").hidden = !moves || !moves.length;
    $("moves").replaceChildren(
      ...(moves || []).map((name, index) => {
        const node = button(MOVE_LABELS[name] || name, index === 0 ? "button primary" : "button", () => this.sendMove(name));
        node.dataset.move = name;
        return node;
      }),
    );
  }

  close() {
    this.closed = true;
    clearInterval(this.ticker);
    clearTimeout(this.resultTimer);
    this.tray.close();
    this.dock?.close();
    $("sit").removeEventListener("click", this.sitHandler);
    $("stand").removeEventListener("click", this.standHandler);
    this.observer?.disconnect();
    try {
      this.scene?.destroy?.();
      this.app?.destroy(true, { children: true });
    } catch (e) {
      console.warn("Vegas: couldn't tidy up the table's graphics", e);
    }
    $("scene").replaceChildren();
    // A winner who walks away before their result card hides still gets their note
    this.hideResult();
    $("moves").replaceChildren();
    $("players").replaceChildren();
  }
}
