// Shared worlds on the page. A shared world runs on the bot's clock: the bot sends batches ("apply these strokes,
// then run N steps") and every screen in the world runs the same batches, so every screen computes the same world.
// This file opens and closes worlds, enters and leaves them, answers the bot's snapshot asks, reports fingerprints so
// drift gets healed, and puts the player back after a dropped connection. The player's private world waits in memory
// while they visit someone else's.
import { note } from "./notes.js";
import { addLayer } from "./render/overlay.js";
import { snowStrokes } from "./runner.js";
import {
  decodeWorld,
  ELEMENTS,
  encodeWorld,
  hashWorld,
  packWorld,
  STROKE,
  strokeCells,
  unpackWorld,
  W,
} from "./sim/index.js";

// A member whose world doesn't come back within this long after a drop goes back to their own world
const REJOIN_MS = 15000;
// Every screen sends its fingerprint after each batch that crosses a multiple of this many steps
const HASH_STEPS = 120;
const CURSOR_MS = 100;
// A preview whose stroke never came back (dropped on the way) is let go after this long
const PREVIEW_MS = 3000;
const OWNER_ONLY = new Set([STROKE.SET, STROKE.CLEAR]);
const PREVIEWED = new Set([STROKE.PAINT, STROKE.LINE, STROKE.BOX, STROKE.FILL]);

function strokeKey(stroke) {
  return JSON.stringify(stroke);
}

export class Shared {
  constructor(state) {
    this.state = state;
    this.conn = null;
    // True once the live connection could not be opened or has closed for good
    this.lost = false;
    // My user id as text, from the bot's hello
    this.you = null;
    // The shared world this page is in (its id), or null in the private world
    this.inWorld = null;
    this.owner = null;
    this.name = "";
    this.players = [];
    this.worldsList = [];
    this.pics = new Map();
    this.cursors = new Map();
    this.opening = false;
    // The player's own world and speed while they visit someone else's world
    this.privateWorld = null;
    this.previews = [];
    this.rejoinTimer = null;
    this.worldCount = 0;
    this.lastCursor = 0;
    this.listeners = [];
    this.handlers = {
      hello: (m) => this.onHello(m),
      worlds: (m) => this.setWorlds(m),
      pic: ([id, png]) => this.onPic(id, png),
      opened: (m) => this.onOpened(m),
      world: (m) => this.onWorld(m),
      b: (m) => this.onBatchMessage(m),
      players: (m) => this.onPlayers(m),
      speed: (m) => this.state.applySpeed(m),
      cur: (m) => this.onCursor(m),
      snapask: () => this.onSnapAsk(),
      closed: (m) => this.backToPrivate(`${m.name} closed the world.`),
      waiting: () => {},
      full: (m) => this.onFull(m),
      follow: (m) => this.emit("follow", m),
      asked: (m) => this.emit("asked", m),
      note: (m) => note(m),
    };
  }

  /** True in a shared world this player runs: opened by them, or handed to them when its owner left */
  get isOwner() {
    return this.inWorld !== null && this.owner === this.you;
  }

  /** In a shared world run by someone else: the world's controls are theirs */
  get locked() {
    return this.inWorld !== null && !this.isOwner;
  }

  /** The owner's name, for hints and notes */
  get ownerName() {
    return this.players.find((p) => p.id === this.owner)?.name ?? this.name;
  }

  /** True when the world on screen is the player's own (private, or theirs opened to friends): it gets saved */
  get ownsWorld() {
    return this.privateWorld === null;
  }

  /** The player's own world, wherever they are */
  ownWorld() {
    return this.privateWorld?.world ?? this.state.world;
  }

  /** fn(kind, data) on every change: "change", "follow", "asked", "cur", "pic" */
  onChange(fn) {
    this.listeners.push(fn);
  }

  emit(kind, data) {
    for (const fn of this.listeners) {
      fn(kind, data);
    }
  }

  send(data) {
    return this.conn !== null && this.conn.send(data);
  }

  /** Opens the live connection. The browser preview has no bot, so it stays private */
  async start() {
    const { hub, runner } = this.state;
    addLayer(30, (ctx, view) => this.drawPreviews(ctx, view));
    runner.onBatch((batch) => this.batchStarted(batch));
    runner.onBatchDone((batch, before) => this.batchDone(batch, before));
    runner.onBehind(() => this.send({ t: "behind" }));
    if (hub.offline) {
      return;
    }
    try {
      this.conn = await hub.socket();
    } catch (e) {
      console.warn("Sandfall: couldn't open the live connection", e);
      this.lost = true;
      this.emit("change");
      return;
    }
    this.conn.on((data) => this.receive(data));
    this.conn.onReconnecting(() => this.reconnecting());
    this.conn.onReconnected(() => this.reconnected());
    this.conn.onClose(() => this.connectionGone());
  }

  receive(data) {
    if (data === null || typeof data !== "object") {
      return;
    }
    for (const [key, value] of Object.entries(data)) {
      const handler = this.handlers[key];
      if (handler) {
        handler(value);
      }
    }
  }

  // The world list and pictures, for the Worlds panel

  onHello({ you, worlds }) {
    this.you = you;
    this.setWorlds(worlds);
  }

  setWorlds(worlds) {
    this.worldsList = worlds;
    const open = new Set(worlds.map((w) => w.id));
    for (const id of this.pics.keys()) {
      if (!open.has(id)) {
        this.pics.delete(id);
      }
    }
    this.emit("change");
  }

  onPic(id, png) {
    this.pics.set(id, png);
    this.emit("pic", id);
  }

  onCursor([id, x, y, size, element]) {
    this.cursors.set(id, { x, y, size, element, at: performance.now() });
    this.emit("cur", id);
  }

  /** Sends my cursor, at most 10 times a second. False when it was held back, so the caller tries again */
  sendCursor(x, y) {
    const now = performance.now();
    if (this.inWorld === null || now - this.lastCursor < CURSOR_MS) {
      return false;
    }
    const { painter } = this.state;
    const element = painter.tool === "eraser" ? 0 : painter.element;
    if (!this.send({ t: "cur", c: [x, y, painter.size, element] })) {
      return false;
    }
    this.lastCursor = now;
    return true;
  }

  // Opening, closing, entering and leaving

  /**
   * Opens my world to friends from a batch boundary. The world keeps running until the bot's clock takes over. With
   * `invite` (a user id), that player is brought straight in
   */
  async open(invite = null) {
    if (this.conn === null || this.inWorld !== null || this.opening) {
      return;
    }
    this.opening = true;
    const { runner } = this.state;
    runner.boundary();
    try {
      const snap = await encodeWorld(this.state.world);
      const message = { t: "open", snap, speed: runner.speed };
      if (invite !== null) {
        message.invite = invite;
      }
      if (!this.send(message)) {
        this.opening = false;
      }
    } catch (e) {
      console.warn("Sandfall: couldn't pack the world to open it", e);
      this.opening = false;
    }
  }

  /** Brings a player who asked into my world, opening it first when it is private (from someone else's, I leave) */
  invite(id) {
    if (this.isOwner) {
      this.send({ t: "open", invite: id });
      return;
    }
    this.exit();
    this.open(id);
  }

  onOpened({ id, b }) {
    this.opening = false;
    this.inWorld = id;
    this.owner = this.you;
    this.state.runner.enterShared(b);
    this.sharedChanged();
  }

  /** Closes my world to friends. A world handed to me by its old owner closes and I go back to my own */
  close() {
    if (!this.isOwner) {
      return;
    }
    this.send({ t: "close" });
    if (this.ownsWorld) {
      this.leaveShared();
    } else {
      this.backToPrivate();
    }
  }

  /** Joins a shared world. My own world is saved and waits here until I come back */
  enter(id) {
    if (this.conn === null || id === this.inWorld) {
      return;
    }
    const { runner } = this.state;
    if (this.privateWorld === null) {
      this.keepPrivate();
    }
    if (!this.send({ t: "enter", id })) {
      this.backToPrivate();
      return;
    }
    const world = this.worldsList.find((w) => w.id === id);
    this.inWorld = id;
    this.owner = world?.owner ?? null;
    this.name = world?.name ?? "";
    this.players = [];
    runner.enterShared(runner.done);
    runner.hold();
    this.waitForWorld();
    this.sharedChanged();
  }

  /** Back to my own world from someone else's */
  exit() {
    if (this.inWorld === null) {
      return;
    }
    this.send({ t: "exit" });
    if (this.ownsWorld) {
      // My own world, now handed to the others: I take my copy of it with me
      this.leaveShared();
    } else {
      this.backToPrivate();
    }
  }

  keepPrivate() {
    const { runner, saver } = this.state;
    runner.boundary();
    this.privateWorld = { world: this.state.world, speed: runner.speed };
    saver?.saveNow({ world: this.privateWorld.world });
  }

  // Leaves shared mode keeping the world on screen as my own private world
  leaveShared() {
    this.clearShared();
    this.state.runner.leaveShared();
    this.sharedChanged();
  }

  /** Back to my own private world, with an optional note */
  backToPrivate(text) {
    if (this.inWorld === null && this.privateWorld === null) {
      return;
    }
    this.clearShared();
    this.state.runner.leaveShared();
    if (this.privateWorld !== null) {
      const { world, speed } = this.privateWorld;
      this.privateWorld = null;
      this.state.setWorld(world);
      this.state.applySpeed(speed);
    }
    this.sharedChanged();
    if (text) {
      note(text);
    }
  }

  clearShared() {
    clearTimeout(this.rejoinTimer);
    this.rejoinTimer = null;
    this.inWorld = null;
    this.owner = null;
    this.players = [];
    this.previews = [];
    this.cursors.clear();
    this.opening = false;
  }

  // Undo, the menus and the speed controls follow whether this page is in a shared world, and who owns it
  sharedChanged() {
    const { undo, worldMenu } = this.state;
    if (this.inWorld !== null) {
      undo?.clear();
    }
    if (undo) {
      undo.button.hidden = this.inWorld !== null;
    }
    worldMenu?.refresh();
    this.state.refreshSpeed?.();
    this.emit("change");
  }

  // The world I just entered had no seat left: back to my own world with the bot's note
  onFull(message) {
    if (message.id === this.inWorld) {
      this.backToPrivate(message.note);
    }
  }

  waitForWorld() {
    clearTimeout(this.rejoinTimer);
    const name = this.name;
    this.rejoinTimer = setTimeout(() => {
      this.rejoinTimer = null;
      this.send({ t: "exit" });
      this.backToPrivate(name ? `${name}'s world closed.` : "That world closed.");
    }, REJOIN_MS);
  }

  // The bot's messages about the world

  onPlayers({ owner, list }) {
    const before = this.owner;
    this.owner = owner;
    this.players = list;
    const ids = new Set(list.map((p) => p.id));
    for (const id of this.cursors.keys()) {
      if (!ids.has(id)) {
        this.cursors.delete(id);
      }
    }
    this.sharedChanged();
    if (before !== null && before !== owner && this.inWorld !== null) {
      note(owner === this.you ? "You now run this world." : `${this.ownerName} now runs this world.`);
    }
  }

  /**
   * Enter or resync: load the snapshot (or keep this page's world when it is null), then run the batches after it.
   * Live batches that arrive while the snapshot unpacks wait in the runner
   */
  async onWorld(message) {
    const { runner } = this.state;
    const count = ++this.worldCount;
    clearTimeout(this.rejoinTimer);
    this.rejoinTimer = null;
    // Invited straight in, or I'm leaving my own shared world for this one: my world waits for me
    if (this.privateWorld === null && this.inWorld !== message.id && !this.opening) {
      this.keepPrivate();
    }
    if (runner.mode !== "shared") {
      runner.enterShared(runner.done);
    }
    runner.hold(message.b);
    Object.assign(this, { inWorld: message.id, owner: message.owner, name: message.name, players: message.players });
    this.previews = [];
    this.state.applySpeed(message.speed);
    let world = null;
    if (message.snap !== null) {
      try {
        world = await decodeWorld(message.snap);
      } catch (e) {
        console.warn("Sandfall: the shared world's snapshot couldn't be read", e);
        this.send({ t: "behind" });
        return;
      }
    }
    // A newer world message, or a step back to the private world, came in while this one unpacked
    if (count !== this.worldCount || this.inWorld !== message.id) {
      return;
    }
    if (world !== null) {
      this.state.setWorld(world);
    }
    runner.resync(message.b, message.batches);
    this.sharedChanged();
  }

  onBatchMessage(batch) {
    if (this.inWorld !== null && this.state.runner.mode === "shared") {
      this.state.runner.push(batch);
    }
  }

  // A snapshot of the world after the last whole batch, packed right away so no later batch slips in
  async onSnapAsk() {
    if (this.inWorld === null) {
      return;
    }
    const b = this.state.runner.boundary();
    const copy = unpackWorld(packWorld(this.state.world));
    try {
      this.send({ t: "snap", b, snap: await encodeWorld(copy) });
    } catch (e) {
      console.warn("Sandfall: couldn't pack a snapshot for the bot", e);
    }
  }

  // What this page sends

  /** A stroke for the shared world. It shows as a see-through preview until its batch comes back */
  sendStroke(stroke) {
    if (OWNER_ONLY.has(stroke[0]) && !this.isOwner) {
      return;
    }
    if (!this.send({ t: "s", k: stroke })) {
      return;
    }
    if (PREVIEWED.has(stroke[0])) {
      this.previews.push({ key: strokeKey(stroke), stroke, cells: strokeCells(stroke), at: performance.now() });
    }
  }

  setSpeed(speed) {
    if (this.isOwner) {
      this.send({ t: "speed", v: speed });
    }
  }

  once() {
    if (this.isOwner) {
      this.send({ t: "once" });
    }
  }

  // The runner's batches

  batchStarted(batch) {
    if (this.inWorld === null || this.state.runner.mode !== "shared") {
      return;
    }
    for (const [player, stroke] of batch[2]) {
      if (player === this.you && this.previews.length > 0) {
        this.dropPreview(strokeKey(stroke));
      }
    }
    // Christmas snow comes from the owner only, so every screen gets the same flakes
    if (this.isOwner && batch[1] > 0) {
      for (const stroke of snowStrokes()) {
        this.send({ t: "s", k: stroke });
      }
    }
  }

  // Own strokes come back in the order they were sent; any older preview whose stroke was dropped goes too
  dropPreview(key) {
    const at = this.previews.findIndex((p) => p.key === key);
    if (at >= 0) {
      this.previews.splice(0, at + 1);
    }
  }

  batchDone(batch, before) {
    if (this.inWorld === null || this.state.runner.mode !== "shared" || this.state.runner.loading) {
      return;
    }
    const step = this.state.world.step;
    if (Math.trunc(step / HASH_STEPS) !== Math.trunc(before / HASH_STEPS)) {
      this.send({ t: "hash", b: batch[0], h: hashWorld(this.state.world) });
    }
  }

  drawPreviews(ctx, view) {
    if (this.previews.length === 0) {
      return;
    }
    const now = performance.now();
    this.previews = this.previews.filter((p) => now - p.at < PREVIEW_MS);
    const scale = view.scale;
    ctx.globalAlpha = 0.45;
    for (const preview of this.previews) {
      const element = preview.stroke[1];
      const [r, g, b] = ELEMENTS[element]?.color ?? [0, 0, 0];
      ctx.fillStyle = element === 0 ? "rgba(0, 0, 0, 0.8)" : `rgb(${r}, ${g}, ${b})`;
      ctx.beginPath();
      for (const i of preview.cells) {
        const [x, y] = view.toScreen(i % W, Math.trunc(i / W));
        ctx.rect(x, y, scale, scale);
      }
      ctx.fill();
    }
  }

  // Dropped connections

  reconnecting() {
    if (this.inWorld !== null || this.opening) {
      note("Lost the connection. Trying again...");
    }
  }

  /** The owner reopens the world from its own copy; a member enters again and catches up from where it stopped */
  async reconnected() {
    if (this.opening) {
      this.opening = false;
      this.open();
      return;
    }
    if (this.inWorld === null) {
      return;
    }
    const { runner } = this.state;
    const b = runner.boundary();
    runner.enterShared(b);
    this.previews = [];
    if (this.isOwner) {
      try {
        const snap = await encodeWorld(this.state.world);
        this.send({ t: "open", snap, speed: runner.speed, id: this.inWorld, b });
      } catch (e) {
        console.warn("Sandfall: couldn't pack the world to reopen it", e);
      }
      return;
    }
    runner.hold();
    this.send({ t: "enter", id: this.inWorld, b });
    this.waitForWorld();
  }

  // The connection is gone for good: an owner keeps the world as their own, a member goes home
  connectionGone() {
    this.conn = null;
    this.lost = true;
    this.emit("change");
    if (this.inWorld === null) {
      return;
    }
    if (this.isOwner && this.ownsWorld) {
      this.leaveShared();
      note("Lost the connection, so your world is private again.");
    } else {
      this.backToPrivate(`Lost the connection to ${this.ownerName}'s world.`);
    }
  }
}
