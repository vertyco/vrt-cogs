// The lobby: a menu of game cards. Texas Hold'em is the banner across the top and every other game a card under it,
// each a button with the game's painting, its name and the faces of the people at its table in this window. The Slots
// card shows the live jackpot too. The people standing in the lobby show along the bottom.
import { GAMES, make, money } from "./format.js";

// The menu's order. The first is the banner across the top
export const CARDS = ["holdem", "blackjack", "craps", "slots", "allin", "war", "hilo", "double", "coin", "cups", "dice"];
// A menu narrower than this has 2 cards across, a wider one 5
const NARROW = 560;
// How many pictures a table's card shows before "+N", and how many the row of people in the lobby does
const TABLE_FACES = 3;
const CROWD_FACES = 8;
// A long name is cut to this many visible characters
export const NAME_MAX = 12;

// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

export class Lobby {
  constructor(scroller, menu, onPick) {
    this.scroller = scroller;
    this.menu = menu;
    this.onPick = onPick;
    this.buttons = {};
    // Under the menu, outside what scrolls: the people standing in the lobby
    this.foot = scroller.parentElement.querySelector(".lobby-foot");
    this.crowd = this.foot.querySelector(".lobby-crowd");
    // The cards are made once and only changed in place after, since a card rebuilt between a press and its
    // release loses the tap
    CARDS.forEach((key, index) => this.addCard(key, index === 0));
    new ResizeObserver(() => this.layout()).observe(scroller);
  }

  addCard(key, banner) {
    const node = make("button", banner ? "game-card banner" : "game-card");
    node.type = "button";
    node.dataset.key = key;
    const art = make("img", "card-art");
    art.src = `art/cards/${key}.jpg`;
    art.alt = "";
    art.draggable = false;
    const faces = make("span", "faces");
    faces.hidden = true;
    const label = make("span", "label");
    node.append(art, faces, label);
    // The Slots pot goes under the name in the card's band
    if (key === "slots") {
      this.pot = make("span", "jackpot");
      this.pot.hidden = true;
      label.append(this.pot);
    }
    node.addEventListener("click", () => this.onPick(key));
    this.menu.append(node);
    this.buttons[key] = { node, label, faces };
  }

  // The Slots pot on its card. A jackpot can come several times a second, so only the words change
  showJackpot(amount) {
    const words = typeof amount === "number" ? `Jackpot ${money(amount)}` : "";
    if (this.pot.textContent !== words) {
      this.pot.textContent = words;
    }
    this.pot.hidden = !words;
  }

  // The strip of people under the menu shows only when someone stands in the lobby, and the page's messages stand on
  // it, not over its faces. The grid is 2 cards across on a narrow menu and 5 on a wide one
  layout() {
    if (!this.scroller.clientWidth) {
      return;
    }
    this.foot.hidden = this.crowd.hidden;
    const app = this.foot.parentElement;
    if (this.foot.hidden) {
      app.style.removeProperty("--lobby-foot");
    } else {
      app.style.setProperty("--lobby-foot", `${this.foot.offsetHeight}px`);
    }
    this.menu.classList.toggle("narrow", this.menu.clientWidth < NARROW);
  }

  // Names, closed games, games the player's access doesn't reach, and who is at each table. `faces` says who is
  // where, `statusOf(id)` what the hub's people list says they're doing, and `awayOf(id)` whether it says they're away
  render(casino, me, faces = {}, statusOf = () => "", awayOf = () => false) {
    const look = { statusOf, awayOf };
    for (const [key, { node, label, faces: box }] of Object.entries(this.buttons)) {
      const game = casino ? casino.games[key] : null;
      const reason = blockedBecause(casino, game, me);
      node.classList.toggle("blocked", Boolean(reason));
      // The names come from the bot, so a card has none until the casino arrives
      showLabel(label, game ? game.name : "", reason);
      if (key === "slots" && this.pot.parentElement !== label) {
        label.append(this.pot);
      }
      node.setAttribute("aria-label", game ? `${game.name}${reason ? `: ${reason}` : ""}` : GAMES[key]);
      const people = faces[key] || [];
      box.hidden = !people.length;
      showFaces(box, people, TABLE_FACES, "span", look);
    }
    const standing = faces.lobby || [];
    const wasHidden = this.crowd.hidden;
    this.crowd.hidden = !standing.length;
    showFaces(this.crowd, standing, CROWD_FACES, "button", look);
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

// A name cut to `most` visible characters (NAME_MAX unless a place needs it shorter), never splitting one
export function shortName(name, most = NAME_MAX) {
  const value = String(name ?? "");
  const letters = characters(value);
  return letters.length > most ? `${letters.slice(0, most - 1).join("")}…` : value;
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
