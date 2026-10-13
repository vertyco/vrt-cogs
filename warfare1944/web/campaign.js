// The campaign's screens: Select Campaign, the difficulty question, the campaign map and the unlock dialogs, ported
// from the original's loadCampaignSelect (F6:605-628), buttonSetup_campaignSelect (F6:947-1005),
// dialog_selectDifficulty (F6:227-271), loadMapScreen (F6:663-705), buttonSetup_mapScreen (F6:1006-1038),
// campaignMapSetup (F6:7196-7266) and displayUnlockDialog (F6:8652-8710). All of them draw on parts of the menu clip
// (sprite 1210). The bot keeps the campaign: the page asks for a new one with newCampaign (side and difficulty) and
// reads the map's numbers from the campaign view in page.save.
// The upgrade screen is in upgrades.js.
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import * as upgrades from "./upgrades.js";

const DEPTH_UNLOCK_DIALOG = 960000;
// The unlock dialog sits in the middle of the 800 x 500 stage (F6:8662-8663)
const STAGE_CENTER_X = 400;
const STAGE_CENTER_Y = 250;
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const EASE = "easeOutSine";
const SIDES = ["british", "german"];
// Flash color transforms: everything 220 % bright (a button under the pointer), and back to its own colors
const BRIGHT = [220, 0, 220, 0, 220, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// campaignMapSections (F6:11036-11037): the map's ten sections, and how see-through their colored backing is
const SECTIONS = Array.from({ length: 10 }, (_, index) => `section${index + 1}`);
const SECTION_ALPHA = 0.35;
// The lit section's red, and the sides' map colors (british.teamColour, german.teamColour, F6:10173, 10178)
const LIT_COLOR = 10027008;
const TEAM_COLOR = { british: 0x666600, german: 0x222222 };
const WHITE = 16777215;
const SECTION_BLUR = 5;
// A thin space between the XP bar's characters, standing in for the original's size 5 spaces (F6:688)
const THIN_SPACE = " ";
// The original's own line for each unit and way to win it unlocks, by side (F6:10217-10689). The spelling is its own
const UNLOCK_TEXT = {
  british: {
    flanking:
      "Moving your men off the battlefield on the enemy's TOP and BOTTOM zones will flank them dropping their MORALE.",
    conquer: "Moving your men to END of the MIDDLE ZONE will win the Battle.",
    objective: "DESTROY the BUNKER with your BAZOOKA TEAMS to take the beach!",
    riflemen: "British riflemen are the core of your infantry. Good in most situations.",
    assault: "Assault Teams are trained and equipped for the task of clearing enemy emplacements.",
    machineGun: "Carrying the .30 Cal, these teams are your defensive backbone. Keep them in cover.",
    sniper: "These men are the best shots in the company. Devastating to enemy machine gun teams.",
    officer: "Officers have the battalion's fire support at their disposal.",
    mortarTeam: "Mortar Teams are vital to support your men with short range artillery.",
    bazooka: "Anti-tank team. Use them in cover to ambush enemy tanks.",
    tank: "Medium tank. Slightly weaker armor than the Panzer III, keep it supported by infantry.",
  },
  german: {
    flanking:
      "Moving your men off the battlefield on the enemy's TOP and BOTTOM zones will flank them dropping their MORALE.",
    conquer: "Moving your men to END of the MIDDLE ZONE will win the Battle.",
    riflemen: "Our riflemen are excellent all round soldiers.",
    assault: "Sturmtruppen or Assault Troops are trained in assaulting enemy in cover.",
    machineGun: "Machine gun teams are best entrenched in defensive positions.",
    sniper: "The sharpshooter is a deadly tool against enemies at long range.",
    officer: "Our officers provide a boost to the morale of the men.",
    mortarTeam: "Mortar Teams are vital to support your men with short range artillery.",
    bazooka: "Devestate the American's tin cans with these anti-tank teams.",
    tank: "Our tanks are superior but they are not invincible, keep them supported.",
  },
};
// The part of the menu clip each screen before Select Campaign shows
const PART_OF = { main: "mainMenu", select: "teamSelect", map: "mapScreen" };
// The unlocks that are ways to win rather than units (F6:8672-8674)
const WAYS_TO_WIN = new Set(["flanking", "conquer", "objective"]);
// How long a sent newCampaign waits for the bot's save before the player may pick again
const NEW_CAMPAIGN_WAIT_MS = 5000;
const DIFFICULTIES = [
  ["RECRUIT", "recruit"],
  ["REGULAR", "regular"],
  ["HARDENED", "hardened"],
];
const NOT_CONNECTED = "Not connected. Try again in a moment.";

let page = null;
// The side and difficulty asked for on Select Campaign, until the bot's new save for them arrives
let pending = null;
let pendingTimer = null;
let unlockCount = 0;

// Gives the module the page it works on. Called once by game.js
export function bindPage(owner) {
  page = owner;
  page.onMessage("save", receiveSave);
  page.onMessage("notice", clearPending);
  upgrades.bindPage(owner);
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

async function menuFor(screen) {
  return menuClip() ?? (await menus.loadMenu(screen));
}

function click() {
  sound.play(CLICK);
}

function clearPending() {
  pending = null;
  clearTimeout(pendingTimer);
}

// A fresh campaign is on mission 1 with no XP. The bot's new save for the side and difficulty just asked for opens
// the map. A save that arrives on the map screen (after a purchase, say) brings its numbers up to date
function isNewSave(save) {
  return save?.side === pending.side && save.difficulty === pending.difficulty && save.mission === 1 && save.xp === 0;
}

function receiveSave(save) {
  if (page.screen === "select" && pending && isNewSave(save)) {
    clearPending();
    page.show("map");
    return;
  }
  if (page.screen === "map" && save) {
    const map = menuClip()?.child("mapScreen");
    if (map) {
      showNumbers(map, save);
    }
  }
}

// ---------- Select Campaign ----------

// loadCampaignSelect (F6:607-628): the picture fades in after the main menu has faded out
async function enterSelect() {
  const had = menuClip() !== null;
  const menu = await menuFor("select");
  clearPending();
  setupSelect(menu.child("teamSelect"));
  if (had) {
    menus.swap(menu, PART_OF[page.previousScreen] ?? null, "teamSelect");
  }
}

// buttonSetup_campaignSelect (F6:947-1005): the flag brightens and its description comes up while the pointer is on it
function setupSelect(select) {
  const descriptions = select.child("descriptions");
  const general = descriptions.child("generalDesc");
  for (const side of SIDES) {
    const button = select.child(side);
    const description = descriptions.child(`${side}Desc`);
    button.setHandler("onRollOver", () => {
      sound.play(ROLL_OVER);
      tweens.colorTransformTo(button.child("flag"), ...BRIGHT, 0.4, EASE);
      tweens.glowTo(button.child("nameTag"), 5, 5);
      tweens.alphaTo(description, 100, 0.8);
      tweens.alphaTo(general, 0, 0.4);
    });
    button.setHandler("onRollOut", () => {
      tweens.colorTransformTo(button.child("flag"), ...NORMAL, 0.6, EASE);
      tweens.glowTo(button.child("nameTag"), 0, 0);
      tweens.alphaTo(description, 0, 0.4);
      tweens.alphaTo(general, 100, 0.8, EASE, 0.5);
    });
    button.setHandler("onRelease", () => pickSide(side));
  }
}

// Picking a flag asks how hard the campaign is (F6:979-1004)
function pickSide(side) {
  click();
  menus.dialog({
    heading: "SELECT DIFFICULTY",
    body: "What kind of commander are you?",
    buttons: DIFFICULTIES.map(([text, difficulty]) => ({ text, onPress: () => startCampaign(side, difficulty) })),
  });
}

// The difficulty asks the bot for a fresh campaign on that side. The map opens when the bot's save arrives
function startCampaign(side, difficulty) {
  if (!page.send({ newCampaign: { side, difficulty } })) {
    page.toast(NOT_CONNECTED);
    return;
  }
  pending = { side, difficulty };
  clearTimeout(pendingTimer);
  pendingTimer = setTimeout(clearPending, NEW_CAMPAIGN_WAIT_MS);
}

// ---------- The campaign map ----------

// loadMapScreen (F6:663-705): the part before it fades out, the map fades in after half a second, and the bot's new
// units and supports are announced one after another
async function enterMap() {
  const save = page.save;
  if (!save) {
    page.toast(NOT_CONNECTED);
    page.show("main");
    return;
  }
  const first = menuClip() === null;
  const menu = await menuFor("map");
  const map = menu.child("mapScreen");
  setupMapButtons(map);
  showNumbers(map, save);
  const from = page.previousScreen;
  if (from === "upgrades") {
    // backToMapScreen (F6:791-801): the map comes back as it was, with no announcements and no new colors
    map.visible = true;
    tweens.alphaTo(map, 100, 0.8, EASE, 0.5);
    return;
  }
  setupSections(map, save);
  if (!first) {
    fadeToMap(menu, map, from);
  }
  announce(save);
}

function fadeToMap(menu, map, from) {
  const previous = menu.child(PART_OF[from] ?? "mainMenu");
  if (previous && previous !== map) {
    const seconds = from === "select" ? 0.4 : 0.8;
    tweens.alphaTo(previous, 0, seconds, EASE, 0, (clip) => {
      clip.visible = false;
    });
  }
  map.alpha = 0;
  map.visible = true;
  tweens.alphaTo(map, 100, 0.8, EASE, 0.5);
}

// buttonSetup_mapScreen (F6:1006-1038): the three buttons brighten under the pointer
function setupMapButtons(map) {
  const presses = {
    launch: () => {
      if (!page.launch({ launch: true })) {
        page.toast(NOT_CONNECTED);
      }
    },
    upgrades: () => upgrades.openUpgrades({ inBattle: false }),
    backToMainButt: () => page.show("main"),
  };
  for (const [name, press] of Object.entries(presses)) {
    const button = map.child(name);
    button.setHandler("onRollOver", () => {
      sound.play(ROLL_OVER);
      tweens.colorTransformTo(button, ...BRIGHT, 0.4, EASE);
    });
    button.setHandler("onRollOut", () => tweens.colorTransformTo(button, ...NORMAL, 0.6, EASE));
    button.setHandler("onRelease", () => {
      click();
      press();
    });
  }
}

// The mission's title and line, the upgrade points and the XP bar (loadMapScreen, F6:663-705). The campaign view
// carries this level's start and the next level's, so the bar is the part of the way between them. At the top level
// there is no next one: the bar is full and the words give the XP
function showNumbers(map, save) {
  const header = map.child("header");
  header.autoSizeCenter();
  header.text = save.title;
  map.child("desc").text = save.description;
  map.child("upgradePointsText").text = save.points;
  const [floor, next] = save.level_xp;
  const words = next === null ? `${save.xp} XP` : `${save.xp - floor} / ${next - floor} XP`;
  map.child("expBar").scale.x = next === null ? 1 : Math.round(((save.xp - floor) / (next - floor)) * 100) / 100;
  map.child("xpText").text = words.split("").join(THIN_SPACE);
}

// campaignMapSetup (F6:7196-7266). The map's picture is the side's frame. American missions walk the sections from 1
// up with a while loop; German ones walk them with for..in, newest first, so from 10 down (as the running original
// paints them). Sections before the mission's are the player's color and the rest the enemy's; the mission's own
// section is lit and shows its icons. Both sides show the one `_icons` clip of a section
function setupSections(map, save) {
  const side = save.side;
  const enemy = side === "british" ? "german" : "british";
  const sections = side === "british" ? SECTIONS : [...SECTIONS].reverse();
  const lit = `section${save.section}`;
  const land = map.child("map");
  map.child("mapBG").gotoAndStop(side);
  let found = false;
  for (const name of sections) {
    const backing = land.child(name).child("backing");
    backing.alpha = SECTION_ALPHA;
    const icons = land.child(`${name}_icons`);
    if (icons) {
      icons.visible = false;
    }
    if (lit === name && !found) {
      // The original's else branch also tints the lit section the enemy's color, and in the running original the red
      // is what shows
      found = true;
      if (icons) {
        icons.visible = true;
      }
      tweens.colorTo(backing, LIT_COLOR);
    } else if (found) {
      tweens.colorTo(backing, TEAM_COLOR[enemy]);
    } else {
      tweens.colorTo(backing, WHITE);
      tweens.colorTo(backing, TEAM_COLOR[side], 2, EASE, 1);
    }
    tweens.blurTo(backing, SECTION_BLUR, 1);
  }
}

// ---------- Unlock dialogs ----------

// checkForUnlocks (F6:8639-8651): each new unit and way to win the mission brings has its own dialog, shown one after
// another, newest first (its queue is filled with for..in). The next one comes up when OK is pressed
function announce(save) {
  const queue = [...save.new].reverse();
  const next = () => {
    if (queue.length) {
      showUnlock(save.side, queue.shift(), next);
    }
  };
  next();
}

// displayUnlockDialog (F6:8652-8681) and unlockInterfaceButton (F6:8682-8702)
async function showUnlock(side, key, onClosed) {
  await page.lib.need([page.lib.exported("unlockDialog")]);
  unlockCount += 1;
  const dialog = page.attach("unlockDialog", DEPTH_UNLOCK_DIALOG + unlockCount, `unlockDialog${unlockCount}`);
  const [black, backing, icon, texts, button] = ["blackOut", "backing", "icon", "textBoxes", "mainButton"].map((name) =>
    dialog.child(name),
  );
  black.alpha = 0.08;
  backing.alpha = 0.08;
  icon.alpha = 0;
  texts.alpha = 0;
  button.alpha = 0;
  // The darkened screen takes presses, so nothing behind the dialog hears them
  black.useHandCursor = false;
  black.setHandler("onRelease", () => {});
  tweens.alphaTo(black, 60, 0.8, EASE);
  tweens.alphaTo(backing, 100, 0.6, EASE);
  tweens.alphaTo(icon, 100, 0.6, EASE, 0.4);
  tweens.alphaTo(texts, 100, 0.6, EASE, 0.4);
  tweens.alphaTo(button, 100, 0.6, EASE, 0.6);
  dialog.position.set(STAGE_CENTER_X, STAGE_CENTER_Y);
  if (WAYS_TO_WIN.has(key)) {
    texts.child("headerText").text = "NEW WAY TO WIN AVAILABLE";
  }
  texts.child("unitHeader").text = key.toUpperCase();
  icon.gotoAndStop(side);
  icon.child("icons").gotoAndStop(key);
  texts.child("description").text = UNLOCK_TEXT[side][key];
  button.child("buttonText").text = "OK";
  setupUnlockButton(dialog, button, onClosed);
}

function setupUnlockButton(dialog, button, onClosed) {
  const backing = button.child("backing");
  button.setHandler("onRollOver", () => tweens.colorTransformTo(backing, ...BRIGHT, 0.4, EASE));
  button.setHandler("onRollOut", () => tweens.colorTransformTo(backing, ...NORMAL, 0.6, EASE));
  button.setHandler("onRelease", () => {
    if (dialog.closing) {
      return;
    }
    dialog.closing = true;
    click();
    tweens.alphaTo(dialog, 0, 0.1, EASE, 0, (gone) => gone.destroy({ children: true }));
    onClosed();
  });
}

// ---------- Screens ----------

function leave(owner, next) {
  menus.keepMenu(next);
}

export const screens = {
  select: { enter: enterSelect, leave },
  map: { enter: enterMap, leave },
  ...upgrades.screens,
};
