// Draws Starhold with PixiJS. The map lives in map units (720 x 1280); the scene's `world` is in view units (see
// view.js), scaled and placed on the page by layout(). During a run the map fills the screen: it is turned on its side
// when that draws it bigger, and its edges may go under the bar or past the screen, since the moon carries on past
// them. The ring menu and the wave button live in screen pixels above the map, so their buttons stay thumb sized at
// any scale. The scene only reads the run: robots and shells are drawn between the rules' steps, smoothed by how far
// the page is into the next one.
import { Application, Container, Graphics } from "../vendor/pixi.min.mjs";
import { MAP, ROBOTS } from "../sim/rules.js";
import { Effects } from "./effects.js";
import { MapView } from "./map.js";
import { Ring } from "./ring.js";
import { RobotViews, robotPicture } from "./robots.js";
import { TowerViews } from "./towers.js";
import { toView, view, viewSize } from "./view.js";
import { WaveButton } from "./wave.js";

// A tap this close to a spot's middle picks it: in map units, and never less than this many pixels on screen
const SPOT_TAP = 46;
const SPOT_TAP_PX = 26;
// A tap this close to a robot's middle picks it, the same way
const ROBOT_TAP = 26;
const ROBOT_TAP_PX = 24;
// Bottom to top. Drones fly, so they sit above the robots they hold
const LAYERS = ["ground", "marks", "towers", "robots", "drones", "shells", "effects"];
// Longer gaps between frames than this (a hidden tab) don't advance the drawing's own clock
const LONGEST_FRAME_S = 0.1;
// The map is never drawn bigger than this, past which the backdrop picture would go soft
const MOST_SCALE = 1.5;
// A pad reaches this far from its middle, the core this far from its own, and the road this far from its line
const PAD_REACH = 34;
const CORE_REACH = 52;
const ROAD_HALF = 33;
const FOCUS = 0xb8fff4;

// The part of the map a run needs on screen, in map units: every pad, the core, and the road on the map (its
// stretches run straight between its corners, so the corners give its edges). The rest of the map is moon, which may
// go under the bar or past the screen's edge
function essentials() {
  const [cx, cy] = MAP.core;
  const xs = [cx - CORE_REACH, cx + CORE_REACH];
  const ys = [cy - CORE_REACH, cy + CORE_REACH];
  for (const [x, y] of MAP.spots) {
    xs.push(x - PAD_REACH, x + PAD_REACH);
    ys.push(y - PAD_REACH, y + PAD_REACH);
  }
  for (const [x, y] of MAP.road) {
    xs.push(x - ROAD_HALF, x + ROAD_HALF);
    ys.push(y - ROAD_HALF, y + ROAD_HALF);
  }
  return {
    left: Math.max(0, Math.min(...xs)),
    top: Math.max(0, Math.min(...ys)),
    right: Math.min(MAP.width, Math.max(...xs)),
    bottom: Math.min(MAP.height, Math.max(...ys)),
  };
}

const ESSENTIALS = essentials();

// How big the map can be drawn with its essentials inside the field, upright or turned
function fitScale(field, turned) {
  const across = ESSENTIALS.right - ESSENTIALS.left;
  const down = ESSENTIALS.bottom - ESSENTIALS.top;
  const [width, height] = turned ? [down, across] : [across, down];
  return Math.min(field.width / width, field.height / height, MOST_SCALE);
}

class Scene {
  constructor(app) {
    this.app = app;
    this.world = new Container();
    this.layers = {};
    for (const name of LAYERS) {
      const layer = new Container();
      this.layers[name] = layer;
      this.world.addChild(layer);
    }
    this.layers.robots.sortableChildren = true;
    app.stage.addChild(this.world);
    this.scale = 1;
    this.origin = { x: 0, y: 0 };
    // The whole map's box on the page, and the field: the part of the page inside the bar and Discord's edges
    this.box = { x: 0, y: 0, width: 0, height: 0 };
    this.field = { x: 0, y: 0, width: 0, height: 0 };
    this.time = 0;
    this.map = new MapView(this.layers.ground);
    this.towers = new TowerViews(this.layers.towers);
    this.robots = new RobotViews(this.layers.robots);
    this.effects = new Effects(this.layers.effects, this.layers.shells, this);
    // The robot tapped for its card, and the mark under its feet
    this.selected = null;
    this.selection = new Graphics().ellipse(0, 0, 22, 9).stroke({ width: 2.5, color: FOCUS });
    this.selection.visible = false;
    this.layers.marks.addChild(this.selection);
    this.wave = new WaveButton(this);
    app.stage.addChild(this.wave.layer);
    this.ring = new Ring(this);
    app.stage.addChild(this.ring.layer);
    // Pictures of each robot type for the page's cards, as image addresses, once they are made
    this.icons = [];
    this.onPress = null;
    this.onFrame = null;
    app.canvas.addEventListener("pointerdown", (event) => this.press(event));
    // A mouse over a ring button or the wave button shows what it is. Touch screens have no hover, so a first tap
    // shows it instead
    app.canvas.addEventListener("pointermove", (event) => this.hover(event));
    app.canvas.addEventListener("pointerleave", () => {
      this.ring.hover(null);
      this.wave.hover(null);
    });
    app.ticker.add(() => this.onFrame?.(performance.now()));
  }

  get turned() {
    return view.turned;
  }

  // `field` is where the map's essentials must go, in page pixels. During a run the map is turned whichever way draws
  // it bigger. Covering (behind the title and game over screens), it fills the field, turned on a wide screen
  layout(field, cover = false) {
    let turned;
    let scale;
    if (cover) {
      turned = field.width > field.height;
      const size = viewSize(turned);
      scale = Math.max(field.width / size.width, field.height / size.height);
    } else {
      const upright = fitScale(field, false);
      const sideways = fitScale(field, true);
      turned = sideways > upright;
      scale = Math.max(upright, sideways);
    }
    if (turned !== view.turned) {
      view.turned = turned;
      this.reorient();
    }
    this.scale = scale || 1;
    this.field = { ...field };
    // Covering, the map's own middle goes to the field's; in a run, the middle of its essentials does
    const middle = cover
      ? [MAP.width / 2, MAP.height / 2]
      : [(ESSENTIALS.left + ESSENTIALS.right) / 2, (ESSENTIALS.top + ESSENTIALS.bottom) / 2];
    const [mx, my] = toView(...middle);
    this.origin = { x: field.x + field.width / 2 - mx * this.scale, y: field.y + field.height / 2 - my * this.scale };
    const size = viewSize();
    this.box = { ...this.origin, width: size.width * this.scale, height: size.height * this.scale };
    this.world.scale.set(this.scale);
    this.world.position.set(this.origin.x, this.origin.y);
    this.ring.layout();
    this.wave.place();
  }

  // The view turned: everything drawn in view units moves to its new place. Effects in flight just end
  reorient() {
    this.map.reorient();
    this.towers.reorient();
    this.effects.clear();
    this.ring.close();
    this.ring.stopParking();
  }

  mapToClient(x, y) {
    const [vx, vy] = toView(x, y);
    return { x: this.origin.x + vx * this.scale, y: this.origin.y + vy * this.scale };
  }

  clientToMap(x, y) {
    const [mx, my] = toView((x - this.origin.x) / this.scale, (y - this.origin.y) / this.scale);
    return { x: mx, y: my };
  }

  clientOf(event) {
    const rect = this.app.canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  // Acts on touch-down, the moment a finger lands. touch is any press that isn't the mouse's, which can't hover
  press(event) {
    if (event.button !== undefined && event.button > 0) {
      return;
    }
    const client = this.clientOf(event);
    this.onPress?.({ client, map: this.clientToMap(client.x, client.y), touch: event.pointerType !== "mouse" });
  }

  hover(event) {
    if (event.pointerType === "mouse") {
      const client = this.clientOf(event);
      this.ring.hover(client);
      this.wave.hover(client);
    }
  }

  spotAt(point) {
    const reach = Math.max(SPOT_TAP, SPOT_TAP_PX / this.scale);
    let best = -1;
    let bestDistance = reach * reach;
    MAP.spots.forEach(([x, y], spot) => {
      const distance = (x - point.x) ** 2 + (y - point.y) ** 2;
      if (distance <= bestDistance) {
        best = spot;
        bestDistance = distance;
      }
    });
    return best;
  }

  /** The id of the robot drawn under a point on the page, or null */
  robotAt(client) {
    const point = { x: (client.x - this.origin.x) / this.scale, y: (client.y - this.origin.y) / this.scale };
    return this.robots.robotAt(point, Math.max(ROBOT_TAP, ROBOT_TAP_PX / this.scale));
  }

  ringButtons() {
    return this.ring.buttons().map(({ action, x, y }) => ({ action, x, y }));
  }

  resetRun(run) {
    this.towers.clear();
    this.robots.clear();
    this.effects.clear();
    this.ring.close();
    this.ring.stopParking();
    this.wave.unpick();
    this.selected = null;
    this.robots.remember(run);
  }

  // Where every robot stood before the step, so drawing can glide from there to where the step put it
  beforeTick(run) {
    this.robots.remember(run);
  }

  // Hands the run's new events to the drawing, and returns them for the sound
  takeEvents(run) {
    const events = run.events;
    if (!events || !events.length) {
      return [];
    }
    run.events = [];
    for (const event of events) {
      this.towers.event(event, this);
      this.robots.event(event);
      this.effects.event(event, run);
    }
    return events;
  }

  draw(run, alpha) {
    const dt = Math.min(LONGEST_FRAME_S, this.app.ticker.deltaMS / 1000);
    this.time += dt;
    this.map.animate(this.time, run);
    this.towers.draw(run, this.time, this);
    this.robots.draw(run, alpha, this.time, dt);
    this.effects.draw(run, alpha, this.time, dt);
    this.wave.draw(run, this.time);
    this.ring.draw(run, this.time);
    const mark = this.selected === null ? null : this.robots.views.get(this.selected)?.root;
    this.selection.visible = Boolean(mark);
    if (mark) {
      this.selection.position.set(mark.x, mark.y);
      this.selection.alpha = 0.6 + 0.4 * Math.sin(this.time * 6);
    }
    const shake = this.effects.shakeOffset();
    this.world.position.set(this.origin.x + shake.x * this.scale, this.origin.y + shake.y * this.scale);
  }
}

async function loadFonts() {
  try {
    await Promise.all([document.fonts.load('700 20px "Rajdhani"'), document.fonts.load('400 16px "Nunito"')]);
  } catch (e) {
    console.warn("Starhold: the fonts didn't load, so text uses a fallback", e);
  }
}

// A picture of each robot type, as an image address for the page's cards. A type whose picture can't be made has none
async function robotIcons(app) {
  const icons = [];
  for (let type = 0; type < ROBOTS.length; type++) {
    const picture = robotPicture(type);
    try {
      icons.push(await app.renderer.extract.base64({ target: picture, resolution: 2 }));
    } catch (e) {
      console.warn("Starhold: couldn't make a robot's picture for the cards", e);
      icons.push("");
    }
    picture.destroy({ children: true });
  }
  return icons;
}

export async function createScene(host) {
  const app = new Application();
  await app.init({
    resizeTo: host,
    background: 0x05080d,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  host.append(app.canvas);
  await loadFonts();
  const scene = new Scene(app);
  await scene.map.load();
  scene.icons = await robotIcons(app);
  return scene;
}
