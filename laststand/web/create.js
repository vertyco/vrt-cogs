// Character creation (openCreateCharacter F4:11159, the setupCharCreate* functions F4:11196-11497, charCreateLaunch
// F4:11424; sprite characterCreation 6107 with its pages namePage 6032, appearance 6046, preMade 6102, attr 6069 and
// skills 6081, and quitToMenu 6106). One clip holds every page and shows one at a time:
//
//   name -> appearance -> occupation -> (Create Custom: attributes -> skills) -> launch
//
// The name is a real text field: an HTML input sits over the art's own name box, in stage pixels times the page's scale
// (the stage never reaches the phone's keyboard otherwise), and is there only while the name page shows.
//
// Every visit starts from a new character: the sex, name, look, occupation, attribute points and marked skills all start
// over (the original kept some of them in globals between visits). Picking Male or Female rolls the name again for that
// sex when the sex changes. The Survival Kit and the mode flags come from newStory; the launch makes the story and
// saves it to the chosen slot before the intro starts, as the original does.
import { data } from "./data.js";
import { setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { light } from "./light.js";
import { decorateMenuHead } from "./menus.js";
import { fadeInBox, fadeOutBox, finger, setAlpha, setColor } from "./panels.js";
import { goto } from "./rig.js";
import { rng } from "./rng.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { newStory } from "./story.js";
import { world } from "./world.js";

const CLIP = "characterCreation";
const DIALOG_CLIP = "createDialog";
const PAGES = { name: "namePage", appearance: "appearance", occupation: "preMade", attributes: "attr", skills: "skills" };
const ATTRIBUTES = ["strength", "precision", "intellect", "endurance", "luck"];
const SEXES = ["male", "female"];
// The appearance rows, the story's look key each one sets, and where its choices come from
const LOOK_ROWS = { hair: "hair", hairColour: "hairColour", skinColour: "skin", facialHair: "facialHair" };
const FIRST_NAME_INK = "#373d4e";
// An occupation's name and its picked colour, as the original's text formats set them (3620174 and 16777215)
const OCCUPATION_INK = { off: "#373d4e", over: "#ffffff" };
// Dialog box over the stage: centred, its shade and its fade as showDialogBox draws them (F4:20000)
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
// BACK TO MENU rests faint, shows at half on a roll-over and dims to a fifth on roll-out (quitToMenuButton F4:11042)
const QUIT_ALPHA = { over: 50, out: 20, seconds: 0.5 };
const NO_OCCUPATION = {
  heading: "SELECT AN OCCUPATION",
  body: "YOU NEED TO SELECT\rAN OCCUPATION OR\rCREATE A CUSTOM ONE",
};
const UNSPENT = {
  heading: "UNSPENT POINTS",
  body: "YOU HAVE NOT ASSIGNED ALL OF\r YOUR CHARACTER'S POINTS\r\rDO YOU WISH TO CONTINUE?",
};
const MOST_RECORDED = 100;

let page = null;
let depth = 0;
let dialogDepth = 0;
// The creation now: { clip, shown, sex, box, options, pick, lists, occupations, current, attrs, remaining, marked,
// dialog, tapped, busy, launched }
let view = null;
// What was pressed and chosen, newest last, for checks
const log = [];

function record(kind, extra = {}) {
  log.push({ kind, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

function constant(name) {
  return data.actors.constants[name];
}

function upper(text) {
  return String(text ?? "").toUpperCase();
}

function capital(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// playMouseClickSound (F4:5562)
function click() {
  sound.play(`sound_mouseClick${rng.random(2) + 1}`);
}

function part(pageName, ...path) {
  let node = view.clip.child(PAGES[pageName]);
  for (const step of path) {
    node = node.child(step);
  }
  return node;
}

// ---------- Buttons ----------

// A part acts on a mouse press, where a finger acts on lifting it, so a touch that starts on one and slides away does
// nothing. press(touched) is told whether a finger made it; over and out are for a mouse's roll-over and roll-out
function wire(node, { press = null, over = null, out = null }) {
  node.setHandler("onRollOver", (event) => {
    if (!finger(event) && !view?.dialog) {
      over?.();
    }
  });
  node.setHandler("onRollOut", (event) => {
    if (!finger(event) && !view?.dialog) {
      out?.();
    }
  });
  node.setHandler("onPress", (event) => {
    if (!view || view.dialog || view.busy || !press) {
      return;
    }
    if (finger(event)) {
      view.tapped = node;
    } else {
      press(false);
    }
  });
  node.setHandler("onRelease", (event) => {
    if (!finger(event) || !view || view.tapped !== node) {
      return;
    }
    view.tapped = null;
    press?.(true);
  });
  node.setHandler("onReleaseOutside", () => {
    if (view) {
      view.tapped = null;
    }
  });
}

// ---------- Pages ----------

function showPage(name) {
  for (const [key, child] of Object.entries(PAGES)) {
    view.clip.child(child).visible = key === name;
  }
  view.shown = name;
  placeBox();
  record("page", { name });
  // The new page's buttons sit where the old page's were, so the second click of a double click presses nothing
  input.shutByClick();
}

function stepTo(from, to, button) {
  wire(part(from, button), {
    press: () => {
      click();
      showPage(to);
    },
  });
}

// ---------- Name page ----------

// A random "<first> <last>" for a sex (randomCharacterName F4:11030)
function randomName(sex) {
  const first = rng.pick(data.actors.names[sex]);
  return `${first} ${rng.pick(data.actors.names.last)}`;
}

// The HTML input over the art's name box. It takes the field's own font, size and colour, and the field's own limit on
// what a player types
function makeBox() {
  const field = part("name", "first");
  field.visible = false;
  const box = document.createElement("input");
  box.id = "name-box";
  box.type = "text";
  box.autocomplete = "off";
  box.spellcheck = false;
  box.maxLength = field.def.maxlength ?? 19;
  box.setAttribute("aria-label", "Character name");
  box.style.fontFamily = field.def.font;
  box.style.color = field.def.color ?? FIRST_NAME_INK;
  document.body.append(box);
  return box;
}

// Puts the input over the name box now: the stage's pixels times the scale, from the canvas's place on the page
function placeBox() {
  const box = view?.box;
  if (!box) {
    return;
  }
  const on = view.shown === "name";
  box.hidden = !on;
  if (!on) {
    return;
  }
  const field = part("name", "first");
  const { x, y, width, height } = field.box;
  const from = field.toGlobal({ x, y });
  const to = field.toGlobal({ x: x + width, y: y + height });
  const canvas = page.app.canvas.getBoundingClientRect();
  const across = canvas.width / page.app.screen.width;
  const down = canvas.height / page.app.screen.height;
  const wide = (to.x - from.x) * across;
  const high = (to.y - from.y) * down;
  const size = field.def.size * page.scale;
  const style = box.style;
  style.left = `${canvas.left + from.x * across}px`;
  style.top = `${canvas.top + from.y * down}px`;
  style.width = `${wide}px`;
  style.height = `${high}px`;
  style.lineHeight = `${high}px`;
  style.fontSize = `${size}px`;
  // Text starts after the field's two-pixel gutter
  style.paddingLeft = `${2 * page.scale}px`;
  style.boxSizing = "border-box";
}

function setSex(sex) {
  const changed = view.sex !== sex;
  view.sex = sex;
  for (const each of SEXES) {
    goto(part("name", each), each === sex ? "on" : "off");
  }
  if (changed) {
    view.box.value = randomName(sex);
  }
  record("sex", { sex });
}

function setupName() {
  view.box = makeBox();
  view.box.value = randomName(view.sex);
  for (const sex of SEXES) {
    goto(part("name", sex), sex === view.sex ? "on" : "off");
    wire(part("name", sex), {
      press: () => {
        click();
        setSex(sex);
      },
    });
  }
  wire(part("name", "randomBtn"), {
    press: () => {
      view.box.value = randomName(view.sex);
      click();
    },
  });
  wire(part("name", "nextBtn"), {
    press: () => {
      view.name = view.box.value;
      click();
      showPage("appearance");
      showLook();
    },
  });
}

// ---------- Appearance page ----------

// The choices of each appearance row: { name, value } in the order the original lists them
function makeLists() {
  const look = data.actors.appearance;
  const colour = (each) => ({ name: each.name, value: `0x${each.colour}` });
  return {
    hair: look.hairStyles.map((name) => ({ name, value: name })),
    hairColour: look.hairColours.map(colour),
    skinColour: look.skins.map(colour),
    facialHair: look.facialHair.map((name) => ({ name, value: name })),
  };
}

function lookNow() {
  const look = { sex: view.sex };
  for (const [row, key] of Object.entries(LOOK_ROWS)) {
    look[key] = view.lists[row][view.pick[row]].value;
  }
  return look;
}

// The head, neck and the rows' words as the choices now stand (updateCharCreateAppearance F4:11242). Facial hair is a
// man's: a woman's row and its heading go, and her choice is none
function showLook() {
  const female = view.sex === "female";
  const appearance = part("appearance");
  appearance.child("facialHairText").visible = !female;
  appearance.child("facialHair").visible = !female;
  if (female) {
    view.pick.facialHair = 0;
  }
  for (const row of Object.keys(LOOK_ROWS)) {
    setText(appearance.child(row).child("txt"), capital(view.lists[row][view.pick[row]].name));
  }
  decorateMenuHead(appearance, lookNow());
}

function stepRow(row, by) {
  const next = view.pick[row] + by;
  if (next < 0 || next >= view.lists[row].length) {
    return;
  }
  view.pick[row] = next;
  showLook();
  click();
}

function randomLook() {
  for (const row of Object.keys(LOOK_ROWS)) {
    view.pick[row] = rng.random(view.lists[row].length);
  }
  if (view.sex === "female") {
    view.pick.facialHair = 0;
  }
  showLook();
  click();
}

function setupAppearance() {
  for (const row of Object.keys(LOOK_ROWS)) {
    wire(part("appearance", row, "upBtn"), { press: () => stepRow(row, 1) });
    wire(part("appearance", row, "downBtn"), { press: () => stepRow(row, -1) });
  }
  wire(part("appearance", "randomBtn"), { press: randomLook });
  stepTo("appearance", "name", "prevBtn");
  wire(part("appearance", "nextBtn"), {
    press: () => {
      click();
      showPage("occupation");
    },
  });
  showLook();
}

// ---------- Occupation page ----------

// The occupation buttons in the order the original lists them: its for-in walks the table from the last entry to the
// first
function makeOccupations() {
  return [...data.actors.occupations].reverse();
}

function skillTitle(name) {
  return upper(data.actors.skills[name].title);
}

// The panel on the right of the page says who an occupation is (charCreateUpdatePreMade F4:11094). It stays on the last
// one pointed at when the pointer leaves
function describeOccupation(occupation) {
  const panel = part("occupation");
  setText(panel.child("preMadeName"), upper(occupation.name));
  occupation.skills.forEach((skill, index) => {
    setText(panel.child(`skill${index + 1}`), skillTitle(skill));
  });
  setText(panel.child("desc"), occupation.desc);
}

function pickOccupation(occupation) {
  view.current = occupation.ref;
  view.occupations.forEach((each, index) => {
    const button = part("occupation", `premade${index}`);
    const on = each === occupation;
    setColor(button.child("txt"), on ? OCCUPATION_INK.over : OCCUPATION_INK.off);
    goto(button, on ? "over" : "off");
  });
  click();
  record("occupation", { ref: occupation.ref });
}

function setupOccupations() {
  view.occupations.forEach((occupation, index) => {
    const button = part("occupation", `premade${index}`);
    setText(button.child("txt"), upper(occupation.name));
    wire(button, {
      press: (touched) => {
        if (touched) {
          describeOccupation(occupation);
        }
        pickOccupation(occupation);
      },
      over: () => describeOccupation(occupation),
    });
  });
  wire(part("occupation", "createCustom"), {
    press: () => {
      click();
      showPage("attributes");
    },
  });
  stepTo("occupation", "appearance", "prevBtn");
  wire(part("occupation", "nextBtn"), { press: finishOccupation });
}

// FINISH on the occupation page: the picked occupation's attributes and skills, or the box that asks for one
function finishOccupation() {
  if (!view.current) {
    showDialog(NO_OCCUPATION.heading, NO_OCCUPATION.body, [{ button: "button3", words: "OK", action: closeDialog }]);
    return;
  }
  const occupation = view.occupations.find((each) => each.ref === view.current);
  const attributes = Object.fromEntries(ATTRIBUTES.map((name) => [name, occupation[name]]));
  launch(attributes, occupation.skills);
}

// ---------- Attributes page ----------

function describeAttribute(name) {
  setText(part("attributes", "desc"), name ? data.actors.attributes[name].desc : "");
}

function showAttributes() {
  for (const name of ATTRIBUTES) {
    setText(part("attributes", name, "txt"), String(view.attrs[name]));
  }
  setText(part("attributes", "pointsRem"), String(view.remaining));
}

function changeAttribute(name, by) {
  const now = view.attrs[name];
  const allowed = by > 0 ? now < constant("attributeStartMax") && view.remaining > 0 : now > 1;
  if (!allowed) {
    return;
  }
  view.attrs[name] = now + by;
  view.remaining -= by;
  showAttributes();
  click();
}

function setupAttributes() {
  setText(part("attributes", "desc"), "");
  for (const name of ATTRIBUTES) {
    const row = part("attributes", name);
    const over = () => describeAttribute(name);
    const out = () => describeAttribute(null);
    for (const [button, by] of [
      ["up", 1],
      ["down", -1],
    ]) {
      wire(row.child(button), {
        press: (touched) => {
          if (touched) {
            describeAttribute(name);
          }
          changeAttribute(name, by);
        },
        over,
        out,
      });
    }
    wire(row.child("backing"), { press: (touched) => touched && describeAttribute(name), over, out });
  }
  showAttributes();
  stepTo("attributes", "occupation", "prevBtn");
  wire(part("attributes", "nextBtn"), {
    press: () => {
      click();
      showPage("skills");
      showSkills();
    },
  });
}

// ---------- Skills page ----------

// A skill's number: its own value and 1.6 for each point of its attribute past 5 (getAttributeMod F4:12897), and the
// bonus when it is marked (updateSkillButtons F4:11487)
function skillNumber(name) {
  const base = constant("skillBase");
  const attribute = view.attrs[data.actors.skills[name].attribute];
  const value = Math.round(base + attribute * constant("attributeMod") - constant("attributeBase"));
  return view.marked.has(name) ? value + constant("selectedSkillBonus") : value;
}

function showSkills() {
  for (const name of data.actors.lists.allSkills) {
    const row = part("skills", name);
    setText(row.child("num"), String(skillNumber(name)));
    row.child("marked").visible = view.marked.has(name);
  }
}

function describeSkill(name) {
  setText(part("skills", "desc"), name ? data.actors.skills[name].desc : "");
}

// A skill row was pressed: it takes a mark while fewer than four are marked, or gives its mark back
function toggleSkill(name) {
  if (view.marked.has(name)) {
    view.marked.delete(name);
  } else if (view.marked.size < constant("numSelectedSkills")) {
    view.marked.add(name);
  } else {
    return;
  }
  showSkills();
  click();
}

function setupSkills() {
  setText(part("skills", "desc"), "");
  for (const name of data.actors.lists.allSkills) {
    const row = part("skills", name);
    setText(row.child("txt"), data.actors.skills[name].title);
    row.child("marked").visible = false;
    wire(row.child("backing"), {
      press: (touched) => {
        if (touched) {
          describeSkill(name);
        }
        toggleSkill(name);
      },
      over: () => describeSkill(name),
      out: () => describeSkill(null),
    });
  }
  stepTo("skills", "attributes", "prevBtn");
  wire(part("skills", "nextBtn"), { press: finishCustom });
}

// NEXT on the last page: a build with points or marks left over asks first, and goes on if the player says so
function finishCustom() {
  if (view.marked.size < constant("numSelectedSkills") || view.remaining > 0) {
    showDialog(UNSPENT.heading, UNSPENT.body, [
      {
        button: "button1",
        words: "YES",
        action: () => {
          closeDialog();
          launchCustom();
        },
      },
      { button: "button2", words: "NO", action: closeDialog },
    ]);
    return;
  }
  launchCustom();
}

function launchCustom() {
  launch({ ...view.attrs }, [...view.marked]);
}

// ---------- Dialogs ----------

function closeDialog() {
  const box = view?.dialog;
  if (!box) {
    return;
  }
  view.dialog = null;
  fadeOutBox(box, DIALOG.out);
}

function dialogButton(box, name, words, action) {
  const button = box.child(name);
  button.visible = true;
  setText(button.child("buttonText"), words);
  button.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

// The box over the pages (showDialogBox F4:20000) with a heading, words and its buttons ({ button, words, action }
// each). It shuts everything behind it off until a button is pressed
function showDialog(heading, body, buttons) {
  const box = page.attach("dialogBox", dialogDepth, DIALOG_CLIP);
  box.position.set(DIALOG.x, DIALOG.y);
  view.dialog = box;
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), heading);
  setText(box.child("textBoxes").child("bodyText"), body);
  for (const { button, words, action } of buttons) {
    dialogButton(box, button, words, action);
  }
  fadeInBox(box, DIALOG.fade);
  record("dialog", { heading });
}

// ---------- Launching ----------

// The story the choices make (newCharacter F4:11499 and setPreMade F4:11106 or confirmSkillSelection F4:11449): the
// attributes as picked, and +10 on each of the four skills
function storyOptions(attributes, skills) {
  const bonus = constant("selectedSkillBonus");
  return {
    name: view.name,
    sex: view.sex,
    look: lookNow(),
    attributes,
    skills: Object.fromEntries(skills.map((name) => [name, constant("skillBase") + bonus])),
    ...view.options,
    touch: page.touch,
  };
}

// charCreateLaunch (F4:11424): the story is made, saved to its slot, and the intro takes over. The world itself starts
// when the intro ends
function launch(attributes, skills) {
  if (!view || view.launched) {
    return;
  }
  view.launched = true;
  const made = storyOptions(attributes, skills);
  rng.seed();
  input.clear();
  world.reset();
  light.reset();
  newStory(made);
  record("launch", { slot: made.slot, name: made.name, attributes, skills });
  click();
  savePoint("create");
  // The pages go before the intro comes, as the original removes its clip first
  leave();
  page.show("intro");
}

// ---------- The screen ----------

function wireQuit() {
  const quit = view.clip.child("quitToMenu");
  wire(quit, {
    press: () => {
      record("quit");
      page.show("menu");
    },
    over: () => tween(quit, "alpha", QUIT_ALPHA.over, QUIT_ALPHA.seconds),
    out: () => tween(quit, "alpha", QUIT_ALPHA.out, QUIT_ALPHA.seconds),
  });
}

function newView(clip, options) {
  const { slot = 0, mode = "survivor", hardcore = false, headshots = false } = options;
  return {
    clip,
    shown: null,
    sex: "male",
    name: "",
    box: null,
    options: { slot, mode, hardcore, headshots },
    pick: { hair: 0, hairColour: 0, skinColour: 0, facialHair: 0 },
    lists: makeLists(),
    occupations: makeOccupations(),
    current: "",
    attrs: Object.fromEntries(ATTRIBUTES.map((name) => [name, constant("attributeBase")])),
    remaining: constant("attributePointsMax"),
    marked: new Set(),
    dialog: null,
    tapped: null,
    busy: false,
    launched: false,
  };
}

function leave() {
  if (!view) {
    return;
  }
  const gone = view;
  view = null;
  gone.box?.remove();
  for (const node of [gone.clip.child("quitToMenu"), gone.dialog]) {
    if (node && !node.destroyed) {
      stopTweens(node);
    }
  }
  page.detach(DIALOG_CLIP);
  page.detach(CLIP);
  record("close");
}

const CREATE_SCREEN = {
  async enter(owner, options = {}) {
    await page.lib.need([page.lib.exported(CLIP)]);
    const clip = page.attach(CLIP, depth, CLIP);
    view = newView(clip, options);
    for (const name of Object.values(PAGES)) {
      clip.child(name).visible = false;
    }
    setupName();
    setupAppearance();
    setupOccupations();
    setupAttributes();
    setupSkills();
    wireQuit();
    showPage("name");
    view.box.focus({ preventScroll: true });
    record("open", { ...view.options });
  },
  leave,
  step: placeBox,
};

export { CREATE_SCREEN };

export function initCreate(owner, band, dialogBand) {
  page = owner;
  depth = band;
  dialogDepth = dialogBand;
}

export const create = {
  get active() {
    return view !== null;
  },
  log,
};

// Helpers for page.py checks
export const createDebug = {
  createState() {
    return (
      view && {
        page: view.shown,
        sex: view.sex,
        name: view.box?.value,
        stored: view.name,
        pick: { ...view.pick },
        lookNow: lookNow(),
        current: view.current,
        attrs: { ...view.attrs },
        remaining: view.remaining,
        marked: [...view.marked],
        dialog: Boolean(view.dialog),
        options: { ...view.options },
        launched: view.launched,
      }
    );
  },

  createLog: () => log.map((each) => ({ ...each })),

  // Where the middle of a part is on the window, for a click: a page name and a path like "appearance", "hair.upBtn"
  createPoint(pageName, path = "") {
    let node = view.clip.child(PAGES[pageName] ?? pageName);
    for (const step of path.split(".").filter(Boolean)) {
      node = node.child(step);
    }
    const box = node.getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: canvas.left + (box.x + box.width / 2) * (canvas.width / page.app.screen.width),
      y: canvas.top + (box.y + box.height / 2) * (canvas.height / page.app.screen.height),
    };
  },

  // The name input as the page has it now
  createBox() {
    const box = view?.box;
    if (!box) {
      return null;
    }
    const rect = box.getBoundingClientRect();
    return {
      hidden: box.hidden,
      value: box.value,
      focused: document.activeElement === box,
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    };
  },
};
