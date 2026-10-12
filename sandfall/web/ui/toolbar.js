// The toolbar: a rail of element tabs with a panel of the open tab's elements beside it, and a dock along the bottom
// with the recent row (keys 1 to 9), the tool row and the brush size. The tool row comes in groups (tools, brush shapes,
// the two switches that change how any tool paints, and search) and every button explains itself on hover or a long
// press. A search box finds any element by name. The panels close themselves as soon as painting starts and fade back
// while a stroke is in progress. On an upright phone all of it lives in a bottom sheet (sheet.js) where the open tab's
// grid stays showing; the small sheet keeps the main tools and tucks the rest behind More.
import { ELEMENT_TOOLS } from "../input.js";
import { onKey } from "../keys.js";
import { EL, ELEMENTS, SHAPE, TABS } from "../sim/index.js";
import { attachHint } from "./hint.js";
import { icon } from "./icons.js";
import { buildSheet } from "./sheet.js";

// The nine elements the recent row starts with, most recently used first
const START_RECENT = [EL.sand, EL.water, EL.fire, EL.lava, EL.plant, EL.salt, EL.oil, EL.wall, EL.wood];
const SWATCH_PX = 40;
// How often, in milliseconds, the swatches in an open panel are drawn again to move their shimmer and flicker
const SWATCH_EVERY = 200;
// Room kept beside a tab scrolled into view
const GAP = 8;

// [key, name, icon, what it does, tucked]. Tucked tools wait behind More in the upright phone's small sheet.
const TOOLS = [
  ["brush", "Brush", "brush", "paints the picked element"],
  ["line", "Line", "line", "drag a line; it paints when you let go"],
  ["box", "Box", "box", "drag a box; it fills when you let go"],
  ["fill", "Fill", "fill", "floods the patch you tap with the picked element"],
  ["eraser", "Eraser", "eraser", "clears what you paint over (E)"],
  ["heat", "Heat", "heat", "warms whatever you hold it over", true],
  ["cool", "Cool", "cool", "chills whatever you hold it over", true],
  ["shove", "Shove", "shove", "pushes loose stuff the way you drag", true],
  ["hand", "Hand", "hand", "grabs the slug or a zombie so you can throw it", true],
  ["lightning", "Lightning", "bolt", "tap to strike a bolt down from the sky", true],
  ["picker", "Picker", "picker", "tap the world to pick the element there", true],
];
const TOOL_NAMES = new Map(TOOLS.map(([key, name]) => [key, name]));
const TUCKED = new Set(TOOLS.filter((tool) => tool[4]).map(([key]) => key));
const SHAPES = [
  [SHAPE.ROUND, "Round brush", "round", "paints a filled circle"],
  [SHAPE.SQUARE, "Square brush", "square", "paints a filled square"],
  [SHAPE.SPRAY, "Spray brush", "spray", "scatters a few cells inside the circle"],
];

function colorOf(element) {
  const [r, g, b] = element.color;
  return `rgb(${r}, ${g}, ${b})`;
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

function paintable(tab) {
  return ELEMENTS.filter((element) => element.tab === tab && element.paint);
}

// Colored sand's hue from the shade byte, the same colors the world draws it with
function hueRgb(shade) {
  const h = shade / 255;
  return [0, 4, 2].map((offset) => {
    const channel = Math.min(1, Math.max(0, Math.abs(((h * 6 + offset) % 6) - 3) - 1));
    return Math.round(255 * 0.95 * (0.4 + 0.6 * channel));
  });
}

function hueGradient() {
  const stops = [];
  for (let k = 0; k <= 12; k++) {
    stops.push(`rgb(${hueRgb(Math.round((k * 255) / 12)).join(", ")})`);
  }
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

/** Fills a swatch canvas with the element's flat color (colored sand, a rainbow) until the renderer draws it */
function drawFlat(canvas, element) {
  const ctx = canvas.getContext("2d");
  canvas.dataset.element = String(element.id);
  delete canvas.dataset.drawn;
  if (element.id === EL.coloredSand) {
    const gradient = ctx.createLinearGradient(0, 0, SWATCH_PX, SWATCH_PX);
    ["#f36", "#fb3", "#6d6", "#3bf", "#c6f"].forEach((color, k) => gradient.addColorStop(k / 4, color));
    ctx.fillStyle = gradient;
  } else {
    ctx.fillStyle = colorOf(element);
  }
  ctx.fillRect(0, 0, SWATCH_PX, SWATCH_PX);
}

function swatch(element) {
  const canvas = make("canvas", "swatch");
  canvas.width = SWATCH_PX;
  canvas.height = SWATCH_PX;
  drawFlat(canvas, element);
  return canvas;
}

function hintText(element) {
  return element.blurb ? `${element.name}: ${element.blurb}` : element.name;
}

function elementButton(element, choose) {
  const button = make("button", "element");
  button.type = "button";
  button.dataset.id = String(element.id);
  button.setAttribute("aria-label", element.name);
  button.append(swatch(element), make("span", "element-name", element.name));
  attachHint(button, () => hintText(element));
  button.addEventListener("click", () => choose(element.id));
  return button;
}

// A tool button with an icon. Its hint names it and says what it does, on hover and on a long press alike.
function toolButton(label, name, getHint) {
  const button = make("button", "tool");
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.append(icon(name));
  attachHint(button, getHint);
  return button;
}

function toolGroup(className, label, buttons) {
  const group = make("div", `tool-group ${className}`);
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", label);
  group.append(...buttons);
  return group;
}

function buildRail(openTab) {
  const rail = make("nav", "rail glass");
  rail.id = "rail";
  rail.setAttribute("aria-label", "Element tabs");
  for (const tab of TABS) {
    const button = make("button", "tab");
    button.type = "button";
    button.dataset.tab = tab.key;
    button.setAttribute("aria-label", tab.name);
    const dot = make("span", "tab-dot");
    const first = paintable(tab.key)[0];
    dot.style.background = first ? colorOf(first) : "transparent";
    button.append(dot, make("span", "tab-name", tab.name));
    button.addEventListener("click", () => openTab(tab.key));
    rail.append(button);
  }
  // In the phone's sheet the tabs scroll sideways; this stays at the right edge while more tabs wait past it
  const more = make("button", "rail-more");
  more.type = "button";
  more.tabIndex = -1;
  more.setAttribute("aria-label", "More tabs");
  more.append(icon("chevron"));
  more.addEventListener("click", () => rail.scrollBy({ left: rail.clientWidth * 0.7, behavior: "smooth" }));
  rail.append(more);
  return rail;
}

function buildSizer(painter, refresh) {
  const box = make("div", "sizer glass");
  // The tool in hand, with the picked element's color when it paints one
  const now = make("span", "tool-now");
  const nowDot = make("span", "tool-now-dot");
  const nowName = make("span", "tool-now-name");
  now.append(nowDot, nowName);
  const label = make("div", "sizer-size");
  const input = document.createElement("input");
  input.type = "range";
  input.min = "1";
  input.max = "40";
  input.step = "1";
  input.title = "Brush size";
  input.setAttribute("aria-label", "Brush size");
  const value = make("output", "sizer-value");
  input.addEventListener("input", () => {
    painter.size = Number(input.value);
    refresh();
  });
  label.append(input, value);
  const hue = document.createElement("input");
  hue.type = "range";
  hue.className = "hue";
  hue.min = "0";
  hue.max = "255";
  hue.step = "1";
  hue.value = String(painter.hue);
  hue.style.background = hueGradient();
  hue.title = "Colored sand color";
  hue.setAttribute("aria-label", "Colored sand color");
  hue.hidden = true;
  hue.addEventListener("input", () => {
    painter.hue = Number(hue.value);
  });
  box.append(now, label, hue);
  return { box, input, value, hue, nowDot, nowName };
}

// The tool row: tools, brush shapes, the two switches, and search, each group set apart. sheetOpen() says whether the
// phone's sheet shows everything, for the More button's hint.
function buildTools(painter, refresh, sheetOpen) {
  const row = make("div", "tools glass");
  row.setAttribute("role", "toolbar");
  row.setAttribute("aria-label", "Tools");
  const tools = TOOLS.map(([key, label, name, does, tucked]) => {
    const button = toolButton(label, name, () => `${label}: ${does}`);
    button.dataset.tool = key;
    button.classList.toggle("tool-tucked", Boolean(tucked));
    button.addEventListener("click", () => {
      painter.tool = key;
      refresh();
    });
    return button;
  });
  const more = toolButton("More tools", "more", () => (sheetOpen() ? "Fewer tools" : "More tools and brush shapes"));
  more.classList.add("tool-more");
  const shapes = SHAPES.map(([value, label, name, does]) => {
    const button = toolButton(label, name, () => `${label}: ${does}`);
    button.dataset.shape = String(value);
    button.addEventListener("click", () => {
      painter.shape = value;
      refresh();
    });
    return button;
  });
  const empty = toolButton("Only into empty", "empty", () => "Only into empty: skips cells that already hold something");
  empty.addEventListener("click", () => {
    painter.onlyEmpty = !painter.onlyEmpty;
    refresh();
  });
  const mirror = toolButton("Mirror", "mirror", () => "Mirror: also paints a copy flipped across the middle");
  mirror.addEventListener("click", () => {
    painter.mirror = !painter.mirror;
    refresh();
  });
  const find = toolButton("Search elements", "search", () => "Search elements (F)");
  row.append(
    toolGroup("tools-main", "Tools", [...tools, more]),
    toolGroup("tools-shapes", "Brush shape", shapes),
    toolGroup("tools-switches", "Painting switches", [empty, mirror]),
    toolGroup("tools-find", "Search", [find]),
  );
  return { row, tools, more, shapes, empty, mirror, find };
}

/**
 * Builds the toolbar into the page. Returns { setElement(id), refresh(), close(), margins(), onResize(fn),
 * drawSwatches(renderer, now), tick(), holdSheet(node), releaseSheet() }. drawSwatches and tick run every frame;
 * drawSwatches decides itself which swatches need drawing.
 * margins() is the room the toolbar takes from each side of the stage: { left, right, bottom }.
 */
export function buildToolbar(state) {
  const painter = state.painter;
  const resizeListeners = [];
  const panel = make("section", "panel glass");
  panel.id = "panel";
  panel.hidden = true;
  const title = make("h2", "panel-title");
  const grid = make("div", "panel-grid");
  panel.append(title, grid);
  let openKey = null;

  // Nine slots for the recent row. recency lists the same ids, newest first; an element not in the row takes the
  // slot of the one used longest ago, so the other number keys keep their elements.
  const slots = [...START_RECENT];
  const recency = [...START_RECENT];
  const recent = make("div", "recent glass");
  recent.setAttribute("role", "group");
  recent.setAttribute("aria-label", "Recent elements");
  const slotButtons = slots.map((id, k) => {
    const button = make("button", "slot");
    button.type = "button";
    button.append(swatch(ELEMENTS[id]), make("span", "slot-key", String(k + 1)));
    attachHint(button, () => `${hintText(ELEMENTS[slots[k]])} (key ${k + 1})`);
    button.addEventListener("click", () => choose(slots[k]));
    return button;
  });
  recent.append(...slotButtons);

  function noteUsed(id) {
    const at = recency.indexOf(id);
    if (at < 0) {
      const oldest = recency.pop();
      slots[slots.indexOf(oldest)] = id;
    } else {
      recency.splice(at, 1);
    }
    recency.unshift(id);
  }

  function choose(id) {
    painter.element = id;
    if (!ELEMENT_TOOLS.has(painter.tool)) {
      painter.tool = "brush";
    }
    noteUsed(id);
    closeSearch();
    refresh();
  }

  function fillPanel(key) {
    title.textContent = TABS.find((tab) => tab.key === key).name;
    grid.replaceChildren(...paintable(key).map((element) => elementButton(element, choose)));
  }

  // On the desktop a tab opens and closes its panel; in the phone's sheet the grid always shows one tab
  const openTab = (key) => {
    closeSearch();
    if (sheet.upright) {
      openKey = key;
    } else {
      openKey = openKey === key ? null : key;
    }
    if (openKey !== null) {
      fillPanel(openKey);
      panel.scrollTop = 0;
    }
    refresh();
    sheet.fit();
    revealTab();
  };
  const rail = buildRail(openTab);
  const sizer = buildSizer(painter, () => refresh());
  const toolRow = buildTools(
    painter,
    () => refresh(),
    () => sheet.open,
  );
  const dock = make("div", "dock");
  dock.id = "dock";
  dock.append(recent, toolRow.row, sizer.box);

  // Search: a box that filters every paintable element by name; Enter picks the first match
  const search = make("section", "search glass");
  search.hidden = true;
  const field = document.createElement("input");
  field.type = "search";
  field.className = "search-field";
  field.placeholder = "Find an element";
  field.autocomplete = "off";
  field.setAttribute("aria-label", "Search elements");
  const results = make("div", "panel-grid");
  search.append(field, results);
  const sheet = buildSheet(
    { rail, panel, search, dock },
    {
      bar: document.getElementById("bar"),
      view: state.view,
      onMode: (upright) => showMode(upright),
      onResize: () => notify(),
      onState: () => refresh(),
    },
  );
  toolRow.more.addEventListener("click", () => sheet.toggle());

  // In the sheet the open tab is kept in view in the sideways-scrolling tab row, and the chevron at its right edge
  // only shows while more tabs wait past it
  function revealTab() {
    const tab = [...rail.children].find((button) => button.dataset.tab === openKey);
    if (!sheet.upright || !tab) {
      return;
    }
    const room = rail.getBoundingClientRect();
    const box = tab.getBoundingClientRect();
    const chevron = rail.lastElementChild.offsetWidth;
    if (box.left < room.left) {
      rail.scrollLeft -= room.left - box.left + GAP;
    } else if (box.right > room.right - chevron) {
      rail.scrollLeft += box.right - (room.right - chevron) + GAP;
    }
    railEnd();
  }
  function railEnd() {
    rail.classList.toggle("at-end", rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 2);
  }
  rail.addEventListener("scroll", railEnd, { passive: true });

  function matches() {
    const query = field.value.trim().toLowerCase();
    return ELEMENTS.filter((element) => element.paint && element.name.toLowerCase().includes(query));
  }

  function showMatches() {
    const found = matches();
    if (found.length === 0) {
      results.replaceChildren(make("p", "search-none", "Nothing by that name"));
    } else {
      results.replaceChildren(...found.map((element) => elementButton(element, choose)));
    }
    refresh();
    sheet.fit();
  }

  function openSearch() {
    if (!sheet.upright) {
      openKey = null;
    }
    // The small sheet leaves the results the most room beside a phone's keyboard
    sheet.collapse();
    search.hidden = false;
    field.value = "";
    showMatches();
    field.focus();
  }

  function closeSearch() {
    if (!search.hidden) {
      search.hidden = true;
      field.blur();
      refresh();
      sheet.fit();
    }
  }

  field.addEventListener("input", showMatches);
  field.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const [first] = matches();
      if (first) {
        choose(first.id);
      }
    } else if (event.key === "Escape") {
      closeSearch();
    }
  });
  toolRow.find.addEventListener("click", () => (search.hidden ? openSearch() : closeSearch()));

  function refresh() {
    panel.hidden = openKey === null || !search.hidden;
    toolRow.find.classList.toggle("on", !search.hidden);
    for (const button of rail.children) {
      button.classList.toggle("open", button.dataset.tab === openKey);
      button.classList.toggle("holding", button.dataset.tab === ELEMENTS[painter.element]?.tab);
    }
    const holding = ELEMENT_TOOLS.has(painter.tool);
    for (const button of [...grid.children, ...results.children]) {
      button.classList?.toggle("picked", Number(button.dataset.id) === painter.element && holding);
    }
    slotButtons.forEach((button, k) => {
      const element = ELEMENTS[slots[k]];
      const canvas = button.firstChild;
      if (canvas.dataset.element !== String(element.id)) {
        drawFlat(canvas, element);
      }
      button.setAttribute("aria-label", `${element.name} (key ${k + 1})`);
      button.classList.toggle("picked", slots[k] === painter.element && holding);
    });
    for (const button of toolRow.tools) {
      const on = button.dataset.tool === painter.tool;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", String(on));
    }
    refreshMore();
    const paints = holding && painter.tool !== "eraser";
    sizer.nowName.textContent = TOOL_NAMES.get(painter.tool) ?? "";
    sizer.nowDot.hidden = !paints;
    sizer.nowDot.style.background = paints ? colorOf(ELEMENTS[painter.element]) : "";
    sizer.nowDot.classList.toggle("rainbow", paints && painter.element === EL.coloredSand);
    for (const button of toolRow.shapes) {
      const on = Number(button.dataset.shape) === painter.shape;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", String(on));
    }
    for (const [button, on] of [
      [toolRow.empty, painter.onlyEmpty],
      [toolRow.mirror, painter.mirror],
    ]) {
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", String(on));
    }
    sizer.input.value = String(painter.size);
    sizer.value.textContent = String(painter.size);
    sizer.hue.hidden = painter.element !== EL.coloredSand;
  }

  // More lights up when the tool in hand is tucked away behind it; its icon only changes when the sheet does
  let moreShows = null;
  function refreshMore() {
    const more = toolRow.more;
    more.classList.toggle("on", !sheet.open && TUCKED.has(painter.tool));
    more.classList.toggle("open", sheet.open);
    more.setAttribute("aria-expanded", String(sheet.open));
    if (moreShows !== sheet.open) {
      moreShows = sheet.open;
      more.replaceChildren(icon(sheet.open ? "less" : "more"));
    }
  }

  // Painting starts: the panels get out of the way and everything else fades back until the stroke ends
  const closePanels = () => {
    if (sheet.upright) {
      if (!search.hidden) {
        closeSearch();
        refresh();
      }
      return;
    }
    if (openKey !== null || !search.hidden) {
      openKey = null;
      closeSearch();
      refresh();
    }
  };
  painter.onStart(closePanels);
  painter.onStroke(closePanels);
  painter.onActive((active) => document.body.classList.toggle("painting", active));

  // Keep focus on the world: a clicked button would otherwise take the next Space or Enter meant for the game
  for (const node of [rail, panel, dock]) {
    node.addEventListener("mousedown", (event) => {
      if (!(event.target instanceof HTMLInputElement)) {
        event.preventDefault();
      }
    });
  }

  onKey("e", () => {
    painter.tool = "eraser";
    refresh();
  });
  onKey("E", () => {
    painter.tool = "eraser";
    refresh();
  });
  for (const key of ["f", "F"]) {
    onKey(key, (event) => {
      event.preventDefault();
      openSearch();
    });
  }
  for (let k = 1; k <= 9; k++) {
    onKey(String(k), () => choose(slots[k - 1]));
  }

  document.body.append(rail, panel, search, dock);
  refresh();

  // Turning to or from the upright phone layout moves the toolbar's parts in or out of the sheet
  function showMode(upright) {
    if (upright) {
      openKey ??= ELEMENTS[painter.element]?.tab ?? TABS[0].key;
      fillPanel(openKey);
      requestAnimationFrame(revealTab);
    } else {
      openKey = null;
      closeSearch();
    }
    refresh();
    notify();
  }

  function notify() {
    resizeListeners.forEach((fn) => fn());
    railEnd();
  }

  // Swatches the renderer has never drawn are drawn at once. While a panel or the search shows, its swatches and the
  // recent row's are drawn again a few times a second; otherwise they stay still and cost nothing.
  let swatchedAt = -Infinity;
  function drawSwatches(renderer, now) {
    if (!renderer) {
      return;
    }
    const showing = [];
    for (const [box, list] of [
      [panel, grid],
      [search, results],
    ]) {
      if (!box.hidden) {
        showing.push(...[...list.querySelectorAll("canvas.swatch")].filter((c) => c.getClientRects().length > 0));
      }
    }
    const animate = showing.length > 0 && now - swatchedAt >= SWATCH_EVERY;
    if (animate) {
      swatchedAt = now;
    }
    for (const canvas of [...showing, ...slotButtons.map((button) => button.firstChild)]) {
      if (animate || canvas.dataset.drawn === undefined) {
        if (renderer.drawSwatch(Number(canvas.dataset.element), canvas.getContext("2d"), now / 1000)) {
          canvas.dataset.drawn = "1";
        }
      }
    }
  }

  // The dock can grow a row on a narrow screen, which moves the world
  new ResizeObserver(notify).observe(dock);

  // Room the toolbar takes from the stage, so the world fits beside it rather than under it. On a short sideways
  // phone the tool row is a strip down the right edge.
  function margins() {
    const upright = sheet.upright;
    const railBox = rail.getBoundingClientRect();
    const toolBox = toolRow.row.getBoundingClientRect();
    const strip = getComputedStyle(toolRow.row).position === "fixed";
    const bottomEdge = upright ? sheet.top() : dock.getBoundingClientRect().top;
    return {
      left: upright ? 0 : railBox.right,
      right: strip ? Math.max(0, window.innerWidth - toolBox.left) : 0,
      bottom: Math.max(0, window.innerHeight - bottomEdge),
    };
  }

  // Shuts the element panel and search, so a menu opening over them doesn't leave them showing behind
  function close() {
    if (!sheet.upright) {
      openKey = null;
    }
    closeSearch();
    refresh();
  }

  sheet.start();

  return {
    setElement: choose,
    refresh,
    close,
    margins,
    onResize: (fn) => resizeListeners.push(fn),
    drawSwatches,
    /** Every frame: keeps the sheet's zoom buttons in step with the zoom */
    tick: () => sheet.tick(),
    /** On an upright phone `node` (the gallery) takes the sheet's place until releaseSheet() */
    holdSheet: (node) => sheet.hold(node),
    releaseSheet: () => sheet.release(),
  };
}
