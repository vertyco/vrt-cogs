// The farm's 14 rooms and the farmhouse's 2 extra rooms: where each one's exits lead, what stands in it, and where the
// farmer can walk.
// Positions are room pixels. A room is 1280 x 720 and its ground starts at HORIZON. A thing stands at its position:
// the middle of its bottom edge (its feet) touches the ground there, and things lower on the screen draw in front.
export const ROOM = { width: 1280, height: 720 };
export const HORIZON = 230;

// The band of a room every screen shows in full, from a strip of sky down to the ground's front edge. Around it,
// more sky and more ground fill the screen, and the HUD and the tool bar float over them
export const VIEW = { outside: { top: 180, bottom: 700 }, inside: { top: 0, bottom: 720 } };

// The exit buttons, the keys that press them, and the side of the next room the farmer comes in from
export const DIRECTIONS = {
  left: { key: "ArrowLeft", from: "right" },
  right: { key: "ArrowRight", from: "left" },
  up: { key: "ArrowUp", from: "down" },
  down: { key: "ArrowDown", from: "up" },
};

// A plot's fenced field, a diamond like FarmVille's. Its 9 spots sit in a 3 by 3 diamond in the middle: rows are
// spots 0-2, 3-5 and 6-8, spot 0 at the back corner. A pen's animals roam the whole fenced diamond
export const FIELD = { x: 640, y: 480, spotWidth: 144, spotHeight: 72, fenceWidth: 660, fenceHeight: 330 };

// Where a plot's spot sits: the middle of its soil diamond
export function spotCenter(index) {
  const row = Math.floor(index / 3);
  const column = index % 3;
  return {
    x: FIELD.x + ((column - row) * FIELD.spotWidth) / 2,
    y: FIELD.y + ((column + row - 2) * FIELD.spotHeight) / 2,
  };
}

// Where the farmer can walk outside: a little below the horizon, so trees at the back stay behind him
const OUTSIDE_WALK = { left: 50, right: 1230, top: 390, bottom: 700 };
// Inside the farmhouse: the floor in front of the wall
const INSIDE_WALK = { left: 120, right: 1160, top: 480, bottom: 700 };
// Where decorations can stand, in the rooms that hold them: the Yard's ground and an extra room's floor. A decoration's
// place is a share (0 to 1) of the whole room's width and height, not of this box; the page only drops one inside it
const YARD_FLOOR = { left: 40, right: 1240, top: 300, bottom: 700 };
const INSIDE_FLOOR = { left: 90, right: 1190, top: 470, bottom: 700 };

const TREES_LEFT = [
  { art: "tree_1", x: 120, y: 360 },
  { art: "bush_2", x: 250, y: 420 },
];
const TREES_RIGHT = [
  { art: "tree_3", x: 1150, y: 370 },
  { art: "tree_2", x: 1010, y: 300 },
];

function farmland(exits, scenery) {
  return {
    name: "Farmland",
    kind: "farmland",
    exits,
    // A dirt path along the room, and branches up and down to the plots on either side
    paths: [
      { x: -1000, y: 470, w: 3280, h: 100 },
      { x: 580, y: 260, w: 120, h: 210 },
      { x: 580, y: 570, w: 120, h: 1000 },
    ],
    scenery: [{ art: "sign", x: 760, y: 465 }, ...scenery],
  };
}

function plot(number, exits) {
  // The gate faces the way back out to the Farmland
  const gate = exits.down ? "front-left" : exits.up ? "back-right" : "back-left";
  return {
    name: `Plot ${number}`,
    kind: "plot",
    plot: number,
    exits,
    fence: { gate },
    walk: { left: 50, right: 1230, top: 330, bottom: 700 },
    // He stops clear of the fence and near the field: below its front corner coming up from the Farmland, and by the
    // back gate coming down or in from the side
    stops: { down: { x: 640, y: 700 }, up: { x: 860, y: 360 }, left: { x: 400, y: 400 } },
    scenery: [
      { art: "tree_2", x: 140, y: 360 },
      { art: "bush_2", x: 170, y: 650 },
      { art: "tree_1", x: 1150, y: 380 },
      { art: "bush_2", x: 1110, y: 660 },
    ],
  };
}

// An extra farmhouse room, bought at the farmhouse board. Its door shows once the farm owns it: room n is the farm's
// (n - 1)th extra room
function extraRoom(number, name, exits) {
  return {
    name,
    kind: "room",
    number,
    needs: number - 1,
    inside: true,
    exits,
    walk: INSIDE_WALK,
    floor: INSIDE_FLOOR,
    scenery: [],
  };
}

const ROOM_LIST = {
  farmhouse: {
    name: "Farmhouse",
    kind: "farmhouse",
    inside: true,
    exits: { right: "yard", left: "room2" },
    walk: INSIDE_WALK,
    // Coming in from the Yard he stops by the board, so an upright phone shows the board and the wardrobe beside it
    stops: { right: { x: 800, y: 590 } },
    scenery: [],
  },
  room2: extraRoom(2, "Second room", { right: "farmhouse", left: "room3" }),
  room3: extraRoom(3, "Third room", { right: "room2" }),
  yard: {
    name: "Yard",
    kind: "yard",
    exits: { left: "farmhouse", up: "pond", down: "market", right: "farmland1" },
    floor: YARD_FLOOR,
    // From the farmhouse's porch out to the Farmland, with branches up to the Pond and down to the Market
    paths: [
      { x: 300, y: 470, w: 1180, h: 100 },
      { x: 590, y: 240, w: 110, h: 230 },
      { x: 590, y: 570, w: 110, h: 1000 },
    ],
    scenery: [
      { art: "farmhouse", x: 200, y: 470 },
      { art: "tree_1", x: 450, y: 320 },
      { art: "bush_2", x: 820, y: 400 },
      { art: "tree_2", x: 1000, y: 300 },
      { art: "tree_3", x: 1190, y: 380 },
      { art: "sign", x: 750, y: 465 },
      { art: "bush_2", x: 330, y: 690 },
    ],
  },
  pond: {
    name: "Pond",
    kind: "pond",
    exits: { down: "yard" },
    paths: [{ x: 590, y: 560, w: 110, h: 1000 }],
    scenery: [
      { art: "pond", x: 640, y: 570, scale: 1.6 },
      { art: "tree_2", x: 200, y: 400 },
      { art: "tree_1", x: 1090, y: 330 },
      { art: "tree_3", x: 1210, y: 430 },
      { art: "bush_2", x: 330, y: 660 },
      { art: "bush_2", x: 990, y: 670 },
    ],
  },
  market: {
    name: "Market",
    kind: "market",
    exits: { up: "yard" },
    // A dirt yard in front of the stall and the bank counter's signpost, and the path down to it from the Yard
    paths: [
      { x: 590, y: 240, w: 110, h: 230 },
      { x: 280, y: 470, w: 720, h: 190 },
    ],
    scenery: [
      { art: "market", label: "stall", x: 420, y: 455, scale: 1.4 },
      { art: "sign", label: "bank", x: 880, y: 470 },
      ...TREES_LEFT,
      ...TREES_RIGHT,
    ],
  },
  farmland1: farmland({ left: "yard", up: "plot1", down: "plot2", right: "farmland2" }, [
    ...TREES_LEFT,
    { art: "tree_2", x: 1060, y: 390 },
    { art: "bush_2", x: 1150, y: 680 },
  ]),
  farmland2: farmland({ left: "farmland1", up: "plot3", down: "plot4", right: "farmland3" }, [
    { art: "tree_3", x: 160, y: 390 },
    { art: "bush_2", x: 340, y: 680 },
    ...TREES_RIGHT,
  ]),
  farmland3: farmland({ left: "farmland2", up: "plot5", down: "plot6", right: "plot7" }, [
    { art: "tree_2", x: 220, y: 380 },
    { art: "tree_1", x: 1120, y: 400 },
    { art: "bush_2", x: 1000, y: 690 },
  ]),
  plot1: plot(1, { down: "farmland1" }),
  plot2: plot(2, { up: "farmland1" }),
  plot3: plot(3, { down: "farmland2" }),
  plot4: plot(4, { up: "farmland2" }),
  plot5: plot(5, { down: "farmland3" }),
  plot6: plot(6, { up: "farmland3" }),
  plot7: plot(7, { left: "farmland3" }),
};

export const ROOMS = Object.fromEntries(
  Object.entries(ROOM_LIST).map(([id, room]) => [id, { id, walk: OUTSIDE_WALK, paths: [], ...room }]),
);

// Where the page opens
export const START_ROOM = "farmhouse";
