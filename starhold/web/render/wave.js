// The button that calls the next wave early, on the road where the robots walk in. A ring around it counts down to
// the wave, and the money for calling it now hangs under it. It shows only while the countdown runs. The mouse over
// it, or a first tap on a touch screen, shows in the card what the wave brings; a click, or a second tap, calls it.
// Drawn in screen pixels above the map, like the ring menu, and under it, so an open ring always takes the tap.
import { Container, Graphics, Text } from "../vendor/pixi.min.mjs";
import { pointAt, ROAD_LENGTH } from "../sim/road.js";
import { MAP, START, STEPS, WAVES } from "../sim/rules.js";

// The button's radius on screen (52 px across, like the ring's buttons), and the countdown ring's
const RADIUS = 26;
const RING = 31;
const TAP_SLACK = 6;
// Room kept between the countdown ring and the field's edge, and under the button for the money label
const EDGE = 4;
const LABEL_ROOM = 22;
// How far apart, in map units, the points along the road are where the button may sit
const STEP = 4;
// The road before its start, off the map's edge, which the map draws on too
const RUN_IN = 2000;
const LIVE = 0x5fe3ff;
const FOCUS = 0xb8fff4;
const EYES = 0xff2e88;
const BONUS = {
  fontFamily: "Rajdhani",
  fontWeight: "700",
  fontSize: 15,
  fill: 0xbff7ff,
  stroke: { color: 0x02080d, width: 4 },
};

// A robot's head: a rounded box with two glowing eyes, a grille and an antenna
function head() {
  const g = new Graphics();
  g.moveTo(0, -10).lineTo(0, -15).stroke({ width: 2, color: LIVE });
  g.circle(0, -16, 2.5).fill(LIVE);
  g.roundRect(-12, -10, 24, 19, 5).fill(0x12303f).stroke({ width: 2, color: LIVE });
  g.circle(-5, -2, 3).fill(EYES).circle(5, -2, 3).fill(EYES);
  g.rect(-6, 4, 12, 2).fill(LIVE);
  return g;
}

function checkMark() {
  const g = new Graphics().circle(19, -19, 9).fill(FOCUS).stroke({ width: 2, color: 0x0b1823 });
  g.moveTo(15, -19).lineTo(18, -16).lineTo(23, -22);
  return g.stroke({ width: 2.5, color: 0x0b1823, cap: "round", join: "round" });
}

// A point on the road in map units: before its start (negative) along its first stretch, or along it
function roadPoint(at) {
  if (at >= 0) {
    const [x, y] = pointAt(Math.min(at, ROAD_LENGTH / 100) * 100);
    return [x / 100, y / 100];
  }
  const [[ax, ay], [bx, by]] = MAP.road;
  const length = Math.hypot(bx - ax, by - ay);
  return [ax + ((bx - ax) / length) * at, ay + ((by - ay) / length) * at];
}

export class WaveButton {
  constructor(scene) {
    this.scene = scene;
    this.layer = new Container();
    this.layer.visible = false;
    this.track = new Graphics();
    this.disc = new Graphics();
    this.arc = new Graphics();
    this.check = checkMark();
    this.label = new Text({ text: "", style: BONUS });
    this.label.anchor.set(0.5, 0);
    this.label.y = RING + 1;
    this.layer.addChild(this.track, this.arc, this.disc, head(), this.check, this.label);
    this.center = { x: 0, y: 0 };
    this.shown = false;
    // The mouse over it, and a first tap on a touch screen
    this.hovered = false;
    this.picked = false;
    this.look = "";
  }

  /** Where it sits: where the road comes into the field, nudged in from the field's edges so the whole button and
   * its money label fit. A road that comes in along the screen's edge keeps the button at its way in all the same */
  place() {
    const field = this.scene.field;
    const inside = (p) =>
      p.x >= field.x && p.x <= field.x + field.width && p.y >= field.y && p.y <= field.y + field.height;
    let at = -RUN_IN;
    let point = this.scene.mapToClient(...roadPoint(at));
    while (!inside(point) && at < ROAD_LENGTH / 100) {
      at += STEP;
      point = this.scene.mapToClient(...roadPoint(at));
    }
    const clamp = (value, low, high) => Math.min(Math.max(value, low), high);
    this.center = {
      x: clamp(point.x, field.x + RING + EDGE, field.x + field.width - RING - EDGE),
      y: clamp(point.y, field.y + RING + EDGE, field.y + field.height - RING - LABEL_ROOM),
    };
    this.layer.position.set(this.center.x, this.center.y);
  }

  get focused() {
    return this.shown && (this.hovered || this.picked);
  }

  hit(client) {
    if (!this.shown) {
      return false;
    }
    return (client.x - this.center.x) ** 2 + (client.y - this.center.y) ** 2 <= (RADIUS + TAP_SLACK) ** 2;
  }

  hover(client) {
    this.hovered = Boolean(client) && this.hit(client);
  }

  pick() {
    this.picked = true;
  }

  unpick() {
    this.picked = false;
  }

  /** Where it reaches on the page when it shows, its money label included */
  area() {
    const { x, y } = this.center;
    return { left: x - RING, top: y - RING, right: x + RING, bottom: y + RING + LABEL_ROOM };
  }

  /** Where it reaches on the page, or null while it's hidden */
  extent() {
    return this.shown ? this.area() : null;
  }

  /** Its middle and size on the page, or null while it's hidden */
  button() {
    return this.shown ? { x: this.center.x, y: this.center.y, size: RADIUS * 2 } : null;
  }

  draw(run, t) {
    this.shown = Boolean(run) && !run.over && run.countdown > 0;
    this.layer.visible = this.shown;
    if (!this.shown) {
      this.hovered = false;
      this.picked = false;
      return;
    }
    const full = run.wave === 0 ? START.countdown : WAVES.countdown;
    const left = Math.min(1, run.countdown / full);
    this.arc.clear();
    this.arc.arc(0, 0, RING, -Math.PI / 2, -Math.PI / 2 + left * Math.PI * 2);
    this.arc.stroke({ width: 4, color: FOCUS, cap: "round" });
    const bonus = `+${WAVES.callBonus * Math.floor(run.countdown / STEPS)}`;
    const look = `${bonus}|${this.focused}|${this.picked}`;
    if (look !== this.look) {
      this.look = look;
      this.label.text = bonus;
      this.track.clear().circle(0, 0, RING).stroke({ width: 4, color: 0x02080d, alpha: 0.75 });
      this.disc.clear().circle(0, 0, RADIUS).fill({ color: 0x0b1823, alpha: 0.94 });
      this.disc.stroke({ width: this.focused ? 3.5 : 2, color: this.focused ? FOCUS : LIVE });
      this.check.visible = this.picked;
    }
    // A slow throb, so it reads as something to press
    this.layer.scale.set(1 + 0.04 * Math.sin(t * 4));
  }
}
