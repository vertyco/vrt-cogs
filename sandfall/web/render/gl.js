// Draws the world with WebGL2. Each frame the four planes are packed into one small texture (one texel per cell) and a
// single full-screen pass looks each pixel's cell up through the view, so zooming and panning cost nothing extra. With
// glow on, a second pass writes each cell's light into a cell-sized buffer, two passes blur it, and a last pass adds
// it over the world.
import { ELEMENTS, EL, H, HEAT_MAX, HEAT_MIN, N, ROOM, W } from "../sim/index.js";
import { BLOOM, BLUR, GLOW, LOOK, VERTEX, WORLD } from "./shaders.js";

// A swatch is a small square patch of one element, SWATCH_CELLS cells a side, drawn SWATCH_PX pixels a side
const SWATCH_CELLS = 10;
const SWATCH_PX = 40;
// How far apart, in cells, the blur reads its taps: a near glow at the cells' own size, then a wide one at half size
const NEAR_SPREAD = 1;
const WIDE_SPREAD = 2.5;
// How strongly the near and wide glows are added
const BLOOM_STRENGTH = [0.5, 0.75];

// Dusk, the default backdrop: the same colors as the page behind the stage
const DUSK = [
  [0x1d / 255, 0x1b / 255, 0x3a / 255],
  [0x5b / 255, 0x3a / 255, 0x5e / 255],
];

// Each backdrop's sky, top and bottom, and the ground drawn under the world, in the order of the world's backdrop
// setting: Dusk, Night, Day, Cave
const SKIES = [
  [...DUSK, [0.2, 0.13, 0.17]],
  [
    [0.02, 0.03, 0.08],
    [0.08, 0.09, 0.2],
    [0.06, 0.06, 0.1],
  ],
  [
    [0.42, 0.66, 0.92],
    [0.8, 0.89, 0.96],
    [0.42, 0.34, 0.25],
  ],
  [
    [0.11, 0.09, 0.08],
    [0.21, 0.17, 0.14],
    [0.13, 0.1, 0.08],
  ],
];

// Elements that flicker like flame, and the wooden ones
const FLICKERS = new Set([EL.fire, EL.torch, EL.spark]);
const WOODS = new Set([EL.wood, EL.branch]);
// Looks that hold their shape and get a lit top in the world and in pictures
const BUILT = new Set([
  LOOK.flat,
  LOOK.solid,
  LOOK.metal,
  LOOK.wood,
  LOOK.leaf,
  LOOK.stone,
  LOOK.glass,
  LOOK.other,
]);
// How much a surface open to the air above is lightened, for built things and for liquids, as the shader does
const BUILT_TOP = 0.14;
const LIQUID_TOP = 0.16;

function lookOf(element) {
  if (element.id === 0) {
    return LOOK.empty;
  }
  if (element.id === EL.coloredSand) {
    return LOOK.hue;
  }
  if (element.id === EL.wall) {
    return LOOK.flat;
  }
  if (element.id === EL.leaf) {
    return LOOK.leaf;
  }
  if (element.id === EL.metal) {
    return LOOK.metal;
  }
  if (element.id === EL.glass) {
    return LOOK.glass;
  }
  if (element.id === EL.stone) {
    return LOOK.stone;
  }
  if (WOODS.has(element.id)) {
    return LOOK.wood;
  }
  if (FLICKERS.has(element.id)) {
    return LOOK.fire;
  }
  return LOOK[element.kind] ?? LOOK.other;
}

// Heat mapped to one byte on a fixed curve: -273..20 fills 0..64, then 20..9999 fills 64..255 on a square root, so the
// temperatures that matter most (water, fire, lava) get the most steps
function heatCurve() {
  const table = new Uint8Array(HEAT_MAX - HEAT_MIN + 1);
  for (let t = HEAT_MIN; t <= HEAT_MAX; t++) {
    const value =
      t <= ROOM
        ? (64 * (t - HEAT_MIN)) / (ROOM - HEAT_MIN)
        : 64 + 191 * Math.sqrt((t - ROOM) / (HEAT_MAX - ROOM));
    table[t - HEAT_MIN] = Math.round(value);
  }
  return table;
}

// How far the shade byte moves a cell's brightness in the picture, the same amounts the shader uses
function shadeAmount(look) {
  if (look === LOOK.stone) {
    return 0.07;
  }
  if (look === LOOK.powder) {
    return 0.06;
  }
  if (look === LOOK.gas) {
    return 0.04;
  }
  if (look === LOOK.flat || look === LOOK.liquid) {
    return 0.02;
  }
  if ([LOOK.solid, LOOK.other, LOOK.leaf, LOOK.metal, LOOK.glass, LOOK.wood].includes(look)) {
    return 0.03;
  }
  return 0;
}

// Nothing solid in a cell: empty, a gas or a flame
function isOpen(id) {
  const look = lookOf(ELEMENTS[id]);
  return look === LOOK.empty || look === LOOK.gas || look === LOOK.fire;
}

// Colored sand's hue from its shade byte, as the shader's hueColor
function hueRgb(shade) {
  const h = shade / 255;
  const out = [0, 0, 0];
  [0, 4, 2].forEach((offset, k) => {
    const channel = Math.min(1, Math.max(0, Math.abs(((h * 6 + offset) % 6) - 3) - 1));
    out[k] = Math.round(255 * 0.95 * (1 - 0.6 + 0.6 * channel));
  });
  return out;
}

// One cell's color in a picture: the palette color with its shade and, where the cell above is open, the same lit top
// the world draws. No glow.
function pictureColor(id, shade, above) {
  const element = ELEMENTS[id];
  const look = lookOf(element);
  if (look === LOOK.hue) {
    return hueRgb(shade);
  }
  const amount = 1 + shadeAmount(look) * ((shade / 255) * 2 - 1);
  let lift = 0;
  if (isOpen(above)) {
    lift = BUILT.has(look) ? BUILT_TOP : look === LOOK.liquid ? LIQUID_TOP : 0;
  }
  return element.color.map((c) => Math.min(255, Math.round(c * amount * (1 - lift) + 255 * lift)));
}

/** Base64 text of a blob, without any `data:` prefix */
export function blobBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).slice(String(reader.result).indexOf(",") + 1));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) ?? "shader failed");
  }
  return shader;
}

function intTexture(gl, width, height, data) {
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8UI, width, height, 0, gl.RGBA_INTEGER, gl.UNSIGNED_BYTE, data);
  return texture;
}

// Row 0: the element's color and look. Row 1: how strongly it glows.
function paletteBytes() {
  const bytes = new Uint8Array(256 * 2 * 4);
  for (const element of ELEMENTS) {
    bytes.set([...element.color, lookOf(element)], element.id * 4);
    bytes[(256 + element.id) * 4] = element.glow ?? 0;
  }
  return bytes;
}

function link(gl, fragment) {
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragment));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) ?? "program failed");
  }
  const found = new Map();
  const at = (name) => {
    if (!found.has(name)) {
      found.set(name, gl.getUniformLocation(program, name));
    }
    return found.get(name);
  };
  return { program, at };
}

// A colour texture with its own framebuffer, to draw into and then read from
function target(gl, width, height, filter) {
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  const framebuffer = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { texture, framebuffer, width, height };
}

// A fixed scatter of shade bytes, so every swatch has the same grain: an integer hash of the cell's place
function scatter(k) {
  let h = Math.imul(k ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  return (h ^ (h >>> 16)) & 255;
}
const SWATCH_SHADES = Uint8Array.from({ length: SWATCH_CELLS * SWATCH_CELLS }, (_, k) => scatter(k));

// One element's swatch patch as cell texels: varied shades at the element's own starting heat. Gases are left patchy
// and colored sand runs through its hues.
function swatchTexels(id, heatBytes) {
  const element = ELEMENTS[id];
  const heat = heatBytes[(element.start ?? ROOM) - HEAT_MIN];
  const words = new Uint32Array(SWATCH_CELLS * SWATCH_CELLS);
  for (let k = 0; k < words.length; k++) {
    const shade = SWATCH_SHADES[k];
    if (element.kind === "gas" && shade < 110) {
      words[k] = heatBytes[ROOM - HEAT_MIN] << 24;
      continue;
    }
    const x = k % SWATCH_CELLS;
    const y = Math.trunc(k / SWATCH_CELLS);
    const tone = id === EL.coloredSand ? ((x + y) * 13) & 255 : shade;
    words[k] = id | (tone << 8) | (heat << 24);
  }
  return new Uint8Array(words.buffer);
}


export class Renderer {
  /** Throws when the browser has no WebGL2; the page then says so instead of showing a blank stage */
  constructor(canvas) {
    this.canvas = canvas;
    this.heatBytes = heatCurve();
    this.pixels = new Uint8Array(N * 4);
    this.words = new Uint32Array(this.pixels.buffer);
    this.glow = true;
    this.heatView = false;
    this.backdrop = 0;
    this.swatches = new Map();
    this.swatchPixels = new Uint8Array(SWATCH_PX * SWATCH_PX * 4);
    this.swatchImage = new ImageData(SWATCH_PX, SWATCH_PX);
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      this.gl = null;
    });
    canvas.addEventListener("webglcontextrestored", () => this.setup());
    this.setup();
  }

  // Texture units: 0 the cells being drawn, 1 the palette, 2 whatever a blur or bloom pass reads
  setup() {
    const gl = this.canvas.getContext("webgl2", { antialias: false, alpha: false });
    if (!gl) {
      throw new Error("WebGL2 is not available");
    }
    this.programs = { world: link(gl, WORLD), glow: link(gl, GLOW), blur: link(gl, BLUR), bloom: link(gl, BLOOM) };
    const corners = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, corners);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.activeTexture(gl.TEXTURE2);
    this.glowA = target(gl, W, H, gl.LINEAR);
    this.glowB = target(gl, W, H, gl.LINEAR);
    this.wideA = target(gl, W / 2, H / 2, gl.LINEAR);
    this.wideB = target(gl, W / 2, H / 2, gl.LINEAR);
    this.swatchTarget = target(gl, SWATCH_PX, SWATCH_PX, gl.NEAREST);
    gl.activeTexture(gl.TEXTURE1);
    intTexture(gl, 256, 2, paletteBytes());
    gl.activeTexture(gl.TEXTURE0);
    this.swatchCells = intTexture(gl, SWATCH_CELLS, SWATCH_CELLS, null);
    this.cells = intTexture(gl, W, H, this.pixels);
    for (const { program, at } of [this.programs.world, this.programs.glow]) {
      gl.useProgram(program);
      gl.uniform1i(at("cells"), 0);
      gl.uniform1i(at("palette"), 1);
    }
    gl.useProgram(this.programs.blur.program);
    gl.uniform1i(this.programs.blur.at("source"), 2);
    gl.useProgram(this.programs.bloom.program);
    gl.uniform1i(this.programs.bloom.at("near"), 2);
    gl.uniform1i(this.programs.bloom.at("wide"), 3);
    this.gl = gl;
  }

  /** Glow on or off: the soft bloom around fire, lava, sparks and anything hot */
  setGlow(on) {
    this.glow = Boolean(on);
  }

  /** Heat view on or off: temperature as color instead of the elements */
  setHeatView(on) {
    this.heatView = Boolean(on);
  }

  /** The backdrop behind the world: 0 Dusk, 1 Night, 2 Day, 3 Cave */
  setBackdrop(index) {
    this.backdrop = SKIES[index] ? index : 0;
  }

  /** Sizes the drawing buffer to the canvas's on-screen size in device pixels */
  resize(width, height, ratio) {
    this.ratio = ratio;
    this.canvas.width = Math.max(1, Math.round(width * ratio));
    this.canvas.height = Math.max(1, Math.round(height * ratio));
  }

  // One texel per cell: element, shade, life's low byte, heat on the fixed curve
  pack(world) {
    const { el, shade, heat, life } = world;
    const words = this.words;
    const heatBytes = this.heatBytes;
    for (let i = 0; i < N; i++) {
      words[i] = el[i] | (shade[i] << 8) | ((life[i] & 255) << 16) | (heatBytes[heat[i] - HEAT_MIN] << 24);
    }
  }

  /**
   * The world as a PNG blob, `width` x `height` pixels, in the palette's own colors (no glow) over the dusk backdrop.
   * Each pixel takes the first filled cell of the block of cells it covers, so a thin line of sand still shows.
   */
  picture(world, width, height) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    const image = ctx.createImageData(width, height);
    const { el, shade } = world;
    for (let py = 0; py < height; py++) {
      const sky = DUSK[0].map((top, k) => Math.round(255 * (top + (DUSK[1][k] - top) * ((py + 0.5) / height))));
      const y0 = Math.floor((py * H) / height);
      const y1 = Math.max(y0 + 1, Math.floor(((py + 1) * H) / height));
      for (let px = 0; px < width; px++) {
        const x0 = Math.floor((px * W) / width);
        const x1 = Math.max(x0 + 1, Math.floor(((px + 1) * W) / width));
        let color = sky;
        search: for (let y = y0; y < y1; y++) {
          for (let x = x0; x < x1; x++) {
            const at = y * W + x;
            if (el[at] !== 0) {
              color = pictureColor(el[at], shade[at], y > 0 ? el[at - W] : el[at]);
              break search;
            }
          }
        }
        image.data.set([color[0], color[1], color[2], 255], (py * width + px) * 4);
      }
    }
    ctx.putImageData(image, 0, 0);
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The picture couldn't be made"))), "image/png");
    });
  }

  /** Draws the world through the view; `time` is in seconds and moves the shimmer, flicker and stars */
  draw(world, view, time = 0) {
    const gl = this.gl;
    if (!gl) {
      return;
    }
    this.setBackdrop(world.settings.backdrop);
    this.pack(world);
    gl.bindTexture(gl.TEXTURE_2D, this.cells);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, W, H, gl.RGBA_INTEGER, gl.UNSIGNED_BYTE, this.pixels);
    const r = this.ratio ?? 1;
    const pass = {
      screen: [this.canvas.width, this.canvas.height],
      origin: [view.panX * r, view.panY * r],
      scale: view.scale * r,
      size: [W, H],
      time,
    };
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    this.drawCells(pass, this.backdrop, this.heatView);
    if (this.glow && !this.heatView) {
      this.drawBloom(pass);
    }
  }

  // The world pass into whatever framebuffer is bound, over the whole of `pass.screen`
  drawCells(pass, backdrop, heatView) {
    const gl = this.gl;
    const { program, at } = this.programs.world;
    gl.useProgram(program);
    gl.viewport(0, 0, pass.screen[0], pass.screen[1]);
    gl.uniform2fv(at("screen"), pass.screen);
    gl.uniform2fv(at("origin"), pass.origin);
    gl.uniform1f(at("scale"), pass.scale);
    gl.uniform2fv(at("size"), pass.size);
    gl.uniform1f(at("time"), pass.time);
    gl.uniform3fv(at("skyTop"), SKIES[backdrop][0]);
    gl.uniform3fv(at("skyBottom"), SKIES[backdrop][1]);
    gl.uniform3fv(at("ground"), SKIES[backdrop][2]);
    gl.uniform1i(at("backdrop"), backdrop);
    gl.uniform1i(at("heatView"), heatView ? 1 : 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  // Each cell's light into glowA, blurred across into glowB and down back into glowA: the near glow. That is blurred
  // again at half size, across into wideA and down into wideB: the wide glow. Both are then screened over the world.
  drawBloom(pass) {
    const gl = this.gl;
    const { glow, blur, bloom } = this.programs;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.glowA.framebuffer);
    gl.viewport(0, 0, W, H);
    gl.useProgram(glow.program);
    gl.uniform1f(glow.at("time"), pass.time);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.useProgram(blur.program);
    gl.activeTexture(gl.TEXTURE2);
    // Directions are in texture units, so the same spread in cells works at either size
    for (const [from, to, direction] of [
      [this.glowA, this.glowB, [NEAR_SPREAD / W, 0]],
      [this.glowB, this.glowA, [0, NEAR_SPREAD / H]],
      [this.glowA, this.wideA, [WIDE_SPREAD / W, 0]],
      [this.wideA, this.wideB, [0, WIDE_SPREAD / H]],
    ]) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, to.framebuffer);
      gl.viewport(0, 0, to.width, to.height);
      gl.bindTexture(gl.TEXTURE_2D, from.texture);
      gl.uniform2fv(blur.at("direction"), direction);
      gl.uniform2fv(blur.at("outSize"), [to.width, to.height]);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    gl.bindTexture(gl.TEXTURE_2D, this.glowA.texture);
    gl.activeTexture(gl.TEXTURE3);
    gl.bindTexture(gl.TEXTURE_2D, this.wideB.texture);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, pass.screen[0], pass.screen[1]);
    gl.useProgram(bloom.program);
    gl.uniform2fv(bloom.at("screen"), pass.screen);
    gl.uniform2fv(bloom.at("origin"), pass.origin);
    gl.uniform1f(bloom.at("scale"), pass.scale);
    gl.uniform2fv(bloom.at("size"), pass.size);
    gl.uniform2fv(bloom.at("strength"), BLOOM_STRENGTH);
    gl.enable(gl.BLEND);
    // Screen blending: the glow brightens the dark backdrop fully but barely shifts the color of what is already bright
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_COLOR);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.disable(gl.BLEND);
  }

  /**
   * Draws element `id` into a 2D canvas context as this renderer sees it: a small patch with varied shades, shimmering
   * or flickering at `time` seconds. It renders offscreen on the world's own WebGL context and copies the pixels out.
   */
  drawSwatch(id, ctx, time = 0) {
    const gl = this.gl;
    if (!gl || !ELEMENTS[id]) {
      return false;
    }
    if (!this.swatches.has(id)) {
      this.swatches.set(id, swatchTexels(id, this.heatBytes));
    }
    gl.bindTexture(gl.TEXTURE_2D, this.swatchCells);
    gl.texSubImage2D(
      gl.TEXTURE_2D, 0, 0, 0, SWATCH_CELLS, SWATCH_CELLS, gl.RGBA_INTEGER, gl.UNSIGNED_BYTE, this.swatches.get(id),
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.swatchTarget.framebuffer);
    const pass = {
      screen: [SWATCH_PX, SWATCH_PX],
      origin: [0, 0],
      scale: SWATCH_PX / SWATCH_CELLS,
      size: [SWATCH_CELLS, SWATCH_CELLS],
      time,
    };
    this.drawCells(pass, 0, false);
    gl.readPixels(0, 0, SWATCH_PX, SWATCH_PX, gl.RGBA, gl.UNSIGNED_BYTE, this.swatchPixels);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.bindTexture(gl.TEXTURE_2D, this.cells);
    // readPixels starts at the bottom row
    const row = SWATCH_PX * 4;
    for (let y = 0; y < SWATCH_PX; y++) {
      const from = (SWATCH_PX - 1 - y) * row;
      this.swatchImage.data.set(this.swatchPixels.subarray(from, from + row), y * row);
    }
    ctx.putImageData(this.swatchImage, 0, 0);
    return true;
  }
}
