// Where the world sits on the screen. Every player's view is their own, even in a shared world, so nothing here
// touches the simulation. Positions are CSS pixels from the stage's top left corner (the stage fills the window).
import { H, W } from "./sim/index.js";

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

export class View {
  constructor() {
    this.zoom = 1;
    // The screen position of the world's top left corner
    this.panX = 0;
    this.panY = 0;
    // Pixels per cell at zoom 1: the whole world fits the free area
    this.base = 1;
    // Room the controls take on each side of the stage; the world fits in what is left
    this.margins = { top: 0, right: 0, bottom: 0, left: 0 };
    this.area = { x: 0, y: 0, w: 1, h: 1 };
  }

  /** Pixels per cell right now */
  get scale() {
    return this.base * this.zoom;
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
    this.measure(width, height);
    this.zoom = 1;
    this.clamp();
  }

  /** A new stage size (a turned phone, new margins): keeps the zoom and the cell in the middle of the free area */
  resize(width, height) {
    const a = this.area;
    const cx = (a.x + a.w / 2 - this.panX) / this.scale;
    const cy = (a.y + a.h / 2 - this.panY) / this.scale;
    this.measure(width, height);
    const b = this.area;
    this.panX = b.x + b.w / 2 - cx * this.scale;
    this.panY = b.y + b.h / 2 - cy * this.scale;
    this.clamp();
  }

  // A world smaller than the free area sits across its middle with its ground on the area's bottom edge, so the sky
  // drawn past its edges fills the room above it; a bigger one always covers the area, so panning never goes past it
  clamp() {
    const a = this.area;
    const ww = W * this.scale;
    const wh = H * this.scale;
    this.panX = ww <= a.w ? a.x + (a.w - ww) / 2 : Math.min(a.x, Math.max(a.x + a.w - ww, this.panX));
    this.panY = wh <= a.h ? a.y + a.h - wh : Math.min(a.y, Math.max(a.y + a.h - wh, this.panY));
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
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.zoom * factor));
    const wx = (clientX - this.panX) / this.scale;
    const wy = (clientY - this.panY) / this.scale;
    this.zoom = zoom;
    this.panX = clientX - wx * this.scale;
    this.panY = clientY - wy * this.scale;
    this.clamp();
  }

  /** Zooms by factor around the middle of the part of the world that is on screen, for the zoom buttons */
  zoomBy(factor) {
    const a = this.area;
    const left = Math.max(a.x, this.panX);
    const right = Math.min(a.x + a.w, this.panX + W * this.scale);
    const top = Math.max(a.y, this.panY);
    const bottom = Math.min(a.y + a.h, this.panY + H * this.scale);
    this.zoomAt((left + right) / 2, (top + bottom) / 2, factor);
  }

  pan(dx, dy) {
    this.panX += dx;
    this.panY += dy;
    this.clamp();
  }
}
