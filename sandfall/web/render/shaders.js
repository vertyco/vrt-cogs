// The renderer's shader programs. Every program draws one full-screen quad; the world pass looks each pixel's cell up
// through the view, the glow pass writes one pixel per cell, and the blur and bloom passes spread and add that glow.
// Nothing here feeds the simulation, so the shaders are free to use sin and floating point.

// How the shader treats an element's color, stored in the palette texture's alpha
export const LOOK = {
  empty: 0,
  powder: 1,
  liquid: 2,
  gas: 3,
  solid: 4,
  flat: 5,
  hue: 6,
  other: 7,
  leaf: 8,
  metal: 9,
  fire: 10,
  glass: 11,
  wood: 12,
  stone: 13,
};

export const VERTEX = `#version 300 es
layout(location = 0) in vec2 corner;
void main() {
  gl_Position = vec4(corner, 0.0, 1.0);
}
`;

// Shared by the world pass and the glow pass: one cell's color from its texel
const CELL = `
precision highp float;
precision highp int;
precision highp usampler2D;
uniform usampler2D cells;
uniform usampler2D palette;
uniform float time;
const uint POWDER = 1u;
const uint LIQUID = 2u;
const uint GAS = 3u;
const uint SOLID = 4u;
const uint FLAT = 5u;
const uint HUE = 6u;
const uint OTHER = 7u;
const uint LEAF = 8u;
const uint METAL = 9u;
const uint FIRE = 10u;
const uint GLASS = 11u;
const uint WOOD = 12u;
const uint STONE = 13u;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float top = mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x);
  float bottom = mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x);
  return mix(top, bottom, f.y);
}

vec3 hueColor(float h) {
  vec3 k = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
  return 0.95 * mix(vec3(1.0), k, 0.6);
}

// How far the shade byte moves a cell's brightness, by look. Liquids barely use it: their ripples carry the texture.
float shadeAmount(uint look) {
  if (look == STONE) return 0.07;
  if (look == POWDER) return 0.06;
  if (look == GAS) return 0.04;
  if (look == FLAT || look == LIQUID) return 0.02;
  if (look == SOLID || look == OTHER || look == LEAF || look == METAL || look == GLASS || look == WOOD) return 0.03;
  return 0.0;
}

// How strongly a cell glows from heat alone, by its heat byte: nothing below about 500 degrees (byte 106), full
// around 2,500 (byte 160)
float hotness(uint heatByte) {
  return smoothstep(106.0, 165.0, float(heatByte));
}

// Red hot, then orange, then nearly white
vec3 hotColor(float hot) {
  return mix(vec3(0.82, 0.16, 0.05), vec3(1.0, 0.86, 0.56), hot * hot);
}

// The element's own color in a cell: base, shade, ripple, flicker, current and heat. Liquids ripple in broad, slow
// waves shared by neighbouring cells, so a pool reads as one body; the shade byte offsets each flame's flicker.
vec3 cellColor(uvec4 here, uvec4 entry, ivec2 at) {
  uint look = entry.a;
  float shade = float(here.g) / 255.0;
  vec3 base = look == HUE ? hueColor(shade) : vec3(entry.rgb) / 255.0;
  // A blossoming tree's leaves keep 1 (pink) or 2 (white) in their life byte
  if (look == LEAF && here.b == 1u) base = vec3(0.96, 0.62, 0.74);
  if (look == LEAF && here.b == 2u) base = vec3(0.97, 0.95, 0.92);
  // Metal carrying a pulse (1 or 2 in its life byte) shows the current's pale yellow
  if (look == METAL && (here.b == 1u || here.b == 2u)) base = vec3(1.0, 250.0 / 255.0, 200.0 / 255.0);
  vec3 tint = base * (1.0 + shadeAmount(look) * (shade * 2.0 - 1.0));
  if (look == LIQUID) {
    vec2 p = vec2(at);
    float swell = noise(p / 9.0 + vec2(time * 0.35, time * 0.21));
    float ripple = noise(p / 4.0 + vec2(-time * 0.5, time * 0.17));
    tint *= 0.95 + 0.06 * swell + 0.04 * ripple;
  }
  if (look == FIRE) {
    float f = 0.5 + 0.5 * sin(time * 13.0 + shade * 18.85 + float(at.y) * 0.9);
    tint = mix(tint * 0.7, mix(tint, vec3(1.0, 0.94, 0.64), 0.5), f);
  }
  // Heat reddens plain materials; elements that glow already have their glowing color
  uint glow = texelFetch(palette, ivec2(int(here.r), 1), 0).r;
  if (look != GAS && look != FIRE && glow == 0u) {
    float hot = hotness(here.a);
    tint = mix(tint, hotColor(hot), hot * 0.85);
  }
  return tint;
}
`;

export const WORLD = `#version 300 es
${CELL}
uniform vec2 screen;
uniform vec2 origin;
uniform float scale;
uniform vec2 size;
uniform vec3 skyTop;
uniform vec3 skyBottom;
uniform vec3 ground;
uniform int backdrop;
uniform bool heatView;
out vec4 color;

const vec3 LUMA = vec3(0.299, 0.587, 0.114);

// The backdrop behind a cell: a sky gradient, with twinkling stars at Night and rough rock in the Cave. Above the
// world's top (y below 0) the sky keeps its top color, deepening a little the higher it goes.
vec3 backdropColor(vec2 cell, float y) {
  vec3 sky = mix(skyTop, skyBottom, max(y, 0.0)) * (1.0 - 0.2 * smoothstep(0.0, 1.0, -y));
  y = max(y, 0.0);
  if (backdrop == 1) {
    vec2 block = floor(cell / 3.0);
    float h = hash(block);
    vec2 star = block * 3.0 + 0.5 + 2.0 * vec2(hash(block + 17.0), hash(block + 41.0));
    float twinkle = 0.45 + 0.55 * (0.5 + 0.5 * sin(time * 1.8 + h * 90.0));
    float spot = step(0.93, h) * (1.0 - smoothstep(0.1, 0.45, length(cell - star)));
    sky += vec3(0.85, 0.88, 1.0) * spot * twinkle * (1.0 - 0.6 * y);
  }
  if (backdrop == 3) {
    float rock = 0.6 * noise(cell / 14.0) + 0.4 * noise(cell / 4.0);
    sky *= 0.7 + 0.6 * rock;
  }
  return sky;
}

// Temperature as color: blue below room temperature, dark at room, then red, orange and white as it heats
vec3 heatColor(float h) {
  vec3 room = vec3(0.1, 0.1, 0.16);
  if (h < 64.0) return mix(room, vec3(0.2, 0.45, 1.0), sqrt(1.0 - h / 64.0));
  float s = (h - 64.0) / 191.0;
  vec3 c = mix(room, vec3(0.86, 0.1, 0.06), smoothstep(0.0, 0.2, s));
  c = mix(c, vec3(1.0, 0.66, 0.12), smoothstep(0.2, 0.45, s));
  return mix(c, vec3(1.0), smoothstep(0.45, 0.8, s));
}

// A neighbouring cell's element. Past the world's edge counts as more of the cell itself, so the edges draw no seam.
uint idAt(ivec2 p, uint self) {
  if (p.x < 0 || p.y < 0 || p.x >= int(size.x) || p.y >= int(size.y)) return self;
  return texelFetch(cells, p, 0).r;
}

// Nothing solid in that cell: empty, a gas or a flame
bool open(uint id) {
  if (id == 0u) return true;
  uint look = texelFetch(palette, ivec2(int(id), 0), 0).a;
  return look == GAS || look == FIRE;
}

// Things that hold their shape (and stone, which settles into heaps): these get a lit top and shaded seams
bool built(uint look) {
  return look == FLAT || look == SOLID || look == METAL || look == WOOD || look == LEAF || look == STONE ||
    look == GLASS || look == OTHER;
}

// A faint texture that tells built materials apart: wall in staggered blocks, brushed rows of metal, wood grain,
// chunky stone and clumps of leaves. It follows the grid, never the cells' outlines.
float grain(uint look, vec2 p) {
  if (look == FLAT) {
    float row = floor(p.y / 3.0);
    float block = floor((p.x + mod(row, 2.0) * 3.0) / 6.0);
    return 0.07 * (hash(vec2(block, row)) - 0.5);
  }
  if (look == STONE) return 0.14 * (noise(p / 2.5) - 0.5);
  if (look == METAL) return 0.06 * (hash(vec2(0.5, p.y)) - 0.5) + 0.05 * (noise(vec2(p.x / 10.0, p.y)) - 0.5);
  if (look == WOOD) return 0.16 * (noise(vec2(p.x / 6.0, p.y * 0.8)) - 0.5);
  if (look == LEAF) return 0.2 * (noise(p / 3.5) - 0.5);
  return 0.0;
}

// A built cell's surface: lit where its top is open to the air, a little darker underneath, and a slight shadow
// where it meets a different material
vec3 surface(vec3 tint, uint look, ivec2 at, uint id, uvec4 around) {
  tint *= 1.0 + grain(look, vec2(at));
  bool upOpen = open(around.x);
  bool downOpen = open(around.y);
  bool leftOpen = open(around.z);
  bool rightOpen = open(around.w);
  if (upOpen) tint = mix(tint, vec3(1.0), 0.14);
  if (downOpen) tint *= 0.9;
  bool contact = (around.x != id && !upOpen) || (around.y != id && !downOpen) || (around.z != id && !leftOpen) ||
    (around.w != id && !rightOpen);
  if (contact) tint *= 0.88;
  return tint;
}

// Keeps a cell's edge apart from the backdrop: darker on a light sky, lighter on a dark one, and only as much as the
// two are alike, so pale glass, ice, snow and steam still show where they end without turning solid
vec3 setOff(vec3 c, vec3 sky) {
  float ls = dot(sky, LUMA);
  float alike = 1.0 - clamp(abs(dot(c, LUMA) - ls) / 0.16, 0.0, 1.0);
  return ls > 0.5 ? c * (1.0 - 0.18 * alike) : mix(c, vec3(1.0), 0.1 * alike);
}

// Past the world's edges the scene carries on: more sky above and beside it, and under it the ground, darkening
// with depth. It is a shade dimmer than the world, with a faint line along the world's edge, so the playable area
// still shows.
vec3 surround(vec2 cell) {
  float y = cell.y / size.y;
  vec3 c;
  if (y >= 1.0) {
    float depth = y - 1.0;
    c = ground * (0.9 + 0.2 * noise(cell / 6.0)) * mix(1.0, 0.55, smoothstep(0.0, 0.6, depth));
  } else {
    c = backdropColor(cell, y);
  }
  c *= 0.9;
  // How far past the nearest edge this pixel is, in screen pixels
  vec2 over = max(-cell, cell - size) * scale;
  float line = 1.0 - smoothstep(1.0, 2.5, max(over.x, over.y));
  vec3 edge = dot(c, LUMA) > 0.5 ? c * 0.72 : mix(c, vec3(1.0), 0.2);
  return mix(c, edge, line);
}

void main() {
  vec2 pixel = vec2(gl_FragCoord.x, screen.y - gl_FragCoord.y);
  vec2 cell = (pixel - origin) / scale;
  if (cell.x < 0.0 || cell.y < 0.0 || cell.x >= size.x || cell.y >= size.y) {
    // In the heat view the outside stays dark, so the temperatures stand out
    color = vec4(heatView ? backdropColor(cell, clamp(cell.y / size.y, 0.0, 1.0)) * 0.45 : surround(cell), 1.0);
    return;
  }
  ivec2 at = ivec2(cell);
  uvec4 here = texelFetch(cells, at, 0);
  if (heatView) {
    vec3 c = heatColor(float(here.a));
    color = vec4(here.r == 0u ? c * 0.55 : c, 1.0);
    return;
  }
  vec3 sky = backdropColor(cell, clamp(cell.y / size.y, 0.0, 1.0));
  if (here.r == 0u) {
    color = vec4(sky, 1.0);
    return;
  }
  uint id = here.r;
  uvec4 entry = texelFetch(palette, ivec2(int(id), 0), 0);
  uint look = entry.a;
  vec3 tint = cellColor(here, entry, at);
  // The elements above, below, left and right
  uvec4 around = uvec4(
    idAt(at + ivec2(0, -1), id),
    idAt(at + ivec2(0, 1), id),
    idAt(at + ivec2(-1, 0), id),
    idAt(at + ivec2(1, 0), id)
  );
  if (built(look)) {
    tint = surface(tint, look, at, id, around);
  } else if (look == LIQUID && open(around.x)) {
    // The liquid's surface catches a little light
    tint = mix(tint, vec3(1.0), 0.16);
  }
  // Gases are thin and glass is faint: the backdrop shows through them
  if (look == GAS) tint = mix(sky, tint, 0.78);
  if (look == GLASS) tint = mix(sky, tint, 0.38);
  if (around.x == 0u || around.y == 0u || around.z == 0u || around.w == 0u) tint = setOff(tint, sky);
  color = vec4(tint, 1.0);
}
`;

// One pixel per cell: how much light each cell gives off, from its element's glow and its heat
export const GLOW = `#version 300 es
${CELL}
out vec4 color;

void main() {
  ivec2 at = ivec2(gl_FragCoord.xy);
  uvec4 here = texelFetch(cells, at, 0);
  if (here.r == 0u) {
    color = vec4(0.0, 0.0, 0.0, 1.0);
    return;
  }
  uvec4 entry = texelFetch(palette, ivec2(int(here.r), 0), 0);
  float glow = float(texelFetch(palette, ivec2(int(here.r), 1), 0).r) / 255.0;
  uint look = entry.a;
  if (look == METAL && (here.b == 1u || here.b == 2u)) glow = 0.75;
  float hot = look == GAS || look == FIRE || glow > 0.0 ? 0.0 : hotness(here.a);
  color = vec4(cellColor(here, entry, at) * max(glow, hot), 1.0);
}
`;

// One direction of a 9-tap Gaussian blur, using the linear filter to read two texels per tap. The output can be
// smaller than the source: that is how the wide glow is made at half size.
export const BLUR = `#version 300 es
precision highp float;
uniform sampler2D source;
uniform vec2 direction;
uniform vec2 outSize;
out vec4 color;

void main() {
  vec2 uv = gl_FragCoord.xy / outSize;
  vec3 sum = texture(source, uv).rgb * 0.227027;
  sum += (texture(source, uv + direction * 1.384615).rgb + texture(source, uv - direction * 1.384615).rgb) * 0.316216;
  sum += (texture(source, uv + direction * 3.230769).rgb + texture(source, uv - direction * 3.230769).rgb) * 0.070270;
  color = vec4(sum, 1.0);
}
`;

// The blurred glow laid over the world through the view (the renderer screen-blends it): a near glow that hugs bright
// cells and a wide, weaker one that spreads their light, with the brightest light squeezed so a big hot area glows
// softly instead of flaring into a hard-edged block
export const BLOOM = `#version 300 es
precision highp float;
uniform sampler2D near;
uniform sampler2D wide;
uniform vec2 screen;
uniform vec2 origin;
uniform float scale;
uniform vec2 size;
uniform vec2 strength;
out vec4 color;

void main() {
  vec2 pixel = vec2(gl_FragCoord.x, screen.y - gl_FragCoord.y);
  vec2 cell = (pixel - origin) / scale;
  // The glow stops at the world's edge rather than smearing the edge cells across the backdrop
  float inside = step(0.0, cell.x) * step(0.0, cell.y) * step(cell.x, size.x) * step(cell.y, size.y);
  vec2 uv = cell / size;
  vec3 light = texture(near, uv).rgb * strength.x + texture(wide, uv).rgb * strength.y;
  light /= 1.0 + 0.6 * max(light.r, max(light.g, light.b));
  color = vec4(light * inside, 1.0);
}
`;
