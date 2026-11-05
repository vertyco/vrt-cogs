// Where the world sits on the screen. Every player's view is their own, even in a shared world, so nothing here
// touches the simulation. Positions are CSS pixels from the stage's top left corner (the stage fills the window).
// When the tools come or go the world glides to its new place over a fifth of a second instead of jumping there;
// panX, panY and scale are always where it is drawn this frame, so a finger paints where it sees the world.
import { H, W } from "./sim/index.js";

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;
// The same as the toolbar's slide in style.css (--glide); a player who asks for less motion gets none
const GLIDE_MS = 220;
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)");

function easeOut(t) {
  return 1 - (1 - t) ** 3;
}

export class View {
  constructor() {
    this.zoom = 1;
    // Where the world's top left corner belongs on the screen
    this.x = 0;
    this.y = 0;
    // Pixels per cell at zoom 1: the whole world fits the free area
    this.base = 1;
    // Room the controls take on each side of the stage; the world fits in what is left
    this.margins = { top: 0, right: 0, bottom: 0, left: 0 };
    this.area = { x: 0, y: 0, w: 1, h: 1 };
    // A screen x for the middle of a world narrower than the free area, or null for the area's own middle
    this.middle = null;
    // While true (an upright phone with its tools hidden) the world is zoomed to fill the free area's height
    this.fill = false;
    this.filled = null;
    // { from: { x, y, scale }, start } while gliding, and where it is drawn this frame
    this.glide = null;
    this.shown = { x: 0, y: 0, scale: 1 };
  }

  /** Pixels per cell as drawn this frame */
  get scale() {
    return this.glide ? this.shown.scale : this.base * this.zoom;
  }

  get panX() {
    return this.glide ? this.shown.x : this.x;
  }

  get panY() {
    return this.glide ? this.shown.y : this.y;
  }

  get minZoom() {
    return MIN_ZOOM;
  }

  get maxZoom() {
    return MAX_ZOOM;
  }

  measure(width, height) {
    const m = this.margins;
    const w = Math.max(1, width - m.left - m.right);
    const h = Math.max(1, height - m.top - m.bottom);
    this.area = { x: m.left, y: m.top, w, h };
    this.base = Math.min(w / W, h / H);
  }

  /** Fits the whole world into a stage of width x height, centred, at zoom 1 */
  fit(width, height) {
    this.glide = null;
    this.measure(width, height);
    this.zoom = 1;
    this.filled = null;
    this.refill();
    this.clamp();
  }

  /**
   * A new stage size or new margins (a turned phone, the tools coming or going): keeps the zoom and the cell in the
   * middle of the free area. With glide, the world moves there smoothly from where it is drawn now.
   */
  resize(width, height, glide = false) {
    const from = { x: this.panX, y: this.panY, scale: this.scale };
    const a = this.area;
    const cx = (a.x + a.w / 2 - this.x) / (this.base * this.zoom);
    const cy = (a.y + a.h / 2 - this.y) / (this.base * this.zoom);
    this.measure(width, height);
    this.refill();
    const b = this.area;
    this.x = b.x + b.w / 2 - cx * this.base * this.zoom;
    this.y = b.y + b.h / 2 - cy * this.base * this.zoom;
    this.clamp();
    if (glide && !STILL.matches) {
      this.glide = { from, start: performance.now() };
      this.shown = { ...from };
    }
  }

  // Fill turning on zooms in until the world is as tall as the free area; turning off zooms back out unless the
  // player has zoomed since. While it stays on, an untouched fill follows the area (a phone's keyboard closing).
  refill() {
    const zoomToFill = Math.min(MAX_ZOOM, this.area.h / H / this.base);
    if (this.fill && this.filled === null) {
      this.filled = { from: this.zoom, to: Math.max(this.zoom, zoomToFill) };
      this.zoom = this.filled.to;
    } else if (this.fill && this.zoom === this.filled.to) {
      this.filled.to = Math.max(this.filled.from, zoomToFill);
      this.zoom = this.filled.to;
    } else if (!this.fill && this.filled !== null) {
      if (this.zoom === this.filled.to) {
        this.zoom = this.filled.from;
      }
      this.filled = null;
    }
  }

  // A world smaller than the free area sits across its middle with its ground on the area's bottom edge, so the sky
  // drawn past its edges fills the room above it; a bigger one always covers the area, so panning never goes past it
  clamp() {
    const a = this.area;
    const scale = this.base * this.zoom;
    const ww = W * scale;
    const wh = H * scale;
    if (ww <= a.w) {
      const middle = this.middle ?? a.x + a.w / 2;
      this.x = Math.min(a.x + a.w - ww, Math.max(a.x, middle - ww / 2));
    } else {
      this.x = Math.min(a.x, Math.max(a.x + a.w - ww, this.x));
    }
    this.y = wh <= a.h ? a.y + a.h - wh : Math.min(a.y, Math.max(a.y + a.h - wh, this.y));
  }

  /** Every frame: moves a glide along, and ends it once the world is where it belongs */
  tick(now) {
    const glide = this.glide;
    if (glide === null) {
      return;
    }
    // A frame's time can be a little before the glide started (the frame began before the press that started it)
    const t = Math.max(0, Math.min(1, (now - glide.start) / GLIDE_MS));
    if (t >= 1) {
      this.glide = null;
      return;
    }
    const k = easeOut(t);
    const { from } = glide;
    this.shown = {
      x: from.x + (this.x - from.x) * k,
      y: from.y + (this.y - from.y) * k,
      scale: from.scale + (this.base * this.zoom - from.scale) * k,
    };
  }

  /** The cell under a screen point as [x, y], or null outside the world. With clampToWorld, the nearest cell instead */
  cellAt(clientX, clientY, clampToWorld = false) {
    const x = Math.floor((clientX - this.panX) / this.scale);
    const y = Math.floor((clientY - this.panY) / this.scale);
    if (clampToWorld) {
      return [Math.min(W - 1, Math.max(0, x)), Math.min(H - 1, Math.max(0, y))];
    }
    return x < 0 || y < 0 || x >= W || y >= H ? null : [x, y];
  }

  /** The screen position of a cell's top left corner */
  toScreen(x, y) {
    return [this.panX + x * this.scale, this.panY + y * this.scale];
  }

  /** Zooms by factor, keeping the world point under (clientX, clientY) where it is */
  zoomAt(clientX, clientY, factor) {
    this.glide = null;
    const before = this.base * this.zoom;
    this.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.zoom * factor));
    const after = this.base * this.zoom;
    this.x = clientX - ((clientX - this.x) / before) * after;
    this.y = clientY - ((clientY - this.y) / before) * after;
    this.clamp();
  }

  /** The screen point in the middle of the part of the world that is on screen, as drawn this frame */
  visibleMiddle() {
    const a = this.area;
    const left = Math.max(a.x, this.panX);
    const right = Math.min(a.x + a.w, this.panX + W * this.scale);
    const top = Math.max(a.y, this.panY);
    const bottom = Math.min(a.y + a.h, this.panY + H * this.scale);
    return [(left + right) / 2, (top + bottom) / 2];
  }

  /** Zooms by factor around the middle of the part of the world that is on screen, for the zoom buttons */
  zoomBy(factor) {
    this.glide = null;
    const [x, y] = this.visibleMiddle();
    this.zoomAt(x, y, factor);
  }

  pan(dx, dy) {
    this.glide = null;
    this.x += dx;
    this.y += dy;
    this.clamp();
  }
}
