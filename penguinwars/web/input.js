// The player's fingers: drag back and let go to slide, tap to brace, and tap near the edge as a seal. Someone watching
// who has their snowballs out taps the ice to throw one. Only the canvas listens, so a press on the bar or a card never
// starts a drag.
import { buildArrow } from "./models.js";
import { aimFrom, ALIVE, edgePoint, FISH, slideSpeed, stopDistance, TAP_MS, TAP_PIXELS } from "./motion.js";
import { ICE_Y } from "./scene.js";

// Where the arrow starts in front of the penguin, how long its head is, and the shortest arrow that still reads
const ARROW_GAP = 0.6;
const ARROW_HEAD = 0.34;
const ARROW_LEAST = 1;
const SHAFT_LEAST = 0.05;
const ARROW_LIFT = 0.04;
// A slide or brace let go this many seconds before the wait is over is kept, and goes the moment it is. The page
// counts a little longer than the wait itself, until it sees the bot's own count end, so a kept move may hold for
// this many milliseconds before it is given up
const EARLY = 0.2;
const EARLY_KEPT_MS = 450;

class Controls {
  constructor(canvas, scene, handlers) {
    this.canvas = canvas;
    this.scene = scene;
    this.handlers = handlers;
    this.drag = { on: false, id: 0, x0: 0, y0: 0, x: 0, y: 0, t0: 0 };
    // The move let go a moment too early: whether one is waiting, its aim, or null for a brace, and when it lapses
    this.early = { on: false, aimed: null, until: 0 };
    // What throws a snowball at a spot on the ice for someone with no seat, or null while their snowballs are put
    // away, and the press that may turn out to be a throw
    this.thrower = null;
    this.toss = { on: false, id: 0, x0: 0, y0: 0 };
    this.arrow = buildArrow(scene.app);
    this.rayNear = new pc.Vec3();
    this.rayFar = new pc.Vec3();
    this.live = false;
    this.listen();
    scene.app.on("update", this.drawAim, this);
  }

  listen() {
    const { canvas } = this;
    const cancel = () => this.cancelDrag();
    // Letting go also ends the hold on the finger, which is no cancel: a move kept from that lift stays
    const cancelFinger = (e) => {
      const held = (press) => press.on && e.pointerId === press.id;
      if (held(this.drag) || held(this.toss)) {
        this.cancelDrag();
      }
    };
    canvas.addEventListener("pointerdown", (e) => this.press(e));
    canvas.addEventListener("pointermove", (e) => this.move(e));
    canvas.addEventListener("pointerup", (e) => this.release(e));
    canvas.addEventListener("pointercancel", cancelFinger);
    canvas.addEventListener("lostpointercapture", cancelFinger);
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    window.addEventListener("blur", cancel);
    window.addEventListener("pagehide", cancel);
    // A press from before the screen turned means nothing on the new layout
    window.addEventListener("resize", cancel);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.cancelDrag();
      }
    });
  }

  // Whether a round is being played. Someone with no seat has no moves, so their fingers do nothing either way,
  // unless they have their snowballs out
  setLive(live) {
    this.live = live;
    if (!live) {
      this.cancelDrag();
    }
  }

  cancelDrag() {
    this.drag.on = false;
    this.early.on = false;
    this.toss.on = false;
  }

  // `thrower(x, z, px, py)` is called with the spot on the ice, and the spot on the screen, of each tap by someone
  // with no seat while a round is played. Null puts the snowballs away
  setThrow(thrower) {
    this.thrower = thrower;
    this.toss.on = false;
  }

  aim() {
    const { drag } = this;
    return aimFrom(drag.x - drag.x0, drag.y - drag.y0, window.innerWidth, window.innerHeight);
  }

  // What the player's penguin or seal can do now, or null with none on show
  moves() {
    const { scene } = this;
    const pen = scene.mySeat === null ? null : scene.pens[scene.mySeat];
    if (!pen?.row) {
      return null;
    }
    const flags = pen.row[2];
    return {
      pen,
      alive: (flags & ALIVE) !== 0,
      fish: (flags & FISH) !== 0,
      bracing: pen.bracing,
      wait: scene.prediction.waitOn(pen.row[3] / 100),
      sealUp: pen.seal.state !== "off",
      sealReady: pen.seal.state === "swim" && scene.prediction.sealWait <= 0,
    };
  }

  // The point on the water under a spot on the screen, or on a level `height` above it
  screenToWater(x, y, height = 0) {
    const { rayNear, rayFar } = this;
    const { camera } = this.scene.camera;
    camera.screenToWorld(x, y, camera.nearClip, rayNear);
    camera.screenToWorld(x, y, camera.farClip, rayFar);
    const drop = rayFar.y - rayNear.y;
    if (Math.abs(drop) < 1e-6) {
      return null;
    }
    const k = (height - rayNear.y) / drop;
    return { x: rayNear.x + (rayFar.x - rayNear.x) * k, z: rayNear.z + (rayFar.z - rayNear.z) * k };
  }

  // Each move goes to the bot and shows on the same frame, unless the connection couldn't take it
  slide({ pen, fish }, { dx, dz, power }) {
    const { prediction, rules } = this.scene;
    if (this.handlers.slide(dx, dz, power)) {
      prediction.slide(pen.x, pen.z, dx, dz, slideSpeed(power, fish, rules), rules, fish);
      this.scene.fx.flick(pen.x - dx * 0.45, pen.z - dz * 0.45, fish, power);
      Object.assign(pen, { yaw: Math.atan2(dx, dz), sliding: true, squash: 0.5 });
    }
  }

  brace({ pen }) {
    if (this.handlers.brace()) {
      this.scene.prediction.brace(this.scene.rules);
      this.scene.fx.brace(pen.x, pen.z);
    }
  }

  // The seal goes down on the tap, for the spot the bot will pick. With no ice that way the bot would refuse it
  splash({ pen }, x, y) {
    const { scene } = this;
    const water = this.screenToWater(x, y);
    if (!water) {
      return;
    }
    const angle = Math.atan2(water.z, water.x);
    const spot = edgePoint(
      angle,
      scene.tiles.map((tile) => tile.state),
    );
    if (spot.reach > 0 && this.handlers.splash(angle)) {
      scene.diveSeal(pen.seal, spot.x, spot.z);
      scene.prediction.dive(pen.seal, scene.rules);
      scene.fx.dive();
    }
  }

  finishDrag(e) {
    const aimed = this.aim();
    // A press is timed by its own events, so a busy page can't turn a quick tap into a long press
    const tap = !aimed && e.timeStamp - this.drag.t0 < TAP_MS;
    const me = this.moves();
    if (!me) {
      return;
    }
    if (me.alive) {
      if (aimed && me.wait <= 0 && !me.bracing) {
        this.slide(me, aimed);
      } else if (tap && me.wait <= 0) {
        this.brace(me);
      } else if ((aimed || tap) && me.wait <= EARLY) {
        Object.assign(this.early, { on: true, aimed, until: performance.now() + EARLY_KEPT_MS });
      }
    } else if (tap && me.sealReady) {
      this.splash(me, e.clientX, e.clientY);
    }
  }

  // Only the main mouse button plays, so a right or middle click is no tap. Fingers and pens always press with it.
  // Someone with no seat has no penguin or seal to move, so their press can only be a snowball's
  press(e) {
    if (e.button !== 0 || !this.live) {
      return;
    }
    const [x, y] = [e.clientX, e.clientY];
    if (this.scene.mySeat === null) {
      if (this.thrower) {
        Object.assign(this.toss, { on: true, id: e.pointerId, x0: x, y0: y });
        this.hold(e);
      }
      return;
    }
    const me = this.moves();
    if (!me || (!me.alive && !me.sealUp)) {
      return;
    }
    // A new press is the player's latest word, so a move still waiting from the last one is dropped
    this.early.on = false;
    Object.assign(this.drag, { on: true, id: e.pointerId, x0: x, y0: y, x, y, t0: e.timeStamp });
    this.hold(e);
  }

  // The canvas keeps hearing from this finger wherever it goes
  hold(e) {
    try {
      this.canvas.setPointerCapture(e.pointerId);
    } catch (err) {
      console.warn("Penguin Wars: couldn't keep hold of the finger", err);
    }
  }

  // A press that lifts about where it came down throws a snowball at that spot on the ice. One that moved away is a
  // change of mind
  finishToss(e) {
    const { toss } = this;
    toss.on = false;
    const spot = this.screenToWater(e.clientX, e.clientY, ICE_Y);
    if (spot && this.thrower && Math.hypot(e.clientX - toss.x0, e.clientY - toss.y0) < TAP_PIXELS) {
      this.thrower(spot.x, spot.z, e.clientX, e.clientY);
    }
  }

  move(e) {
    const { drag } = this;
    if (drag.on && e.pointerId === drag.id) {
      drag.x = e.clientX;
      drag.y = e.clientY;
    }
  }

  release(e) {
    const { drag, toss } = this;
    if (drag.on && e.pointerId === drag.id) {
      this.move(e);
      drag.on = false;
      this.finishDrag(e);
    } else if (toss.on && e.pointerId === toss.id) {
      this.finishToss(e);
    }
  }

  paintArrow(me, power) {
    const { material } = this.arrow;
    if (me.wait > 0 || me.bracing) {
      material.emissive.set(0.45, 0.5, 0.55);
    } else if (me.fish) {
      material.emissive.set(1, 0.6, 0.15);
    } else {
      material.emissive.set(1, 0.81 - 0.5 * power, 0.2 - 0.1 * power);
    }
    material.update();
  }

  placeArrow(me, { dx, dz, power }) {
    const { arrow, scene } = this;
    const reach = Math.max(ARROW_LEAST, stopDistance(slideSpeed(power, me.fish, scene.rules), scene.rules));
    const shaft = Math.max(SHAFT_LEAST, reach - ARROW_GAP - ARROW_HEAD);
    me.pen.aimYaw = Math.atan2(dx, dz);
    arrow.root.setPosition(me.pen.x, ICE_Y + ARROW_LIFT, me.pen.z);
    arrow.root.setEulerAngles(0, (me.pen.aimYaw * 180) / Math.PI, 0);
    arrow.shaft.setLocalScale(0.16, 0.03, shaft);
    arrow.shaft.setLocalPosition(0, 0, ARROW_GAP + shaft / 2);
    arrow.head.setLocalPosition(0, 0, ARROW_GAP + shaft + ARROW_HEAD / 2);
    this.paintArrow(me, power);
  }

  // The move let go a moment early goes as soon as the wait is over. It is dropped if the penguin fell in meanwhile,
  // or the wait outlasts it
  sendEarly(me) {
    const { early } = this;
    if (!me?.alive || performance.now() > early.until) {
      early.on = false;
    } else if (me.wait <= 0 && !me.bracing) {
      early.on = false;
      if (early.aimed) {
        this.slide(me, early.aimed);
      } else {
        this.brace(me);
      }
    }
  }

  // The arrow and the penguin's lean, after the scene has drawn the penguin for this frame. With no drag, no arrow
  // left to clear and no move waiting there is nothing to do
  drawAim() {
    const { arrow, drag, early } = this;
    if (!drag.on && !arrow.root.enabled && !early.on) {
      return;
    }
    const me = this.moves();
    if (early.on) {
      this.sendEarly(me);
    }
    const aimed = drag.on && me?.alive ? this.aim() : null;
    arrow.root.enabled = Boolean(aimed);
    if (me) {
      me.pen.windup = aimed ? aimed.power : 0;
    }
    if (aimed) {
      this.placeArrow(me, aimed);
    }
  }
}

// `handlers` takes slide(dx, dz, power), brace() and splash(angle), each saying whether the move went out to the bot.
// Gives back something with setLive(live) and cancelDrag()
export function bindInput(canvas, scene, handlers) {
  return new Controls(canvas, scene, handlers);
}
