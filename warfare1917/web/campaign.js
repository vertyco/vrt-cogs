// The campaign's screens: Select Campaign, the campaign map and the unlock dialogs, ported from the original's
// loadCampaignSelect (F5:413-431), buttonSetup_campaignSelect (F5:723-784), loadMapScreen (F5:465-502),
// buttonSetup_mapScreen (F5:785-817), campaignMapSetup (F5:4557-4620) and displayUnlockDialog (F5:5854-5908). All
// of them draw on parts of the menu clip (sprite 1036). The bot keeps the campaign: the page asks for a new one
// with newCampaign and reads the map's numbers from the campaign view in page.save.
// The upgrade screen is in upgrades.js.
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import * as upgrades from "./upgrades.js";

const DEPTH_UNLOCK_DIALOG = 960000;
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const EASE = "easeOutSine";
const SIDES = ["british", "german"];
// Flash color transforms: everything 220 % bright (a button under the pointer), and back to its own colors
const BRIGHT = [220, 0, 220, 0, 220, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// campaignMapSections (F5:7381-7382): the map's ten sections, and how see-through their colored backing is
const SECTIONS = Array.from({ length: 10 }, (_, index) => `section${index + 1}`);
const SECTION_ALPHA = 0.35;
// The lit section's red, and the sides' map colors (british.teamColour, german.teamColour, F5:6960, 6965)
const LIT_COLOR = 10027008;
const TEAM_COLOR = { british: 0x666600, german: 0x222222 };
const WHITE = 16777215;
const SECTION_BLUR = 5;
// A thin space between the XP bar's characters, standing in for the original's size 5 spaces (F5:487)
const THIN_SPACE = " ";
// The original's own line for each unit and support it unlocks, by side (F5:6975-7226)
const UNLOCK_TEXT = {
  british: {
    artillery: "Devastating heavy rounds that will destroy anything in their way.",
    mortar: "Explosive rounds good for hitting large numbers of infantry in the open.",
    gas: "Gas rounds are a long lasting area attack. Best used on men in entrenched positions.",
    antiTank: "Direct fire rounds for taking out tanks.",
    riflemen: "British riflemen are the core of your infantry. Good in most situations.",
    assault: "Using rush tactics and mills bombs, Assault Teams are best at clearing trenches.",
    machineGun: "Carrying the Lewis Gun, these teams are your defensive backbone. Keep them entrenched.",
    sniper: "These men are the best shots in the company. Devastating to enemy machine gun teams.",
    officer: "Officers inspire their men, providing them with an accuracy bonus when close.",
    tank: "'Land-ships' are a fearsome sight to the Fritz. Blazing machine guns and cannons, hurrah!",
  },
  german: {
    artillery: "Heavy artillery rounds for taking out all types of targets.",
    mortar: "Indirect medium explosive fire.",
    gas: "Toxic gases used to disable enemies. Best used on entrenched soldiers.",
    antiTank: "Direct fire rounds for taking out tanks.",
    riflemen: "Our riflemen are excellent all round soldiers.",
    assault: "Sturmtruppen or Assault Troops are trained in assaulting trenches.",
    machineGun: "Machine gun teams are best entrenched in defensive positions.",
    sniper: "The sharpshooter is a deadly tool against enemies at long range.",
    officer: "Our officers provide a boost to the morale of the men.",
    tank: "Our answer to the Mark IV. Devastating to infantry.",
  },
};
// The part of the menu clip each screen before Select Campaign shows
const PART_OF = { main: "mainMenu", select: "teamSelect", map: "mapScreen" };
const SUPPORTS = new Set(["mortar", "artillery", "gas", "antiTank"]);
const NOT_CONNECTED = "Not connected. Try again in a moment.";

let page = null;
// The side picked on Select Campaign, until the bot's new save for it arrives
let pickedSide = null;
let unlockCount = 0;

// Gives the module the page it works on. Called once by game.js
export function bindPage(owner) {
  page = owner;
  page.onMessage("save", receiveSave);
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

// The bot's new save for the side just picked opens the map. A save that arrives on the map screen (after a purchase,
// say) brings its numbers up to date
function receiveSave(save) {
  if (page.screen === "select" && pickedSide && save?.side === pickedSide) {
    pickedSide = null;
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

// loadCampaignSelect (F5:413-431): the picture fades in after the main menu has faded out
async function enterSelect() {
  const had = menuClip() !== null;
  const menu = await menuFor("select");
  pickedSide = null;
  setupSelect(menu.child("teamSelect"));
  if (had) {
    menus.swap(menu, PART_OF[page.previousScreen] ?? null, "teamSelect");
  }
}

// buttonSetup_campaignSelect (F5:723-784): the flag brightens and its description comes up while the pointer is on it
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

// Picking a flag asks the bot for a fresh campaign on that side. The map opens when the bot's save arrives
function pickSide(side) {
  click();
  if (pickedSide) {
    return;
  }
  if (!page.send({ newCampaign: side })) {
    page.toast(NOT_CONNECTED);
    return;
  }
  pickedSide = side;
}

// ---------- The campaign map ----------

// loadMapScreen (F5:465-502): the part before it fades out, the map fades in after half a second, and the bot's new
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
    // backToMapScreen (F5:584-594): the map comes back as it was, with no announcements and no new colors
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

// buttonSetup_mapScreen (F5:785-817): the three buttons brighten under the pointer
function setupMapButtons(map) {
  const presses = {
    launch: () => page.launch({ launch: true }),
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

// The mission's title and line, the upgrade points and the XP bar (loadMapScreen, F5:465-502, 5008). The campaign view
// carries this level's start and the next level's, so the bar is the part of the way between them. At the top level
// there is no next one: the bar is full and the words give the XP
function showNumbers(map, save) {
  const header = map.child("header");
  const desc = map.child("desc");
  header.autoSizeCenter();
  desc.autoSizeCenter();
  header.text = save.title;
  desc.text = save.description;
  map.child("upgradePointsText").text = save.points;
  const [floor, next] = save.level_xp;
  const words = next === null ? `${save.xp} XP` : `${save.xp - floor} / ${next - floor} XP`;
  map.child("expBar").scale.x = next === null ? 1 : Math.round(((save.xp - floor) / (next - floor)) * 100) / 100;
  map.child("xpText").text = words.split("").join(THIN_SPACE);
}

// campaignMapSetup (F5:4557-4620). British missions walk the sections from 1 up with a while loop; German ones walk
// them with for..in, newest first, so from 10 down (the game's own trace, Ruffle shot of the German map). Sections
// before the mission's are the player's color and the rest the enemy's; the mission's own section is lit and shows
// its icons
function setupSections(map, save) {
  const side = save.side;
  const enemy = side === "british" ? "german" : "british";
  const sections = side === "british" ? SECTIONS : [...SECTIONS].reverse();
  const iconsName = side === "british" ? "_icons" : "_icons_german";
  const lit = `section${save.section}`;
  const land = map.child("map");
  let found = false;
  for (const name of sections) {
    const backing = land.child(name).child("backing");
    backing.alpha = SECTION_ALPHA;
    for (const suffix of ["_icons_german", "_icons"]) {
      const icons = land.child(name + suffix);
      if (icons) {
        icons.visible = false;
      }
    }
    if (lit === name && !found) {
      // The original's else branch also tints the lit section the enemy's color, and in the running original the red
      // is what shows
      found = true;
      const icons = land.child(name + iconsName);
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

// checkForUnlocks (F5:5841-5853): each new unit and support the mission brings has its own dialog, shown one after
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

// displayUnlockDialog (F5:5854-5908) and unlockInterfaceButton (F5:5909-5925)
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
  dialog.position.set(400, 210);
  if (SUPPORTS.has(key)) {
    texts.child("headerText").text = "NEW SUPPORT AVAILABLE";
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
