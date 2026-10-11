// The lobby: the walk-in casino floor. Each table in the picture is a button, with its medallion bobbing over it
// and the faces of the people at that table in this window. The people standing in the lobby show along the bottom.
import { make } from "./format.js";

// The picture is 1536 x 1024. Where each table sits in it, in pixels: the point the medallion's bottom floats at
// (the approved mockup's), and the box people tap. A box covers the table top, not its base, since the
// medallions in front float over the bases behind them. `faces` is which way the faces of the people at a table hang
// from its medallion when a neighbour's table is close on the other side (Hi-Lo to Blackjack's right, Double or
// Nothing to War's left)
const ART_WIDTH = 1536;
const ART_HEIGHT = 1024;
const STATIONS = {
  allin: { icon: [768, 128], box: [671, 137, 880, 325], row: "back" },
  hilo: { icon: [491, 305], box: [378, 317, 605, 466], row: "back" },
  double: { icon: [1073, 290], box: [961, 294, 1188, 466], row: "back" },
  blackjack: { icon: [292, 462], box: [92, 468, 491, 575], row: "middle", faces: "left" },
  craps: { icon: [771, 438], box: [513, 440, 1028, 585], row: "middle" },
  war: { icon: [1270, 474], box: [1092, 479, 1447, 575], row: "middle", faces: "right" },
  coin: { icon: [308, 712], box: [140, 712, 477, 967], row: "front" },
  cups: { icon: [770, 718], box: [587, 715, 952, 975], row: "front" },
  dice: { icon: [1230, 712], box: [1060, 710, 1398, 963], row: "front" },
};
// Medallions further back are smaller, as a share of the picture's width
const ICON_SIZE = { back: 0.048, middle: 0.058, front: 0.068 };
// The All In slot machine's cabinet at the back, where the jackpot light pulses
const JACKPOT = [685, 138, 848, 394];
// Each medallion's shadow on the floor, as shares of the medallion's width: how wide, how tall, and how far below
// the medallion's bottom its middle sits
const SHADOW = { width: 0.7, height: 0.16, below: 0.14 };
// How far down the picture the lowest medallion floats, as a share of its height. A wide screen that cuts the floor
// above this hides a whole row of tables, so the swipe strip shows
const LOWEST_ICON = Math.max(...Object.values(STATIONS).map((station) => station.icon[1])) / ART_HEIGHT;
const HINTS = { across: "← swipe to look around →", down: "↑ swipe to look around ↓" };
// How many pictures a table's sign shows before "+N", and how many the row of people in the lobby does
const TABLE_FACES = 3;
const CROWD_FACES = 8;
// A long name is cut to this many visible characters
const NAME_MAX = 12;

// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

function percent(value, whole) {
  return `${(value / whole) * 100}%`;
}

export class Lobby {
  constructor(scroller, floor, onPick) {
    this.scroller = scroller;
    this.floor = floor;
    this.onPick = onPick;
    this.buttons = {};
    this.size = null;
    this.pan = null;
    this.floorSize = null;
    // Under the floor, outside what pans: the people standing in the lobby, and the hint to swipe
    this.foot = scroller.parentElement.querySelector(".lobby-foot");
    this.hint = this.foot.querySelector(".swipe-hint");
    this.crowd = this.foot.querySelector(".lobby-crowd");
    this.addJackpot();
    Object.entries(STATIONS).forEach(([key, station], index) => this.addStation(key, station, index));
    new ResizeObserver(() => this.layout()).observe(scroller);
    // A hidden lobby forgets where it was panned to, so remember it to put back on the way in
    scroller.addEventListener("scroll", () => {
      if (scroller.clientWidth) {
        this.pan = [scroller.scrollLeft, scroller.scrollTop];
      }
    });
  }

  addJackpot() {
    const [left, top, right, bottom] = JACKPOT;
    const glow = make("span", "jackpot");
    Object.assign(glow.style, {
      left: percent(left, ART_WIDTH),
      top: percent(top, ART_HEIGHT),
      width: percent(right - left, ART_WIDTH),
      height: percent(bottom - top, ART_HEIGHT),
    });
    this.floor.append(glow);
  }

  addStation(key, station, index) {
    const [left, top, right, bottom] = station.box;
    const node = make("button", "station");
    node.type = "button";
    node.dataset.key = key;
    if (station.faces) {
      node.dataset.faces = station.faces;
    }
    Object.assign(node.style, {
      left: percent(left, ART_WIDTH),
      top: percent(top, ART_HEIGHT),
      width: percent(right - left, ART_WIDTH),
      height: percent(bottom - top, ART_HEIGHT),
    });
    // The medallion's point is placed relative to the table's box, so it moves with it
    const medallion = make("span", "medallion");
    Object.assign(medallion.style, {
      left: percent(station.icon[0] - left, right - left),
      top: percent(station.icon[1] - top, bottom - top),
      width: `${(ICON_SIZE[station.row] * ART_WIDTH * 100) / (right - left)}%`,
    });
    // The shadow stays on the floor under the medallion's point and shrinks as the medallion bobs up
    const iconWidth = ICON_SIZE[station.row] * ART_WIDTH;
    const shadow = make("span", "medallion-shadow");
    Object.assign(shadow.style, {
      left: medallion.style.left,
      top: percent(station.icon[1] + SHADOW.below * iconWidth - top, bottom - top),
      width: percent(SHADOW.width * iconWidth, right - left),
      height: percent(SHADOW.height * iconWidth, bottom - top),
    });
    node.style.setProperty("--bob-delay", `${-index * 0.37}s`);
    const icon = make("img");
    icon.src = `art/icons/${key}.png`;
    icon.alt = "";
    icon.draggable = false;
    const faces = make("span", "faces");
    faces.hidden = true;
    medallion.append(icon, faces);
    const label = make("span", "label");
    node.append(shadow, medallion, label);
    node.addEventListener("click", () => this.onPick(key));
    node.addEventListener("pointerenter", () => node.classList.add("lit"));
    node.addEventListener("pointerleave", () => node.classList.remove("lit"));
    this.floor.append(node);
    this.buttons[key] = { node, label, faces };
  }

  // The picture fills the lobby without stretching. What doesn't fit pans with a swipe, starting in the middle
  // across and at the top down, where the slot machine's medallion floats. Under it, a strip holds the people
  // standing in the lobby, and says so when the picture pans sideways or a row of tables is out of sight below.
  // The strip takes its room from the floor, so it never covers a table
  layout() {
    const width = this.scroller.clientWidth;
    if (!width || !this.scroller.clientHeight) {
      return;
    }
    // The room the floor and the strip share, whatever the strip is showing now
    this.foot.hidden = false;
    const full = this.scroller.clientHeight + this.foot.offsetHeight;
    const crowd = this.crowd.hidden ? 0 : this.crowd.offsetHeight;
    const ratio = ART_WIDTH / ART_HEIGHT;
    const wide = width / full >= ratio;
    const hidesARow = (width / ratio) * LOWEST_ICON > full - crowd;
    this.hint.hidden = wide && !hidesARow;
    this.hint.textContent = wide ? HINTS.down : HINTS.across;
    this.foot.hidden = this.hint.hidden && this.crowd.hidden;
    // The page's messages stand on the strip, not over its faces
    const app = this.foot.parentElement;
    if (this.foot.hidden) {
      app.style.removeProperty("--lobby-foot");
    } else {
      app.style.setProperty("--lobby-foot", `${this.foot.offsetHeight}px`);
    }
    const height = this.scroller.clientHeight;
    const floorWidth = wide ? width : height * ratio;
    const floorHeight = wide ? width / ratio : height;
    this.floor.style.width = `${floorWidth}px`;
    this.floor.style.height = `${floorHeight}px`;
    const size = `${width}x${full}`;
    if (size !== this.size) {
      this.size = size;
      this.scroller.scrollLeft = (floorWidth - width) / 2;
      this.scroller.scrollTop = 0;
    } else if (this.pan && this.floorSize) {
      // The strip coming or going changes the floor's size under the same screen, so the view keeps its middle
      const [wasWidth, wasHeight] = this.floorSize;
      this.scroller.scrollLeft = ((this.pan[0] + width / 2) / wasWidth) * floorWidth - width / 2;
      this.scroller.scrollTop = ((this.pan[1] + height / 2) / wasHeight) * floorHeight - height / 2;
    }
    // The scroll event comes a frame later, and a change of size in that frame must start from here
    this.pan = [this.scroller.scrollLeft, this.scroller.scrollTop];
    this.floorSize = [floorWidth, floorHeight];
  }

  // Names, closed games, games the player's access doesn't reach, and who is at each table. `faces` says who is
  // where, `statusOf(id)` what the hub's people list says they're doing, and `awayOf(id)` whether it says they're away
  render(casino, me, faces = {}, statusOf = () => "", awayOf = () => false) {
    const look = { statusOf, awayOf };
    for (const [key, { node, label, faces: box }] of Object.entries(this.buttons)) {
      const game = casino ? casino.games[key] : null;
      const reason = blockedBecause(casino, game, me);
      node.classList.toggle("blocked", Boolean(reason));
      showLabel(label, game ? game.name : key, reason);
      node.setAttribute("aria-label", game ? `${game.name}${reason ? `: ${reason}` : ""}` : key);
      const people = faces[key] || [];
      box.hidden = !people.length;
      showFaces(box, people, TABLE_FACES, "span", look);
    }
    const standing = faces.lobby || [];
    const wasHidden = this.crowd.hidden;
    this.crowd.hidden = !standing.length;
    showFaces(this.crowd, standing, CROWD_FACES, "button", look);
    // The strip takes its room from the floor
    if (wasHidden !== this.crowd.hidden) {
      this.layout();
    }
  }
}

// A table's name, and why it can't be played under it. The lobby is drawn again on every people list, up to 4 times
// a second, so the label inside the table's button is only rewritten when what it says changes
function showLabel(label, name, reason) {
  const shows = JSON.stringify([name, reason]);
  if (label.dataset.shows === shows) {
    return;
  }
  label.dataset.shows = shows;
  label.replaceChildren(make("span", "", name));
  if (reason) {
    label.append(make("span", "note", reason));
  }
}

// The faces in `box`: up to `most` pictures, then "+N". Table faces sit inside the table's button, so they are
// spans that show a name on hover; the lobby's are buttons that say it on a tap too. The pictures are only rebuilt
// when who is shown changes, since a face rebuilt between a press and its release loses the tap. Names, statuses
// and dimming follow the hub's list in place
function showFaces(box, people, most, tag, { statusOf, awayOf }) {
  const shown = people.slice(0, most);
  const look = JSON.stringify([people.length, shown.map((person) => [person.id, person.name, person.avatar])]);
  if (box.dataset.look !== look) {
    box.dataset.look = look;
    box.replaceChildren(...shown.map((person) => newFace(person, tag)));
    if (people.length > shown.length) {
      box.append(make("span", "more", `+${people.length - shown.length}`));
    }
  }
  for (const face of box.querySelectorAll(".face")) {
    const away = Boolean(awayOf(face.dataset.id));
    face.classList.toggle("away", away);
    // The name sits between marks that keep a right-to-left name from turning the sentence around
    const name = `\u2068${shortName(face.dataset.name)}\u2069`;
    const doing = away ? "Away" : statusOf(face.dataset.id);
    const words = doing ? `${name}: ${doing}` : name;
    // Writing the same title again can close a tooltip that is showing
    if (face.title !== words) {
      face.title = words;
      if (face.tagName === "BUTTON") {
        face.setAttribute("aria-label", words);
      }
    }
  }
}

function shortName(name) {
  const letters = characters(name);
  return letters.length > NAME_MAX ? `${letters.slice(0, NAME_MAX - 1).join("")}…` : name;
}

function newFace(person, tag) {
  const face = make(tag, "face");
  face.dataset.id = person.id;
  face.dataset.name = person.name;
  // The first letter of the name stands in for a picture that can't be had
  const letter = document.createTextNode(characters(person.name)[0]?.toUpperCase() ?? "");
  if (person.avatar) {
    const img = make("img");
    img.alt = "";
    img.draggable = false;
    img.addEventListener("error", () => img.replaceWith(letter));
    img.src = person.avatar;
    face.append(img);
  } else {
    face.append(letter);
  }
  if (tag === "button") {
    face.type = "button";
    face.addEventListener("click", () => {
      face.dispatchEvent(new CustomEvent("face", { bubbles: true, detail: face.title }));
    });
  }
  return face;
}

// Why the player can't play a game right now, in a few words, or "" when they can
export function blockedBecause(casino, game, me) {
  if (!casino || !game) {
    return "";
  }
  if (!casino.open) {
    return "Closed";
  }
  if (!game.open) {
    return "Closed";
  }
  if (me && game.access > me.access) {
    return `Needs access ${game.access}`;
  }
  return "";
}
