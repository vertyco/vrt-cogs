// The junk robot horde: scrap-built mechs of mismatched rust plates and dull metal with hot magenta and green warning
// lights, each with a dark outline so it reads on a small phone. Walkers step on jointed legs and settle onto each
// planted foot, Skitters scuttle on four spider legs, tread vehicles roll on turning wheels and moving track links,
// and Buzzers hover on spinning fans. Robots are drawn between the rules' steps, smoothed by `alpha`. Robots piled at
// a Drone bay's wall stand side by side in rows, so a crowd reads as a crowd. Robots are placed in view units (see
// view.js), so they face the way they walk on screen whichever way the map is turned.
import { Container, Graphics } from "../vendor/pixi.min.mjs";
import { pointAt } from "../sim/road.js";
import { toView } from "./view.js";

const INK = 0x140b06;
const RUST = 0x8a4a28;
const RUST_DARK = 0x5e321c;
const RUST_LIGHT = 0xa55f36;
const METAL = 0x767b80;
const METAL_DARK = 0x474c51;
const METAL_LIGHT = 0x9aa0a5;
const TREAD = 0x25292e;
const GLASS = 0x1c1216;
const MAGENTA = 0xff2e88;
const GREEN = 0x6dff5a;
const AMBER = 0xffc23d;
const OUTLINE = { width: 2, color: INK };
const THIN = { width: 1.5, color: INK };
const FINE = { width: 1, color: INK };
const HEAVY = { width: 3, color: INK };
const FROZEN = 0x8fd6ff;
const SLOWED = 0xc4b5ff;
// Limbs on the far side of a robot are shaded darker, so near and far legs read apart
const FAR = 0x8f8f8f;
// Each type's health bar, by type index: its width, and its height above the robot's feet
const BAR = [
  [24, 33],
  [16, 15],
  [21, 33],
  [36, 44],
  [30, 27],
  [70, 97],
];
// A hit's white flash: how strong it starts and how fast it fades (gone in about a sixteenth of a second), so a
// robot under fast fire still shows its own colors
const FLASH_PEAK = 0.5;
const FLASH_FADE = 16;
// A pile at a Drone bay's wall: three across the road (map units from its middle), the front row this far behind the
// wall's barrier, each row after it this much further back, and how fast a robot shuffles into its place
const CROWD_ACROSS = [0, -15, 15];
const CROWD_FRONT = 8;
const CROWD_ROW = 14;
const CROWD_EASE = 8;
// Roughly how far apart a tread's links sit, in map units
const LINK_PITCH = 6;
// A robot fades in over its first stretch of road (hundredths of a map unit), which starts off the map's edge
const ENTER_FADE = 4000;
// Hull outlines, drawn once as the hull and once as its white hit flash
const SCRAPPER_HULL = [-11, -3, -12, -12, -7, -17, 8, -17, 12, -12, 11, -3, 5, 0, -7, 0];
const SPIDER_POD = [-9, -3, -7, -9, 4, -10, 9, -6, 8, -1, -6, 0];
const BUZZER_HULL = [-11, -13, -7, -19, 6, -19, 12, -14, 9, -8, -8, -8];
const BRUTE_HULL = [-14, -10, -13, -26, -5, -32, 8, -32, 14, -25, 15, -10];
const SPLITTER_HULL = [-21, 0, -20, -11, 13, -11, 22, -7, 21, 0];
const COLOSSUS_HULL = [-28, -56, 22, -58, 32, -46, 34, -18, 24, -10, -24, -10, -32, -20, -32, -46];

function parts() {
  return {
    root: new Container(),
    // Everything that turns to face the way the robot goes
    body: new Container(),
    // The part that bobs, rumbles or hovers
    torso: new Container(),
    legs: [],
    arms: [],
    wheels: [],
    links: [],
    fans: [],
    riders: [],
    track: null,
    stride: 1,
    settle: 0,
    animate: null,
    flash: null,
    bar: null,
  };
}

function shadow(view, w, h, y) {
  view.root.addChild(new Graphics().ellipse(0, y, w, h).fill({ color: 0x000000, alpha: 0.35 }));
}

function bolts(g, points) {
  for (const [x, y] of points) {
    g.circle(x, y, 1).fill(INK);
  }
}

// One part of a jointed limb, hanging down from its joint at (0, 0), with a bolt through the joint
function bone(length, width, color, outline) {
  const g = new Graphics();
  g.roundRect(-width / 2, -width / 2, width, length + width, width / 2).fill(color).stroke(outline);
  g.circle(0, 0, width * 0.32).fill(METAL_LIGHT).stroke(FINE);
  return g;
}

// A hydraulic piston along a thigh
function piston(length, width) {
  const x = width / 2 + 1.2;
  return new Graphics()
    .rect(x - 1, 1, 2, length - 2)
    .fill(METAL_LIGHT)
    .stroke(FINE)
    .rect(x - 1.6, 1, 3.2, length * 0.45)
    .fill(METAL_DARK)
    .stroke(FINE);
}

function pose(limb, swing, up) {
  limb.hip.rotation = limb.rest[0] + swing * limb.reach + up * limb.lift[0];
  limb.knee.rotation = limb.rest[1] + up * limb.lift[1];
  if (limb.foot) {
    // Feet stay flat to the ground
    limb.foot.rotation = -(limb.hip.rotation + limb.knee.rotation);
  }
}

// A two-part leg: the hip swings the whole leg and the knee bends the lower part. `rest` is the hip and knee angle
// standing still, `reach` how far the hip swings in a stride, `lift` how hip and knee change to raise the foot, and
// `phase` where in the stride this leg is, so legs half a stride apart take turns
function leg(parent, spec) {
  const hip = new Container();
  hip.position.set(spec.x, spec.y);
  if (spec.piston) {
    hip.addChild(piston(spec.upper, spec.width));
  }
  hip.addChild(bone(spec.upper, spec.width, spec.color, spec.outline));
  const knee = new Container();
  knee.y = spec.upper;
  knee.addChild(bone(spec.lower, spec.width * 0.85, spec.color, spec.outline));
  hip.addChild(knee);
  const foot = spec.foot ? spec.foot() : null;
  if (foot) {
    foot.y = spec.lower;
    knee.addChild(foot);
  }
  if (spec.cap) {
    knee.addChild(spec.cap());
  }
  if (spec.far) {
    hip.tint = FAR;
  }
  parent.addChild(hip);
  const limb = { hip, knee, foot, rest: spec.rest, reach: spec.reach, lift: spec.lift, phase: spec.phase };
  pose(limb, 0, 0);
  return limb;
}

// Each leg pushes back while its foot is down, then lifts and swings forward, taking turns by phase
function stride(view, travel) {
  const cycle = (travel / view.stride) * Math.PI * 2;
  for (const limb of view.legs) {
    const p = cycle + limb.phase;
    pose(limb, Math.sin(p), Math.max(0, -Math.cos(p)));
  }
  return cycle;
}

function walk(view, travel) {
  const cycle = stride(view, travel);
  // The body drops onto each planted foot and settles: heavy, not bouncy
  view.torso.y = Math.pow(Math.abs(Math.sin(cycle)), 6) * view.settle;
  for (const arm of view.arms) {
    arm.rotation = Math.sin(cycle) * 0.08;
  }
}

function scuttle(view, travel) {
  const cycle = stride(view, travel);
  view.torso.y = Math.sin(cycle * 2) * 0.5;
}

// Where a link is, `s` map units round a track from the top of its back wheel, going forward along the top
function trackPoint(track, s) {
  const { left, right, y, r } = track;
  const run = right - left;
  const bend = Math.PI * r;
  if (s < run) {
    return [left + s, y - r, 0];
  }
  if (s < run + bend) {
    const a = -Math.PI / 2 + (s - run) / r;
    return [right + Math.cos(a) * r, y + Math.sin(a) * r, a + Math.PI / 2];
  }
  if (s < 2 * run + bend) {
    return [right - (s - run - bend), y + r, Math.PI];
  }
  const a = Math.PI / 2 + (s - 2 * run - bend) / r;
  return [left + Math.cos(a) * r, y + Math.sin(a) * r, a + Math.PI / 2];
}

// The wheels turn and the links run round the track as far as the robot has gone, so the track grips the road
function roll(view, travel) {
  for (const wheel of view.wheels) {
    wheel.node.rotation = travel / wheel.radius;
  }
  const track = view.track;
  view.links.forEach((link, i) => {
    const s = (((i * track.pitch + travel) % track.length) + track.length) % track.length;
    const [x, y, angle] = trackPoint(track, s);
    link.position.set(x, y);
    link.rotation = angle;
  });
  // The engine's rumble
  view.torso.y = Math.sin(travel * 1.3) * 0.35;
}

// The riders shift their feet as the carrier rolls
function carry(view, travel, t) {
  roll(view, travel);
  view.riders.forEach((rider, i) => scuttle(rider, t * 3 + i * 4));
}

function hover(view, travel, t, id) {
  view.torso.y = Math.sin(t * 5 + id) * 1.5;
  view.fans.forEach((blades, i) => {
    blades.rotation = t * 40 + i;
  });
}

// A tread: a band round its wheels, the road wheels, and links that run round the band. `left` and `right` are the
// end wheels' centres, `y` their height and `r` the band's end radius
function tread(view, left, right, y, r, wheels) {
  const band = new Graphics().roundRect(left - r, y - r, right - left + 2 * r, 2 * r, r);
  view.body.addChild(band.fill(TREAD).stroke(OUTLINE));
  const radius = r - 1.9;
  for (let i = 0; i < wheels; i++) {
    const node = new Graphics().circle(0, 0, radius).fill(METAL).stroke(THIN);
    node.circle(0, 0, radius * 0.42).fill(METAL_DARK).stroke(FINE);
    for (let k = 0; k < 3; k++) {
      const a = (k * Math.PI * 2) / 3;
      node.circle(Math.cos(a) * radius * 0.7, Math.sin(a) * radius * 0.7, 0.9).fill(INK);
    }
    node.position.set(left + ((right - left) * i) / (wheels - 1), y);
    view.body.addChild(node);
    view.wheels.push({ node, radius });
  }
  const length = 2 * (right - left) + 2 * Math.PI * r;
  const count = Math.round(length / LINK_PITCH);
  view.track = { left, right, y, r, length, pitch: length / count };
  for (let i = 0; i < count; i++) {
    const link = new Graphics().rect(-1.7, -1.4, 3.4, 2.8).fill(METAL).stroke(FINE);
    view.body.addChild(link);
    view.links.push(link);
  }
}

// A white copy of the hull flashes on hits, and the health bar sits on top of everything
function finish(view, outline) {
  const flash = new Graphics();
  outline(flash);
  flash.fill(0xffffff);
  flash.alpha = 0;
  view.torso.addChild(flash);
  view.flash = flash;
  view.root.addChild(view.body);
  view.bar = new Graphics();
  view.root.addChild(view.bar);
  return view;
}

// A walker's foot: a flat plate with its toes forward
function clawFoot() {
  return new Graphics().poly([-3.5, -0.6, 4.5, -0.6, 6.5, 2.4, -4, 2.4]).fill(METAL).stroke(THIN);
}

function scrapperLeg(far) {
  return {
    x: far ? 3 : -3,
    y: far ? -3 : -2,
    upper: 9,
    lower: 10,
    width: 4,
    color: METAL_DARK,
    outline: THIN,
    far,
    // Knees bend backward, like a bird's
    rest: [0.45, -0.9],
    reach: 0.32,
    lift: [0.3, -0.7],
    phase: far ? Math.PI : 0,
    piston: true,
    foot: clawFoot,
  };
}

function scrapperHull() {
  const g = new Graphics();
  // The arm gun, slung under the front
  g.rect(3, -9.5, 12, 4.5).fill(METAL_DARK).stroke(THIN);
  g.rect(14, -8.6, 6, 2.6).fill(METAL).stroke(FINE);
  g.poly(SCRAPPER_HULL).fill(RUST).stroke(OUTLINE);
  // A mismatched plate bolted over a hole, and a dark seam
  g.poly([-10, -12, -3, -14, -2, -6, -9, -5]).fill(METAL).stroke(FINE);
  g.rect(-8, -3.5, 14, 2).fill(RUST_DARK);
  bolts(g, [
    [-8.6, -11.2],
    [-3.6, -12.6],
    [-3.4, -6.8],
    [-8.2, -6.2],
    [8, -12],
    [8, -5],
  ]);
  // The sensor head with its magenta eye, and an antenna with a green light
  g.poly([0, -17, 2, -23, 11, -23, 13.5, -18.5, 10, -16]).fill(METAL_DARK).stroke(OUTLINE);
  g.circle(8.8, -19.8, 2.6).fill(MAGENTA).stroke(FINE);
  g.moveTo(-6, -17).lineTo(-8, -24).stroke({ width: 1.5, color: INK });
  g.circle(-8, -24.6, 1.9).fill(GREEN);
  return g;
}

// A light two-legged walker on backward-bending legs, with a sensor head and a small arm gun
function scrapper() {
  const view = parts();
  shadow(view, 14, 3.5, 17);
  view.legs.push(leg(view.body, scrapperLeg(true)));
  view.body.addChild(view.torso);
  view.legs.push(leg(view.body, scrapperLeg(false)));
  view.torso.addChild(scrapperHull());
  Object.assign(view, { stride: 22, settle: 1.6, animate: walk });
  return finish(view, (s) => s.poly(SCRAPPER_HULL));
}

function spiderLeg(front, far) {
  const side = front ? 1 : -1;
  return {
    x: side * 4 + (far ? 1.5 : 0),
    y: far ? -3 : -2,
    upper: 7,
    lower: 10,
    width: 3.2,
    color: METAL,
    outline: THIN,
    far,
    // Knees high above the body, feet planted wide
    rest: [-2 * side, 1.75 * side],
    reach: 0.28,
    lift: [0, -0.7 * side],
    // Diagonal pairs step together: near front with far back, far front with near back
    phase: front === far ? Math.PI : 0,
  };
}

// A small four-legged spider mech built into `into`, its body pod in `torso`
function spiderRig(into, torso) {
  const legs = [];
  for (const far of [true, false]) {
    if (!far) {
      into.addChild(torso);
    }
    for (const front of [true, false]) {
      legs.push(leg(into, spiderLeg(front, far)));
    }
  }
  const g = new Graphics();
  g.poly(SPIDER_POD).fill(METAL).stroke(OUTLINE);
  g.poly([-7, -8, -1, -9, -2, -4, -7, -3]).fill(RUST).stroke(FINE);
  g.rect(-4, -1.6, 9, 1.6).fill(METAL_DARK);
  g.circle(6, -5.4, 2).fill(GREEN).stroke(FINE);
  bolts(g, [
    [1.5, -8],
    [-5, -1.8],
  ]);
  torso.addChild(g);
  return { legs, torso, stride: 13 };
}

function skitter() {
  const view = parts();
  shadow(view, 12, 3, 5);
  const rig = spiderRig(view.body, view.torso);
  Object.assign(view, { legs: rig.legs, stride: rig.stride, animate: scuttle });
  return finish(view, (s) => s.poly(SPIDER_POD));
}

// A ducted fan seen from the side: the duct, and blades spinning inside it
function fan(view, x, y) {
  const node = new Container();
  node.position.set(x, y);
  node.scale.y = 0.45;
  const blades = new Graphics()
    .rect(-6.5, -1.3, 13, 2.6)
    .rect(-1.3, -6.5, 2.6, 13)
    .fill({ color: 0xc9ccd0, alpha: 0.8 });
  const duct = new Graphics()
    .circle(0, 0, 7.5)
    .stroke({ width: 5, color: INK })
    .circle(0, 0, 7.5)
    .stroke({ width: 2.6, color: METAL_DARK });
  node.addChild(blades, duct, new Graphics().circle(0, 0, 1.8).fill(METAL_LIGHT));
  view.torso.addChild(node);
  view.fans.push(blades);
}

// A flying gunship drone on two ducted fans, with a sensor canopy and a chin gun
function buzzer() {
  const view = parts();
  // Its shadow falls well below it: it flies
  shadow(view, 11, 3, 17);
  view.body.addChild(view.torso);
  const g = new Graphics();
  g.moveTo(-5, -18).lineTo(-12, -24).moveTo(5, -18).lineTo(11, -24).stroke({ width: 2.5, color: INK });
  g.rect(3, -9.5, 10, 3.2).fill(METAL_DARK).stroke(FINE);
  g.rect(12, -8.9, 5, 2).fill(METAL).stroke(FINE);
  g.poly([-11, -13, -16, -19, -13, -12]).fill(METAL_DARK).stroke(THIN);
  g.poly(BUZZER_HULL).fill(METAL).stroke(OUTLINE);
  g.poly([-8, -15, -1, -17, 0, -10, -8, -10]).fill(RUST).stroke(FINE);
  g.poly([4, -18.5, 7, -18.5, 11.5, -14, 5.5, -12.5]).fill(GLASS).stroke(FINE);
  g.circle(8.3, -14.8, 2.3).fill(MAGENTA);
  g.circle(-13.5, -16.5, 1.5).fill(GREEN);
  bolts(g, [
    [-6.5, -14],
    [-1.8, -11],
  ]);
  view.torso.addChild(g);
  fan(view, -12, -24);
  fan(view, 11, -24);
  // Nose down, flying forward
  view.torso.rotation = 0.06;
  view.animate = hover;
  return finish(view, (s) => s.poly(BUZZER_HULL));
}

function bruteHull() {
  const g = new Graphics();
  // On its back: the warning light's mast and a rocket pod
  g.moveTo(-9, -31).lineTo(-11, -37).stroke({ width: 1.8, color: INK });
  g.circle(-11, -37.6, 2.2).fill(MAGENTA).stroke(FINE);
  g.roundRect(-21, -30, 10, 14, 2).fill(RUST).stroke(THIN);
  g.circle(-16, -26, 2).circle(-16, -20.5, 2).fill(INK);
  // The chassis deck over the treads
  g.poly([-22, -2, -20, -10, 20, -10, 23, -2]).fill(METAL_DARK).stroke(OUTLINE);
  g.rect(-17, -8, 8, 4.5).fill(RUST_LIGHT).stroke(FINE);
  // The upper body: armor plates, a rust patch, the visor's green slit
  g.poly(BRUTE_HULL).fill(METAL).stroke(OUTLINE);
  g.poly([-13, -25, -5, -31, -2, -31, -6, -21]).fill(METAL_DARK).stroke(FINE);
  g.poly([-12, -18, -1, -19.5, -1, -11.5, -12, -11.5]).fill(RUST).stroke(FINE);
  bolts(g, [
    [-10.5, -16.5],
    [-2.8, -17.5],
    [-2.8, -13.2],
    [-10.5, -13.2],
    [12, -12],
    [-4, -27],
  ]);
  g.roundRect(3, -30, 10, 5.5, 1.5).fill(METAL_DARK).stroke(THIN);
  g.rect(5, -28.9, 7, 2.6).fill(GREEN);
  // The arm cannon on its shoulder joint
  g.rect(9, -21, 16, 7).fill(METAL_DARK).stroke(THIN);
  g.rect(24, -22.5, 4, 10).fill(METAL).stroke(THIN);
  g.circle(9, -17.5, 4.5).fill(METAL_LIGHT).stroke(THIN);
  return g;
}

// A heavy armored mech on treads: an armored upper body with a green visor, an arm cannon and a rocket pod
function brute() {
  const view = parts();
  shadow(view, 25, 5, 11);
  view.body.addChild(view.torso);
  view.torso.addChild(bruteHull());
  tread(view, -16, 16, 4, 6.5, 4);
  view.animate = roll;
  return finish(view, (s) => s.poly(BRUTE_HULL));
}

function splitterHull() {
  const g = new Graphics();
  g.poly(SPLITTER_HULL).fill(RUST).stroke(OUTLINE);
  g.rect(-19, -8, 6, 6).fill(METAL).stroke(FINE);
  bolts(g, [
    [-18, -7],
    [-14, -3],
    [3, -9],
    [16, -4],
  ]);
  // The seams it bursts along
  g.moveTo(-10, -10).lineTo(-8, -1).moveTo(0, -10).lineTo(-2, -1).moveTo(9, -10).lineTo(11, -1);
  g.stroke({ width: 1.8, color: GREEN });
  return g;
}

function cab() {
  const g = new Graphics();
  g.poly([12, -11, 14, -18, 19, -18, 23, -12, 22, -7]).fill(METAL_DARK).stroke(OUTLINE);
  g.poly([15, -16.5, 18.5, -16.5, 21, -12.5, 15, -12.5]).fill(GLASS).stroke(FINE);
  g.circle(18.2, -14.4, 2).fill(MAGENTA);
  return g;
}

// Where the riders sit on the deck: x, and height
const RIDERS = [
  [-12, -11],
  [4, -11],
];

// A tread carrier with Skitters riding on its back, the same spiders that jump off when it bursts; green seams mark
// where it breaks apart
function splitter() {
  const view = parts();
  shadow(view, 21, 4, 10);
  view.body.addChild(view.torso);
  view.torso.addChild(splitterHull());
  for (const [x, y] of RIDERS) {
    const seat = new Container();
    seat.position.set(x, y);
    seat.scale.set(0.7);
    view.torso.addChild(seat);
    view.riders.push(spiderRig(seat, new Container()));
  }
  view.torso.addChild(cab());
  tread(view, -15, 15, 5, 5, 4);
  view.animate = carry;
  return finish(view, (s) => s.poly(SPLITTER_HULL));
}

// A big flat foot, toes forward
function stompFoot() {
  const g = new Graphics().poly([-9, -1.5, 10, -1.5, 14, 4.5, -11, 4.5]).fill(METAL_DARK).stroke(HEAVY);
  g.moveTo(5, 0).lineTo(7, 4).moveTo(9.5, 0).lineTo(11.5, 4).stroke({ width: 1.5, color: INK });
  return g;
}

function kneeCap() {
  return new Graphics().poly([-3, -6.5, 8.5, -4, 8.5, 4.5, -3, 6.5]).fill(RUST_DARK).stroke(OUTLINE);
}

function colossusLeg(far) {
  return {
    x: far ? 7 : -8,
    y: far ? -12 : -10,
    upper: 20,
    lower: 18,
    width: 12,
    color: METAL_DARK,
    outline: HEAVY,
    far,
    // Knees bend forward, like a person's
    rest: [-0.25, 0.45],
    reach: 0.24,
    lift: [-0.3, 0.6],
    phase: far ? Math.PI : 0,
    piston: true,
    foot: stompFoot,
    cap: kneeCap,
  };
}

function colossusHull() {
  const g = new Graphics();
  // The pelvis block the legs hang from
  g.roundRect(-19, -18, 38, 13, 4).fill(METAL_DARK).stroke(HEAVY);
  g.rect(-11, -14, 22, 5).fill(RUST_DARK).stroke(FINE);
  g.poly(COLOSSUS_HULL).fill(METAL_DARK).stroke(HEAVY);
  g.poly([-26, -53, 20, -55, 29, -45, -29, -43]).fill(METAL).stroke(THIN);
  g.rect(-25, -38, 17, 14).fill(RUST).stroke(THIN);
  g.poly([4, -34, 26, -36, 28, -25, 6, -23]).fill(RUST_DARK).stroke(THIN);
  g.rect(-31, -40, 5, 18).fill(RUST_LIGHT).stroke(FINE);
  bolts(g, [
    [-23, -36],
    [-10, -36],
    [-23, -26],
    [-10, -26],
    [7, -32],
    [24, -34],
    [8, -25],
    [25, -27],
    [-22, -51],
    [14, -52],
  ]);
  g.circle(-20, -15, 2).fill(GREEN);
  g.circle(28, -40, 1.8).fill(GREEN);
  return g;
}

// The cockpit at the front of the chest, with three magenta lights behind its visor
function cockpit() {
  const g = new Graphics();
  g.poly([4, -56, 8, -70, 28, -70, 34, -60, 28, -54]).fill(METAL).stroke(HEAVY);
  g.poly([12, -67, 28, -67, 31, -61, 12, -61]).fill(GLASS).stroke(FINE);
  for (const x of [16, 22, 28]) {
    g.circle(x, -64, 2.6).fill(MAGENTA);
  }
  return g;
}

// A twin cannon on a shoulder mount, its barrels over the cockpit; the far one is set back and shaded
function shoulderCannon(far) {
  const g = new Graphics();
  g.rect(-22, -74, 12, 18).fill(METAL_DARK).stroke(THIN);
  g.roundRect(-30, -86, 26, 14, 3).fill(METAL_DARK).stroke(HEAVY);
  g.rect(-6, -84, 32, 4.5).fill(METAL).stroke(THIN);
  g.rect(-6, -78, 32, 4.5).fill(METAL).stroke(THIN);
  g.rect(24, -85.5, 5, 13).fill(METAL_DARK).stroke(THIN);
  g.rect(-26, -82, 9, 7).fill(RUST).stroke(FINE);
  g.circle(-9, -79, 1.6).fill(GREEN);
  if (far) {
    g.position.set(6, -5);
    g.tint = FAR;
  }
  return g;
}

function armGun() {
  const arm = new Container();
  const g = new Graphics();
  g.roundRect(-5, -3, 10, 20, 4).fill(METAL_DARK).stroke(HEAVY);
  g.roundRect(-7, 14, 32, 10, 3).fill(METAL).stroke(HEAVY);
  g.rect(24, 16.5, 10, 5).fill(METAL_DARK).stroke(THIN);
  g.rect(-3, 16.5, 9, 5).fill(RUST).stroke(FINE);
  g.circle(19, 19, 1.8).fill(GREEN);
  // The shoulder's armor pad
  g.roundRect(-10, -8, 20, 12, 5).fill(RUST).stroke(HEAVY);
  bolts(g, [
    [-5, -2],
    [5, -2],
  ]);
  arm.addChild(g);
  return arm;
}

// The giant boss: two heavy legs, twin shoulder cannons, an arm gun and a cockpit
function colossus() {
  const view = parts();
  shadow(view, 34, 7, 30);
  view.legs.push(leg(view.body, colossusLeg(true)));
  view.body.addChild(view.torso);
  view.torso.addChild(shoulderCannon(true), colossusHull(), cockpit(), shoulderCannon(false));
  const arm = armGun();
  arm.position.set(-4, -44);
  view.torso.addChild(arm);
  view.arms.push(arm);
  view.legs.push(leg(view.body, colossusLeg(false)));
  Object.assign(view, { stride: 48, settle: 4, animate: walk });
  return finish(view, (s) => s.poly(COLOSSUS_HULL));
}

// By type index: Scrapper, Skitter, Buzzer, Brute, Splitter, Scrap Colossus
const BUILDERS = [scrapper, skitter, buzzer, brute, splitter, colossus];

/** A robot of this type standing still, for a picture of it on the page */
export function robotPicture(type) {
  return BUILDERS[type]().root;
}

// Where the slot-th robot of a pile stands, as an offset from its place on the road's middle line
function crowdSpot(d, slot) {
  const [ax, ay] = pointAt(d - 100);
  const [bx, by] = pointAt(d);
  const length = Math.hypot(bx - ax, by - ay) || 1;
  const fx = (bx - ax) / length;
  const fy = (by - ay) / length;
  const across = CROWD_ACROSS[slot % CROWD_ACROSS.length];
  const back = CROWD_FRONT + Math.floor(slot / CROWD_ACROSS.length) * CROWD_ROW;
  return [-fy * across - fx * back, fx * across - fy * back];
}

export class RobotViews {
  constructor(layer) {
    this.layer = layer;
    this.views = new Map();
    // Where each robot stood before the latest step, in map units
    this.prev = new Map();
  }

  clear() {
    for (const view of this.views.values()) {
      view.root.destroy({ children: true, context: true });
    }
    this.views.clear();
    this.prev.clear();
  }

  remember(run) {
    this.prev.clear();
    if (!run) {
      return;
    }
    for (const robot of run.robots) {
      this.prev.set(robot.id, [robot.x / 100, robot.y / 100]);
    }
  }

  // Where a robot is drawn now, or where it last stood (a robot killed this step still has a spot for its shot), in
  // view units
  positionOf(id) {
    const view = this.views.get(id);
    if (view) {
      return { x: view.root.x, y: view.root.y };
    }
    const at = this.prev.get(id);
    if (!at) {
      return null;
    }
    const [x, y] = toView(...at);
    return { x, y };
  }

  /** The robot drawn nearest a point in view units, within `reach` of its middle, or null */
  robotAt(point, reach) {
    let best = null;
    let bestDistance = reach * reach;
    for (const [id, view] of this.views) {
      const distance = (view.root.x - point.x) ** 2 + (view.root.y - view.middle - point.y) ** 2;
      if (distance <= bestDistance && view.root.alpha > 0.5) {
        best = id;
        bestDistance = distance;
      }
    }
    return best;
  }

  event(e) {
    if (e.kind === "hit") {
      const view = this.views.get(e.id);
      if (view) {
        view.flashing = 1;
      }
    }
  }

  draw(run, alpha, t, dt) {
    const seen = new Set();
    // How many of each bay's pile have their place so far this frame
    const piled = new Map();
    for (const robot of run ? run.robots : []) {
      if (robot.gone) {
        continue;
      }
      seen.add(robot.id);
      let slot = -1;
      if (robot.heldBy >= 0) {
        slot = piled.get(robot.heldBy) ?? 0;
        piled.set(robot.heldBy, slot + 1);
      }
      this.place(robot, run, alpha, t, dt, slot);
    }
    for (const [id, view] of this.views) {
      if (!seen.has(id)) {
        view.root.destroy({ children: true, context: true });
        this.views.delete(id);
      }
    }
  }

  // slot is the robot's place in a Drone bay's pile, or -1 while it walks free
  place(robot, run, alpha, t, dt, slot) {
    let view = this.views.get(robot.id);
    if (!view) {
      view = BUILDERS[robot.type]();
      // middle is how far above its feet the robot's body is, for taps on it
      Object.assign(view, { face: 1, flashing: 0, shownHp: -1, crowdX: 0, crowdY: 0, middle: BAR[robot.type][1] / 2 });
      this.layer.addChild(view.root);
      this.views.set(robot.id, view);
    }
    const [mapX, mapY] = [robot.x / 100, robot.y / 100];
    const [x, y] = toView(mapX, mapY);
    const [fromX, fromY] = toView(...(this.prev.get(robot.id) ?? [mapX, mapY]));
    const [crowdX, crowdY] = slot >= 0 ? toView(...crowdSpot(robot.d, slot)) : [0, 0];
    const ease = Math.min(1, dt * CROWD_EASE);
    view.crowdX += (crowdX - view.crowdX) * ease;
    view.crowdY += (crowdY - view.crowdY) * ease;
    view.root.position.set(fromX + (x - fromX) * alpha + view.crowdX, fromY + (y - fromY) * alpha + view.crowdY);
    view.root.alpha = Math.min(1, robot.d / ENTER_FADE);
    // Robots lower on the screen are nearer the viewer, so they are drawn over the ones above them
    view.root.zIndex = view.root.y;
    if (Math.abs(x - fromX) > 0.01) {
      view.face = x > fromX ? 1 : -1;
    }
    view.body.scale.x = view.face;
    // How far along the road the robot is drawn, so legs and tracks move as smoothly as it glides
    const travel = robot.d / 100 - Math.hypot(x - fromX, y - fromY) * (1 - alpha);
    view.animate(view, travel, t, robot.id);
    view.flashing = Math.max(0, view.flashing - dt * FLASH_FADE);
    view.flash.alpha = view.flashing * FLASH_PEAK;
    view.root.tint = robot.frozenUntil > run.step ? FROZEN : robot.slowUntil > run.step ? SLOWED : 0xffffff;
    this.drawBar(view, robot);
  }

  // Only once hurt, and only redrawn when the health changed
  drawBar(view, robot) {
    if (view.shownHp === robot.hp) {
      return;
    }
    view.shownHp = robot.hp;
    const g = view.bar;
    g.clear();
    if (robot.hp >= robot.maxHp) {
      return;
    }
    const [width, lift] = BAR[robot.type];
    const share = Math.max(0, robot.hp / robot.maxHp);
    g.rect(-width / 2 - 1, -lift - 1, width + 2, 5).fill(INK);
    g.rect(-width / 2, -lift, width * share, 3).fill(share > 0.5 ? GREEN : share > 0.25 ? AMBER : MAGENTA);
  }
}
