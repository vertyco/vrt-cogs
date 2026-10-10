// The lobby: the walk-in casino floor. Each table in the picture is a button, with its medallion bobbing over it
// and a badge counting the people at that table in this window.
import { make } from "./format.js";

// The picture is 1536 x 1024. Where each table sits in it, in pixels: the point the medallion's bottom floats at
// (the approved mockup's), and the box people tap. A box covers the table top, not its base, since the
// medallions in front float over the bases behind them
const ART_WIDTH = 1536;
const ART_HEIGHT = 1024;
const STATIONS = {
  allin: { icon: [768, 128], box: [671, 137, 880, 325], row: "back" },
  hilo: { icon: [491, 305], box: [378, 317, 605, 466], row: "back" },
  double: { icon: [1073, 290], box: [961, 294, 1188, 466], row: "back" },
  blackjack: { icon: [292, 462], box: [92, 468, 491, 575], row: "middle" },
  craps: { icon: [771, 438], box: [513, 440, 1028, 585], row: "middle" },
  war: { icon: [1270, 474], box: [1092, 479, 1447, 575], row: "middle" },
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
    this.hint = scroller.querySelector(".swipe-hint");
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
    const count = make("span", "count");
    count.hidden = true;
    medallion.append(icon, count);
    const label = make("span", "label");
    node.append(shadow, medallion, label);
    node.addEventListener("click", () => this.onPick(key));
    node.addEventListener("pointerenter", () => node.classList.add("lit"));
    node.addEventListener("pointerleave", () => node.classList.remove("lit"));
    this.floor.append(node);
    this.buttons[key] = { node, label, count };
  }

  // The picture fills the lobby without stretching. What doesn't fit pans with a swipe, starting in the middle
  // across and at the top down, where the slot machine's medallion floats. When it pans sideways, a strip under
  // the floor says so
  layout() {
    const width = this.scroller.clientWidth;
    let height = this.scroller.clientHeight;
    if (!width || !height) {
      return;
    }
    const ratio = ART_WIDTH / ART_HEIGHT;
    const wide = width / height >= ratio;
    if (this.hint) {
      this.hint.hidden = wide;
      height -= wide ? 0 : this.hint.offsetHeight;
    }
    const floorWidth = wide ? width : height * ratio;
    const floorHeight = wide ? width / ratio : height;
    this.floor.style.width = `${floorWidth}px`;
    this.floor.style.height = `${floorHeight}px`;
    const size = `${width}x${height}`;
    if (size !== this.size) {
      this.size = size;
      this.scroller.scrollLeft = (floorWidth - width) / 2;
      this.scroller.scrollTop = 0;
    } else if (this.pan) {
      [this.scroller.scrollLeft, this.scroller.scrollTop] = this.pan;
    }
  }

  // Names, closed games, games the player's access doesn't reach, and how many people are at each table
  render(casino, counts, me) {
    for (const [key, { node, label, count }] of Object.entries(this.buttons)) {
      const game = casino ? casino.games[key] : null;
      const reason = blockedBecause(casino, game, me);
      node.classList.toggle("blocked", Boolean(reason));
      label.replaceChildren(make("span", "", game ? game.name : key));
      if (reason) {
        label.append(make("span", "note", reason));
      }
      node.setAttribute("aria-label", game ? `${game.name}${reason ? `: ${reason}` : ""}` : key);
      const people = counts[key] || 0;
      count.hidden = !people;
      count.textContent = String(people);
    }
  }
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
