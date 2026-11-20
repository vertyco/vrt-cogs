// The names over the penguins and the crate, and the word for what came out of a crate. They are page elements on top
// of the canvas, so they stay sharp on any screen. A name shows in the style its player wears, with their title as a
// small line under it.

const NAME_MAX = 13;
// The titles a player can wear, by the id the bot knows each by, as the words shown under their name
export const TITLES = {
  chilly: "Chill Penguin",
  waddler: "Pro Waddler",
  icebreaker: "Ice Breaker",
  bigfish: "Big Fish",
  royalty: "Ice Royalty",
  regular: "Ice Regular",
  fishfan: "Fish Fanatic",
  bouncer: "The Bouncer",
  sealslayer: "Seal Slayer",
  champion: "Champion",
};
// The name styles a player can wear, by the bot's ids. The page's styles draw each one as `.name-<id>`, on a dark plate
export const NAME_STYLES = ["rose", "ice", "sunset", "neon", "mint", "aurora", "lava", "gold"];
// A crate's tag says whose it is, so the name in it is cut shorter
const CRATE_NAME_MAX = 10;
// The word for what a crate held floats up over whoever opened it: for this long, this many pixels, starting this far
// above their name, and fading over the last share of its time. It keeps this far inside the screen's edges
const WORD_SECONDS = 1.2;
const WORD_RISE = 30;
const WORD_GAP = 24;
const WORD_FADE = 0.35;
const WORD_EDGE = 4;
// Two crates can't open closer together than one takes to fall, which is as long as a word shows
const WORDS = 2;
// What a crate can hold, as the word and the color of its tag
const POWER_WORDS = {
  shield: ["Shield!", "#7a48f0"],
  frost: ["Frost!", "#1486d1"],
  feast: ["Fish feast!", "#f0611a"],
};
// Names keep this many pixels between them
const NAME_GAP = 2;
// How quickly a name moves over to another spot: a share of the way per second, and never slower than this many pixels
// a second, so the end of the way doesn't drag on
const ROW_EASE = 16;
const MIN_SPEED = 300;
// What a name's spot rests on: its own place, or else the top (2 * n) or the bottom (2 * n + 1) of name n
const OWN = -1;
// A tag that gives way steps sideways off a name by at most this share of its own width, so it stays over its own thing
const SIDESTEP = 0.6;

// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

export function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

// The name as it shows, cut with an ellipsis when it is longer than `max` characters
export function fieldName(name, max = NAME_MAX) {
  const letters = characters(name);
  return letters.length > max ? `${letters.slice(0, max - 1).join("")}…` : name;
}

// The words of the title in a seat's looks ({kind: id}), or null with none worn or one this page doesn't know
export function titleOf(looks) {
  const id = looks?.title;
  return typeof id === "string" && Object.hasOwn(TITLES, id) ? TITLES[id] : null;
}

// The id of the name style in a seat's looks, or null with none worn or one this page doesn't know
export function nameStyleOf(looks) {
  return NAME_STYLES.includes(looks?.name) ? looks.name : null;
}

// A name between marks that keep a right-to-left name from turning the sentence around it
export function isolate(name) {
  return `⁨${name}⁩`;
}

// A name as an element in a name style, by its id, or plain with null. Names come from Discord, so they only ever go
// in as text. The style needs something dark behind it: `plate` puts the name on a plate of its own, for a light card
export function styledName(name, style, plate = false) {
  const text = document.createElement("span");
  text.className = style ? `styled-name name-${style}` : "styled-name";
  text.textContent = name;
  if (!plate || !style) {
    return text;
  }
  const box = document.createElement("span");
  box.className = "name-plate";
  box.append(text);
  return box;
}

// The two lines of a name tag, put into `tag`: the name and, under it, the title
export function tagLines(tag) {
  const name = document.createElement("span");
  const title = document.createElement("span");
  title.className = "tag-title";
  title.hidden = true;
  tag.append(name, title);
  return { name, title };
}

// Writes a name into a tag's lines, in its style (an id or null), with its title under it ("" for none)
export function fillTag(tag, lines, text, style, title) {
  // Names come from Discord, so they only ever go in as text
  lines.name.textContent = text;
  lines.name.className = style ? `tag-name name-${style}` : "tag-name";
  lines.title.textContent = title;
  lines.title.hidden = !title;
  tag.classList.toggle("styled", Boolean(style));
  tag.classList.toggle("titled", Boolean(title));
}

// The placed name that a name of `box`'s size at (left, top) would lie on, counting the gap around each as covered, or
// null. A placed name is { left, top, width, height, index }
function nameUnder(left, top, box, taken) {
  for (const other of taken) {
    const across = Math.min(left + box.width, other.left + other.width) - Math.max(left, other.left) + NAME_GAP;
    const down = Math.min(top + box.height, other.top + other.height) - Math.max(top, other.top) + NAME_GAP;
    if (across > 0 && down > 0) {
      return other;
    }
  }
  return null;
}

// Moves a name from its own top over each placed name it lies on, up or down, until it is clear. Gives { top, beside }
// with `beside` what the spot rests on, or null when the edge of the field comes first. `lowest` is the lowest top
// inside the field
function climb(left, own, box, taken, lowest, down) {
  let top = own;
  let beside = OWN;
  for (let other = nameUnder(left, top, box, taken); other; other = nameUnder(left, top, box, taken)) {
    top = down ? other.top + other.height + NAME_GAP : other.top - box.height - NAME_GAP;
    beside = other.index * 2 + (down ? 1 : 0);
    if (top < 0 || top > lowest) {
      return null;
    }
  }
  return { top, beside };
}

// Whether a tag that gives way may step from `left` to `side`: a short step, inside the field and onto no name
function mayStep(side, left, top, box, taken, width) {
  const short = Math.abs(side - left) <= box.width * SIDESTEP;
  return short && side >= 0 && side <= width - box.width && !nameUnder(side, top, box, taken);
}

// Where a tag that gives way goes instead of lying on a name: just clear of it, on the nearer side if it may.
// Otherwise it stays, and moves up or down as any name does
function sidestep(left, top, box, taken, width) {
  const other = nameUnder(left, top, box, taken);
  if (!other) {
    return left;
  }
  const before = other.left - NAME_GAP - box.width;
  const after = other.left + other.width + NAME_GAP;
  const near = left - before <= after - left ? before : after;
  const far = near === before ? after : before;
  if (mayStep(near, left, top, box, taken, width)) {
    return near;
  }
  return mayStep(far, left, top, box, taken, width) ? far : left;
}

// How far up a name is drawn this frame, moving from where it was drawn toward `aim`, the rise the layout gives it.
// Resting on the same thing as before, its spot is being carried along, and the name keeps up with it at once instead
// of trailing onto whatever pushes it. Moving over to another spot eases there
function easeRise(box, aim, beside, dt) {
  if (!Number.isFinite(box.rise)) {
    return aim;
  }
  const rise = beside === box.beside ? box.rise + aim - box.aim : box.rise;
  const left = aim - rise;
  const step = Math.max(Math.abs(left) * Math.min(1, dt * ROW_EASE), dt * MIN_SPEED);
  return step >= Math.abs(left) ? aim : rise + Math.sign(left) * step;
}

// Where each name goes, for boxes of { x, y, width, height, rise, aim, beside } centered on x, with y the top edge of
// the name's own spot, `rise` how far above that it was drawn last, or null for a name just come on, and `aim` and
// `beside` what this gave it last. A name is pulled inside the field and keeps its own spot when that touches no name
// already placed, or else moves up over the names it would lie on, or down under them at the top of the field. Names
// are placed from the lowest on the screen up, so a name being pushed only moves up over names below it, and each keeps
// clear of where the names before it are drawn, even those still on their way. One just come on is placed last, to fit
// in around the rest. A box with `gives` set is no player's name (the crate's tag): it is placed after every name, so
// it never moves one, and takes a step to the side when that is shorter than the move up or down. `dt` is the seconds
// since the last frame. Gives { x, rise, aim, beside } for each box, in the order they came in: `rise` is how far up
// to draw it now and `aim` where it is going, both negative for a name moved down, and `beside` says what its spot
// rests on
export function layoutNames(boxes, width, height, dt = 0) {
  const bottom = (box) => (Number.isFinite(box.rise) ? box.y - box.rise + box.height : -Number.MAX_VALUE);
  const order = boxes.map((box, index) => index).sort((a, b) => {
    const last = (boxes[a].gives ? 1 : 0) - (boxes[b].gives ? 1 : 0);
    return last || bottom(boxes[b]) - bottom(boxes[a]) || boxes[a].x - boxes[b].x;
  });
  const taken = [];
  const placed = [];
  for (const index of order) {
    const box = boxes[index];
    const lowest = height - box.height;
    const own = Math.max(0, Math.min(lowest, box.y));
    const inside = Math.min(width - box.width, Math.max(0, box.x - box.width / 2));
    const moved = climb(inside, own, box, taken, lowest, false) ?? climb(inside, own, box, taken, lowest, true);
    const aside = box.gives ? sidestep(inside, own, box, taken, width) : inside;
    const sideways = aside !== inside && (!moved || Math.abs(aside - inside) < Math.abs(moved.top - own));
    const left = sideways ? aside : inside;
    // Six names always fit somewhere on a phone, so a name lying on another is only for a field too small for them
    const { top, beside } = (sideways ? null : moved) ?? { top: own, beside: OWN };
    const aim = box.y - top;
    const rise = easeRise(box, aim, beside, dt);
    taken.push({ left, top: box.y - rise, width: box.width, height: box.height, index });
    placed[index] = { x: left + box.width / 2, rise, aim, beside };
  }
  return placed;
}

// A tag of the names' own look. `kind` names what else it is, for the page's styles, and `style` sets its look here
function newTag(layer, kind, style) {
  const tag = document.createElement("div");
  tag.className = kind ? `tag ${kind}` : "tag";
  tag.hidden = true;
  Object.assign(tag.style, style);
  layer.append(tag);
  return tag;
}

// One tag for each seat and one for the crate, on a page layer that fills the screen. The crate's is the last, and is
// placed among the names like one of them
export class NameTags {
  constructor(layer, seats) {
    this.layer = layer;
    this.tags = Array.from({ length: seats }, () => newTag(layer));
    // A seat's tag holds the name and, under it, the title. What each last showed, so a list that says the same
    // leaves its tag alone
    this.parts = this.tags.map((tag) => ({ ...tagLines(tag), shows: "" }));
    this.crate = seats;
    this.tags.push(newTag(layer, "crate", { background: "#e8413c", color: "#fff", fontSize: "11px" }));
    // The words in the air: each one's tag, the seat it floats over, the seconds it has shown (-1 for not showing), its
    // size, and the point it rises from, which is kept once its penguin has gone
    this.words = Array.from({ length: WORDS }, () => {
      const tag = newTag(layer, "word", { padding: "5px 10px", color: "#fff", fontSize: "14px" });
      return { tag, seat: 0, t: -1, width: 0, height: 0, x: 0, y: 0, placed: false };
    });
    this.wordNext = 0;
    // Each tag's size, which only changes with its words, how far up it shows now, and where the layout last put it.
    // `width` 0 is not measured yet, and `rise` null says the tag has only just come on. `x` is where the middle of a
    // tag that gives way is drawn, as it moves over to a step aside
    this.looks = this.tags.map(() => ({ width: 0, height: 0, rise: null, aim: 0, beside: OWN, x: 0 }));
    // The game's font arriving changes the size of every name
    document.fonts?.addEventListener("loadingdone", () => {
      for (const look of this.looks) {
        look.width = 0;
      }
    });
  }

  // `nemesis` is the id of this player's nemesis, or null. Whoever that is carries a mark, on this page alone
  setSeats(seats, mySeat, nemesis = null) {
    seats.forEach((seat, number) => {
      const tag = this.tags[number];
      const part = this.parts[number];
      const text = fieldName(seat.name);
      const style = nameStyleOf(seat.looks);
      const title = titleOf(seat.looks) ?? "";
      const foe = nemesis !== null && seat.kind === "human" && seat.id === nemesis;
      const shows = JSON.stringify([text, style, title, foe]);
      if (part.shows !== shows) {
        part.shows = shows;
        fillTag(tag, part, text, style, title);
        tag.classList.toggle("nemesis", foe);
        this.looks[number].width = 0;
      }
      tag.classList.toggle("you", number === mySeat);
      tag.classList.toggle("away", seat.away);
    });
  }

  // Names the crate after whoever paid for it. No name takes its tag away
  nameCrate(name) {
    const tag = this.tags[this.crate];
    // Names come from Discord, so they only ever go in as text
    const text = name ? `${fieldName(name, CRATE_NAME_MAX)}'s crate` : "";
    if (tag.textContent !== text) {
      tag.textContent = text;
      this.looks[this.crate].width = 0;
    }
  }

  // Floats the word for what a crate held up from over a seat's name. A thing this page has no word for says nothing
  say(seat, power) {
    if (!Object.hasOwn(POWER_WORDS, power)) {
      return;
    }
    const [text, color] = POWER_WORDS[power];
    const word = this.words[this.wordNext];
    this.wordNext = (this.wordNext + 1) % this.words.length;
    word.tag.className = `tag word ${power}`;
    word.tag.textContent = text;
    word.tag.style.background = color;
    word.tag.hidden = true;
    Object.assign(word, { seat, t: 0, width: 0, placed: false });
  }

  // Moves each word up and fades it out. It shows once its seat has a spot to rise from, and stays inside the screen
  placeWords(spots, dt) {
    for (const word of this.words) {
      if (word.t < 0) {
        continue;
      }
      word.t += dt;
      const k = word.t / WORD_SECONDS;
      const spot = spots[word.seat];
      if (spot) {
        word.x = spot.x;
        word.y = spot.y;
        word.placed = true;
      }
      if (k >= 1 || !word.placed) {
        word.t = k >= 1 ? -1 : word.t;
        word.tag.hidden = true;
        continue;
      }
      word.tag.hidden = false;
      if (!word.width) {
        word.width = word.tag.offsetWidth;
        word.height = word.tag.offsetHeight;
      }
      // Quick at first and slowing, so the word is read where it comes to rest
      const rise = WORD_RISE * (1 - (1 - k) * (1 - k));
      const most = this.layer.clientWidth - word.width - WORD_EDGE;
      const left = Math.max(WORD_EDGE, Math.min(most, word.x - word.width / 2));
      const top = Math.max(WORD_EDGE, word.y - WORD_GAP - word.height - rise);
      word.tag.style.transform = `translate(${left.toFixed(1)}px,${top.toFixed(1)}px)`;
      word.tag.style.opacity = Math.min(1, (1 - k) / WORD_FADE).toFixed(2);
    }
  }

  // The tag's size, read from the page only when its words have changed
  measure(tag, look) {
    if (!look.width) {
      look.width = tag.offsetWidth;
      look.height = tag.offsetHeight;
    }
    return look;
  }

  // `spots` holds { x, y, seal, wait } for each seat and then the crate, the screen point under the middle of its tag,
  // or null for no tag, and `dt` is the seconds since the last call. `wait` dims the player's own seal while it can't
  // dive. A name needing another spot moves over to it, one just on goes straight in
  place(spots, dt) {
    const shown = [];
    this.tags.forEach((tag, number) => {
      const spot = spots[number];
      const show = Boolean(spot && tag.textContent);
      if (show === tag.hidden) {
        tag.hidden = !show;
      }
      if (show) {
        tag.classList.toggle("seal", spot.seal);
        tag.classList.toggle("wait", Boolean(spot.wait));
        shown.push({ tag, spot, look: this.measure(tag, this.looks[number]), gives: number === this.crate });
      } else {
        this.looks[number].rise = null;
      }
    });
    const boxes = shown.map(({ spot, look, gives }) => {
      const { width, height, rise, aim, beside } = look;
      return { x: spot.x, y: spot.y - height, width, height, rise, aim, beside, gives };
    });
    const placed = layoutNames(boxes, this.layer.clientWidth, this.layer.clientHeight, dt);
    shown.forEach(({ tag, look, gives }, index) => {
      const { x, rise, aim, beside } = placed[index];
      // A step aside is eased, so the tag glides as the names around it move. One just on goes straight in
      const glide = gives && Number.isFinite(look.rise) ? Math.min(1, dt * ROW_EASE) : 1;
      look.x += (x - look.x) * glide;
      Object.assign(look, { rise, aim, beside });
      const left = look.x - look.width / 2;
      const top = boxes[index].y - rise;
      tag.style.transform = `translate(${left.toFixed(1)}px,${top.toFixed(1)}px)`;
    });
    this.placeWords(spots, dt);
  }
}
