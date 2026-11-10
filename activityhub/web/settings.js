// The settings panel: how the menu looks at each level (the player's own, the server's, the bot-wide defaults), the
// player's order of games, which games are on, and the Stats tab. Edits are staged and previewed on the menu behind
// the panel, and nothing is kept until Save. menu.js owns the menu itself and hands this file what it needs from it.
import { $, clamp, el, option } from "./dom.js";
import { icon } from "./people.js";
import { request } from "./sdk.js";
import { StatsPanel } from "./stats.js";

const TAB_NAMES = { look: "My look", order: "My order", server: "This server", defaults: "Defaults", stats: "Stats" };
// Each look tab edits one saved level and falls back to the levels before it
const LEVELS = ["global", "guild", "user"];
const TAB_LEVEL = { defaults: "global", server: "guild", look: "user" };
// Tabs with game on/off switches: the state list they come from and their heading
const SWITCHES = {
  server: { list: "switches", legend: "Activities in this server" },
  defaults: { list: "globalSwitches", legend: "Activities in every server" },
};
const FIELDS = ["theme", "layout", "accent", "glow", "background", "details", "sounds", "fps"];
// Fields only My look saves: the bot refuses them as a server or bot-wide default
const PLAYER_FIELDS = ["volume"];
const FIELD_NAMES = {
  theme: "Theme",
  layout: "Layout",
  accent: "Accent color",
  glow: "Glow color",
  background: "Background",
  details: "Descriptions",
  sounds: "Menu sounds",
  fps: "Frame rate",
};
const CHOICES = {
  theme: [["standard", "Standard"], ["orb", "Orb"]],
  layout: [["grid", "Grid"], ["list", "List"], ["compact", "Compact"]],
  background: [["dark", "Dark"], ["darker", "Darker"], ["gradient", "Gradient"]],
  details: [[true, "Show"], [false, "Hide"]],
  sounds: [[true, "On"], [false, "Off"]],
  fps: [[true, "Show"], [false, "Hide"]],
};
const TRUE_FALSE = new Set(["details", "sounds", "fps"]);
const ACCENTS = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#00A8FC", "#F0B232", "#99AAB5"];
// A row dragged this near the top or bottom of the order list scrolls the list, at most this many pixels a frame
const DRAG_EDGE = 48;
const DRAG_SCROLL = 10;

function refocus(selector) {
  const target = document.querySelector(selector);
  if (target && !target.disabled) {
    target.focus();
  }
}

function status(text) {
  $("panel-status").textContent = text;
}

function sameColor(a, b) {
  return Boolean(a) && a.toLowerCase() === b.toLowerCase();
}

function field(name, control) {
  const box = el("div", "field");
  const label = el("label", "field-label", FIELD_NAMES[name]);
  if (control.tagName === "SELECT") {
    label.htmlFor = control.id;
  }
  box.append(label, control);
  return box;
}

// A bot restart forgets every login. A request goes again once with a fresh login, like a game's request does, so
// the edits on screen aren't thrown away
async function askBot(host, path, body) {
  try {
    return await request(path, { body, session: host.login?.session });
  } catch (e) {
    if (e.status !== 401 || !host.inDiscord) {
      throw e;
    }
    // Without a fresh login the refusal stands, and the menu says the session expired
    const login = await host.relogin().catch((failed) => {
      console.error(failed);
      throw e;
    });
    return request(path, { body, session: login.session });
  }
}

export class SettingsPanel {
  // `menu` is what the panel needs from the menu around it: host and sounds, state() and setState(state) for what the
  // bot last sent, applyLook(look) and renderGames(games) to preview an edit, render() to draw the saved menu,
  // turn(step) as the panel opens (1) or closes (-1), focusOpener() and sessionExpired()
  constructor(menu) {
    this.menu = menu;
    // The open tab and its staged edits. Both are null while the panel is closed
    this.tab = null;
    this.staged = null;
    // The volume saves still on their way. Each waits for the one before, so the bot keeps the last one sent
    this.volumeSaves = Promise.resolve();
    $("gear").append(icon(document, "gear"));
    $("close").append(icon(document, "close"));
    $("gear").addEventListener("click", () => this.open());
    $("close").addEventListener("click", () => this.closeByPlayer());
    $("scrim").addEventListener("click", () => this.closeByPlayer());
    $("save").addEventListener("click", () => this.save());
    $("reset").addEventListener("click", () => this.reset());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        this.closeByPlayer();
      }
    });
    $("panel").inert = true;
  }

  get state() {
    return this.menu.state();
  }

  isOpen() {
    return this.staged !== null;
  }

  // Keyboard focus moves into the panel, so Tab doesn't wander through the menu behind it first
  open() {
    this.selectTab(this.state.tabs[0]);
    this.menu.turn(1);
    document.body.classList.add("panel-open");
    $("panel").inert = false;
    $("panel").setAttribute("aria-hidden", "false");
    $("tabs").querySelector('[aria-selected="true"]')?.focus({ preventScroll: true });
  }

  // Closing drops unsaved edits: the menu goes back to the saved state
  close() {
    if (!this.isOpen()) {
      return;
    }
    document.body.classList.remove("panel-open");
    $("panel").inert = true;
    $("panel").setAttribute("aria-hidden", "true");
    this.tab = null;
    this.staged = null;
    this.menu.render();
    this.menu.turn(-1);
  }

  closeByPlayer() {
    if (!this.isOpen()) {
      return;
    }
    this.menu.sounds.play("back");
    this.close();
    this.menu.focusOpener();
  }

  selectTab(tab) {
    this.tab = tab;
    this.staged = this.stagedFrom(tab);
    status("");
    this.renderPanel();
  }

  stagedFrom(tab) {
    // Stats has nothing to stage, but an open panel always has something staged
    if (tab === "stats") {
      return {};
    }
    const state = this.state;
    if (tab === "order") {
      return { order: state.games.map((game) => game.key), cleared: false };
    }
    const staged = { look: { ...state.looks[TAB_LEVEL[tab]] } };
    if (tab in SWITCHES) {
      staged.disabled = state[SWITCHES[tab].list].filter((game) => !game.on).map((game) => game.key);
    }
    if (this.labelsTab(tab)) {
      staged.economyLabels = state.economyLabels.on;
    }
    return staged;
  }

  // What a look tab falls back to: the built-in look plus the levels before the tab's own
  inherited() {
    const looks = this.state.looks;
    const below = LEVELS.slice(0, LEVELS.indexOf(TAB_LEVEL[this.tab]));
    return Object.assign({}, looks.builtin, ...below.map((level) => looks[level]));
  }

  // The preview leaves out levels after the tab's own, so an admin sees the server look even if they set their own.
  // The volume stays the player's own on every tab, since only My look holds one
  previewLook() {
    const look = { ...this.inherited(), ...this.staged.look };
    if (this.tab !== "look") {
      look.volume = this.state.look.volume;
    }
    return look;
  }

  preview() {
    const state = this.state;
    if (this.tab === "order") {
      this.menu.applyLook(state.look);
      const byKey = new Map(state.games.map((game) => [game.key, game]));
      this.menu.renderGames(this.staged.order.map((key) => byKey.get(key)).filter(Boolean));
    } else if (this.tab === "stats") {
      this.menu.applyLook(state.look);
      this.menu.renderGames(state.games);
    } else {
      this.menu.applyLook(this.previewLook());
      this.menu.renderGames(state.games);
    }
  }

  renderPanel() {
    $("tabs").replaceChildren(...this.state.tabs.map((tab) => this.tabButton(tab)));
    $("panel").classList.toggle("read-only", this.tab === "stats");
    const body = $("tab-body");
    if (this.tab === "order") {
      body.replaceChildren(this.orderEditor());
    } else if (this.tab === "stats") {
      const load = (query) => askBot(this.menu.host, `/hub/api/stats?${query}`);
      body.replaceChildren(new StatsPanel(load, () => this.menu.sessionExpired()).root);
    } else {
      body.replaceChildren(
        ...this.lookEditor(),
        ...(this.tab in SWITCHES ? [this.switchEditor()] : []),
        ...(this.labelsTab(this.tab) ? [this.labelsEditor()] : []),
      );
    }
    this.preview();
  }

  tabButton(tab) {
    const button = el("button", "tab", TAB_NAMES[tab]);
    button.type = "button";
    button.dataset.tab = tab;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(tab === this.tab));
    button.addEventListener("click", () => this.selectTab(tab));
    return button;
  }

  // ---------- Look fields ----------

  // The orb theme has its own background and layout, its glow color in place of the accent, and only it has menu
  // sounds. Their volume slider sits under the switch in My look alone
  lookEditor() {
    const base = this.inherited();
    if (this.previewLook().theme === "orb") {
      const menuSounds = this.choiceField("sounds", base);
      if (this.tab === "look") {
        menuSounds.append(this.volumeSlider());
      }
      return [
        this.choiceField("theme", base),
        this.colorField("glow", base),
        this.choiceField("details", base),
        menuSounds,
        this.choiceField("fps", base),
      ];
    }
    return [
      this.choiceField("theme", base),
      this.choiceField("layout", base),
      this.colorField("accent", base),
      this.choiceField("background", base),
      this.choiceField("details", base),
      this.choiceField("fps", base),
    ];
  }

  // The menu sounds' volume. It changes as the slider moves, and saves once let go, on its own: the tab's other edits
  // still wait for Save
  volumeSlider() {
    const sounds = this.menu.sounds;
    const slider = el("input", "volume");
    slider.type = "range";
    slider.id = "field-volume";
    slider.min = "0";
    slider.max = "100";
    slider.step = "5";
    slider.value = String(this.previewLook().volume);
    slider.setAttribute("aria-label", "Menu sounds volume");
    const fill = () => slider.style.setProperty("--level", `${slider.value}%`);
    fill();
    slider.addEventListener("input", () => {
      this.staged.look.volume = Number(slider.value);
      fill();
      sounds.setVolume(this.staged.look.volume);
    });
    slider.addEventListener("change", () => {
      // One short sound at the new level, so the player hears where it landed
      sounds.play("move");
      this.saveVolume(Number(slider.value));
    });
    return slider;
  }

  choiceField(name, base) {
    const select = el("select");
    select.id = `field-${name}`;
    const fallback = CHOICES[name].find(([value]) => value === base[name]);
    select.append(option("", `Default (${fallback ? fallback[1] : base[name]})`));
    for (const [value, label] of CHOICES[name]) {
      select.append(option(String(value), label));
    }
    const staged = this.staged.look[name];
    select.value = staged === undefined ? "" : String(staged);
    select.addEventListener("change", () => {
      if (select.value === "") {
        delete this.staged.look[name];
      } else {
        this.staged.look[name] = TRUE_FALSE.has(name) ? select.value === "true" : select.value;
      }
      if (name === "theme") {
        this.renderPanel();
        refocus("#field-theme");
      } else {
        this.preview();
      }
    });
    return field(name, select);
  }

  // The accent color in the Standard theme and the glow color in the Orb theme: a default, the preset colors and
  // a picker for any other, which sits in a rainbow ring so it doesn't pass for one more preset
  colorField(name, base) {
    const row = el("div", "swatches");
    row.id = `field-${name}`;
    const current = this.staged.look[name];
    row.append(this.swatch(name, null, base[name], current === undefined));
    for (const color of ACCENTS) {
      row.append(this.swatch(name, color, color, sameColor(current, color)));
    }
    const picker = el("input");
    picker.type = "color";
    picker.setAttribute("aria-label", `Custom ${FIELD_NAMES[name].toLowerCase()}`);
    picker.value = (current || base[name]).toLowerCase();
    picker.addEventListener("input", () => {
      this.staged.look[name] = picker.value;
      this.preview();
    });
    picker.addEventListener("change", () => this.renderPanel());
    const ring = el("span", "custom-color");
    ring.append(picker);
    row.append(ring);
    return field(name, row);
  }

  swatch(name, value, color, pressed) {
    const button = el("button", value === null ? "swatch default" : "swatch");
    button.type = "button";
    button.dataset.swatch = value === null ? "default" : value;
    button.style.backgroundColor = color;
    button.title = value === null ? `Default (${color})` : color;
    button.setAttribute("aria-label", button.title);
    button.setAttribute("aria-pressed", String(pressed));
    button.addEventListener("click", () => {
      if (value === null) {
        delete this.staged.look[name];
      } else {
        this.staged.look[name] = value;
      }
      this.renderPanel();
      refocus(`.swatch[data-swatch="${button.dataset.swatch}"]`);
    });
    return button;
  }

  // ---------- Order and server switches ----------

  orderEditor() {
    const list = el("ol", "order");
    const names = new Map(this.state.games.map((game) => [game.key, game.name]));
    this.staged.order.forEach((key, index) => list.append(this.orderRow(key, names.get(key), index)));
    if (!this.staged.order.length) {
      list.append(el("li", "empty", "No activities to arrange yet."));
    }
    return list;
  }

  // The arrows work with the keyboard, so the grip is only for a mouse or a finger and screen readers skip it
  orderRow(key, name, index) {
    const row = el("li", "order-row");
    row.dataset.key = key;
    const grip = el("span", "handle");
    grip.setAttribute("aria-hidden", "true");
    grip.append(icon(document, "grip"));
    grip.addEventListener("pointerdown", (event) => this.startDrag(event, row, index));
    const last = this.staged.order.length - 1;
    row.append(
      grip,
      el("span", "order-name", name),
      this.moveButton("up", `Move ${name} up`, index, index - 1, index === 0),
      this.moveButton("down", `Move ${name} down`, index, index + 1, index === last),
    );
    return row;
  }

  // A row dragged by its grip follows the pointer, and the rows it passes step aside to show where it would land.
  // Letting go puts it there. Near the top or bottom of a list too long for the panel, the list scrolls under it
  startDrag(event, row, index) {
    const rows = [...row.parentElement.children];
    if (event.button !== 0 || rows.length < 2) {
      return;
    }
    event.preventDefault();
    const grip = event.currentTarget;
    grip.setPointerCapture(event.pointerId);
    const body = $("tab-body");
    const step = rows[1].offsetTop - rows[0].offsetTop;
    const drag = { from: event.clientY, at: event.clientY, scrolled: body.scrollTop, to: index, frame: null };
    const place = () => {
      const moved = drag.at - drag.from + body.scrollTop - drag.scrolled;
      const dy = clamp(moved, -index * step, (rows.length - 1 - index) * step);
      drag.to = index + Math.round(dy / step);
      row.style.transform = `translateY(${dy}px)`;
      rows.forEach((other, i) => {
        if (other !== row) {
          const shift = i > index && i <= drag.to ? -step : i < index && i >= drag.to ? step : 0;
          other.style.transform = shift ? `translateY(${shift}px)` : "";
        }
      });
    };
    const scroll = () => {
      const box = body.getBoundingClientRect();
      const past = Math.max(0, drag.at - box.bottom + DRAG_EDGE) - Math.max(0, box.top + DRAG_EDGE - drag.at);
      if (past) {
        body.scrollTop += clamp(past / 4, -DRAG_SCROLL, DRAG_SCROLL);
        place();
      }
      drag.frame = requestAnimationFrame(scroll);
    };
    const listening = new AbortController();
    const end = (dropped) => {
      listening.abort();
      cancelAnimationFrame(drag.frame);
      if (dropped && drag.to !== index) {
        // Drawing the list again puts every row in its new place
        this.moveGame(index, drag.to);
        return;
      }
      row.classList.remove("dragging");
      rows.forEach((other) => (other.style.transform = ""));
    };
    const options = { signal: listening.signal };
    grip.addEventListener(
      "pointermove",
      (moved) => {
        drag.at = moved.clientY;
        place();
      },
      options,
    );
    grip.addEventListener("pointerup", () => end(true), options);
    grip.addEventListener("pointercancel", () => end(false), options);
    row.classList.add("dragging");
    drag.frame = requestAnimationFrame(scroll);
  }

  moveButton(direction, label, from, to, disabled) {
    const button = el("button", "icon-button");
    button.type = "button";
    button.dataset.move = direction;
    button.setAttribute("aria-label", label);
    button.disabled = disabled;
    button.append(icon(document, direction));
    button.addEventListener("click", () => this.moveGame(from, to, direction));
    return button;
  }

  moveGame(from, to, direction) {
    const order = this.staged.order;
    if (to < 0 || to >= order.length || from === to) {
      return;
    }
    const [key] = order.splice(from, 1);
    order.splice(to, 0, key);
    this.staged.cleared = false;
    this.renderPanel();
    if (direction) {
      refocus(`.order-row[data-key="${CSS.escape(key)}"] [data-move="${direction}"]`);
    }
  }

  // One row with a switch: the whole row takes the tap
  switchRow(name, on, changed) {
    const input = el("input");
    input.type = "checkbox";
    input.checked = on;
    input.addEventListener("change", () => changed(input.checked));
    const label = el("label", "switch");
    label.append(el("span", "switch-name", name), input);
    return label;
  }

  switchEditor() {
    const { list, legend } = SWITCHES[this.tab];
    const switches = this.state[list];
    const box = el("fieldset", "switches");
    box.append(el("legend", "field-label", legend));
    for (const game of switches) {
      const row = this.switchRow(game.name, !this.staged.disabled.includes(game.key), (on) => {
        const off = new Set(this.staged.disabled);
        if (on) {
          off.delete(game.key);
        } else {
          off.add(game.key);
        }
        this.staged.disabled = [...off];
      });
      row.querySelector("input").dataset.key = game.key;
      box.append(row);
    }
    if (!switches.length) {
      box.append(el("p", "", "No activities installed yet."));
    }
    return box;
  }

  // The tab holding the currency labels switch: the server tab, or the owner's defaults tab with a global bank
  labelsTab(tab) {
    return this.state.economyLabels?.tab === tab;
  }

  labelsEditor() {
    const row = this.switchRow("Show currency labels", this.staged.economyLabels, (on) => {
      this.staged.economyLabels = on;
    });
    row.querySelector("input").id = "economy-labels";
    const box = el("fieldset", "switches");
    box.append(el("legend", "field-label", "Games that use currency"), row);
    return box;
  }

  // ---------- Save and reset ----------

  saveBody() {
    const body = { tab: this.tab };
    if (this.tab === "order") {
      // After Reset no order means "alphabetical", so games installed later also land in order. An empty list
      // can't mean that: it is what a server with every game off sends
      body.order = this.staged.cleared ? null : this.staged.order;
    } else {
      const names = this.tab === "look" ? [...FIELDS, ...PLAYER_FIELDS] : FIELDS;
      const look = this.staged.look;
      body.look = Object.fromEntries(names.map((name) => [name, name in look ? look[name] : null]));
    }
    if (this.tab in SWITCHES) {
      body.disabled = this.staged.disabled;
    }
    if (this.labelsTab(this.tab)) {
      body.economyLabels = this.staged.economyLabels;
    }
    return body;
  }

  // Takes the menu the bot sends back after a save. False when the save failed, once the panel says why
  async sendSettings(body) {
    try {
      this.menu.setState(await askBot(this.menu.host, "/hub/api/settings", body));
      return true;
    } catch (e) {
      if (e.status === 401) {
        await this.menu.sessionExpired();
      } else {
        status(e.message);
      }
      return false;
    }
  }

  async save() {
    status("Saving…");
    if (!(await this.sendSettings(this.saveBody()))) {
      return;
    }
    // The panel may have closed while the save was on its way
    if (!this.isOpen()) {
      this.menu.render();
      return;
    }
    this.staged = this.stagedFrom(this.tab);
    this.renderPanel();
    status("Saved.");
  }

  // Only the volume is sent, so it saves without the tab's other edits, which stay on screen
  saveVolume(volume) {
    this.volumeSaves = this.volumeSaves
      .then(async () => {
        if ((await this.sendSettings({ tab: "look", look: { volume } })) && !this.isOpen()) {
          this.menu.render();
        }
      })
      .catch((e) => console.error(e));
  }

  // Reset is staged like any other edit: it shows the level above and saves nothing until Save
  reset() {
    if (this.tab === "order") {
      const byName = (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      this.staged.order = [...this.state.games].sort(byName).map((game) => game.key);
      this.staged.cleared = true;
    } else {
      this.staged.look = {};
    }
    this.renderPanel();
    status("Reset. Save to keep it.");
  }
}
