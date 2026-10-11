// The frame every bundled game shares: the top bar, the title, pause and results screens, the server
// leaderboard, sounds, and short messages over the playfield. Games import it with:
//   import { startArcade } from "activityhub/arcade.js";
// The page needs a <main id="stage"> holding the playfield; banners and hints are drawn inside it.
//
// The game itself only draws and plays. It hands startArcade four callbacks:
//   play(seed)  start a new round. The seed comes from the bot, so it can replay the round later
//   pause()     stop moving until resume() is called
//   resume()    carry on after a pause
//   stop()      end the round now and return { score, proof } for it
// and calls arcade.over(score, proof) when a round ends by itself.
import { connect } from "activityhub";

const MUTE_KEY = "activityhub-arcade-muted";
const PAUSE_KEYS = ["Escape", "p", "P"];
const BANNER_MS = 1500;
const COUNT_UP_MS = 700;
const MEDALS = ["gold", "silver", "bronze"];
const PASS_MS = 1600;
// Passing notes this close together share one
const PASS_MERGE_MS = 1000;
const STRIP_MAX = 5;
const STRIP_MAX_PHONE = 3;
// The mark beside someone mid-round. A Map, since the state is another player's word and a plain object would
// answer to names like "constructor"
const MARKS = new Map([
  ["playing", "▶"],
  ["paused", "❚❚"],
]);
// A narrow window gets a smaller strip: fewer entries, and only the player's own name
const phone = window.matchMedia("(max-width: 520px)");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// Static markup only, never player text
const ICONS = {
  back: '<path d="M15 5l-7 7 7 7"/>',
  sound: '<path class="fill" d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
  muted: '<path class="fill" d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9.5l5 5M22 9.5l-5 5"/>',
  pause: '<rect class="fill" x="6" y="5" width="4" height="14" rx="1"/><rect class="fill" x="14" y="5" width="4" height="14" rx="1"/>',
};

// Added as soon as this file loads, so the page never shows unstyled while the game sets up
document.head.append(el("link", { rel: "stylesheet", href: new URL("./arcade.css", import.meta.url).href }));

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name === "text") {
      node.textContent = value;
    } else if (name === "onclick") {
      node.addEventListener("click", value);
    } else {
      node.setAttribute(name, value);
    }
  }
  node.append(...children);
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name];
  return svg;
}

function fmt(n) {
  return Number(n).toLocaleString();
}

function ordinal(n) {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
}

function randomSeed() {
  return Math.floor(Math.random() * 2 ** 32);
}

// Dark text on light accents, white on dark ones
function textOn(color) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? "#10121d" : "#ffffff";
}

function readMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveMuted(muted) {
  try {
    localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
  } catch {
    // Storage can be blocked in the activity frame; muting still works until the game closes
  }
}

class Arcade {
  constructor(hub, options) {
    this.hub = hub;
    this.options = options;
    this.game = options;
    this.inServer = !hub.offline && Boolean(hub.player && hub.player.guildId);
    this.playing = false;
    this.paused = false;
    this.run = null;
    // The last saved round, which can be cashed in until the next one starts
    this.cashRun = null;
    this.saving = null;
    this.best = null;
    this.audio = null;
    this.muted = readMuted();
    this.stage = document.getElementById("stage") || document.body;
    if (options.accent) {
      document.documentElement.style.setProperty("--arcade-accent", options.accent);
      document.documentElement.style.setProperty("--arcade-on-accent", textOn(options.accent));
    }
    // This round's score, and whether the player has a score this session
    this.score = 0;
    this.scored = false;
    // The others the player can still pass this round: seen at or above the player's score
    this.ahead = new Set();
    // The passing note on show, when it began, and whether a second pass has already joined it
    this.passNames = [];
    this.passAt = -Infinity;
    this.passExtended = false;
    this.passTimer = null;
    // What the strip shows, and each entry's parts by person, so a change only touches what moved
    this.stripKey = "";
    this.liveRows = new Map();
    this.buildBar();
    this.screen = el("div", { class: "arcade-screen", role: "dialog", "aria-modal": "true" });
    this.hintText = el("div", { class: "arcade-hint", "aria-live": "polite" });
    this.hintText.hidden = true;
    this.stage.append(this.hintText);
    this.passNoteBox = el("div", { class: "arcade-pass", "aria-live": "polite" });
    this.passNoteBox.hidden = true;
    this.stage.append(this.passNoteBox);
    this.strip = el("ol", { class: "arcade-live", "aria-label": "Playing here now" });
    this.strip.hidden = true;
    this.bar.after(this.strip);
    this.liveMore = el("li", { class: "arcade-live-more" });
    hub.onPeople(() => {
      this.followRivals();
      this.showLive();
    });
    phone.addEventListener("change", () => this.showLive());
    this.bannerNode = null;
    document.body.append(this.screen);
    this.listen(options.autoPause !== false);
  }

  // ---------- Top bar ----------

  buildBar() {
    this.scoreText = el("b", { class: "arcade-score", text: "0" });
    this.bestText = el("b", { class: "arcade-best" });
    this.bestStat = el("span", { class: "arcade-stat" }, [el("small", { text: "Best" }), this.bestText]);
    this.muteButton = el("button", { type: "button", class: "arcade-icon", onclick: () => this.toggleMute() });
    this.pauseButton = el("button", { type: "button", class: "arcade-icon", "aria-label": "Pause" }, [icon("pause")]);
    this.pauseButton.addEventListener("click", () => this.pause());
    const back = el("button", { type: "button", class: "arcade-back", onclick: () => this.leave() }, [
      icon("back"),
      el("span", { text: "Menu" }),
    ]);
    const name = el("span", { class: "arcade-name" }, [el("strong", { class: "arcade-title", text: this.options.title })]);
    if (this.options.icon) {
      name.prepend(this.logo("arcade-bar-logo"));
    }
    const stats = el("span", { class: "arcade-stats" }, [
      el("span", { class: "arcade-stat" }, [el("small", { text: "Score" }), this.scoreText]),
      this.bestStat,
    ]);
    const people = this.hub.peopleButton();
    const bar = el("header", { class: "arcade-bar" }, [back, name, stats, people, this.muteButton, this.pauseButton]);
    // A clicked button would keep the keyboard, so the next Space or Enter meant for the game would press it again.
    // Tab still reaches the buttons
    bar.addEventListener("mousedown", (event) => event.preventDefault());
    document.body.prepend(bar);
    this.bar = bar;
    this.showMute();
    this.showBest();
    this.pauseButton.hidden = true;
  }

  logo(className) {
    const img = el("img", { class: className, src: this.options.icon, alt: "" });
    img.addEventListener("error", () => img.remove());
    return img;
  }

  // Shows the score in the bar. False when it was already showing
  drawScore(score) {
    const text = fmt(score);
    if (this.scoreText.textContent === text) {
      return false;
    }
    this.scoreText.textContent = text;
    // Restarting the bump animation needs a reflow between taking the class off and putting it back
    this.scoreText.classList.remove("bump");
    void this.scoreText.offsetWidth;
    this.scoreText.classList.add("bump");
    return true;
  }

  setScore(score) {
    this.score = score;
    if (this.drawScore(score)) {
      this.report();
      this.checkPassed();
      this.showLive();
    }
  }

  showBest() {
    this.bestStat.hidden = !this.best;
    this.bestText.textContent = this.best ? fmt(this.best) : "";
  }

  // ---------- Who's here ----------

  // What everyone else in the window sees this player doing, and whether leaving now would cost them a round
  report() {
    let text = "Getting ready";
    let data = { state: "idle" };
    if (this.playing) {
      const state = this.paused ? "paused" : "playing";
      text = `${this.paused ? "Paused" : "Playing"} · ${fmt(this.score)}`;
      data = { state, score: this.score };
    } else if (this.scored) {
      text = `Scored ${fmt(this.score)}`;
      data = { state: "over", score: this.score };
    }
    this.hub.status(text, data);
    this.hub.busy(this.playing);
  }

  // The others in this game with a score this session
  rivals() {
    return this.hub.people
      .filter((p) => p.here && !p.you && p.data && typeof p.data.score === "number" && p.data.state !== "idle")
      .map((p) => ({ id: p.id, name: p.name, avatar: p.avatar, score: p.data.score, state: p.data.state, away: p.away }));
  }

  // Everyone here with a score, the player included, best first. The player always sees their own place, and
  // comes before anyone with the same score, as on the results. Nothing here takes a click, so it is only redrawn
  // when what it shows has changed, and then entry by entry, so a point of the player's own redraws no picture
  showLive() {
    const rivals = this.rivals();
    if (!rivals.length) {
      this.strip.hidden = true;
      this.stripKey = "";
      this.liveRows.clear();
      return;
    }
    const rows = [...rivals];
    if (this.scored) {
      const state = this.playing ? (this.paused ? "paused" : "playing") : "over";
      const you = { id: this.hub.player?.id, name: "You", avatar: this.hub.player?.avatar, score: this.score, state };
      rows.push({ ...you, you: true });
    }
    rows.sort((a, b) => b.score - a.score || Boolean(b.you) - Boolean(a.you));
    const shown = rows.slice(0, phone.matches ? STRIP_MAX_PHONE : STRIP_MAX);
    const mine = rows.find((row) => row.you);
    if (mine && !shown.includes(mine)) {
      shown[shown.length - 1] = mine;
    }
    const lines = shown.map((row) => [rows.indexOf(row) + 1, row]);
    const more = rows.length - shown.length;
    const key = JSON.stringify([lines, more]);
    if (key === this.stripKey) {
      return;
    }
    this.stripKey = key;
    const items = lines.map(([rank, row]) => this.liveRow(row, rank));
    const keep = new Set(lines.map(([, row]) => (row.you ? "you" : row.id)));
    for (const id of this.liveRows.keys()) {
      if (!keep.has(id)) {
        this.liveRows.delete(id);
      }
    }
    if (more > 0) {
      this.liveMore.textContent = `+${more}`;
      items.push(this.liveMore);
    }
    const same = items.length === this.strip.children.length && items.every((item, i) => this.strip.children[i] === item);
    if (!same) {
      this.strip.replaceChildren(...items);
    }
    this.strip.hidden = false;
  }

  // The picture, or the first letter of the name in a circle when there is none or it can't load
  liveAvatar(row) {
    const initial = () => el("span", { class: "avatar", text: Array.from(row.name)[0]?.toUpperCase() ?? "" });
    if (!row.avatar) {
      return initial();
    }
    const picture = el("img", { class: "avatar", src: row.avatar, alt: "" });
    picture.addEventListener("error", () => picture.replaceWith(initial()));
    return picture;
  }

  // One entry, made once per person and updated in place after that. Its picture is only drawn again when the
  // picture or the name changes
  liveRow(row, rank) {
    const id = row.you ? "you" : row.id;
    let entry = this.liveRows.get(id);
    if (!entry) {
      entry = {
        item: el("li"),
        rank: el("span", { class: "rank" }),
        name: el("span", { class: "name" }),
        points: el("b", { class: "points" }),
        state: el("span", { class: "state" }),
        face: null,
      };
      entry.item.append(entry.rank, el("span"), entry.name, entry.points);
      this.liveRows.set(id, entry);
    }
    const face = `${row.avatar || ""}|${row.name}`;
    if (entry.face !== face) {
      entry.face = face;
      entry.item.children[1].replaceWith(this.liveAvatar(row));
    }
    entry.rank.textContent = String(rank);
    entry.name.textContent = row.name;
    entry.points.textContent = fmt(row.score);
    const mark = MARKS.get(row.state);
    if (mark) {
      entry.state.textContent = mark;
      entry.state.setAttribute("aria-label", row.state);
      entry.item.append(entry.state);
    } else {
      entry.state.remove();
    }
    entry.item.className = row.you ? "you" : row.away ? "away" : "";
    return entry.item;
  }

  // The others the player can still pass: those seen at or above their score. One who drops below without the player
  // scoring has started a new round, and was not passed
  followRivals() {
    const rivals = this.rivals();
    for (const id of this.ahead) {
      const rival = rivals.find((r) => r.id === id);
      if (!rival || rival.score < this.score) {
        this.ahead.delete(id);
      }
    }
    rivals.filter((r) => r.score >= this.score).forEach((r) => this.ahead.add(r.id));
  }

  // "You passed Ann!" when the player's score goes above someone who was at or above it, and shows a score above 0
  checkPassed() {
    if (!this.playing) {
      return;
    }
    const rivals = this.rivals();
    const passed = rivals.filter((r) => this.ahead.has(r.id) && r.score > 0 && this.score > r.score);
    passed.forEach((rival) => this.ahead.delete(rival.id));
    rivals.filter((r) => r.score >= this.score).forEach((r) => this.ahead.add(r.id));
    if (!passed.length) {
      return;
    }
    this.passNote(passed.map((rival) => rival.name));
  }

  // Shows the note for these names. A pass within a second of the note's start joins it, once
  passNote(names) {
    const now = performance.now();
    if (now - this.passAt < PASS_MERGE_MS && !this.passExtended) {
      this.passNames = [...this.passNames, ...names];
      this.passExtended = true;
    } else {
      this.passNames = names;
      this.passAt = now;
      this.passExtended = false;
    }
    // Each name sits in its own <bdi>, so a name written right to left can't reorder the words around it
    const parts = ["You passed "];
    this.passNames.forEach((name, i) => {
      if (i > 0) {
        parts.push(i === this.passNames.length - 1 ? " and " : ", ");
      }
      parts.push(el("bdi", { text: name }));
    });
    parts.push("!");
    this.passNoteBox.replaceChildren(...parts);
    this.passNoteBox.hidden = false;
    this.passNoteBox.classList.remove("show");
    void this.passNoteBox.offsetWidth;
    this.passNoteBox.classList.add("show");
    clearTimeout(this.passTimer);
    this.passTimer = setTimeout(() => {
      this.passNoteBox.hidden = true;
    }, PASS_MS);
  }

  // "2nd of 3 here right now" on the results, when others here have a score
  placeLine(score) {
    const rivals = this.rivals();
    if (!rivals.length) {
      return null;
    }
    const place = 1 + rivals.filter((rival) => rival.score > score).length;
    return this.note(`${ordinal(place)} of ${rivals.length + 1} here right now`, "arcade-note arcade-place");
  }

  showMute() {
    this.muteButton.replaceChildren(icon(this.muted ? "muted" : "sound"));
    this.muteButton.setAttribute("aria-label", this.muted ? "Turn sound on" : "Turn sound off");
  }

  toggleMute() {
    this.muted = !this.muted;
    saveMuted(this.muted);
    this.showMute();
  }

  // ---------- Sound ----------

  // Browsers only allow sound after the player has clicked or pressed a key
  unlockAudio() {
    if (!this.audio) {
      this.audio = new AudioContext();
    }
    if (this.audio.state === "suspended") {
      this.audio.resume();
    }
  }

  // Every sound is a short synthesized tone, so there are no audio files to load
  tone(freq, duration, { type = "square", volume = 0.08, slide = 1, delay = 0 } = {}) {
    if (this.muted || !this.audio) {
      return;
    }
    const start = this.audio.currentTime + delay;
    const osc = this.audio.createOscillator();
    const gain = this.audio.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    if (slide !== 1) {
      osc.frequency.exponentialRampToValueAtTime(freq * slide, start + duration);
    }
    gain.gain.setValueAtTime(volume, start);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(gain).connect(this.audio.destination);
    osc.start(start);
    osc.stop(start + duration);
  }

  tune(notes, gap, duration = 0.16) {
    notes.forEach((freq, i) => this.tone(freq, duration, { type: "triangle", delay: i * gap }));
  }

  // ---------- Over the playfield ----------

  // A big short-lived message, like "Level 2"
  banner(title, subtitle = "") {
    if (this.bannerNode) {
      this.bannerNode.remove();
    }
    const node = el("div", { class: "arcade-banner", "aria-live": "polite" }, [el("strong", { text: title })]);
    if (subtitle) {
      node.append(el("span", { text: subtitle }));
    }
    this.stage.append(node);
    this.bannerNode = node;
    setTimeout(() => node.remove(), BANNER_MS);
  }

  // A small line that stays until it's cleared with hint("")
  hint(text) {
    this.hintText.textContent = text;
    this.hintText.hidden = !text;
  }

  shake() {
    if (reducedMotion.matches) {
      return;
    }
    this.stage.classList.remove("arcade-shake");
    void this.stage.offsetWidth;
    this.stage.classList.add("arcade-shake");
  }

  // ---------- Screens ----------

  show(children, className = "") {
    this.screen.replaceChildren(el("div", { class: `arcade-card ${className}` }, children));
    this.screen.hidden = false;
    this.focusPrimary();
  }

  focusPrimary() {
    const first = this.screen.querySelector("button.primary:not(:disabled)");
    if (first) {
      first.focus();
    }
  }

  hide() {
    this.screen.hidden = true;
    this.screen.replaceChildren();
  }

  button(text, onclick, primary = false) {
    return el("button", { type: "button", class: primary ? "primary" : "secondary", text, onclick });
  }

  note(text, className = "arcade-note") {
    return el("p", { class: className, text });
  }

  actions(buttons) {
    return el("div", { class: "arcade-actions" }, buttons);
  }

  controls() {
    const rows = [...(this.options.controls || []), ["Esc / P", "Pause"]];
    return el(
      "ul",
      { class: "arcade-controls" },
      rows.map(([keys, does]) => el("li", {}, [el("kbd", { text: keys }), el("span", { text: does })])),
    );
  }

  standing(board) {
    if (!board.you) {
      return "No score here yet. Play to get on the board.";
    }
    return `Your best ${fmt(board.you.score)} · #${board.you.rank} in ${board.server}`;
  }

  async showTitle(problem = "") {
    // Whether this is the first time or a round failed to start, nothing is being played now. The people
    // listener only fires on changes, so this is also the first look at whoever is here already
    this.scored = false;
    this.report();
    this.showLive();
    const status = this.note(problem, problem ? "arcade-note arcade-error" : "arcade-note");
    const buttons = [this.button(problem ? "Try again" : "Play", () => this.play(), true)];
    if (this.inServer) {
      buttons.push(this.button("Leaderboard", () => this.showBoard()));
    }
    this.show(
      [
        ...(this.options.icon ? [this.logo("arcade-logo")] : []),
        el("h1", { text: this.options.title }),
        el("p", { class: "arcade-help", text: this.options.help }),
        this.controls(),
        status,
        this.actions(buttons),
      ],
      "arcade-title-card",
    );
    if (problem) {
      return;
    }
    if (this.hub.offline) {
      status.textContent = "Preview: open this from Discord to save scores.";
    } else if (!this.inServer) {
      status.textContent = "Scores are only saved when you play in a server.";
    } else {
      const board = await this.loadBoard(status);
      if (board && status.isConnected) {
        status.textContent = this.standing(board);
      }
    }
  }

  async loadBoard(status) {
    try {
      const board = await this.hub.api("board");
      this.best = board.you ? board.you.score : null;
      this.showBest();
      return board;
    } catch (e) {
      status.textContent = e.message;
      status.classList.add("arcade-error");
      return null;
    }
  }

  async showBoard() {
    const status = this.note("Loading...");
    this.show([el("h1", { text: "Leaderboard" }), status, this.actions([this.button("Back", () => this.showTitle(), true)])]);
    const board = await this.loadBoard(status);
    if (board && status.isConnected) {
      status.replaceWith(this.boardList(board));
    }
  }

  boardRow(row) {
    const medal = MEDALS[row.rank - 1];
    const avatar = el("img", { class: "avatar", src: row.avatar, alt: "" });
    avatar.addEventListener("error", () => avatar.replaceWith(el("span", { class: "avatar" })));
    return el("li", { class: row.you ? "you" : "" }, [
      el("span", { class: medal ? `rank ${medal}` : "rank", text: String(row.rank) }),
      avatar,
      el("span", { class: "name", text: row.name }),
      el("span", { class: "points", text: fmt(row.score) }),
    ]);
  }

  boardList(board) {
    if (!board.top.length) {
      return this.note(`Nobody in ${board.server} has a score yet. Be the first!`);
    }
    const rows = board.top.map((row) => this.boardRow(row));
    // Someone outside the top still sees where they stand, under a gap
    if (board.you && !board.top.some((row) => row.you)) {
      rows.push(el("li", { class: "gap", "aria-hidden": "true", text: "⋯" }), this.boardRow(board.you));
    }
    return el("div", { class: "arcade-board-box" }, [
      el("p", { class: "arcade-server", text: `Top scores in ${board.server}` }),
      el("ol", { class: "arcade-board" }, rows),
    ]);
  }

  // ---------- Rounds ----------

  async newRound() {
    if (this.hub.offline) {
      return { seed: randomSeed(), run: null };
    }
    return this.hub.api("start");
  }

  async play() {
    this.unlockAudio();
    this.show([this.note("Starting...")]);
    let round;
    try {
      round = await this.newRound();
    } catch (e) {
      console.warn("Arcade: couldn't start a round", e);
      this.showTitle(`Couldn't start a round: ${e.message}`);
      return;
    }
    this.run = round.run;
    this.cashRun = null;
    this.hide();
    this.playing = true;
    this.paused = false;
    this.pauseButton.hidden = false;
    this.score = 0;
    this.scored = true;
    this.ahead.clear();
    this.drawScore(0);
    this.report();
    this.followRivals();
    this.showLive();
    this.game.play(round.seed);
  }

  pause() {
    if (!this.playing || this.paused) {
      return;
    }
    this.paused = true;
    this.report();
    this.game.pause();
    this.show([
      el("h1", { text: "Paused" }),
      this.note("Press Esc or P to keep playing."),
      this.actions([this.button("Resume", () => this.resume(), true), this.button("End round", () => this.endNow())]),
    ]);
  }

  resume() {
    this.paused = false;
    this.report();
    this.hide();
    this.game.resume();
  }

  endNow() {
    const { score, proof } = this.game.stop();
    this.over(score, proof);
  }

  // The bot keeps the round open until a finish reaches it. When the request got no answer (a dropped
  // connection) or the bot failed, the round is kept so it can be sent again; any other answer closed it
  async save(proof) {
    const run = this.run;
    if (!run) {
      return null;
    }
    try {
      const result = await this.hub.api("finish", { run, ...proof });
      this.run = null;
      this.cashRun = run;
      return result;
    } catch (e) {
      if (e.status >= 400 && e.status < 500) {
        this.run = null;
      }
      throw e;
    }
  }

  countUp(node, value) {
    node.dataset.value = String(value);
    if (reducedMotion.matches || value <= 0) {
      node.textContent = fmt(value);
      return;
    }
    const start = performance.now();
    const tick = (now) => {
      const done = Math.min(1, (now - start) / COUNT_UP_MS);
      node.textContent = fmt(Math.round(value * (1 - (1 - done) ** 3)));
      if (done < 1 && node.isConnected) {
        requestAnimationFrame(tick);
      }
    };
    requestAnimationFrame(tick);
  }

  // A round can end by itself while the player ends it too (a last move landing as they leave), so only the
  // first end counts
  async over(score, proof) {
    if (!this.playing) {
      return;
    }
    this.playing = false;
    this.paused = false;
    this.pauseButton.hidden = true;
    this.hint("");
    this.score = score;
    this.report();
    this.showLive();
    const place = this.placeLine(score);
    const final = el("p", { class: "arcade-final" });
    const status = this.note(this.run ? "Saving..." : "");
    const again = this.button("Play again", () => this.play(), true);
    const menu = this.button("Menu", () => this.leave());
    this.show(
      [el("h1", { text: "Game over" }), final, ...(place ? [place] : []), status, this.actions([again, menu])],
      "arcade-results",
    );
    this.countUp(final, score);
    if (!this.run) {
      status.textContent = this.hub.offline
        ? "Preview: open this from Discord to save scores."
        : "Scores are only saved when you play in a server.";
      return;
    }
    this.saving = this.finishSave(proof, status, again);
    await this.saving;
    this.focusPrimary();
  }

  async finishSave(proof, status, again) {
    again.disabled = true;
    try {
      this.showSaved(await this.save(proof), status);
    } catch (e) {
      status.textContent = e.message;
      status.classList.add("arcade-error");
      if (this.run === null) {
        return;
      }
      const retry = this.button("Retry save", () => {
        status.classList.remove("arcade-error");
        status.textContent = "Saving...";
        this.saving = this.finishSave(proof, status, again);
      });
      status.append(" ", retry);
    } finally {
      again.disabled = false;
    }
  }

  showSaved(result, status) {
    this.best = result.best;
    this.showBest();
    if (result.newBest) {
      status.replaceChildren(el("span", { class: "arcade-new-best", text: "★ New best!" }));
      this.tune([659, 784, 988, 1319], 0.08);
    } else {
      status.textContent = result.best ? `Your best ${fmt(result.best)}` : "Score some points to get on the board.";
    }
    status.after(...this.offer(result.offer), this.boardList(result.board));
  }

  // ---------- Cashing in ----------

  // Where the server pays for scores: what this round is worth, and a button to cash it in. Playing again gives
  // it up, so players save their few cash-ins a day for their best rounds
  offer(offer) {
    if (!offer) {
      return [];
    }
    if (offer.left <= 0) {
      return [this.note("No cash-ins left for this game today. They come back at midnight UTC.")];
    }
    if (offer.worth <= 0) {
      return [this.note(`Score more to earn ${offer.currency}.`)];
    }
    const text = this.note(
      `Worth ${fmt(offer.worth)} ${offer.currency} · ${offer.left} of ${offer.plays} cash-ins left today`,
    );
    const button = this.button(`Cash in ${fmt(offer.worth)}`, () => this.cashIn(box, button), true);
    button.classList.add("arcade-cash");
    const box = el("div", { class: "arcade-offer" }, [text, button]);
    return [box];
  }

  async cashIn(box, button) {
    button.disabled = true;
    button.textContent = "Cashing in...";
    try {
      const paid = await this.hub.api("cashin", { run: this.cashRun });
      const left = paid.left === 1 ? "1 cash-in" : `${paid.left} cash-ins`;
      box.replaceChildren(
        el("span", { class: "arcade-paid", text: `+${fmt(paid.paid)} ${paid.currency}` }),
        this.note(`${left} left for this game today.`),
      );
      this.tune([784, 988, 1175, 1568], 0.06);
      this.focusPrimary();
    } catch (e) {
      box.replaceChildren(this.note(e.message, "arcade-note arcade-error"));
      this.focusPrimary();
    }
  }

  // Leaving mid-round still saves the score so far
  async leave() {
    if (this.playing) {
      const { score, proof } = this.game.stop();
      this.playing = false;
      if (score > 0) {
        await this.save(proof).catch((e) => console.warn("Arcade: couldn't save the round before leaving", e));
      }
    } else if (this.saving) {
      // Closing the game frame would cancel a save that is still on its way
      await this.saving;
    }
    this.hub.backToMenu();
  }

  // ---------- Input ----------

  listen(autoPause) {
    window.addEventListener("pointerdown", () => this.unlockAudio());
    window.addEventListener("keydown", (event) => {
      this.unlockAudio();
      if (PAUSE_KEYS.includes(event.key) && this.playing) {
        if (this.paused) {
          this.resume();
        } else {
          this.pause();
        }
      } else if (event.key === "m" || event.key === "M") {
        this.toggleMute();
      }
    });
    if (!autoPause) {
      return;
    }
    // Clicking into Discord's chat takes the keyboard away from the game, so a moving game stops and waits
    window.addEventListener("blur", () => this.pause());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.pause();
      }
    });
  }
}

export async function startArcade(options) {
  const hub = await connect();
  const arcade = new Arcade(hub, options);
  arcade.showTitle();
  return arcade;
}
