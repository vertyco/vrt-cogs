// The bottom sheet of an upright phone. The tab row, the element grid, the recent row, the tools and the size slider
// move into it from the page. It starts small (the tabs, two rows of elements and the main tools) so the world keeps
// most of the screen, and opens up to show everything, never past the bottom of the world drawn at its full width.
// Its top row is the drag handle with zoom buttons beside it, so a small build can be blown up and painted. A panel
// such as the gallery can take the sheet's place for a while and give it back as it was.
import { H, W } from "../sim/index.js";

export const UPRIGHT_QUERY = "(orientation: portrait) and (max-width: 640px)";
const GAP = 8;
const TAP_PX = 6;
// A drag that ends past this share of the way between small and open snaps open
const SNAP_AT = 0.5;
const ZOOM_STEP = 1.5;

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
 * Builds the sheet around the toolbar's parts (`parts` = { rail, panel, search, dock }). Returns
 * { upright, open, node, toggle(), collapse(), fit(), hold(panel), release(), tick(), top(), start() }. `onMode(upright)` runs
 * when a phone turns upright or sideways, `onResize()` whenever the sheet's height changes and `onState()` when it
 * opens or closes.
 */
export function buildSheet(parts, { bar, view, onMode, onResize, onState }) {
  const query = window.matchMedia(UPRIGHT_QUERY);
  const node = make("div", "sheet glass compact");
  node.id = "sheet";
  const head = make("div", "sheet-head");
  const handle = make("button", "sheet-handle");
  handle.type = "button";
  handle.setAttribute("aria-label", "Show more or fewer tools");
  handle.append(make("span", "sheet-grip"));
  const zoomOut = zoomButton("Zoom out", "−");
  const zoomIn = zoomButton("Zoom in", "+");
  const zoomLevel = make("span", "sheet-zoom-level", "1x");
  const zoom = make("div", "sheet-zooms");
  zoom.setAttribute("role", "group");
  zoom.setAttribute("aria-label", "Zoom");
  zoom.append(zoomOut, zoomLevel, zoomIn);
  head.append(handle, zoom);
  let open = false;
  let held = null;
  let heights = { small: 0, big: 0, most: 0 };

  function natural(compact) {
    node.classList.toggle("compact", compact);
    node.style.height = "auto";
    return node.offsetHeight;
  }

  // The small and open heights of the tools, and the most the sheet may take: the room under the world at full width
  function measure() {
    const was = { compact: node.classList.contains("compact"), held: node.classList.contains("held") };
    const wasHeight = node.style.height;
    node.classList.remove("held");
    if (held !== null) {
      held.style.display = "none";
    }
    const small = natural(true);
    const big = natural(false);
    const bottom = node.getBoundingClientRect().bottom;
    if (held !== null) {
      held.style.display = "";
    }
    node.classList.toggle("compact", was.compact);
    node.classList.toggle("held", was.held);
    node.style.height = wasHeight;
    const worldBottom = bar.getBoundingClientRect().bottom + GAP + ((window.innerWidth - 2 * GAP) * H) / W + GAP;
    const most = Math.max(small, bottom - worldBottom);
    heights = { small, big: Math.min(big, most), most };
  }

  function apply(height) {
    node.style.height = `${height}px`;
    document.documentElement.style.setProperty("--sheet-h", `${height}px`);
    onResize();
  }

  function show() {
    measure();
    node.classList.toggle("held", held !== null);
    node.classList.toggle("compact", held === null && !open);
    apply(held !== null ? heights.most : open ? heights.big : heights.small);
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

  // Dragging the handle follows the finger; letting go snaps small or open, and a tap flips between them
  let drag = null;
  handle.addEventListener("pointerdown", (event) => {
    measure();
    drag = { y: event.clientY, from: node.offsetHeight, moved: false };
    handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener("pointermove", (event) => {
    if (drag === null) {
      return;
    }
    const delta = drag.y - event.clientY;
    drag.moved = drag.moved || Math.abs(delta) > TAP_PX;
    if (drag.moved) {
      const height = Math.min(heights.big, Math.max(heights.small, drag.from + delta));
      node.classList.toggle("compact", height <= heights.small + TAP_PX);
      apply(height);
    }
  });
  const release = (event) => {
    if (drag === null) {
      return;
    }
    const { moved } = drag;
    drag = null;
    if (event.type !== "pointercancel") {
      const spread = Math.max(1, heights.big - heights.small);
      open = moved ? (node.offsetHeight - heights.small) / spread > SNAP_AT : !open;
    }
    show();
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);
  node.addEventListener("mousedown", (event) => {
    if (!(event.target instanceof HTMLInputElement)) {
      event.preventDefault();
    }
  });
  zoomOut.addEventListener("click", () => view.zoomBy(1 / ZOOM_STEP));
  zoomIn.addEventListener("click", () => view.zoomBy(ZOOM_STEP));

  query.addEventListener("change", mode);
  // The window changing size (a keyboard, a turned phone, the hub's frame) changes how much room is left
  window.addEventListener("resize", () => {
    if (query.matches) {
      show();
    }
  });

  let shownZoom = null;
  return {
    get upright() {
      return query.matches;
    },
    get open() {
      return open;
    },
    node,
    toggle() {
      open = !open;
      if (query.matches) {
        show();
      }
    },
    /** Back to the small sheet */
    collapse() {
      if (open) {
        open = false;
        if (query.matches) {
          show();
        }
      }
    },
    /** Measures again after the grid's contents change (a new tab, new search results) */
    fit() {
      if (query.matches) {
        show();
      }
    },
    /** `panel` takes the sheet's place until release(); away from the upright layout it stays where it is */
    hold(panel) {
      held = panel;
      panel.classList.add("in-sheet");
      if (query.matches) {
        node.append(panel);
        show();
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
      if (query.matches) {
        show();
      }
    },
    /** Every frame: the zoom buttons follow the zoom, which a pinch also changes */
    tick() {
      if (!query.matches || view.zoom === shownZoom) {
        return;
      }
      shownZoom = view.zoom;
      zoomLevel.textContent = `${Math.round(view.zoom * 10) / 10}x`;
      zoomOut.disabled = view.zoom <= view.minZoom;
      zoomIn.disabled = view.zoom >= view.maxZoom;
    },
    /** The sheet's top edge in screen pixels, or the window's bottom when there is no sheet */
    top: () => (query.matches ? node.getBoundingClientRect().top : window.innerHeight),
    start: mode,
  };
}
