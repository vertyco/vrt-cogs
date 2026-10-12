// The settings panel behind the bar's gear button. It starts empty: each part of the page that has a setting adds its
// own row with addToggle or addSlider, and every row reads its value again each time the panel opens.
import { addBarButton } from "./bar.js";
import { icon } from "./icons.js";

const rows = [];
let panel = null;
let list = null;
let empty = null;

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

function panelNode() {
  if (panel === null) {
    panel = make("section", "settings glass");
    panel.id = "settings";
    panel.hidden = true;
    list = make("div", "settings-list");
    empty = make("p", "menu-hint", "Nothing to change yet.");
    panel.append(make("h2", "menu-title", "Settings"), list, empty);
    document.body.append(panel);
  }
  return panel;
}

function addRow(node, refresh) {
  panelNode();
  list.append(node);
  rows.push(refresh);
  empty.hidden = true;
  refresh();
  return node;
}

/** Adds an on/off row. `get()` says whether it is on now; `set(on)` runs when the player flips it */
export function addToggle(label, get, set) {
  const row = make("div", "setting");
  const name = make("span", "setting-label", label);
  const button = make("button", "switch");
  button.type = "button";
  button.setAttribute("role", "switch");
  button.setAttribute("aria-label", label);
  button.append(make("span", "switch-knob"));
  button.addEventListener("click", () => {
    set(!get());
    button.setAttribute("aria-checked", String(get()));
  });
  row.append(name, button);
  return addRow(row, () => button.setAttribute("aria-checked", String(get())));
}

/** Adds a slider row from `min` to `max` in whole steps. `get()` is its value now; `set(value)` runs as it moves */
export function addSlider(label, min, max, get, set) {
  const row = make("div", "setting");
  const name = make("span", "setting-label", label);
  const input = make("input", "setting-range");
  input.type = "range";
  input.min = String(min);
  input.max = String(max);
  input.step = "1";
  input.setAttribute("aria-label", label);
  const value = make("output", "menu-value");
  input.addEventListener("input", () => {
    set(Number(input.value));
    value.textContent = input.value;
  });
  row.append(name, input, value);
  return addRow(row, () => {
    input.value = String(get());
    value.textContent = input.value;
  });
}

/** Adds the gear button (bar order 60) and wires the panel to it. Returns { open, close } */
export function buildSettings(state) {
  const node = panelNode();
  const button = addBarButton({
    id: "settings",
    label: "Settings",
    icon: icon("gear"),
    order: 60,
    onClick: () => (node.hidden ? open() : close()),
  });
  button.setAttribute("aria-haspopup", "true");
  button.setAttribute("aria-controls", node.id);
  button.setAttribute("aria-expanded", "false");

  function open() {
    state.toolbar?.close();
    for (const refresh of rows) {
      refresh();
    }
    node.hidden = false;
    button.setAttribute("aria-expanded", "true");
  }

  function close() {
    node.hidden = true;
    button.setAttribute("aria-expanded", "false");
  }

  document.addEventListener("pointerdown", (event) => {
    if (!node.hidden && !node.contains(event.target) && !button.contains(event.target)) {
      close();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !node.hidden) {
      close();
      button.focus();
    }
  });
  return { open, close };
}
