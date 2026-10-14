// Bloxorz's leaderboard screen. It is drawn from the end screen's art (its glow backdrop, DefineSprite_197 from frame 320)
// and the original's digit pictures (DefineSprite_162), with the instruction pages' Prev, Next and Back to Menu
// buttons. Names are set in the game's pixel font. The bot ranks everyone: the `leaderboard` action answers for
// stage 0 (every stage: stages cleared, then total moves) or for one stage (fewest moves).
import { TextField } from "./flash.js";
import { wireButton } from "./menu.js";
import { Container, Sprite } from "./vendor/pixi.min.mjs";

// The original's characters: the end screen's backdrop, a digit picture, and the instruction pages' buttons
const GLOW = 46;
const BACKDROP = 184;
const DIGIT = 162;
const BACK_BUTTON = 212;
const PREV_BUTTON = 224;
const NEXT_BUTTON = 214;
// A digit picture is 10 pixels wide and its middle sits 18 pixels above where it is put, so a row's digits are put 18
// below the row's top
const DIGIT_WIDTH = 10;
const DIGIT_DROP = 18;
// The menu's glow (placed at the stage's middle, like the menu's), shown from a bright part of its pulse
const GLOW_AT = [275, 150];
const GLOW_FRAME = 201;
// The buttons' lettering starts this far left of the place a button is put, and Next's ends this far left of it
const BUTTON_INK_LEFT = 60;
const NEXT_INK_RIGHT = 11;
const STAGES = 33;
const TOP = 10;

const FONT = '"Square721 BT_10pt_st", Verdana, Geneva, sans-serif';
const SIZE = 14;
const LETTERS = "#ffffff";
const MINE = "#ff9a3c";
const HOVER = 0xff6a5a;
const DIM = "#c9916a";
// A text field's own margin around its words (flash.js's GUTTER)
const MARGIN = 2;
const FIELD_HEIGHT = 18;

// Where things sit, in the original's stage pixels
const HEADING = { x: 275, y: 8, scale: 0.6 };
const TITLE_Y = 46;
const PREV_AT = 20;
const NEXT_RIGHT = 530;
const HEADERS_Y = 64;
const ROWS_Y = 80;
const ROW_PITCH = 15;
const YOU_Y = 232;
const BACK_AT = { x: 20, y: 280 };
// Columns: the rank's digits end at RANK_RIGHT, names start at NAME_LEFT, then the stages cleared and the moves end
// at their right edges
const RANK_RIGHT = 62;
const NAME_LEFT = 74;
const NAME_RIGHT = 330;
const CLEARED_RIGHT = 400;
const MOVES_RIGHT = 500;
const MESSAGE = { x: 75, width: 400, y: 120 };
const TITLE_WIDTH = 190;
// The picture of the heading, which the menu's Leaderboard row uses too
const HEADING_PICTURE = "menu-leaderboard.png";

const OFFLINE = "Open this in Discord to see the leaderboard.";
const NOBODY_ALL = "No one has cleared a stage yet.";
const NOBODY_ONE = "No one has cleared this stage yet.";
const LOADING = "Loading...";
const ELLIPSIS = "…";

const state = {
  heading: null,
  // What is drawn now: the screen's container, the title's field and the one that holds the rows
  box: null,
  title: null,
  rows: null,
  message: null,
  headers: null,
  // 0 is every stage, 1 to 33 one stage. `asked` counts requests, so a slow answer for a stage the player has already
  // left is dropped
  view: 0,
  asked: 0,
  measure: null,
};

// ---------- Words ----------

function field(text, left, y, width, align, color = LETTERS) {
  const words = new TextField({
    bounds: [0, 0, width, FIELD_HEIGHT],
    font: FONT,
    bold: false,
    size: SIZE,
    color,
    align,
    multiline: false,
    wrap: false,
    leading: 0,
    var: "",
    text: "",
  });
  words.text = text;
  words.position.set(left - MARGIN, y);
  return words;
}

function measureWidth(text) {
  if (!state.measure) {
    state.measure = document.createElement("canvas").getContext("2d");
  }
  state.measure.font = `${SIZE}px ${FONT}`;
  return state.measure.measureText(text).width;
}

// A name no wider than the room, cut by whole characters (a letter with its accents or an emoji is never split) with
// an ellipsis where it was cut
function fitName(name, room) {
  if (measureWidth(name) <= room) {
    return name;
  }
  const parts = [...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(name)].map((part) => part.segment);
  let kept = parts.length;
  while (kept > 0 && measureWidth(parts.slice(0, kept).join("") + ELLIPSIS) > room) {
    kept -= 1;
  }
  return parts.slice(0, kept).join("").trimEnd() + ELLIPSIS;
}

// ---------- Numbers ----------

// A whole number in the original's digit pictures, its last digit ending at `right`
function number(page, value, right, y, tint) {
  const holder = new Container();
  const digits = String(Math.max(0, Math.floor(value))).split("");
  digits.forEach((text, index) => {
    const clip = page.lib.make(DIGIT);
    clip.gotoAndStop(Number(text) + 1);
    clip.position.set(right - (digits.length - index) * DIGIT_WIDTH, y);
    if (tint) {
      clip.tint = tint;
    }
    holder.addChild(clip);
  });
  return holder;
}

// ---------- The rows ----------

function rowFor(page, row, y, mine, showCleared) {
  const holder = new Container();
  const tint = mine ? 0xff9a3c : 0;
  const color = mine ? MINE : LETTERS;
  holder.addChild(number(page, row.rank, RANK_RIGHT, y + DIGIT_DROP, tint));
  holder.addChild(field(fitName(row.name, NAME_RIGHT - NAME_LEFT - MARGIN * 2), NAME_LEFT, y, NAME_RIGHT - NAME_LEFT, "left", color));
  if (showCleared) {
    holder.addChild(number(page, row.cleared, CLEARED_RIGHT, y + DIGIT_DROP, tint));
  }
  holder.addChild(number(page, row.moves, MOVES_RIGHT, y + DIGIT_DROP, tint));
  return holder;
}

function drawRows(page, table) {
  state.rows?.destroy({ children: true });
  const rows = new Container();
  state.rows = rows;
  state.box.addChild(rows);
  const all = state.view === 0;
  const me = table.you?.id ?? null;
  table.top.slice(0, TOP).forEach((row, index) => {
    rows.addChild(rowFor(page, row, ROWS_Y + index * ROW_PITCH, row.id === me, all));
  });
  if (table.you && !table.top.some((row) => row.id === table.you.id)) {
    const you = { ...table.you, name: `You (${table.you.name})` };
    rows.addChild(rowFor(page, you, YOU_Y, true, all));
  }
}

// ---------- What shows ----------

function titleText() {
  return state.view === 0 ? "All stages" : `Stage ${state.view}`;
}

function setTitle() {
  state.title.text = titleText();
}

function setMessage(text) {
  state.message.text = text;
  state.message.visible = Boolean(text);
}

function setHeaders(show) {
  state.headers.visible = show;
  state.headers.cleared.visible = show && state.view === 0;
}

function showTable(page, table) {
  if (!table.top.length) {
    state.rows?.destroy({ children: true });
    state.rows = null;
    setHeaders(false);
    setMessage(state.view === 0 ? NOBODY_ALL : NOBODY_ONE);
    return;
  }
  setMessage("");
  setHeaders(true);
  drawRows(page, table);
}

// Asks the bot for the shown view's ranking
async function load(page) {
  state.asked += 1;
  const asked = state.asked;
  state.rows?.destroy({ children: true });
  state.rows = null;
  setHeaders(false);
  setTitle();
  if (page.offline || !page.hub) {
    setMessage(OFFLINE);
    return;
  }
  setMessage(LOADING);
  let table;
  try {
    table = await page.hub.api("leaderboard", { stage: state.view });
  } catch (e) {
    console.warn("Bloxorz: couldn't get the leaderboard", e);
    if (asked === state.asked && state.box) {
      setMessage(e.message);
    }
    return;
  }
  if (asked === state.asked && state.box) {
    showTable(page, table);
  }
}

// Prev and Next step through all stages and stages 1 to 33, round and round
function step(page, by) {
  state.view = (state.view + by + STAGES + 1) % (STAGES + 1);
  load(page);
}

// ---------- Building the screen ----------

async function loadHeading(page) {
  // Drawn at about half its size, so it gets mipmaps
  state.heading ??= await page.picture(HEADING_PICTURE, true);
}

function placeButton(page, id, x, y, release) {
  const button = page.lib.make(id);
  button.position.set(x, y);
  // The buttons' pictures have black backgrounds, which would show as boxes over the glow, so each look is drawn with
  // the screen blend, which leaves black out. The over look's color filter would draw its box anyway, so it is the up
  // look with the hover red the menu's own rows take
  const show = button.show.bind(button);
  button.show = (look) => {
    show(look === "o" ? "u" : look);
    for (const part of button.children) {
      part.blendMode = "screen";
      part.tint = look === "o" ? HOVER : 0xffffff;
    }
  };
  button.show("u");
  wireButton(page, button, release);
  state.box.addChild(button);
  return button;
}

function addHeading() {
  const picture = new Sprite(state.heading);
  picture.scale.set(HEADING.scale);
  picture.position.set(HEADING.x - picture.width / 2, HEADING.y);
  state.box.addChild(picture);
}

function addHeaders() {
  const holder = new Container();
  holder.addChild(field("Name", NAME_LEFT, HEADERS_Y, NAME_RIGHT - NAME_LEFT, "left", DIM));
  holder.cleared = field("Stages", CLEARED_RIGHT - 80, HEADERS_Y, 80, "right", DIM);
  holder.addChild(holder.cleared);
  holder.addChild(field("Moves", MOVES_RIGHT - 80, HEADERS_Y, 80, "right", DIM));
  state.headers = holder;
  state.box.addChild(holder);
}

function enterLeaderboard(page) {
  state.view = 0;
  state.box = new Container();
  page.root.addChild(state.box);
  const glow = page.lib.make(GLOW, GLOW_FRAME);
  glow.position.set(...GLOW_AT);
  // The screens' own clips step with the ticker, which only steps the root's children
  state.box.advance = () => glow.advance();
  state.box.addChild(glow, page.lib.make(BACKDROP));
  addHeading();
  state.title = field("", (550 - TITLE_WIDTH) / 2, TITLE_Y - FIELD_HEIGHT / 2, TITLE_WIDTH, "center");
  state.box.addChild(state.title);
  addHeaders();
  state.message = field("", MESSAGE.x, MESSAGE.y, MESSAGE.width, "center", DIM);
  state.box.addChild(state.message);
  placeButton(page, PREV_BUTTON, PREV_AT + BUTTON_INK_LEFT, TITLE_Y, () => step(page, -1));
  placeButton(page, NEXT_BUTTON, NEXT_RIGHT + NEXT_INK_RIGHT, TITLE_Y, () => step(page, 1));
  placeButton(page, BACK_BUTTON, BACK_AT.x + BUTTON_INK_LEFT, BACK_AT.y, () => {
    page.skiptomenu = true;
    page.go("menu");
  });
  load(page);
}

function leaveLeaderboard() {
  // A slow answer that arrives after this is dropped
  state.asked += 1;
  state.box?.destroy({ children: true });
  state.box = null;
  state.title = null;
  state.rows = null;
  state.message = null;
  state.headers = null;
}

// ---------- Setup ----------

// The leaderboard screen, which game.js shows. The menu's Leaderboard row goes to it
export function setupLeaderboard() {
  return {
    screens: {
      leaderboard: {
        art: [GLOW, BACKDROP, DIGIT, BACK_BUTTON, PREV_BUTTON, NEXT_BUTTON],
        load: loadHeading,
        enter: enterLeaderboard,
        leave: leaveLeaderboard,
      },
    },
  };
}
