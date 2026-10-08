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
    this.best = null;
    this.audio = null;
    this.muted = readMuted();
    this.stage = document.getElementById("stage") || document.body;
    if (options.accent) {
      document.documentElement.style.setProperty("--arcade-accent", options.accent);
      document.documentElement.style.setProperty("--arcade-on-accent", textOn(options.accent));
    }
    this.buildBar();
    this.screen = el("div", { class: "arcade-screen", role: "dialog", "aria-modal": "true" });
    this.hintText = el("div", { class: "arcade-hint", "aria-live": "polite" });
    this.hintText.hidden = true;
    this.stage.append(this.hintText);
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
    document.body.prepend(el("header", { class: "arcade-bar" }, [back, name, stats, this.muteButton, this.pauseButton]));
    this.showMute();
    this.showBest();
    this.pauseButton.hidden = true;
  }

  logo(className) {
    const img = el("img", { class: className, src: this.options.icon, alt: "" });
    img.addEventListener("error", () => img.remove());
    return img;
  }

  setScore(score) {
    const text = fmt(score);
    if (this.scoreText.textContent === text) {
      return;
    }
    this.scoreText.textContent = text;
    // Restarting the bump animation needs a reflow between taking the class off and putting it back
    this.scoreText.classList.remove("bump");
    void this.scoreText.offsetWidth;
    this.scoreText.classList.add("bump");
  }

  showBest() {
    this.bestStat.hidden = !this.best;
    this.bestText.textContent = this.best ? fmt(this.best) : "";
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
    this.hide();
    this.playing = true;
    this.paused = false;
    this.pauseButton.hidden = false;
    this.setScore(0);
    this.game.play(round.seed);
  }

  pause() {
    if (!this.playing || this.paused) {
      return;
    }
    this.paused = true;
    this.game.pause();
    this.show([
      el("h1", { text: "Paused" }),
      this.note("Press Esc or P to keep playing."),
      this.actions([this.button("Resume", () => this.resume(), true), this.button("End round", () => this.endNow())]),
    ]);
  }

  resume() {
    this.paused = false;
    this.hide();
    this.game.resume();
  }

  endNow() {
    const { score, proof } = this.game.stop();
    this.over(score, proof);
  }

  async save(proof) {
    const run = this.run;
    this.run = null;
    if (!run) {
      return null;
    }
    return this.hub.api("finish", { run, ...proof });
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
    const final = el("p", { class: "arcade-final" });
    const status = this.note(this.run ? "Saving..." : "");
    const again = this.button("Play again", () => this.play(), true);
    const menu = this.button("Menu", () => this.leave());
    this.show([el("h1", { text: "Game over" }), final, status, this.actions([again, menu])], "arcade-results");
    this.countUp(final, score);
    if (!this.run) {
      status.textContent = this.hub.offline
        ? "Preview: open this from Discord to save scores."
        : "Scores are only saved when you play in a server.";
      return;
    }
    again.disabled = true;
    try {
      this.showSaved(await this.save(proof), status);
    } catch (e) {
      status.textContent = e.message;
      status.classList.add("arcade-error");
    }
    again.disabled = false;
    this.focusPrimary();
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
    status.after(this.boardList(result.board));
  }

  // Leaving mid-round still saves the score so far
  async leave() {
    if (this.playing) {
      const { score, proof } = this.game.stop();
      this.playing = false;
      if (score > 0) {
        await this.save(proof).catch((e) => console.warn("Arcade: couldn't save the round before leaving", e));
      }
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
