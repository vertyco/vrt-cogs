// The 3D scene: the renderer, the lights, and the one handle the other page modules draw through.
// The camera, the belt and the ground layout live in camera.js, belt.js and layout.js.
import * as THREE from "./vendor/three.module.min.js";
import { ARROW_SPACING, BELT_UNITS_PER_SECOND, buildBelt } from "./belt.js";
import { CameraRig } from "./camera.js";
import { createFx } from "./fx.js";
import { Layout } from "./layout.js";
import { createLooks } from "./looks/index.js";
import { createPicture } from "./picture.js";
import { buildPigs, createPigs } from "./pigs.js";
import { flipPosition } from "./space.js";

const BACKGROUND = 0x3a3b61;

function makeRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  // Phones report 3x pixels; capping at 2 keeps them cool with little visible loss
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.setClearColor(BACKGROUND);
  return renderer;
}

function makeLights(scene) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x6a6aa0, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(-6, 14, 8);
  scene.add(sun);
}

// The handle: `rig` (camera), `layout` (ground spots and boxes), `picture` (the cubes, picture.js), `pigs` (the pigs,
// trays and slot row, pigs.js), `fx` (motion and effects, fx.js), `looks` (the features' looks, looks/index.js),
// `layoutLevel(level)`, `showLevel(state)`, `resize()`,
// `render(seconds)`, `requestRender()`, `screenBoxes()`, `project(worldPoint)`, `counterSpot()` (where the free-tray
// counter's middle is on screen, in pixels from the column's top left) and `onLayout(handler)` (called after every
// resize and every refit, for page elements that follow the board)
export async function createScene(canvas, board) {
  const renderer = makeRenderer(canvas);
  const scene = new THREE.Scene();
  makeLights(scene);
  const belt = await buildBelt(board);
  scene.add(belt.group);
  const rig = new CameraRig(board, belt.box, belt.reach);
  const layout = new Layout(board, rig, belt.box);
  const picture = await createPicture(scene, rig);
  const pigs = await createPigs(scene, layout, board);
  const fx = createFx(scene, picture);
  const looks = await createLooks(scene, picture);
  pigs.fx = fx;
  pigs.looks = looks;
  fx.looks = looks;
  const state = { arrowOffset: 0, requested: false, shown: false, layoutHandlers: [] };

  // Draw now. `seconds` (the page's clock) scrolls the belt's arrows and flies the chips; leave it out to draw a still
  // picture
  function render(seconds) {
    if (seconds !== undefined) {
      state.arrowOffset = -(seconds * BELT_UNITS_PER_SECOND) / ARROW_SPACING;
      picture.frame(seconds);
    }
    belt.arrows.offset.x = state.arrowOffset;
    picture.animate();
    renderer.render(scene, rig.camera);
    state.shown = true;
  }

  // Draw once on the next frame, however many changes ask for it before then
  function requestRender() {
    if (state.requested) {
      return;
    }
    state.requested = true;
    requestAnimationFrame(() => {
      state.requested = false;
      render();
    });
  }

  // Size the drawing to the play column and refit the camera to its shape
  function resize() {
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    renderer.setSize(width, height, false);
    rig.resize(width, height);
    pigs.refresh();
    state.layoutHandlers.forEach((handler) => handler());
  }

  // Frame this level's picture with the belt, then draw
  function layoutLevel(level) {
    rig.fit(level);
    pigs.forgetBoxes();
    requestRender();
    state.layoutHandlers.forEach((handler) => handler());
  }

  // Frame this level's picture and put its cubes up, then draw
  function showLevel(simState) {
    picture.build(simState);
    buildPigs(handle, simState);
    layoutLevel(simState.level);
  }

  resize();
  new ResizeObserver(() => {
    resize();
    if (state.shown) {
      requestRender();
    }
  }).observe(canvas);
  const handle = {
    renderer,
    scene,
    rig,
    layout,
    picture,
    pigs,
    fx,
    looks,
    resize,
    render,
    requestRender,
    layoutLevel,
    showLevel,
    screenBoxes: () => layout.screenBoxes(),
    project: (point) => rig.project(point),
    counterSpot: () => rig.project(flipPosition(board.anchors.free_tray_counter.position)),
    onLayout: (handler) => state.layoutHandlers.push(handler),
  };
  return handle;
}
