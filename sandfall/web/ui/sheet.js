// The bottom sheet of an upright phone. The tab row, the element grid, the recent row, the tools and the size slider
// move into it from the page. It starts small (the tabs, two rows of elements and the main tools) so the world keeps
// most of the screen, opens up to show everything (never past the bottom of the world drawn at its full width), and
// shrinks to its top row when the tools are hidden, so the world gets the room. Its top row is the drag handle, with
// the toolbar's own buttons (Hide tools, Undo, the tool chip) over its left end and the zoom buttons over its right
// end. While the tools are hidden, a peek shows the small sheet over the world for a moment without moving the world.
// A panel such as the gallery can take the sheet's place for a while and give it back as it was.
import { H, W } from "../sim/index.js";

export const UPRIGHT_QUERY = "(orientation: portrait) and (max-width: 640px)";
const GAP = 8;
// The element grid's gap between rows (style.css .panel-grid), and the most rows it shows before it scrolls
const GRID_GAP = 4;
const MAX_ROWS = 5;
const TAP_PX = 6;
const ZOOM_STEP = 1.5;
// As long as the height's CSS transition, so the parts hidden in the top-row-only sheet stay in view while it shrinks
const SHRINK_MS = 230;
// A player who asks for less motion gets no height transition (style.css), so nothing waits for one
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)");

function make(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text) {
    node.textContent = text;
  }
  return node;
}

function zoomButton(label, text) {
  const button = make("button", "sheet-zoom", text);
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  return button;
}

/**
 * Builds the sheet around the toolbar's parts (`parts` = { rail, panel, search, dock }). Returns { upright, open,
 * node, slot, toggle(), collapse(), fit(), tuck(on), peek(on), hold(panel), release(), tick(), top(), start() }.
 * `slot` is the top row's left end, for the toolbar's buttons. `onMode(upright)` runs when a phone turns upright or
 * sideways, `onResize(glide)` whenever the sheet's height changes (glide when it changed with a snap rather than under
 * a finger), `onState()` when it opens or closes, and `onTuck(on)` when the handle hides or shows the tools.
 */
export function buildSheet(parts, { bar, view, onMode, onResize, onState, onTuck }) {
  const query = window.matchMedia(UPRIGHT_QUERY);
  const node = make("div", "sheet glass compact");
  node.id = "sheet";
  const head = make("div", "sheet-head");
  const handle = make("button", "sheet-handle");
  handle.type = "button";
  handle.setAttribute("aria-label", "Show more or fewer tools");
  handle.append(make("span", "sheet-grip"));
  const slot = make("div", "sheet-slot");
  const zoomOut = zoomButton("Zoom out", "−");
  const zoomIn = zoomButton("Zoom in", "+");
  const zoomLevel = make("span", "sheet-zoom-level", "1x");
  const zoom = make("div", "sheet-zooms");
  zoom.setAttribute("role", "group");
  zoom.setAttribute("aria-label", "Zoom");
  zoom.append(zoomOut, zoomLevel, zoomIn);
  head.append(handle, slot, zoom);
  let open = false;
  let tucked = false;
  let peeking = false;
  let held = null;
  let heights = { mini: 0, small: 0, big: 0, most: 0 };
  // The sheet's height in each look less its element grid, and one grid row with the gap under it
  let around = { small: 0, big: 0 };
  let row = 1;
  // The height the world makes room for: the top row alone while the tools are hidden, even during a peek
  let rest = 0;
  let shrinkTimer = 0;

  // The sheet's own height for a look: "mini" (the top row), "small" or "big"
  function natural(look) {
    node.classList.toggle("compact", look !== "big");
    node.classList.toggle("mini", look === "mini");
    node.style.height = "auto";
    return node.offsetHeight;
  }

  // The heights of the three looks, and the most the sheet may take: the room under the world at full width. The
  // small and open sheets both fill that room, so opening never moves the world, and the grid shows as many whole rows
  // as fit (rowsFor), from five down to two small and one open; past that the sheet runs over the world's bottom.
  function measure() {
    const was = ["compact", "mini", "held"].map((name) => [name, node.classList.contains(name)]);
    const wasHeight = node.style.height;
    const wasRows = node.style.getPropertyValue("--grid-rows");
    node.classList.remove("held");
    node.style.setProperty("--grid-rows", String(MAX_ROWS));
    if (held !== null) {
      held.style.display = "none";
    }
    const mini = natural("mini");
    const small = natural("small");
    const big = natural("big");
    const bottom = node.getBoundingClientRect().bottom;
    if (held !== null) {
      held.style.display = "";
    }
    was.forEach(([name, on]) => node.classList.toggle(name, on));
    node.style.setProperty("--grid-rows", wasRows);
    node.style.height = wasHeight;
    // Settles the height it had, so the next change runs its transition from there rather than from "auto"
    void node.offsetHeight;
    const worldBottom = bar.getBoundingClientRect().bottom + GAP + ((window.innerWidth - 2 * GAP) * H) / W + GAP;
    const room = bottom - worldBottom;
    row = parseFloat(getComputedStyle(node).getPropertyValue("--el-h")) + GRID_GAP;
    const grid = MAX_ROWS * row - GRID_GAP;
    around = { small: small - grid, big: big - grid };
    const fewest = { small: small - (MAX_ROWS - 2) * row, big: big - (MAX_ROWS - 1) * row };
    heights = {
      mini,
      small: Math.max(room, fewest.small),
      big: Math.max(room, fewest.big),
      most: Math.max(fewest.small, room),
    };
  }

  // Whole rows of elements for the small or open sheet at `height`; the room a part row would take sits above the
  // tools instead, so a row is never cut through
  function rowsFor(name, height) {
    const rows = Math.floor((height - around[name] + GRID_GAP) / row);
    return Math.max(name === "big" ? 1 : 2, Math.min(MAX_ROWS, rows));
  }

  function apply(height, glide = false) {
    node.style.height = `${height}px`;
    const name = node.classList.contains("compact") ? "small" : "big";
    node.style.setProperty("--grid-rows", String(rowsFor(name, height)));
    document.documentElement.style.setProperty("--sheet-h", `${height}px`);
    onResize(glide);
  }

  // Which look shows: a held panel fills the most room; hidden tools show the top row, or the small or open sheet
  // during a peek
  function look() {
    if (held !== null) {
      return "held";
    }
    if (tucked && !peeking) {
      return "mini";
    }
    return open ? "big" : "small";
  }

  // A sheet shrinking to its top row keeps its parts until it has shrunk, so they slide away under its edge (at once
  // when there is no slide)
  function setLook(name) {
    clearTimeout(shrinkTimer);
    node.classList.toggle("held", name === "held");
    node.classList.toggle("compact", name !== "big");
    if (name === "mini" && !node.classList.contains("mini") && !STILL.matches) {
      shrinkTimer = setTimeout(() => node.classList.add("mini"), SHRINK_MS);
    } else {
      node.classList.toggle("mini", name === "mini");
    }
  }

  function show(glide = false) {
    measure();
    const name = look();
    setLook(name);
    rest = tucked ? heights.mini : name === "held" ? heights.most : heights[name];
    apply(name === "held" ? heights.most : heights[name], glide);
    onState();
  }

  function attach() {
    node.append(head, parts.rail, parts.panel, parts.search, parts.dock);
    if (held !== null) {
      node.append(held);
    }
    document.body.append(node);
    document.body.classList.add("upright");
  }

  function detach() {
    document.body.classList.remove("upright");
    document.body.append(parts.rail, parts.panel, parts.search, parts.dock);
    if (held !== null) {
      document.body.append(held);
    }
    node.remove();
    document.documentElement.style.removeProperty("--sheet-h");
  }

  // The toolbar fills the sheet in onMode, so the sheet measures itself after that
  function mode() {
    if (query.matches) {
      attach();
    } else {
      detach();
    }
    onMode(query.matches);
    if (query.matches) {
      show();
    }
  }

  // Dragging the handle follows the finger, from the top row alone up to the open sheet. Letting go snaps to whichever
  // of the three is nearest; the top row alone hides the tools. A tap shows hidden tools, or flips small and open.
  let drag = null;
  handle.addEventListener("pointerdown", (event) => {
    measure();
    // Exact heights, since offsetHeight rounds and the snap compares against the measured looks
    const from = node.getBoundingClientRect().height;
    drag = { y: event.clientY, from, height: from, moved: false };
    handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener("pointermove", (event) => {
    if (drag === null) {
      return;
    }
    const delta = drag.y - event.clientY;
    drag.moved = drag.moved || Math.abs(delta) > TAP_PX;
    if (drag.moved) {
      clearTimeout(shrinkTimer);
      node.classList.add("dragging");
      node.classList.remove("mini");
      const height = Math.min(heights.big, Math.max(heights.mini, drag.from + delta));
      node.classList.toggle("compact", height <= heights.small + TAP_PX);
      drag.height = height;
      rest = height;
      apply(height);
    }
  });
  const release = (event) => {
    if (drag === null) {
      return;
    }
    const { moved, height } = drag;
    drag = null;
    node.classList.remove("dragging");
    if (event.type === "pointercancel") {
      show(true);
    } else if (!moved) {
      tapped();
    } else {
      snap(height);
    }
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);

  function tapped() {
    if (tucked) {
      onTuck(false);
      return;
    }
    open = !open;
    show(true);
  }

  function snap(height) {
    const { mini, small, big } = heights;
    const hide = height < (mini + small) / 2;
    open = !hide && height > (small + big) / 2;
    // Pulled back down to the top row during a peek ends the peek, through the toolbar that started it
    if (hide !== tucked || (hide && peeking)) {
      onTuck(hide);
    } else {
      show(true);
    }
  }

  node.addEventListener("mousedown", (event) => {
    if (!(event.target instanceof HTMLInputElement)) {
      event.preventDefault();
    }
  });
  zoomOut.addEventListener("click", () => view.zoomBy(1 / ZOOM_STEP));
  zoomIn.addEventListener("click", () => view.zoomBy(ZOOM_STEP));

  query.addEventListener("change", mode);
  // The window changing size (a keyboard, a turned phone, the hub's frame) changes how much room is left. A turned
  // phone's resize comes before the query's change, so everything below asks whether the sheet is on the page, not
  // whether the query matches: a sheet measured off the page measures nothing. Here both must hold: a sheet still on
  // the page of a phone just turned sideways would measure the sideways screen and squash the world for a moment, and
  // the world would lose its place. The query's change moves the sheet either way and measures it then.
  window.addEventListener("resize", () => {
    if (node.isConnected && query.matches) {
      show();
    }
  });

  let shownZoom = null;
  return {
    get upright() {
      return node.isConnected;
    },
    get open() {
      return open;
    },
    node,
    slot,
    toggle() {
      open = !open;
      if (node.isConnected) {
        show(true);
      }
    },
    /** Back to the small sheet */
    collapse() {
      if (open) {
        open = false;
        if (node.isConnected) {
          show(true);
        }
      }
    },
    /** Measures again after the grid's contents change (a new tab, new search results) */
    fit() {
      if (node.isConnected) {
        show();
      }
    },
    /** Hides the tools down to the top row (on) or brings the small sheet back */
    tuck(on) {
      tucked = on;
      peeking = false;
      if (on) {
        open = false;
      }
      if (node.isConnected) {
        show(true);
      }
    },
    /** While the tools are hidden, shows the small sheet over the world (on) or hides it again */
    peek(on) {
      peeking = on;
      if (!on) {
        open = false;
      }
      if (node.isConnected) {
        show(true);
      }
    },
    /** `panel` takes the sheet's place until release(); away from the upright layout it stays where it is */
    hold(panel) {
      held = panel;
      panel.classList.add("in-sheet");
      if (node.isConnected) {
        node.append(panel);
        show(true);
      }
    },
    release() {
      if (held === null) {
        return;
      }
      const panel = held;
      held = null;
      panel.classList.remove("in-sheet");
      if (panel.parentNode === node) {
        document.body.append(panel);
      }
      if (node.isConnected) {
        show(true);
      }
    },
    /** Every frame: the zoom buttons follow the zoom, which a pinch also changes */
    tick() {
      if (!node.isConnected || view.zoom === shownZoom) {
        return;
      }
      shownZoom = view.zoom;
      zoomLevel.textContent = `${Math.round(view.zoom * 10) / 10}x`;
      zoomOut.disabled = view.zoom <= view.minZoom;
      zoomIn.disabled = view.zoom >= view.maxZoom;
    },
    /** Where the sheet's top edge rests in screen pixels (not where a snap has it now), or the window's bottom */
    top: () => (node.isConnected ? node.getBoundingClientRect().bottom - rest : window.innerHeight),
    start: mode,
  };
}
