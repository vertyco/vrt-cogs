// The run's own controls and numbers: lives, money, the wave, the score, pause, and the two round power buttons in
// the bottom corners. A cooling power is gray with its seconds left; a ready one glows, and pops the moment it is
// ready again. The first time a robot type comes in during a run, a note says what it does. Text is only
// written when it changed, so the page does no needless work each frame. Game buttons act on press, not release,
// like taps on the map.
import { POWERS, ROBOTS, STEPS, WAVES } from "../sim/rules.js";
import { robotRole } from "./info.js";

const POWER_NAMES = ["strike", "stasis"];
const POWER_LABELS = { strike: "Strike", stasis: "Stasis" };
// How long a power that just became ready pops, in milliseconds
const FRESH_MS = 900;
const LOW_LIVES = 5;
// How long each new robot's note stays up, in milliseconds
const NOTE_MS = 5000;

function $(id) {
  return document.getElementById(id);
}

// Acts the moment a finger or the mouse goes down. A keyboard's Enter or Space only makes a click, which has no
// pointer behind it (detail 0), so that still works too
function press(id, handler) {
  const node = $(id);
  node.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    handler();
  });
  node.addEventListener("click", (event) => {
    if (event.detail === 0) {
      handler();
    }
  });
}

export class Hud {
  constructor(page, actions) {
    this.page = page;
    this.aim = null;
    // What each element shows now, so a frame that changes nothing writes nothing
    this.shown = new Map();
    // Robot types this run has already brought, and the notes about new ones waiting their turn
    this.seen = new Set();
    this.notes = [];
    this.noteTimer = null;
    press("pause", () => actions.pause());
    for (const name of POWER_NAMES) {
      press(`power-${name}`, () => this.toggleAim(name));
    }
  }

  text(id, value) {
    if (this.shown.get(id) !== value) {
      this.shown.set(id, value);
      $(id).textContent = value;
    }
  }

  flag(id, name, on) {
    const key = `${id}:${name}`;
    if (this.shown.get(key) !== on) {
      this.shown.set(key, on);
      $(id).classList.toggle(name, on);
    }
  }

  update(run) {
    this.text("lives", String(run.lives));
    this.flag("lives-box", "low", run.lives <= LOW_LIVES);
    this.text("money", run.money.toLocaleString());
    this.text("score", run.score.toLocaleString());
    this.text("wave", String(run.wave));
    this.power("strike", run.strikeReady, POWERS.strike.cooldown, run);
    this.power("stasis", run.stasisReady, POWERS.stasis.cooldown, run);
    for (const robot of run.robots) {
      if (!this.seen.has(robot.type)) {
        this.seen.add(robot.type);
        this.note(robot.type);
      }
    }
  }

  // A new run: the robot types it has brought so far need no note. A run brought back mid-way has had every type
  // its waves so far could bring
  startRun(run) {
    for (const name of POWER_NAMES) {
      this.shown.delete(`${name}:cool`);
    }
    this.seen.clear();
    ROBOTS.forEach((info, type) => {
      const boss = info.boss && run.wave > WAVES.bossEvery;
      if ((info.from >= 1 && info.from < run.wave) || boss) {
        this.seen.add(type);
      }
    });
    for (const robot of run.robots) {
      this.seen.add(robot.type);
    }
    this.notes = [];
    clearTimeout(this.noteTimer);
    this.noteTimer = null;
    $("news").hidden = true;
  }

  // The note about a new robot type, after any already showing
  note(type) {
    this.notes.push(type);
    if (this.noteTimer === null) {
      this.nextNote();
    }
  }

  nextNote() {
    const type = this.notes.shift();
    if (type === undefined) {
      this.noteTimer = null;
      $("news").hidden = true;
      return;
    }
    const icon = this.page.scene.icons[type] || "";
    $("news-icon").hidden = !icon;
    if (icon) {
      $("news-icon").src = icon;
    }
    $("news-name").textContent = ROBOTS[type].name;
    $("news-text").textContent = robotRole(type);
    $("news").hidden = false;
    this.noteTimer = setTimeout(() => this.nextNote(), NOTE_MS);
  }

  // Cooling down, a ring fills round the edge and the whole seconds left show in place of the icon. A ready power
  // glows, and one that only now became ready pops (not at a run's start, when both just are)
  power(name, readyAt, cooldown, run) {
    const left = Math.max(0, readyAt - run.step);
    const cool = left > 0 ? (left / cooldown).toFixed(3) : "0";
    const key = `${name}:cool`;
    if (this.shown.get(key) !== cool) {
      const was = this.shown.get(key);
      this.shown.set(key, cool);
      const button = $(`power-${name}`);
      button.style.setProperty("--cool", cool);
      button.classList.toggle("ready", left === 0);
      button.setAttribute("aria-disabled", String(left > 0));
      if (left === 0 && was !== undefined && was !== "0") {
        this.pop(button);
      }
    }
    this.text(`power-${name}-label`, left > 0 ? `${Math.ceil(left / STEPS)}s` : POWER_LABELS[name]);
    if (left > 0 && this.aim === name) {
      this.setAim(null);
    }
  }

  pop(button) {
    button.classList.remove("fresh");
    // Read the layout so taking the class off and putting it back starts the animation again
    void button.offsetWidth;
    button.classList.add("fresh");
    clearTimeout(button.freshTimer);
    button.freshTimer = setTimeout(() => button.classList.remove("fresh"), FRESH_MS);
  }

  // Tap a ready power and it lights up for the next tap on the map; tap it again to put it away
  toggleAim(name) {
    const page = this.page;
    const run = page.run;
    if (!run || page.paused || page.finished || page.stopped || page.screen !== "play") {
      return;
    }
    if (this.aim === name) {
      this.setAim(null);
      return;
    }
    const readyAt = name === "strike" ? run.strikeReady : run.stasisReady;
    if (run.step >= readyAt) {
      page.clearFocus();
      this.setAim(name);
    }
  }

  setAim(name) {
    this.aim = name;
    for (const other of POWER_NAMES) {
      $(`power-${other}`).classList.toggle("lit", other === name);
    }
    document.body.classList.toggle("aiming", name !== null);
  }
}
