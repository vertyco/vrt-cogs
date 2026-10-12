// Sandfall's page. It connects to the hub first, then builds the world, the clock, the drawing and the controls, and
// runs them from one animation frame loop.
import { backToMenu, connect } from "activityhub";
import { Painter } from "./input.js";
import { onKey } from "./keys.js";
import { addCreatureLayer } from "./render/creatures.js";
import { Renderer } from "./render/gl.js";
import {
  addCellInfoLayer,
  addLayer,
  addOutlineLayer,
  drawOverlay,
  resizeOverlay,
  setupOverlay,
} from "./render/overlay.js";
import { Runner } from "./runner.js";
import { startSaving } from "./save.js";
import { Shared } from "./shared.js";
import { createWorld, EL, ELEMENTS, hashWorld, SHAPE, stepWorld, STROKE } from "./sim/index.js";
import { paintingKind, Sound } from "./sound.js";
import { addBarItem, buildBarMore } from "./ui/bar.js";
import { buildCursors } from "./ui/cursors.js";
import { buildGallery } from "./ui/gallery.js";
import { buildHelp } from "./ui/help.js";
import { icon } from "./ui/icons.js";
import { addSlider, addToggle, buildSettings } from "./ui/settings.js";
import { buildSoundControls } from "./ui/soundbuttons.js";
import { buildToolbar } from "./ui/toolbar.js";
import { buildWorldMenu } from "./ui/worldmenu.js";
import { buildWorlds } from "./ui/worlds.js";
import { buildUndo } from "./undo.js";
import { View } from "./view.js";
import { watchPeople } from "./whoshere.js";

const GAP = 8;
const POINT_TOOLS = new Set(["fill", "picker", "lightning", "hand"]);
const SPEED_NAMES = ["Paused", "1/4", "1/2", "1x", "2x"];
const GLOW_KEY = "sandfall:glow";
// Glow turns itself off for the session when frames keep taking longer than SLOW_FRAME_MS for SLOW_FOR_MS
const SLOW_FRAME_MS = 25;
const SLOW_FOR_MS = 3000;
// A gap this long between frames means the page was hidden, which says nothing about how fast the device is
const HIDDEN_GAP_MS = 1000;
let lastFrame = null;
let slowSince = null;

document.getElementById("back").addEventListener("click", () => backToMenu());

let hub;
try {
  hub = await connect();
} catch (e) {
  console.warn("Sandfall: couldn't connect to the hub", e);
  const message = document.getElementById("bar-error");
  message.textContent = e.message;
  message.hidden = false;
  throw e;
}

// Right after connect(), before any other await, so the hub's floating button never shows
addBarItem(100, hub.peopleButton());

const stage = document.getElementById("stage");
const bar = document.getElementById("bar");
const world = createWorld({ seed: Math.floor(Math.random() * 0x100000000) });
const view = new View();
const runner = new Runner(world);
const state = {
  hub,
  world,
  runner,
  renderer: null,
  view,
  painter: null,
  shared: null,
  sound: null,
  toolbar: null,
  worldMenu: null,
  undo: null,
  worlds: null,
  gallery: null,
  settings: null,
  help: null,
  saver: null,
  // Every stroke, painted or from a menu, leaves the page through here: to the bot in a shared world, to the page's
  // own clock otherwise. Clearing or resetting a private world can be undone too.
  sendStroke(stroke) {
    if (state.shared?.inWorld) {
      state.shared.sendStroke(stroke);
      return;
    }
    if (stroke[0] === STROKE.CLEAR || stroke[0] === STROKE.RESET) {
      state.undo.push();
    }
    runner.queueStroke(stroke);
  },
  // setSpeed is the player asking for a speed (the bot decides in a shared world); applySpeed shows the one in force
  setSpeed: () => {},
  applySpeed: () => {},
  refreshSpeed: () => {},
  stepOnce() {
    if (state.shared?.inWorld) {
      state.shared.once();
    } else {
      runner.once();
    }
  },
  setWorld,
};
state.painter = new Painter(stage, view, () => state.world);
state.sound = new Sound();
state.toolbar = buildToolbar(state);

try {
  state.renderer = new Renderer(document.getElementById("world"));
} catch (e) {
  console.warn("Sandfall: WebGL2 is missing, so the world can't be drawn", e);
  const message = document.createElement("p");
  message.className = "stage-message";
  message.textContent = "Sandfall needs WebGL2 to draw the world, and this browser doesn't have it.";
  stage.append(message);
}
setupOverlay(document.getElementById("overlay"));

// The world fits the stage between the bar above and the toolbar beside and below it
let fitted = false;
function layout() {
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  const room = state.toolbar.margins();
  view.margins = {
    top: bar.getBoundingClientRect().bottom + GAP,
    right: room.right + GAP,
    bottom: room.bottom + GAP,
    left: room.left + GAP,
  };
  if (fitted) {
    view.resize(width, height);
  } else {
    view.fit(width, height);
    fitted = true;
  }
  const ratio = window.devicePixelRatio || 1;
  state.renderer?.resize(width, height, ratio);
  resizeOverlay(width, height, ratio);
}
new ResizeObserver(() => layout()).observe(stage);
layout();
state.toolbar.onResize(layout);

// The brush ring where the cursor is: the brush's real footprint, dashed for spray
addLayer(10, (ctx, v, s) => {
  const painter = s.painter;
  const cell = painter.pointer;
  if (cell === null) {
    return;
  }
  const scale = v.scale;
  // Tools that act on one cell show a one-cell ring
  const size = POINT_TOOLS.has(painter.tool) ? 1 : painter.size;
  ctx.beginPath();
  if (painter.shape === SHAPE.SQUARE) {
    const low = -(size >> 1);
    const [x, y] = v.toScreen(cell[0] + low, cell[1] + low);
    ctx.rect(x, y, size * scale, size * scale);
  } else {
    const [x, y] = v.toScreen(cell[0] + 0.5, cell[1] + 0.5);
    ctx.arc(x, y, Math.max(scale * 0.7, (size / 2) * scale), 0, Math.PI * 2);
  }
  ctx.setLineDash(painter.shape === SHAPE.SPRAY ? [4, 4] : []);
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0, 0, 0, 0.45)";
  ctx.stroke();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
  ctx.stroke();
});

addOutlineLayer();
addCreatureLayer();
addCellInfoLayer();
state.undo = buildUndo(state, setWorld);
wirePainting();
runner.onBatchDone(() => state.sound.world(runner.takeHeard(), state.world.tally));
buildSpeedControl();
state.worldMenu = buildWorldMenu(state);
state.shared = new Shared(state);
state.worlds = buildWorlds(state);
state.gallery = buildGallery(state);
buildCursors(state);
state.settings = buildSettings(state);
buildSoundControls(state.sound);
state.help = buildHelp();
buildBarMore();
buildLook();

window.sandfall = {
  state,
  EL,
  stroke: (s) => state.sendStroke(s),
  steps(n) {
    runner.boundary();
    for (let k = 0; k < n; k++) {
      stepWorld(state.world);
    }
  },
  addToggle,
  addSlider,
  hash: () => hashWorld(state.world),
  saveNow: () => state.saver?.saveNow() ?? Promise.resolve(false),
  open: () => state.shared.open(),
  close: () => state.shared.close(),
  enter: (id) => state.shared.enter(id),
  exit: () => state.shared.exit(),
};

// The player's own world comes back before the first frame, so the starter scene never flashes up first
state.saver = await startSaving(state);
state.shared.start();
watchPeople(state);
frame(performance.now());

/** Makes `next` the page's world: the clock, the drawing and the menus all follow it */
function setWorld(next) {
  state.world = next;
  runner.replaceWorld(next);
  state.worldMenu?.refresh();
  state.saver?.changed();
}

function frame(now) {
  runner.frame(now);
  state.renderer?.draw(state.world, view, now / 1000);
  state.toolbar.drawSwatches(state.renderer, now);
  state.toolbar.tick();
  drawOverlay(view, state, now);
  watchFrameTime(now);
  requestAnimationFrame(frame);
}

// A device too slow for the glow loses it for this session; the settings toggle can still turn it back on
function watchFrameTime(now) {
  const renderer = state.renderer;
  const gap = lastFrame === null ? 0 : now - lastFrame;
  lastFrame = now;
  if (!renderer?.glow || renderer.heatView || gap <= SLOW_FRAME_MS || gap > HIDDEN_GAP_MS) {
    slowSince = null;
    return;
  }
  slowSince ??= now;
  if (now - slowSince >= SLOW_FOR_MS) {
    console.info("Sandfall: frames stayed slow, so the glow is off for now");
    renderer.setGlow(false);
    slowSince = null;
  }
}

function readGlow() {
  try {
    return localStorage.getItem(GLOW_KEY) !== "off";
  } catch (e) {
    console.warn("Sandfall: couldn't read the glow setting", e);
    return true;
  }
}

function saveGlow(on) {
  try {
    localStorage.setItem(GLOW_KEY, on ? "on" : "off");
  } catch (e) {
    console.warn("Sandfall: couldn't save the glow setting", e);
  }
}

// The Glow setting, and the heat view: the H key and a switch in the world menu. Heat view is this player's own view.
function buildLook() {
  const renderer = state.renderer;
  if (!renderer) {
    return;
  }
  renderer.setGlow(readGlow());
  addToggle(
    "Glow",
    () => renderer.glow,
    (on) => {
      renderer.setGlow(on);
      saveGlow(on);
    },
  );
  const row = document.createElement("div");
  row.className = "menu-row";
  const label = document.createElement("span");
  label.className = "menu-label";
  label.textContent = "Heat view";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "switch";
  button.setAttribute("role", "switch");
  button.setAttribute("aria-label", "Heat view");
  button.title = "Heat view (H)";
  const knob = document.createElement("span");
  knob.className = "switch-knob";
  button.append(knob);
  row.append(label, button);
  const show = () => button.setAttribute("aria-checked", String(renderer.heatView));
  const flip = () => {
    renderer.setHeatView(!renderer.heatView);
    show();
  };
  button.addEventListener("click", flip);
  onKey("h", flip);
  onKey("H", flip);
  show();
  state.worldMenu.addRow(70, row);
}

function wirePainting() {
  const { painter, toolbar } = state;
  painter.onStroke((stroke) => state.sendStroke(stroke));
  painter.onStart(() => state.undo.push());
  // Only the brush pours: a dragged Line or Box lands on release, and the other tools make no sound of their own
  painter.onActive((active) => {
    const pouring = active && painter.tool === "brush";
    state.sound.painting(pouring ? paintingKind(painter.element) : null);
  });
  // Made elements (wet soil, stone...) can't be painted, so picking one leaves the brush as it is
  painter.onPick((id) => {
    if (ELEMENTS[id]?.paint) {
      toolbar.setElement(id);
    }
  });
  const resize = (by) => {
    painter.size = Math.min(40, Math.max(1, painter.size + by));
    toolbar.refresh();
  };
  onKey("[", () => resize(-1));
  onKey("]", () => resize(1));
}

function speedButton(id, label, child, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bar-button";
  button.id = `bar-${id}`;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.append(child);
  button.addEventListener("click", onClick);
  return button;
}

// Pause and play, step once (only while paused) and the speed, which cycles 1/4, 1/2, 1x, 2x
function buildSpeedControl() {
  let playSpeed = 3;
  const group = document.createElement("div");
  group.className = "bar-speed";
  const toggle = () => state.setSpeed(runner.speed === 0 ? playSpeed : 0);
  const play = speedButton("pause", "Pause", icon("pause"), toggle);
  const step = speedButton("step", "Step once", icon("step"), () => state.stepOnce());
  const label = document.createElement("span");
  const speed = speedButton("speed", "Speed", label, () => {
    const next = playSpeed === 4 ? 1 : playSpeed + 1;
    if (runner.speed === 0) {
      playSpeed = next;
    }
    state.setSpeed(runner.speed === 0 ? 0 : next);
  });
  speed.classList.add("bar-speed-value");
  group.append(play, step, speed);
  addBarItem(10, group);

  // In someone else's shared world the speed is the owner's to change
  function refreshLock() {
    const locked = state.shared?.locked ?? false;
    const hint = locked ? `Only ${state.shared.ownerName || "the world's owner"} can change the speed` : null;
    for (const button of [play, step, speed]) {
      button.disabled = locked;
      button.title = hint ?? button.getAttribute("aria-label");
    }
  }

  // Any speed above 0 is also the one Play returns to
  function applySpeed(s) {
    runner.speed = s;
    if (s > 0) {
      playSpeed = s;
    }
    const paused = s === 0;
    play.replaceChildren(icon(paused ? "play" : "pause"));
    play.title = paused ? "Play" : "Pause";
    play.setAttribute("aria-label", play.title);
    step.hidden = !paused;
    label.textContent = SPEED_NAMES[playSpeed];
    speed.title = `Speed: ${SPEED_NAMES[playSpeed]}`;
    speed.setAttribute("aria-label", speed.title);
    refreshLock();
    state.worldMenu?.refresh();
  }
  state.applySpeed = applySpeed;
  state.refreshSpeed = refreshLock;
  state.setSpeed = (s) => {
    if (state.shared?.inWorld) {
      state.shared.setSpeed(s);
    } else {
      applySpeed(s);
    }
  };
  applySpeed(runner.speed);

  // Space pauses. Holding Space and dragging pans the view instead, so a drag takes that pause back
  let spacePaused = false;
  onKey(" ", (event) => {
    event.preventDefault();
    if (event.repeat) {
      return;
    }
    // A focused button would also click on Space's release
    if (document.activeElement instanceof HTMLButtonElement) {
      document.activeElement.blur();
    }
    toggle();
    spacePaused = true;
  });
  window.addEventListener("keyup", (event) => {
    if (event.key === " ") {
      spacePaused = false;
    }
  });
  state.painter.onSpaceDrag(() => {
    if (spacePaused) {
      spacePaused = false;
      toggle();
    }
  });
  onKey(".", () => {
    if (runner.speed === 0) {
      state.stepOnce();
    }
  });
}
