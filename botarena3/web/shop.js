// The original's shop (root frame 4 and its frame script): the parts for sale, the inventory and the player's robots
// in three scrolling lists, the info monitor that describes whatever was picked, the team color picker, and the
// buttons that buy, sell, mount and change robots. The page decides nothing: each button sends its request, and the
// lists, cash and team weight are drawn again from the career the bot sends back. Buttons grey out the way the
// original's do, only as a picture of what the bot will allow.
import { FPS } from "./flash.js";
import { Container, Rectangle, Sprite } from "./vendor/pixi.min.mjs";

// The original's characters the shop builds or reaches for by id
const INFO_SCREEN = 475;
const COLOR_PICKER = 524;
const ROW_PICTURE = 520;
// Root frame 4 names two clips botnamebox: the robot name box, which Flash finds first by that name, and the team
// color picker. The page tells them apart by depth
const NAME_BOX_DEPTH = 83;
const PICKER_DEPTH = 164;
const LISTS = ["shop", "inventory", "mybots"];
// A list row is 40 pixels tall and pictured 180 wide; a list shows 220 pixels of rows, and its scroller runs from 15
// to 205 down the list's side, easing a fifth of the way to its place each frame
const ROW_HEIGHT = 40;
const ROW_WIDTH = 180;
const LIST_SHOWS = 220;
const SCROLL_X = 190;
const SCROLL_TOP = 15;
const SCROLL_BOTTOM = 205;
const SCROLL_RANGE = 190;
const SCROLL_EASE = 5;
// A list row's white highlight: picked, or under the pointer. A row lighter than PICKED_FROM is the picked one
const PICKED = 0.5;
const HOVERED = 0.2;
const PICKED_FROM = 0.4;
// The original's greyed buttons and inactive name box: half see-through
const GREYED = 0.5;
// The bars under a robot's name share 120 pixels out by its chassis's whole load
const BAR_LENGTH = 120;
const BARS = ["bar_chas", "bar_plat", "bar_weap", "bar_heal", "bar_none"];
const MAX_ROBOTS = 5;
const TEAM_COLORS = 8;
const PICKER_WIDTH = 125;
// The original's name box takes capitals, numbers and spaces, 17 at most
const NAME_LONGEST = 17;
// The original's words
const CANT_FIGHT_BECAUSE = "YOU CANNOT ENGAGE IN BATTLE AT THE MOMENT BECAUSE:";
const SAVED = "CAREER SAVED!";
const ROBOT_SUBTITLE = "ROBOT SUBTITLE";
const NAME_LABEL = "TITLE";
const WORDS = {
  dismounttopbutton: "DISMOUNT ITEM",
  sellbotbutton: "SELL BOT",
  enabledisablebutton: "ENABLE/DISABLE BOT",
  buyitembutton: "PURCHASE ITEM",
  mountitembutton: "MOUNT ITEM",
  sellitembutton: "SELL ITEM",
  mountviewbutton: "COMPONENTS",
  platingviewbutton: "PLATING",
  chassisviewbutton: "CHASSIS",
  startbattlebutton: "START",
  exitbutton: "EXIT",
  savebutton: "SAVE",
};
// The bottom buttons' pictures (frames of sprite 487)
const LOOKS = { savebutton: 2, exitbutton: 1, startbattlebutton: 3 };
// The shop's tabs and what each lists
const TABS = { mountviewbutton: "weapon", platingviewbutton: "plating", chassisviewbutton: "chassis" };
// The original's list colors (frames of sprite 499): guns red, repair tools purple, plating blue, chassis green, and
// robots orange when enabled, grey when not
const TINTS = { weapon: "red", tool: "purple", plating: "blue", chassis: "green" };
// The sound the original plays when each request is carried out
const DONE_SOUNDS = {
  buy: "cash",
  sell: "cash",
  sellRobot: "cash",
  mount: "mount",
  dismount: "dismount",
  color: "cons",
};

// The shop while it shows, or null
let state = null;

function $(id) {
  return document.getElementById(id);
}

function effect(name) {
  state.page.sound.effect(name, "misc");
}

// Flash writes numbers with 15 significant digits, so 6.27 x 60 shows as 376.2
function flashNumber(value) {
  return String(Number(value.toPrecision(15)));
}

function partNamed(name) {
  return state.parts.get(name);
}

// Every part the bot's data lists, by name, with which of the three it is
function indexParts(data) {
  const parts = new Map();
  const groups = { weapon: data?.weapons, plating: data?.platings, chassis: data?.chassis };
  for (const [slot, rows] of Object.entries(groups)) {
    for (const part of rows ?? []) {
      parts.set(part.name, { ...part, slot });
    }
  }
  return parts;
}

// ---------- Showing and leaving ----------

function enter(page) {
  const root = page.root;
  page.fader.gotoAndPlay("fadein");
  page.sound.fadeIn(2);
  page.sound.music("shop");
  state = {
    page,
    root,
    parts: indexParts(page.data),
    mode: "chassis",
    lists: {},
    buttons: {},
    screen: root.child("infomon").child("screen"),
    nameBox: root.at(NAME_BOX_DEPTH),
    titleField: root.child("bottitlefield"),
    picker: root.at(PICKER_DEPTH),
    nameActive: false,
    namePlace: null,
    // The robot whose name is being typed, the name last sent for a robot until the bot's career shows it, and the
    // robot last enabled or disabled
    editing: null,
    sentName: null,
    toggled: null,
    // The requests sent and not yet answered, oldest first
    asked: [],
    color: page.career?.color ?? 1,
    // The screen size the row pictures were drawn for
    pictureSize: pictureSize(page),
    listening: new AbortController(),
  };
  delete document.body.dataset.monitor;
  setUpButtons(root);
  setUpTabs(root);
  setUpNameBox(root);
  for (const name of LISTS) {
    const clip = root.child(name);
    state.lists[name] = { name, clip, hold: clip.child("itemhold"), scroller: clip.child("scroller"), items: [] };
    Object.assign(state.lists[name], { pictures: [], rows: [], details: [], key: null, selected: null, scrollpos: 0 });
  }
  page.flashMonitor(state.screen);
  update();
}

function leave() {
  if (!state) {
    return;
  }
  // A name still being typed goes to the bot
  $("name-input").blur();
  showNameField(false);
  state.listening.abort();
  for (const list of Object.values(state.lists)) {
    clearRows(list);
  }
  delete document.body.dataset.monitor;
  state = null;
}

// When the window changes size (a phone's keyboard opening, a window made full screen) the name field follows the
// name box, and the row pictures are drawn again at the new size
function step() {
  if (!state) {
    return;
  }
  if (state.nameActive) {
    placeName();
  }
  const size = pictureSize(state.page);
  if (size !== state.pictureSize) {
    state.pictureSize = size;
    redrawPictures();
  }
}

function receive(page, data) {
  if (!state) {
    return;
  }
  if ("data" in data) {
    state.parts = indexParts(page.data);
    // A new connection: what the old one asked is never answered
    state.asked = [];
  }
  if (data.done || data.refused) {
    answered(data);
  }
  if ("career" in data) {
    update();
    const sent = state.sentName;
    if (sent && page.career?.robots[sent.index]?.name === sent.name) {
      state.sentName = null;
    }
  }
  if (data.done) {
    done(data.done, data.said);
  }
  if (data.refused) {
    changeScreen("error");
    state.screen.set("txt_displaytext", data.refused);
    effect("cons");
  }
}

// The career the bot sent: cash, team weight and color, and each list drawn again when what it shows has changed
function update() {
  const view = state.page.career;
  state.root.set("cash", view?.cash ?? 0);
  state.root.set("teamweight", view?.weight ?? 0);
  showList(state.lists.shop, shopRows());
  showList(state.lists.inventory, inventoryRows());
  showList(state.lists.mybots, robotRows());
  if ((view?.color ?? 1) !== state.color) {
    state.color = view?.color ?? 1;
    showColor(state.picker, state.color);
  }
}

// What the bot carried out: its words on the monitor's prompt, and the original's sound for it
function done(kind, said) {
  if (said) {
    changeScreen("prompt");
    state.screen.set("txt_displaytext", said);
  }
  // The original checks PURCHASE ITEM again after a buy, for the cash that is left
  if (kind === "buy" && picked("shop")) {
    shopPicked();
  }
  if (kind === "toggle") {
    effect(state.page.career?.robots[state.toggled]?.enabled ? "pup" : "pdown");
  } else if (DONE_SOUNDS[kind]) {
    effect(DONE_SOUNDS[kind]);
  }
}

// ---------- Buttons ----------

function setUpButtons(root) {
  for (const [name, words] of Object.entries(WORDS)) {
    root.child(name).set("displaytext", words);
  }
  for (const [name, frame] of Object.entries(LOOKS)) {
    root.child(name).gotoAndStop(frame);
  }
  const actions = {
    buyitembutton: buy,
    sellitembutton: () => send({ sell: state.lists.inventory.selected }),
    mountitembutton: () => send({ mount: [state.lists.mybots.selected, state.lists.inventory.selected] }),
    dismounttopbutton: () => send({ dismount: state.lists.mybots.selected }),
    sellbotbutton: () => send({ sellRobot: state.lists.mybots.selected }),
    enabledisablebutton: toggle,
    startbattlebutton: start,
    savebutton: save,
    exitbutton: exit,
  };
  for (const [name, action] of Object.entries(actions)) {
    const clip = root.child(name);
    state.buttons[name] = { clip, on: false };
    clip.setHandler("onPress", () => state?.buttons[name].on && action());
    // The original starts with every button greyed but START, SAVE and EXIT
    enable(name, ["startbattlebutton", "savebutton", "exitbutton"].includes(name));
  }
}

// The original's enablebutton and voidbutton: a greyed button has no hand cursor and does nothing
function enable(name, on) {
  const button = state.buttons[name];
  button.on = on;
  button.clip.alpha = on ? 1 : GREYED;
  button.clip.useHandCursor = on;
}

function picked(name) {
  const list = state.lists[name];
  return list.selected === null ? null : list.details[list.selected];
}

// The original's checkmountable, the same rule as the bot's: plating goes on a bare chassis, a weapon on plating
// with no weapon yet, and either only within what the chassis can still carry
function mountable(robot, part) {
  if (part.weight > robot.max - robot.load) {
    return false;
  }
  return part.slot === "plating" ? !robot.plating : Boolean(robot.plating) && !robot.weapon;
}

// Buttons change only where the original's do: when a row is picked (its itemwasclicked handlers), when a list
// lets its pick go (itemsunselected), and after a buy. A career that changes otherwise leaves them as they are, and
// the bot refuses what no longer works

// shop.itemwasclicked: PURCHASE ITEM works when the part is affordable, and a chassis only below 5 robots
function shopPicked() {
  const view = state.page.career;
  const part = picked("shop");
  const full = (view?.robots.length ?? 0) >= MAX_ROBOTS && state.mode === "chassis";
  enable("buyitembutton", !(part.cost > (view?.cash ?? 0) || full));
}

// checkmountable
function checkMountable() {
  const item = picked("inventory");
  const robot = picked("mybots");
  enable("mountitembutton", Boolean(item && robot && mountable(robot, item)));
}

// inventory.itemwasclicked
function inventoryPicked() {
  checkMountable();
  enable("sellitembutton", true);
}

// mybots.itemwasclicked: the name box takes typing, and the robot's buttons work
function robotPicked(robot) {
  state.root.set("setbottitle", robot.name);
  activateName(true);
  checkMountable();
  enable("sellbotbutton", true);
  enable("enabledisablebutton", true);
  enable("dismounttopbutton", Boolean(robot.weapon || robot.plating));
}

// The buttons each list's itemsunselected greys
const UNPICKED = {
  shop: ["buyitembutton"],
  inventory: ["mountitembutton", "sellitembutton"],
  mybots: ["mountitembutton", "sellbotbutton", "dismounttopbutton", "enabledisablebutton"],
};

// The bot answers each of the shop's requests, in the order they were sent, with done or refused; the shop keeps
// what it asked until then. True when the request went
function send(message) {
  const sent = state.page.send(message);
  if (sent) {
    state.asked.push(message);
  }
  return sent;
}

// A refused rename never comes, so the list shows the bot's name again. Only the rename the list is showing counts:
// a refusal of anything else, or of an older name, leaves it
function answered(data) {
  const asked = state.asked.shift();
  const sent = state.sentName;
  if (data.refused && asked?.rename && sent?.index === asked.rename[0] && sent.name === asked.rename[1]) {
    state.sentName = null;
  }
}

function buy() {
  send({ buy: picked("shop").name });
}

function toggle() {
  state.toggled = state.lists.mybots.selected;
  send({ toggle: state.toggled });
}

function blink(name) {
  state.root.child(name).child("blinker").gotoAndPlay(2);
}

// START: the original's error panel when the team can't fight, the arena list when it can
function start() {
  blink("startbattlebutton");
  const problems = state.page.career?.problems ?? [];
  if (problems.length === 0) {
    showNameField(false);
    state.page.go("levelselect", { fadeSound: 3 });
    return;
  }
  effect("cons");
  changeScreen("error");
  state.screen.set("txt_displaytext", cantFight(problems));
}

// The error panel's words for a team that can't go: the original's heading, then each problem on its own line. The
// PvP screen shows the same
export function cantFight(problems) {
  return `${CANT_FIGHT_BECAUSE}\r${problems.map((problem) => `${problem}\r`).join("")}`;
}

// The bot saves every change, so SAVE only says so
function save() {
  changeScreen("prompt");
  state.screen.set("txt_displaytext", SAVED);
  effect("cons");
  blink("savebutton");
}

// The original asked whether to save first; the bot already has, so EXIT goes straight to the menu
function exit() {
  blink("exitbutton");
  showNameField(false);
  state.page.go("menu", { fadeSound: 3 });
}

// The shop's tabs: COMPONENTS (weapons), PLATING and CHASSIS, with CHASSIS showing first
function setUpTabs(root) {
  for (const [name, mode] of Object.entries(TABS)) {
    const tab = root.child(name);
    tab.setHandler("onPress", () => {
      if (!state || tab.frame !== 1) {
        return;
      }
      for (const other of Object.keys(TABS)) {
        root.child(other).gotoAndStop(other === name ? 2 : 1);
      }
      state.mode = mode;
      showList(state.lists.shop, shopRows());
      effect("dit");
    });
  }
  root.child("chassisviewbutton").gotoAndStop(2);
}

// ---------- The lists ----------

function tintOf(part) {
  if (part.slot === "weapon") {
    return part.kind.startsWith("TOOL") ? TINTS.tool : TINTS.weapon;
  }
  return TINTS[part.slot];
}

// The original's generateshop: each row's title, subtitle, details line and color, and what a press on it shows
function shopRows() {
  const data = state.page.data;
  const level = state.page.career?.level ?? 0;
  const source = { weapon: data?.weapons, plating: data?.platings, chassis: data?.chassis }[state.mode] ?? [];
  const parts = source.filter((part) => part.level <= level).map((part) => partNamed(part.name));
  const rows = parts.map((part) => {
    const cost = `COST: ${part.cost}`;
    return [part.name, part.kind, part.slot === "chassis" ? cost : `WEIGHT: ${part.weight}, ${cost}`, tintOf(part)];
  });
  return { rows, details: parts };
}

function inventoryRows() {
  const parts = (state.page.career?.inventory ?? []).map(partNamed);
  const rows = parts.map((part) => [
    part.name,
    part.kind,
    `WEIGHT: ${part.weight}, RESALE: ${part.cost / 2}`,
    tintOf(part),
  ]);
  return { rows, details: parts };
}

// A robot whose name is being typed keeps the typed name, and one whose new name was sent keeps that name until the
// bot's career shows it, so an answer to an earlier name doesn't redraw the list and let the robot go
function robotRows() {
  const typedName = state.root.get("setbottitle");
  const sent = state.sentName;
  const nameOf = (robot, index) => {
    if (index === state.editing) {
      return typedName;
    }
    return index === sent?.index ? sent.name : robot.name;
  };
  const robots = (state.page.career?.robots ?? []).map((robot, index) => ({
    ...robot,
    name: nameOf(robot, index),
    index,
  }));
  const rows = robots.map((robot) => [
    robot.name,
    ROBOT_SUBTITLE,
    `LOAD: ${robot.load} MAX: ${robot.max}`,
    robot.enabled ? "orange" : "grey",
  ]);
  return { rows, details: robots };
}

// What a list shows, team color included since plating shows it
function keyOf(rows, details) {
  return JSON.stringify([rows, details, state.page.career?.color]);
}

// A list is drawn again only when what it shows changed, so a change elsewhere keeps its pick, as the original
// redraws only the lists an action touched (and all three for a new team color)
function showList(list, { rows, details }) {
  const key = keyOf(rows, details);
  if (key !== list.key) {
    populate(list, rows, details);
    list.key = key;
  }
}

function clearRows(list) {
  // A row's picture loses its texture as the row goes, so the textures are let go first
  for (const picture of list.pictures) {
    picture.texture.destroy(true);
  }
  for (const item of list.items) {
    item.destroy({ children: true });
  }
  list.items = [];
  list.pictures = [];
}

// The original's populatelist: the old rows go, a row for each entry comes, and the scroller is set up for them
function populate(list, rows, details) {
  unpick(list);
  clearRows(list);
  list.rows = rows;
  list.details = details;
  rows.forEach((row, index) => list.items.push(addRow(list, row, details[index], index)));
  if (rows.length) {
    list.scrollpos = 0;
    list.scroller.y = SCROLL_TOP;
  }
  setUpScroller(list, rows.length);
}

function addRow(list, row, detail, index) {
  const item = list.hold.attach(state.page.lib.makeExported("listitem"), `listitem${index}`);
  item.vars.ypos = index * ROW_HEIGHT;
  item.set("itemtitle", row[0]);
  item.set("itemsubtitle", row[1]);
  item.set("itemdetails", row[2]);
  // Robots' rows show their name in a field of their own, so a new name shows while it is typed
  item.gotoAndStop(list.name === "mybots" ? 2 : 1);
  const picture = drawRow(row, detail, list.name === "mybots");
  list.pictures.push(picture);
  item.child("bmphold").addChild(picture);
  item.setHandler("onPress", () => state && pressRow(list, index));
  item.onEnterFrame = () => {
    item.y = item.vars.ypos + list.scrollpos;
    const white = item.child("white");
    if (white.alpha < PICKED_FROM) {
      const pointer = state.page.lib.pointer;
      white.alpha = item.child("hitarea").getBounds().containsPoint(pointer.x, pointer.y) ? HOVERED : 0;
    }
  };
  item.onEnterFrame();
  return item;
}

// A press on a row picks it, or, on the picked row, lets it go
function pressRow(list, index) {
  const white = list.items[index].child("white");
  const wasPicked = white.alpha > PICKED_FROM;
  for (const item of list.items) {
    item.child("white").alpha = 0;
  }
  if (wasPicked) {
    white.alpha = HOVERED;
    unpick(list);
    return;
  }
  white.alpha = PICKED;
  list.selected = index;
  const detail = list.details[index];
  if (list.name === "mybots") {
    robotPicked(detail);
    giveBotInfo(detail);
  } else {
    if (list.name === "shop") {
      shopPicked();
    } else {
      inventoryPicked();
    }
    giveItemInfo(detail, list.name === "shop");
  }
  effect("cons");
}

// The original's itemsunselected
function unpick(list) {
  list.selected = null;
  for (const name of UNPICKED[list.name]) {
    enable(name, false);
  }
  if (list.name === "mybots" && state.nameActive) {
    dropName();
    state.root.set("setbottitle", "");
    activateName(false);
  }
}

function setUpScroller(list, count) {
  const scroller = list.scroller;
  const scrolls = count * ROW_HEIGHT > LIST_SHOWS;
  scroller.alpha = scrolls ? 1 : GREYED;
  scroller.useHandCursor = scrolls;
  if (!scrolls) {
    scroller.setHandler("onPress", () => {});
    scroller.setHandler("onReleaseOutside", () => {});
    return;
  }
  scroller.vars.maxiscroll = count * ROW_HEIGHT - LIST_SHOWS;
  scroller.setHandler("onPress", () => {
    scroller.startDrag(false, [SCROLL_X, SCROLL_TOP, SCROLL_X, SCROLL_BOTTOM]);
    scroller.onEnterFrame = () => {
      const wanted = (-(scroller.y - SCROLL_TOP) * scroller.vars.maxiscroll) / SCROLL_RANGE;
      list.scrollpos += (wanted - list.scrollpos) / SCROLL_EASE;
    };
  });
  scroller.setHandler("onRelease", () => scroller.stopDrag());
  scroller.setHandler("onReleaseOutside", () => scroller.stopDrag());
}

// ---------- Row pictures ----------

// A row's picture, drawn once from the original's row clip as the original drew it into a 180 by 40 bitmap. It is
// drawn at the screen's size so it stays sharp
function drawRow(row, detail, robot) {
  const { lib, app } = state.page;
  const render = lib.make(ROW_PICTURE);
  render.set("itemtitle", row[0]);
  render.set("itemsubtitle", row[1]);
  render.set("itemdetails", row[2]);
  render.child("tint").gotoAndStop(row[3]);
  if (robot) {
    render.gotoAndStop(2);
    drawBars(render.child("wg"), detail);
    drawRobot(render.child("disp"), detail);
  } else {
    drawPart(render.child("disp"), detail);
  }
  const scale = lib.filterScale;
  const holder = new Container();
  render.scale.set(scale);
  holder.addChild(render);
  const frame = new Rectangle(0, 0, ROW_WIDTH * scale, ROW_HEIGHT * scale);
  const texture = app.renderer.generateTexture({ target: holder, frame, resolution: app.renderer.resolution });
  holder.destroy({ children: true });
  const picture = new Sprite(texture);
  picture.label = "picture";
  picture.scale.set(1 / scale);
  picture.roundPixels = true;
  picture.eventMode = "none";
  return picture;
}

// The screen pixels per stage pixel the row pictures are drawn at
function pictureSize(page) {
  return page.lib.filterScale * page.app.renderer.resolution;
}

function redrawPictures() {
  for (const list of Object.values(state.lists)) {
    list.pictures.forEach((old, index) => {
      const picture = drawRow(list.rows[index], list.details[index], list.name === "mybots");
      old.parent.addChild(picture);
      const texture = old.texture;
      old.destroy();
      texture.destroy(true);
      list.pictures[index] = picture;
    });
  }
}

// The robot's load as bars: chassis, plating, weapon (or repair tool) and what is still free, each with its weight
function drawBars(wg, robot) {
  const bars = Object.fromEntries(BARS.map((name) => [name, wg.child(name)]));
  for (const bar of Object.values(bars)) {
    bar.child("am").scale.x = 0;
  }
  const chassis = partNamed(robot.chassis).weight;
  let carried = chassis;
  sizeBar(bars.bar_chas, chassis, robot.max);
  bars.bar_plat.visible = Boolean(robot.plating);
  if (robot.plating) {
    const plating = partNamed(robot.plating).weight;
    carried += plating;
    sizeBar(bars.bar_plat, plating, robot.max);
    bars.bar_plat.x = bars.bar_chas.width;
  }
  const weapon = robot.weapon ? partNamed(robot.weapon) : null;
  bars.bar_weap.visible = Boolean(weapon) && weapon.damage > 0;
  bars.bar_heal.visible = Boolean(weapon) && weapon.damage <= 0;
  if (weapon) {
    carried += weapon.weight;
    const bar = weapon.damage > 0 ? bars.bar_weap : bars.bar_heal;
    sizeBar(bar, weapon.weight, robot.max);
    bar.x = bars.bar_plat.width + bars.bar_chas.width;
  }
  bars.bar_none.visible = carried < robot.max;
  if (carried < robot.max) {
    sizeBar(bars.bar_none, robot.max - carried, robot.max);
  }
  // Each bar's number keeps its own size however far its bar was stretched
  for (const bar of Object.values(bars)) {
    bar.child("am").scale.x = bar.scale.x ? 1 / bar.scale.x : 1;
  }
}

function sizeBar(bar, amount, max) {
  bar.width = (BAR_LENGTH / max) * amount;
  bar.child("am").set("amount", amount);
}

// The original's team color on a robot top: its glaze and each of its lights
function paintTeam(top) {
  const color = state.page.career?.color ?? 1;
  top.child("tcolor")?.gotoAndStop(color);
  for (let n = 1; top.child(`teamlight${n}`)?.visible; n += 1) {
    top.child(`teamlight${n}`).child("tcolor")?.gotoAndStop(color);
  }
}

// A robot row's picture (sprite 519): its top with its gun when it has plating, else its bare chassis
function drawRobot(disp, robot) {
  if (!robot.plating) {
    disp.gotoAndStop("chassis");
    disp.child("item").gotoAndStop(partNamed(robot.chassis).graphic);
    return;
  }
  disp.gotoAndStop("top");
  const top = disp.child("item");
  top.gotoAndStop(partNamed(robot.plating).graphic);
  paintTeam(top);
  const spinner = top.child("spinnr");
  if (spinner) {
    spinner.angle = 0;
  }
  const gun = top.child("gun");
  gun.visible = Boolean(robot.weapon);
  if (robot.weapon) {
    gun.angle = 90;
    gun.gotoAndStop(partNamed(robot.weapon).gun);
  }
}

// A part row's picture (sprite 505)
function drawPart(disp, part) {
  disp.gotoAndStop(part.slot);
  const item = disp.child("item");
  if (part.slot === "weapon") {
    item.gotoAndStop(part.gun);
    return;
  }
  item.gotoAndStop(part.graphic);
  if (part.slot === "plating") {
    paintTeam(item);
    const spinner = item.child("spinnr");
    if (spinner) {
      spinner.angle = 0;
    }
    item.child("gun").visible = false;
  }
}

// ---------- The info monitor (sprite 477, its screen 475) ----------

// The original's changeinfoscreen: the screen flashes and turns to a page, and tests can see which
function changeScreen(label) {
  const screen = state.screen;
  screen.onLeavePage?.();
  screen.gotoAndStop(1);
  screen.gotoAndStop(label);
  state.page.flashMonitor(screen);
  document.body.dataset.monitor = label;
}

// Sprite 475's page scripts: each picture turns a degree a frame from 45 (the robot's gun the other way, faster),
// and stops when the page is left. A plating picture shows no gun
function monitorPage(page, screen, frame) {
  const spin = (holder, name, speed) => {
    const graphic = screen.child(holder).child(name);
    graphic.angle = 45;
    graphic.onEnterFrame = () => {
      graphic.angle += speed;
    };
    if (name === "platinggraphic") {
      graphic.child("gun")?.removeMovieClip();
    }
    return graphic;
  };
  const pages = {
    2: () => [spin("holder", "gungraphic", 1)],
    3: () => [spin("holder", "platinggraphic", 1)],
    4: () => [spin("holder", "chassisgraphic", 1)],
    5: () => [
      spin("holder3", "gungraphic", -1.5),
      spin("holder2", "platinggraphic", 1),
      spin("holder1", "chassisgraphic", 1),
    ],
  };
  const spinning = pages[frame]?.() ?? [];
  screen.onLeavePage = () => {
    for (const graphic of spinning) {
      graphic.onEnterFrame = null;
    }
  };
}

function setWords(words) {
  for (const [name, value] of Object.entries(words)) {
    state.screen.set(name, value);
  }
}

// The original's damage per minute: refire rate x 33 / 1000 x 60 x damage, positive for repair tools too
function perMinute(weapon) {
  const rate = weapon.damage > 0 ? weapon.refire : -weapon.refire;
  return flashNumber(((rate * FPS) / 1000) * 60 * weapon.damage);
}

function weaponWords(weapon) {
  const uses = flashNumber(((weapon.refire * FPS) / 1000) * 60);
  if (weapon.damage > 0) {
    return {
      txt_damage: `CAUSES ${weapon.damage} DAMAGE PER SHOT`,
      txt_refirerate: `FIRES ${uses} SHOTS PER MINUTE`,
      txt_dps: `INFLICTS ${perMinute(weapon)} DAMAGE PER MINUTE`,
    };
  }
  return {
    txt_damage: `REPAIRS ${-weapon.damage} DAMAGE PER USE`,
    txt_refirerate: `ACTIVATES ${uses} TIMES PER MINUTE`,
    txt_dps: `REPAIRS ${perMinute(weapon)} DAMAGE PER MINUTE`,
  };
}

// The original's giveiteminfo: a part's page. Its price is the shop's, or half that for one you own
function giveItemInfo(part, fromShop) {
  const screen = state.screen;
  const cost = fromShop ? `COST: ${part.cost}` : `RESALE VALUE: ${part.cost / 2}`;
  const words = { txt_name: part.name, txt_subname: part.kind, txt_cost: cost, txt_desc: part.description };
  if (part.slot === "weapon") {
    changeScreen("weapon_show");
    screen.child("holder").child("gungraphic").gotoAndStop(part.gun);
    const ranges = `FIRING DISTANCE: ${part.min_range}-${part.max_range}`;
    setWords({ ...words, txt_weight: `WEIGHT: ${part.weight}`, txt_ranges: ranges, ...weaponWords(part) });
  } else if (part.slot === "plating") {
    changeScreen("plating_show");
    const top = screen.child("holder").child("platinggraphic");
    top.gotoAndStop(part.graphic);
    paintTeam(top);
    const shielding = `PROVIDES ${part.shielding} POINTS OF SHIELDING`;
    setWords({ ...words, txt_weight: `WEIGHT: ${part.weight}`, txt_shielding: shielding });
  } else {
    changeScreen("chassis_show");
    screen.child("holder").child("chassisgraphic").gotoAndStop(part.graphic);
    const shielding = `PROVIDES ${part.shielding} POINTS OF SHIELDING`;
    const load = `MAX WEIGHT LOAD: ${part.max_load}`;
    setWords({ ...words, txt_weight: `SELF WEIGHT: ${part.weight}`, txt_maxweight: load, txt_shielding: shielding });
  }
  screen.child("infohold").visible = true;
}

// The small "i" beside each of a robot's parts opens that part's own page
function infoButton(name, part) {
  const button = state.screen.child(name);
  button.visible = Boolean(part);
  if (part) {
    button.setHandler("onPress", () => {
      giveItemInfo(part, false);
      effect("cons");
    });
  }
}

// The original's givebotinfo: a robot's page, with its parts, shielding, resale value and damage per minute
function giveBotInfo(robot) {
  const screen = state.screen;
  changeScreen("mybot_show");
  const chassis = partNamed(robot.chassis);
  const plating = robot.plating ? partNamed(robot.plating) : null;
  const weapon = robot.weapon ? partNamed(robot.weapon) : null;
  setWords({
    txt_name: robot.name,
    txt_subname: ROBOT_SUBTITLE,
    txt_weight: `WEIGHT: ${robot.load}`,
    txt_maxweight: `MAX WEIGHT LOAD: ${robot.max}`,
    txt_chassis: `CHASSIS: ${robot.chassis}`,
    txt_plating: `PLATING: ${plating ? plating.name : "NONE"}`,
    txt_status: `READY STATUS: ${robot.enabled ? "ENABLED" : "DISABLED"}`,
    txt_weapon: `WEAPON: ${weapon ? weapon.name : "NONE"}`,
    txt_dps: weapon ? weaponWords(weapon).txt_dps : "INFLICTS NO DAMAGE",
  });
  infoButton("info_chassis", chassis);
  infoButton("info_plating", plating);
  infoButton("info_weapon", weapon);
  // The bare chassis shows when there is no plating; otherwise the plated top does
  screen.child("holder1").child("chassisgraphic").gotoAndStop(chassis.graphic);
  screen.child("holder1").visible = !plating;
  screen.child("holder2").visible = Boolean(plating);
  if (plating) {
    const top = screen.child("holder2").child("platinggraphic");
    top.gotoAndStop(plating.graphic);
    paintTeam(top);
  }
  screen.child("holder3").visible = Boolean(weapon);
  if (weapon) {
    screen.child("holder3").child("gungraphic").gotoAndStop(weapon.gun);
  }
  const owned = [chassis, plating, weapon].filter(Boolean);
  const shielding = chassis.shielding + (plating?.shielding ?? 0);
  const resale = owned.reduce((sum, part) => sum + part.cost / 2, 0);
  setWords({ txt_shielding: `HAS ${shielding} POINTS OF SHIELDING`, txt_resale: `RESALE VALUE: ${resale}` });
}

// ---------- The robot name box ----------

// The original's name field (bottitlefield) takes typing while a robot is picked. The page lays its own field over
// it for that time, so phones bring up their keyboard. A name goes to the bot when the field loses focus or Enter is
// pressed
function setUpNameBox(root) {
  state.nameBox.set("displaytext", NAME_LABEL);
  root.set("setbottitle", "");
  activateName(false);
  const input = $("name-input");
  const signal = state.listening.signal;
  const typing = () => {
    state.editing = state.lists.mybots.selected;
  };
  input.addEventListener("focus", typing, { signal });
  input.addEventListener("input", typed, { signal });
  input.addEventListener("keydown", (e) => e.key === "Enter" && input.blur(), { signal });
  input.addEventListener("blur", sendName, { signal });
  // A press anywhere else ends the typing before the press does anything, so the name goes to the robot it was
  // typed for
  const elsewhere = (e) => {
    if (document.activeElement === input && e.target !== input) {
      input.blur();
    }
  };
  window.addEventListener("pointerdown", elsewhere, { signal, capture: true });
}

// The box is half see-through, and takes no typing, until a robot is picked
function activateName(on) {
  state.nameActive = on;
  state.nameBox.alpha = on ? 1 : GREYED;
  if (on) {
    $("name-input").value = state.root.get("setbottitle") ?? "";
  }
  showNameField(on);
}

function showNameField(on) {
  $("name-input").hidden = !on;
  state.titleField.visible = !on;
  if (on) {
    placeName();
  }
}

function placeName() {
  const input = $("name-input");
  const field = state.titleField;
  const [left, top, right, bottom] = field.def.bounds;
  const from = field.toGlobal({ x: left, y: top });
  const to = field.toGlobal({ x: right, y: bottom });
  const canvas = state.page.app.canvas.getBoundingClientRect();
  const scale = (to.y - from.y) / (bottom - top);
  const place = [canvas.left + from.x, canvas.top + from.y, to.x - from.x, to.y - from.y, scale].join();
  if (place === state.namePlace) {
    return;
  }
  state.namePlace = place;
  Object.assign(input.style, {
    left: `${canvas.left + from.x}px`,
    top: `${canvas.top + from.y}px`,
    width: `${to.x - from.x}px`,
    height: `${to.y - from.y}px`,
    fontSize: `${field.def.size * scale}px`,
    padding: `0 ${2 * scale}px`,
  });
}

// The original's name rules as the player types: capitals, numbers and spaces, 17 at most. The new name shows in
// the robot's row and on its monitor page straight away
function typed() {
  const input = $("name-input");
  const kept = (text) => text.toUpperCase().replace(/[^A-Z0-9 ]/g, "");
  const name = kept(input.value).slice(0, NAME_LONGEST);
  if (input.value !== name) {
    // The cursor stays where it was among the letters that are kept
    const start = Math.min(kept(input.value.slice(0, input.selectionStart ?? 0)).length, name.length);
    const end = Math.min(kept(input.value.slice(0, input.selectionEnd ?? 0)).length, name.length);
    input.value = name;
    if (document.activeElement === input) {
      input.setSelectionRange(start, end);
    }
  }
  const list = state.lists.mybots;
  const index = state.editing ?? list.selected;
  state.root.set("setbottitle", name);
  list.items[index]?.set("itemtitle", name);
  // The bot's answer then matches what the list shows, so the list keeps its pick
  if (list.rows[index]) {
    list.rows[index][0] = name;
    list.details[index].name = name;
    list.key = keyOf(list.rows, list.details);
  }
  if (state.screen.frame === state.screen.frameOf("mybot_show")) {
    state.screen.set("txt_name", name);
  }
}

// Typing ended: the name goes to the bot when it changed
function sendName() {
  if (state.editing === null) {
    return;
  }
  // A change made without an input event (a script setting the field) still follows the name rules and shows
  typed();
  const index = state.editing;
  state.editing = null;
  const name = $("name-input").value;
  const robot = state.page.career?.robots[index];
  const known = index === state.sentName?.index ? state.sentName.name : robot?.name;
  if (robot && known !== name && send({ rename: [index, name] })) {
    state.sentName = { index, name };
  }
}

// The robot's row went away while its name was being typed: the typing is dropped
function dropName() {
  state.editing = null;
  $("name-input").blur();
}

// ---------- The team color picker (sprite 524) ----------

// Its frame script: eight balls in a row, the team's color showing, the others lighting up under the pointer
function setUpPicker(page, picker) {
  const colorNow = () => page.career?.color ?? 1;
  for (let id = 1; id <= TEAM_COLORS; id += 1) {
    const ball = picker.attach(page.lib.makeExported("tcolorball"), `tc${id}`);
    ball.width = PICKER_WIDTH / TEAM_COLORS;
    ball.x = (PICKER_WIDTH / TEAM_COLORS) * (id - 1);
    ball.child("tcolor").gotoAndStop(id);
    ball.setHandler("onRollOver", () => {
      if (id !== colorNow()) {
        ball.child("hider").visible = false;
      }
    });
    ball.setHandler("onRollOut", () => {
      if (id !== colorNow()) {
        ball.child("hider").visible = true;
      }
    });
    ball.setHandler("onPress", () => state && id !== colorNow() && send({ color: id }));
  }
  showColor(picker, colorNow());
}

function showColor(picker, color) {
  for (let id = 1; id <= TEAM_COLORS; id += 1) {
    const ball = picker.child(`tc${id}`);
    ball.child("shower").visible = id === color;
    ball.child("hider").visible = id !== color;
  }
}

export const shop = {
  enter,
  leave,
  receive,
  step,
  scripts: { [INFO_SCREEN]: monitorPage, [COLOR_PICKER]: setUpPicker },
};
