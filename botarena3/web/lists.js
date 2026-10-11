// The original's arena list (root frame 10), challenge list (root frame 11) and win screen (root frame 8). Each list is
// the original's panel of nodes that appear one after another, each wearing its arena's mark. A press on a node slides
// the panel over to the info holder: the arena's name, the original's details, its map turning on the spot, and PLAY.
// The page decides nothing: each arena's mark comes from the career the bot sends, and PLAY only asks the bot for the
// battle, which the bot starts or refuses.

// The original's characters the lists build or reach for by id
const ARENA_PANEL = 724;
const CHALLENGE_PANEL = 743;
const INFO_PANEL = 738;
// The node the original attaches for each arena or challenge (its "lnode" linkage), and the hit area inside it that
// takes presses
const NODE = 244;
const HIT_AREA = 220;
// The map preview's two turning layers: the arena's floor, and its walls cut out of the same picture
const MAP_FLOOR = 727;
const MAP_WALLS = 728;
// The panels ease a fifth of the way to their place each frame and snap there from 2 pixels away. The list shows at
// 0 with the info holder one stage width to its right; PLAY slides both one more width left, and leaving slides the
// list back out to the right, where it starts
const SLIDE_EASE = 5;
const SLIDE_SNAP = 2;
const STAGE_WIDTH = 640;
const LIST_AT = 0;
const INFO_AT = -640;
const PLAYING_AT = -1280;
const OUTSIDE = 640;
// The nodes stand 250 pixels in, every other one 15 further, and each waits 3 frames longer than the one before it
const NODE_X = 250;
const NODE_STAGGER = 15;
const NODE_WAIT = 3;
// The marks the original's node plays: too heavy and too poor at once shows as too heavy
const NODE_MARKS = { good: "good", locked: "locked", bad: "bad", both: "bad", poor: "poor" };
// A node's name and glow fade by a tenth each frame once the pointer leaves it
const HOVER_FADE = 10;
// PLAY fades the sound out faster than the other ways off a list
const PLAY_FADE = 6;
const LEAVE_FADE = 3;

// The two lists: where their nodes spread down the stage (spread / count x n + top), what they list, each entry's
// mark and details, the request PLAY sends, and where the panel's own button leads
const LISTS = {
  levelselect: {
    spread: 400,
    top: 55,
    entries: (page) => page.data?.arenas ?? [],
    status: (page, index) => page.career?.arenas?.[index],
    details: arenaDetails,
    request: (index) => ({ arena: index }),
    back: "SHOP",
    backTo: "shop",
  },
  challengeselect: {
    spread: 300,
    top: 100,
    entries: (page) => page.data?.challenges ?? [],
    // The original's challenges are fought at level 1 with no weight limit and no fee, so every one is open
    status: () => "good",
    details: (page, challenge) => challenge.description,
    request: (index) => ({ challenge: index }),
    back: "BACK",
    backTo: "menu",
  },
};

// The list while it shows, or null
let state = null;

// ---------- Showing and leaving ----------

function enter(page, name) {
  const list = LISTS[name];
  page.fader.gotoAndPlay("fadein");
  page.sound.fadeIn(2);
  page.sound.music("rave");
  state = {
    page,
    list,
    panel: page.root.child("bholder"),
    info: page.root.child("iholder"),
    entries: list.entries(page),
    // Where the panel is headed (the original's gotox)
    gotox: LIST_AT,
    nodes: [],
    // The entry the info holder shows, and whether PLAY has asked the bot for its battle and heard nothing back yet
    shown: null,
    asked: false,
  };
  state.panel.x = OUTSIDE;
  state.panel.onEnterFrame = slide;
  slide();
  state.entries.forEach((entry, index) => addNode(page, entry, index));
  setUpButtons(page, list);
}

function leave() {
  state = null;
}

// While PLAY waits: the bot's battle fades to it, and anything else (a refusal, a notice that a battle is already
// running, or the career sent again after a dropped connection) means no battle is coming, so the arena comes back
function receive(page, data) {
  if (!state?.asked) {
    return;
  }
  if (data.battle) {
    state.asked = false;
    page.go("battle", { fadeSound: PLAY_FADE });
    return;
  }
  if ("career" in data || data.notice) {
    state.asked = false;
    if (data.refused) {
      page.toast(data.refused);
    }
    showInfo(state.shown);
  }
}

// The original's bholder.onEnterFrame: the panel eases toward gotox, the info holder one stage width to its right
function slide() {
  if (!state) {
    return;
  }
  const { panel, info } = state;
  const gap = state.gotox - panel.x;
  panel.x = Math.abs(gap) > SLIDE_SNAP ? panel.x + gap / SLIDE_EASE : state.gotox;
  info.x = panel.x + STAGE_WIDTH;
}

// ---------- The nodes ----------

// One of the original's lnode clips: it waits its turn, then fades in and plays its arena's mark
function addNode(page, entry, index) {
  const { panel, list } = state;
  const node = panel.attach(page.lib.make(NODE), `levelnode${index}`);
  node.x = NODE_X + (index % 2 ? NODE_STAGGER : 0);
  node.y = (list.spread / state.entries.length) * index + list.top;
  node.stop();
  node.set("displayt", entry.name);
  let wait = NODE_WAIT * (index + 1);
  node.onEnterFrame = () => {
    hover(page, node);
    if (wait > 0) {
      wait -= 1;
      return;
    }
    const status = list.status(page, index);
    if (node.frame === 1 && status) {
      node.gotoAndPlay(2);
      node.child("node").gotoAndPlay(NODE_MARKS[status]);
    }
  };
  state.nodes.push(node);
}

// The node's name and glow show while the pointer is over its hit area, and fade once it leaves. The original tests
// the pointer every frame rather than waiting for roll overs
function hover(page, node) {
  const mark = node.child("node");
  const area = mark?.child("hitarea");
  const name = mark?.child("thename");
  const glow = mark?.child("glower");
  if (!area || !name || !glow) {
    return;
  }
  const { x, y } = page.lib.pointer;
  if (area.getBounds().containsPoint(x, y)) {
    name.alpha = 1;
    glow.alpha = 1;
  } else if (name.alpha > 0) {
    name.alpha = fade(name.alpha);
    glow.alpha = fade(glow.alpha);
  }
}

// Ten percent off each frame, so ten frames take a node from shown to gone. Flash keeps alpha in steps of 1/256; the
// page rounds to whole percents instead, which looks the same and lands exactly on 0
function fade(alpha) {
  return Math.max(0, Math.round(alpha * 100 - HOVER_FADE) / 100);
}

// The hit area's frame script (sprite 220): a press calls the original's clickaction with its node
function hitArea(page, clip) {
  clip.setHandler("onPress", () => {
    const index = state ? state.nodes.indexOf(clip.parentClip?.parentClip) : -1;
    if (index >= 0 && !state.asked) {
      showInfo(index);
    }
  });
}

// The map preview's layers (sprites 727 and 728) turn a degree a frame
function turn(page, clip) {
  clip.onEnterFrame = () => {
    clip.angle += 1;
  };
}

// ---------- The info holder ----------

// The original's clickaction: the info holder slides in on the entry's mark. A locked arena shows only why; any
// other shows its name, details and map, and PLAY, which the art keeps off the stage unless the arena is open
function showInfo(index) {
  const { page, info, list } = state;
  const status = list.status(page, index);
  if (!status) {
    return;
  }
  state.gotox = INFO_AT;
  state.shown = index;
  const play = info.child("playbutton");
  info.gotoAndStop(status);
  if (status === "locked") {
    play.visible = false;
    return;
  }
  const entry = state.entries[index];
  info.set("battlename", entry.name);
  info.set("details", list.details(page, entry));
  const map = info.child("map");
  for (const layer of ["bg", "ob"]) {
    map.child(layer).child("graphic").gotoAndStop(entry.background);
  }
  play.visible = true;
}

// The original's details for an arena, line for line
function arenaDetails(page, arena) {
  const most = new Map(page.data.weight_classes).get(arena.weight_class);
  const { weight, cash } = page.career;
  return (
    `WEIGHT LIMIT: ${arena.weight_class} (${most})\r` +
    `YOUR TEAM'S WEIGHT: ${weight}\r\r` +
    `ENTRY COST: ${arena.fee}\r` +
    `YOUR CASH: ${cash}\r\r` +
    `PRIZE MONEY: ${arena.prize}`
  );
}

// ---------- Buttons ----------

function setUpButtons(page, list) {
  const { panel, info } = state;
  const back = panel.child("backbutton");
  back.set("displaytext", list.back);
  back.setHandler("onPress", () => {
    state.gotox = OUTSIDE;
    page.go(list.backTo, { fadeSound: LEAVE_FADE });
  });
  const infoBack = info.child("backbutton");
  infoBack.set("displaytext", "BACK");
  infoBack.setHandler("onPress", () => {
    state.gotox = LIST_AT;
  });
  const play = info.child("playbutton");
  play.set("displaytext", "PLAY");
  play.setHandler("onPress", () => playPressed(page));
}

// PLAY asks the bot for the battle and slides everything away to the left, as the original does on its way to the
// battle (bringing on its GET READY!). The fade waits for the bot's answer
function playPressed(page) {
  if (state.asked || state.shown === null || !page.send(state.list.request(state.shown))) {
    return;
  }
  state.asked = true;
  state.gotox = PLAYING_AT;
}

// ---------- The win screen (root frame 8) ----------

function enterWin(page) {
  page.sound.music("rave");
  page.fader.gotoAndPlay("fadein");
  page.sound.fadeIn(2);
  const back = page.root.child("backbutton");
  back.setHandler("onPress", () => {
    // The original's back button takes one press
    back.setHandler("onPress", null);
    back.useHandCursor = false;
    page.go("shop", { fadeSound: LEAVE_FADE });
  });
}

const scripts = { [HIT_AREA]: hitArea, [MAP_FLOOR]: turn, [MAP_WALLS]: turn };

export const levelselect = {
  art: [ARENA_PANEL, INFO_PANEL, NODE],
  enter: (page) => enter(page, "levelselect"),
  leave,
  receive,
  scripts,
};

export const challengeselect = {
  art: [CHALLENGE_PANEL, INFO_PANEL, NODE],
  enter: (page) => enter(page, "challengeselect"),
  leave,
  receive,
  scripts,
};

export const wingame = { enter: enterWin };
