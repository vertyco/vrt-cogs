// The upgrade screen, ported from loadUpgradeScreen (F5:538-556), loadUpgradeScreenInGame (F5:557-583),
// backToMapScreen (F5:584-594), setupUpgradeInterface (F5:5008-5020), updateUpgradeButtons (F5:5021-5078) and
// buyUpgrade (F5:5151-5163). The screen is the upgrades clip (sprite 1180, frames "british" and "german"), attached to
// the menu clip on the campaign map and to a blank clip over the battle. The bot keeps the points and the owned
// upgrades and decides every buy: the page sends buy and redraws from the save the bot sends back (page.save's
// upgrades, the numbers owned, and open, the numbers unlocked and not owned).
import * as menus from "./menus.js";
import * as tweens from "./tween.js";

const DEPTH_HUD_UPGRADES = 910000;
const EASE = "easeOutSine";
const SLOT_COUNT = 22;
const NOT_CONNECTED = "Not connected. Try again in a moment.";
// Flash color transforms for a slot: owned, open (unlocked and not owned) and open under the pointer
const OWNED = [235, 0, 218, 0, 156, 0, 100, 0];
const OPEN = [245, 0, 250, 0, 235, 0, 100, 0];
const OPEN_HOVER = [250, 0, 250, 0, 250, 0, 100, 0];
// The details panel sits on the slot, and on the far right it moves 75 left so it stays on the screen (F5:5040-5046)
const DETAILS_FLIP_X = 320;
const DETAILS_SHIFT = 75;
// Upgrade number n is entry n - 1: [name, text, effect, cost] (F5:4688-5007). The bot holds the same table and checks
// every buy against its own copy; the page's copy is for the details panel
const UPGRADES = {
  british: [
    ["RALLY", "Reinforcements will arrive quicker for all infantry.", "10% faster reinforcement", 1],
    ["BALLISTICS", "All Infantry armed with rifles will inflict more damage.", "+15% Damage to Rifles", 1],
    ["HARD HEADED", "All Infantry soldiers gain a slight defensive bonus.", "+10% to Defence", 1],
    ["MORALE BOOST", "Your men recieve an extra ration of rum before each fight.", "15% boost to Morale", 1],
    ["POST HASTE", "Decreases the reinforcment time for all units even further.", "15% faster reinforcement", 2],
    [
      "HIGH EXPLOSIVE",
      "Our engineers have tweaked the Mills bomb to pack more of a punch.",
      "Larger area of effect for grenades.",
      2,
    ],
    [
      "ENTRENCHED",
      "Infantry have been trained in defending themselves better in the trenches.",
      "+10% Defence when Entrenched",
      2,
    ],
    ["OFFICER RALLY", "Your officers will take command over larger numbers of men.", "Larger bonus area", 2],
    [
      "RANGE TRAINING",
      "Your Sharpshooters have spent time training on the range.",
      "+50% Damage for Sharpshooters",
      3,
    ],
    [
      "FIRE SUPPORT",
      "Gunner crews are trained together to provide more deadly fire support.",
      "+30% Damage for Lewis Gunners",
      3,
    ],
    ["TANK COMMAND", "Tanks deal more damage and take less.", "+25% Damage and Defence", 3],
    ["MORTAR ACCURACY", "Mortar crews will fire far more accurately at designated targets.", "+25% more Accurate", 1],
    ["MORTAR BARRAGE", "Increases the amount of rounds fired in a single mortar strike.", "Additional Rounds", 1],
    ["HEAVY MORTAR", "Mortar shells are far more effective against tanks.", "+30% Damage to Tanks", 1],
    ["TOXIC GAS", "Our gas make up has been altered to be more effective.", "+25% Damage", 1],
    ["ARTILLERY ACCURACY", "Artillery crews fire more accurately on designated targets.", "+25% more Accurate", 2],
    [
      "ARTILLERY BARRAGE",
      "Increases the amount of rounds fired in a single artillery strike.",
      "Additional Rounds",
      2,
    ],
    [
      "HEAVY ARTILLERY",
      "Artillery and Anti-Tank shells are more effective against hard targets.",
      "+30% Damage to Tanks",
      2,
    ],
    ["LINGERING GAS", "Our gas has been reformulated to hang longer in the air.", "+30% Duration", 2],
    ["RESUPPLY", "All types of fire support resupply are shortened significantly.", "+40% faster Resupply", 3],
    [
      "BARRAGE OF FIRE",
      "Makes artillery strikes long and intense barrages which will decimate the enemy.",
      "Additional Rounds",
      3,
    ],
    ["ANTI-TANK BARRAGE", "Anti-tank batteries will fire more rounds at enemy tanks.", "Additional Rounds", 3],
  ],
  german: [
    ["BALLISTICS", "All Infantry armed with rifles will inflict more damage.", "+15% Damage to Rifles", 1],
    ["TRENCH ARMOUR", "Our engineers have designed armor to protect our men better.", "+10% to Defence", 1],
    ["REINFORCEMENTS", "Additional reinforcements have been allotted to our fight", "10% faster reinforcement", 1],
    ["FOR THE KAISER", "Our men are inspired by the Kaiser.", "15% boost to Morale", 1],
    [
      "MACHINE GUN TRENCH",
      "Our Machine Gun teams have been training in operating in trenches.",
      "+15% Damage when Entrenched",
      2,
    ],
    ["ENTRENCH", "Trenches are more secure now providing better cover.", "+10% Defence when Entrenched", 2],
    ["RAPID DEPLOYMENT", "Reinforcements arrive even faster.", "15% faster reinforcement", 2],
    ["FOR THE FATHERLAND", "Our men will die for our country.", "20% boost to Morale", 2],
    ["STURMTRUPPEN", "Our Sturmtruppen are a tool of destruction.", "+30% Damage for Sturmtruppen", 3],
    [
      "INDUSTRIAL ACTION",
      "Our engineers are able to supply us with Tanks much faster.",
      "+25% faster reinforcement of Tanks",
      3,
    ],
    ["GREAT LEADER", "Our Officers provide great leadership to our men.", "+30% Damage bonus to surrounding men", 3],
    ["MORTAR ACCURACY", "Mortar crews will fire far more accurately at designated targets.", "+25% more Accurate", 1],
    ["MORTAR BARRAGE", "Increases the amount of rounds fired in a single mortar strike.", "Additional Rounds", 1],
    ["HEAVY MORTAR", "Mortar shells are far more effective against tanks.", "+30% Damage to Tanks", 1],
    ["TOXIC GAS", "Our gas make up has been altered to be more effective.", "+25% Damage", 1],
    ["ARTILLERY ACCURACY", "Artillery crews fire more accurately on designated targets.", "+25% more Accurate", 2],
    [
      "ARTILLERY BARRAGE",
      "Increases the amount of rounds fired in a single artillery strike.",
      "Additional Rounds",
      2,
    ],
    [
      "HEAVY ARTILLERY",
      "Artillery and Anti-Tank shells are more effective against hard targets.",
      "+30% Damage to Tanks",
      2,
    ],
    ["LINGERING GAS", "Our gas has been reformulated to hang longer in the air.", "+30% Duration", 2],
    ["RESUPPLY", "All types of fire support resupply are shortened significantly.", "+40% faster Resupply", 3],
    [
      "BARRAGE OF FIRE",
      "Makes artillery strikes long and intense barrages which will decimate the enemy.",
      "Additional Rounds",
      3,
    ],
    ["ANTI-TANK BARRAGE", "Anti-tank batteries will fire more rounds at enemy tanks.", "Additional Rounds", 3],
  ],
};

let page = null;
// The screen that is up: { clip: the upgrades clip, holder: the blank clip it sits in over a battle, or null }
let shown = null;
// The upgrades presses asked for, until a save answers each, and the numbers owned when a save last came
const asked = new Set();
let owned = [];

// Gives the module the page it works on. Called once by campaign.js
export function bindPage(owner) {
  page = owner;
  page.onMessage("save", receiveSave);
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

// ---------- Drawing ----------

// Each slot's look from the bot's word (updateUpgradeButtons, F5:5021-5078): an owned upgrade is lit and its icon
// in colour, an open one is a little lit, a locked one stays dark and grey
function refresh(clip, save) {
  clip.child("upgradePointsText").text = save.points;
  for (let number = 1; number <= SLOT_COUNT; number += 1) {
    const slot = clip.child(`slot${number}`);
    if (save.upgrades.includes(number)) {
      tweens.colorTransformTo(slot, ...OWNED, 0.4, EASE);
      clip.child(`icon_slot${number}`).gotoAndStop("colour");
    } else if (save.open.includes(number)) {
      tweens.colorTransformTo(slot, ...OPEN, 0.4, EASE);
    }
  }
}

function isOpen(number) {
  return Boolean(page.save?.open.includes(number));
}

// The panel with an upgrade's name, cost, text and effect comes up over its slot (F5:5034-5058)
function showDetails(clip, slot, number) {
  const [name, text, effect, cost] = UPGRADES[page.save.side][number - 1];
  const details = clip.child("details");
  details.child("upgradeName").text = name;
  details.child("upgradeCost").text = `Cost: ${cost}`;
  details.child("upgradeDesc").text = text;
  details.child("upgradeEffect").text = `Effect: ${effect}`;
  details.x = slot.x >= DETAILS_FLIP_X ? slot.x - DETAILS_SHIFT : slot.x;
  details.y = slot.y;
  details.visible = true;
  tweens.alphaTo(details, 100, 0.3, EASE);
  if (isOpen(number)) {
    tweens.colorTransformTo(slot, ...OPEN_HOVER, 0.4, EASE);
  }
}

function hideDetails(clip, slot, number) {
  tweens.alphaTo(clip.child("details"), 0, 0.3, EASE, 0, (panel) => {
    panel.visible = false;
  });
  if (isOpen(number)) {
    tweens.colorTransformTo(slot, ...OPEN, 0.4, EASE);
  }
}

// buyUpgrade (F5:5151-5163): an upgrade that is open and paid for is asked of the bot, which checks it again
function buy(number) {
  const save = page.save;
  if (!save || !isOpen(number) || save.points < UPGRADES[save.side][number - 1][3]) {
    return;
  }
  if (!page.send({ buy: number })) {
    page.toast(NOT_CONNECTED);
    return;
  }
  asked.add(number);
}

// What the original does as it builds the screen: the side's frame, the slots' handlers and their looks
function setup(clip, save) {
  clip.gotoAndStop(save.side);
  clip.child("details").visible = false;
  owned = [...save.upgrades];
  asked.clear();
  for (let number = 1; number <= SLOT_COUNT; number += 1) {
    const slot = clip.child(`slot${number}`);
    slot.setHandler("onRollOver", () => showDetails(clip, slot, number));
    slot.setHandler("onRollOut", () => hideDetails(clip, slot, number));
    slot.setHandler("onRelease", () => buy(number));
  }
  refresh(clip, save);
}

// The bot's save: the battle's Upgrades dial takes its points from it, and the screen redraws. A save that arrives
// while a press is unanswered (a level reached in the battle, say) isn't the answer. A press is answered by a save
// that holds its upgrade (and says so with a quick message), or by the reply the bot marks with the upgrade's number,
// which also covers a refused buy
function receiveSave(save, message) {
  if (!save) {
    return;
  }
  // Not once the battle has ended: bonus XP only shows with the results screen, not on the dial during the cheers
  if (!page.field?.ending) {
    page.field?.hud?.setPoints(save.points);
  }
  if (!shown?.clip || shown.clip.destroyed) {
    return;
  }
  let bought = false;
  for (const number of [...asked]) {
    const has = save.upgrades.includes(number);
    if (has || message?.answer === number) {
      asked.delete(number);
      bought ||= has && !owned.includes(number);
    }
  }
  owned = [...save.upgrades];
  refresh(shown.clip, save);
  if (bought) {
    page.quickMessage("UPGRADE PURCHASED");
  }
}

// ---------- Opening and closing ----------

// The campaign map's Upgrade Units opens the screen in the menu. The battle's Upgrades dial opens it over the battle,
// which the bot pauses for as long as it is up
export function openUpgrades({ inBattle = false } = {}) {
  if (!inBattle) {
    page.show("upgrades");
    return Promise.resolve();
  }
  return openOverBattle();
}

// loadUpgradeScreen (F5:538-556): the screen is up at once while the map fades out under it. Done goes back to the
// map, which brings itself back
async function enterUpgrades() {
  const save = page.save;
  if (!save) {
    page.toast(NOT_CONNECTED);
    page.show("main");
    return;
  }
  const menu = menuClip() ?? (await menus.loadMenu("map"));
  await page.lib.need([page.lib.exported("upgrades")]);
  menu.child("upgrades")?.removeMovieClip();
  const clip = menu.attach(page.lib.makeExported("upgrades"), "upgrades");
  shown = { clip, holder: null };
  setup(clip, save);
  clip.child("doneButton").setHandler("onRelease", () => page.show("map"));
  tweens.alphaTo(menu.child("mapScreen"), 0, 0.6, EASE, 0, (part) => {
    part.visible = false;
  });
}

// backToMapScreen (F5:584-594): the screen fades out as the map comes back (campaign.js brings the map back)
function leaveUpgrades(owner, next) {
  const clip = shown?.clip;
  shown = null;
  if (clip && !clip.destroyed) {
    tweens.alphaTo(clip, 0, 0.6, EASE, 0, (gone) => gone.removeMovieClip());
  }
  menus.keepMenu(next);
}

// loadUpgradeScreenInGame (F5:557-583): the battle pauses, the screen comes up over it on a blank clip and the field
// shows dimly through it. The original stops the battle's presses with an empty onRelease on the HUD; here the dimmed
// backing takes them
async function openOverBattle() {
  const save = page.save;
  if (shown || !save) {
    return;
  }
  await page.lib.need([page.lib.exported("blankMovie"), page.lib.exported("upgrades")]);
  if (shown) {
    return;
  }
  if (!page.send({ pause: true })) {
    page.toast(NOT_CONNECTED);
    return;
  }
  const holder = page.attach("blankMovie", DEPTH_HUD_UPGRADES, "upgradesOverlay");
  const clip = holder.attach(page.lib.makeExported("upgrades"), "upgrades");
  shown = { clip, holder };
  setup(clip, save);
  const backing = clip.child("backing");
  backing.useHandCursor = false;
  backing.setHandler("onRelease", () => {});
  tweens.alphaTo(backing, 60, 1);
  clip.child("doneButton").setHandler("onRelease", closeOverBattle);
}

function closeOverBattle() {
  if (!shown?.holder || shown.closing) {
    return;
  }
  shown.closing = true;
  tweens.alphaTo(shown.holder, 0, 0.6, EASE, 0.1, () => {
    page.detach("upgradesOverlay");
    shown = null;
    page.send({ pause: false });
  });
}

export const screens = {
  upgrades: { enter: enterUpgrades, leave: leaveUpgrades },
};
