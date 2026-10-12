// The world menu: the dropdown under the bar's world button. It holds what belongs to the whole world rather than to
// the brush, in groups: Sharing, Spigots, Simulation (speed, the bottom edge, the creatures) and Appearance (the
// backdrop and the heat view), with Reset and Clear set apart at the bottom. Every change is a stroke sent the same
// way painting is, so a shared world applies it at the same step on every screen.
import { ELEMENTS, STROKE, TABS } from "../sim/index.js";
import { icon } from "./icons.js";

const SPEEDS = ["Paused", "1/4", "1/2", "1x", "2x"];
const SET_SPIGOT_ELEMENT = 0;
const SET_SPIGOT_SIZE = 4;
const SET = { floor: 8, slug: 9, zombies: 10, backdrop: 11 };
const SPIGOT_COUNT = 4;
const SPIGOT_MAX = 5;
const ZOMBIE_COUNTS = [0, 10, 20, 30];
// [title, first row order, column]: a row joins the last group whose first order is at or below its own. Reset and
// Clear sit alone at 90. The columns only show on a short sideways screen; elsewhere the groups run in one column, in this order.
const GROUPS = [
  ["Sharing", 0, 0],
  ["Spigots", 10, 0],
  ["Simulation", 20, 1],
  ["Appearance", 60, 1],
];
const END = 90;

function pair(...buttons) {
  const node = make("div", "menu-pair");
  node.append(...buttons);
  return node;
}

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

function row(label, ...controls) {
  const node = make("div", "menu-row");
  node.append(make("span", "menu-label", label), ...controls);
  return node;
}

// A row of buttons where exactly one is on. pick(value) runs when one is pressed; refresh(value) lights the right one.
function segmented(label, options, pick) {
  const group = make("div", "seg");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", label);
  const buttons = options.map(([value, text]) => {
    const button = make("button");
    button.type = "button";
    if (typeof text === "string") {
      button.textContent = text;
    } else {
      button.append(text);
    }
    button.addEventListener("click", () => {
      show(value);
      pick(value);
    });
    group.append(button);
    return [value, button];
  });
  function show(current) {
    for (const [value, button] of buttons) {
      button.setAttribute("aria-pressed", String(value === current));
    }
  }
  return { node: group, show };
}

// Elements the spigots can pour: everything painted from a tab, grouped like the tabs
function elementSelect(label) {
  const select = make("select", "menu-select");
  select.setAttribute("aria-label", label);
  for (const tab of TABS) {
    const group = make("optgroup");
    group.label = tab.name;
    for (const element of ELEMENTS.filter((e) => e.tab === tab.key && e.paint)) {
      const option = make("option", "", element.name);
      option.value = String(element.id);
      group.append(option);
    }
    select.append(group);
  }
  return select;
}

function spigotRow(k, send) {
  const select = elementSelect(`Spigot ${k + 1} element`);
  const range = make("input", "menu-range");
  range.type = "range";
  range.min = "0";
  range.max = String(SPIGOT_MAX);
  range.step = "1";
  range.setAttribute("aria-label", `Spigot ${k + 1} size`);
  const size = make("output", "menu-value");
  select.addEventListener("change", () => send([STROKE.SET, SET_SPIGOT_ELEMENT + k, Number(select.value)]));
  range.addEventListener("input", () => {
    size.textContent = range.value === "0" ? "Off" : range.value;
    send([STROKE.SET, SET_SPIGOT_SIZE + k, Number(range.value)]);
  });
  const node = row(`Spigot ${k + 1}`, select, range, size);
  node.classList.add("menu-spigot");
  // A control the player is using keeps what they just set until they let go
  function refresh(world) {
    const [element, level] = world.spigots[k];
    if (document.activeElement !== select) {
      select.value = String(element);
    }
    if (document.activeElement !== range) {
      range.value = String(level);
    }
    size.textContent = level === 0 ? "Off" : String(level);
  }
  return { node, refresh };
}

/**
 * Builds the world menu behind the bar's world button. Returns { addRow(order, element), refresh() }. Other parts of
 * the page add their own rows with addRow; refresh() reads the world and the speed again.
 */
export function buildWorldMenu(state) {
  const button = document.getElementById("world-menu");
  const panel = make("section", "worldmenu glass");
  panel.id = "worldmenu";
  panel.hidden = true;
  button.setAttribute("aria-controls", panel.id);
  button.setAttribute("aria-expanded", "false");
  const send = (stroke) => state.sendStroke(stroke);
  const refreshers = [];

  // Rows marked owner-only are the world's controls: in someone else's shared world they are the owner's to change
  const ownerOnly = [];
  const hint = make("p", "menu-hint");
  hint.hidden = true;

  const columns = [make("div", "menu-col"), make("div", "menu-col")];
  const groups = GROUPS.map(([title, from, column]) => {
    const node = make("div", "menu-group");
    node.append(make("h2", "menu-title", title));
    columns[column].append(node);
    return { node, from };
  });
  const end = make("div", "menu-end");
  panel.append(...columns, end);

  // Rows are kept in order within their group; each part of the page says where its own rows go
  function addRow(order, element) {
    element.dataset.order = String(order);
    const box = order >= END ? end : groups.findLast((group) => group.from <= order).node;
    const after = [...box.children].find((child) => Number(child.dataset.order) > order);
    box.insertBefore(element, after ?? null);
    return element;
  }

  addRow(5, hint);
  for (let k = 0; k < SPIGOT_COUNT; k++) {
    const spigot = spigotRow(k, send);
    refreshers.push(spigot.refresh);
    ownerOnly.push(addRow(10 + k, spigot.node));
  }

  // Sharing: open or close my world to friends, the Worlds panel, and leaving someone else's world
  function shareButton(label, onClick) {
    const node = make("button", "menu-action", label);
    node.type = "button";
    node.addEventListener("click", () => {
      setOpen(false);
      onClick();
    });
    return node;
  }
  const openToFriends = shareButton("Open to friends", () => state.shared.open());
  const closeToFriends = shareButton("Close to friends", () => state.shared.close());
  const worlds = shareButton("Worlds", () => state.worlds?.toggle());
  const leave = shareButton("Leave", () => state.shared.exit());
  const sharing = make("div", "menu-share");
  sharing.append(openToFriends, closeToFriends, worlds, leave);
  addRow(1, sharing);

  // Speed, with Step once beside it while paused
  const speed = segmented(
    "Speed",
    // Paused shows the pause icon: the word doesn't fit beside four more buttons
    SPEEDS.map((text, value) => [value, value === 0 ? icon("pause") : text]),
    (value) => state.setSpeed(value),
  );
  speed.node.firstElementChild.setAttribute("aria-label", SPEEDS[0]);
  speed.node.firstElementChild.title = SPEEDS[0];
  const step = make("button", "menu-action", "Step");
  step.type = "button";
  step.title = "Step once";
  step.addEventListener("click", () => state.stepOnce());
  ownerOnly.push(addRow(20, row("Speed", speed.node, step)));
  refreshers.push(() => speed.show(state.runner.speed));

  function setting(order, label, key, field, options) {
    const control = segmented(label, options, (value) => send([STROKE.SET, key, value]));
    ownerOnly.push(addRow(order, row(label, control.node)));
    refreshers.push((world) => control.show(world.settings[field]));
  }
  setting(30, "Bottom", SET.floor, "floor", [
    [0, "Drain"],
    [1, "Floor"],
  ]);
  setting(40, "Slug", SET.slug, "slug", [
    [0, "Move"],
    [1, "Stop"],
    [2, "Gone"],
  ]);
  setting(
    50,
    "Zombies",
    SET.zombies,
    "zombies",
    ZOMBIE_COUNTS.map((n) => [n, String(n)]),
  );
  setting(60, "Backdrop", SET.backdrop, "backdrop", [
    [0, "Dusk"],
    [1, "Night"],
    [2, "Day"],
    [3, "Cave"],
  ]);

  const reset = make("button", "menu-action menu-danger", "Reset to start");
  reset.type = "button";
  reset.title = "Puts back the scene every new world starts with";
  reset.addEventListener("click", () => send([STROKE.RESET]));
  const clear = make("button", "menu-action menu-danger", "Clear the world");
  clear.type = "button";
  clear.addEventListener("click", () => send([STROKE.CLEAR]));
  ownerOnly.push(addRow(END, pair(reset, clear)));

  // The world button names the world on screen
  const worldName = button.querySelector(".bar-world-name");
  function refreshShare() {
    const shared = state.shared;
    const inWorld = shared?.inWorld != null;
    openToFriends.hidden = inWorld;
    openToFriends.disabled = shared?.conn == null || shared.lost;
    openToFriends.title = openToFriends.disabled ? "Needs the live connection" : "";
    closeToFriends.hidden = !shared?.isOwner;
    leave.hidden = !inWorld || shared.ownsWorld;
    worldName.textContent = !inWorld || shared.ownsWorld ? "Your world" : `${shared.ownerName}'s world`;
  }

  function refreshLock() {
    const locked = state.shared?.locked ?? false;
    hint.hidden = !locked;
    const owner = state.shared?.ownerName || "The owner";
    hint.textContent = locked ? `${owner} runs this world, so only they can change these.` : "";
    for (const node of ownerOnly) {
      for (const control of node.querySelectorAll("button, select, input")) {
        control.disabled = locked;
      }
    }
    step.disabled = locked || state.runner.speed !== 0;
  }

  function refresh() {
    for (const fn of refreshers) {
      fn(state.world);
    }
    refreshShare();
    refreshLock();
  }

  // Under the world button, kept on screen
  function place() {
    const edge = 8;
    const room = document.documentElement.clientWidth - panel.offsetWidth - edge;
    panel.style.left = `${Math.max(edge, Math.min(button.getBoundingClientRect().left, room))}px`;
  }
  function setOpen(open) {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) {
      state.toolbar?.close();
      place();
      refresh();
    }
  }
  button.addEventListener("click", () => setOpen(panel.hidden));
  document.addEventListener("pointerdown", (event) => {
    if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
      setOpen(false);
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      setOpen(false);
      button.focus();
    }
  });
  window.addEventListener("resize", () => {
    if (!panel.hidden) {
      place();
    }
  });
  // A setting that changed (here, by a reset, or from the owner of a shared world) shows up once its batch has been
  // applied
  state.runner.onBatch((batch) => {
    if (!panel.hidden && batch[2].some(([, stroke]) => stroke[0] === STROKE.SET || stroke[0] === STROKE.RESET)) {
      refresh();
    }
  });

  document.body.append(panel);
  refresh();
  return { addRow, refresh, close: () => setOpen(false) };
}
