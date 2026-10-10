// One table: its scene, the round's status and clock, the players at it, the player's own buttons, and results.
// The bot runs the round. Messages wait in a queue so each animation finishes before the next thing shows,
// the same pacing the bot keeps (PACE), so a result never shows before the cards or dice that decide it.
import { Application, Container } from "./vendor/pixi.min.mjs";
import { avatar, button, duration, make, money } from "./format.js";
import { Tray } from "./tray.js";

// How long each kind of event animates, in seconds. The same numbers as PACE in casino/common/table.py
export const PACE = { flip: 2.0, shuffle: 3.0, roll: 2.0, deal: 0.45, reveal: 0.6, burn: 1.2, pull: 3.0 };
// A scene gets this much longer than its pace to finish, then the table moves on without waiting
const GRACE_MS = 350;
// More waiting messages than this means the page fell behind (it was hidden), so it skips the animations
const MAX_BEHIND = 12;
const RESULT_MS = 3500;
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
    case "push":
      return { tone: "even", big: "Push", small: `Your ${money(result.stake)} came back. Balance: ${money(result.balance)}` };
    case "surrender":
      return {
        tone: "even",
        big: "Surrendered",
        small: `${money(result.payout)} of your ${money(result.stake)} came back. Balance: ${money(result.balance)}`,
      };
    case "bust":
      return { tone: "lose", big: "Bust", small };
    default:
      return { tone: "lose", big: game === "allin" ? "No luck" : "House wins", small };
  }
}

export class TableView {
  // page: send(message), sound, casino(), me(), readyIn(game), showPlayer(id), toast(text)
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
    this.tray = new Tray(game, {
      onBet: (message) => this.bet(message),
      onGo: () => this.page.send({ t: "go" }),
      sound: page.sound,
    });
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
    } catch (e) {
      console.error("Casino: couldn't start the table's graphics", e);
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
      actions: {
        choose: (value) => this.tray.choose(value),
        sit: (seat) => this.page.send({ t: "sit", seat }),
        stand: () => this.page.send({ t: "stand" }),
        move: (name) => this.sendMove(name),
        place: () => this.tray.place(),
      },
    };
  }

  layout() {
    const host = $("scene");
    if (!this.scene || !this.app || !host.clientWidth || !host.clientHeight) {
      return;
    }
    this.app.resize();
    this.scene.layout(host.clientWidth, host.clientHeight);
  }

  // ---------- Messages ----------

  receive(message) {
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
        console.error("Casino: a table update failed", e);
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
    } else if (message.t === "event") {
      await this.animate(message);
    } else if (message.t === "result") {
      this.showResult(message);
    } else if (message.t === "ask") {
      this.moves = message.moves;
      this.renderMoves();
    }
  }

  async animate(event) {
    if (!this.scene) {
      return;
    }
    const limit = (PACE[event.kind] ?? 0) * 1000 + GRACE_MS;
    let late = false;
    await Promise.race([this.scene.play(event), wait(limit).then(() => (late = true))]);
    // The bot has moved on by now, so an animation this slow falls behind the table
    if (late) {
      console.warn(`Casino: the ${this.game} ${event.kind} animation ran past ${limit} ms`);
    }
  }

  // A refused bet or move: the bot says why in a notice
  notice() {
    this.pulling = false;
    this.update();
  }

  showResult(result) {
    this.pulling = false;
    const view = resultView(result, this.game);
    $("result").className = `result ${view.tone}`;
    $("result-big").textContent = view.big;
    $("result-small").textContent = view.small;
    $("result").hidden = false;
    clearTimeout(this.resultTimer);
    this.resultTimer = setTimeout(() => {
      $("result").hidden = true;
    }, RESULT_MS);
    const big = result.outcome === "win" && (this.game === "allin" || result.payout >= result.stake * 5);
    this.page.sound.play(result.outcome === "win" ? (big ? "bigwin" : "win") : result.payout > 0 ? "push" : "lose");
    if (result.outcome === "win") {
      this.page.sound.play("collect");
    }
    this.scene?.result?.(result);
    this.update();
  }

  // ---------- The player's part ----------

  bet(message) {
    if (message.t === "pull") {
      this.pulling = true;
    }
    this.page.send(message);
    this.update();
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
      return "The reels are spinning...";
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
      this.tray.configure(game);
    }
    const state = this.state;
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
    if (state.phase === "idle") {
      return this.game === "allin" ? "Pick a multiplier and pull the lever." : "Place your bets.";
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
    this.tray.render({ blocked: this.blockedReason(), canGo, balance: this.page.me()?.balance ?? 0 });
  }

  tick() {
    const left = this.deadline === null ? null : Math.max(0, Math.ceil((this.deadline - performance.now()) / 1000));
    $("clock").textContent = left === null ? "" : `${left}s`;
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
        row.append(make("span", won ? "win" : "lose", won ? `+${money(player.payout)}` : player.outcome));
      } else if (player.bet !== null) {
        const call = player.choice === null ? "" : ` on ${player.choice}`;
        row.append(make("span", "bet", `${money(player.bet)}${call}`));
      }
      row.addEventListener("click", () => this.page.showPlayer(player.id));
      item.append(row);
      return item;
    });
    $("players").replaceChildren(...rows);
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
    $("sit").removeEventListener("click", this.sitHandler);
    $("stand").removeEventListener("click", this.standHandler);
    this.observer?.disconnect();
    try {
      this.scene?.destroy?.();
      this.app?.destroy(true, { children: true });
    } catch (e) {
      console.warn("Casino: couldn't tidy up the table's graphics", e);
    }
    $("scene").replaceChildren();
    $("result").hidden = true;
    $("moves").replaceChildren();
    $("players").replaceChildren();
  }
}
