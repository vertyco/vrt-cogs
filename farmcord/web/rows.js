// The rows the Market's shop and the farmhouse board list things in, with their buttons, count boxes and pen pickers.
// Their styles are the shop's (market.css).

export const PICTURE = 48;
// The bot's own words for a refusal the state already shows coming
export const NO_COINS = "Not enough FarmCoins";
// The page's own words when the state shows no pen with room for a new animal. The bot never hears of that case: the
// page has no pen to send it
export const NO_PEN = "Animals need a pen. Unlock a plot and pick Animals.";
export const PENS_FULL = "Your pens are full";

// One line: { key, picture, name, note, owned }, what can be done (`deal`: buttons and boxes), and why it can't be done
// now, if the state already shows the bot would say no. A row with no picture is a plain one
export function shopRow(ctx, base, deal = [], why = "") {
  const { make } = ctx.hud;
  const item = make("li", base.picture ? "shop-row" : "shop-row plain");
  item.dataset.key = base.key;
  if (base.picture) {
    const picture = make("span", "shop-picture");
    picture.append(base.picture);
    item.append(picture);
  }
  const words = make("span", "shop-words");
  words.append(make("b", "", base.name));
  if (base.note) {
    words.append(make("small", "", base.note));
  }
  item.append(words);
  if (base.owned) {
    item.append(make("span", "shop-owned", base.owned));
  }
  const area = make("div", "shop-deal");
  area.append(...deal);
  const reason = make("p", "shop-why", why);
  reason.hidden = !why;
  item.append(area, reason);
  return item;
}

// A row above the player's level: the level it opens at and its price, nothing to press
export function lockedRow(ctx, base, level, coins) {
  const needs = ctx.hud.make("span", "shop-level", `Unlocks at level ${level}`);
  const row = shopRow(ctx, base, [needs, ctx.hud.price(coins)]);
  row.classList.add("locked");
  return row;
}

// A button with what it does and, when it costs or brings FarmCoins, how many
export function dealButton(ctx, words, coins = null) {
  const button = ctx.hud.make("button", "button primary deal");
  button.type = "button";
  button.append(ctx.hud.make("span", "", words));
  if (coins !== null) {
    button.append(ctx.hud.price(coins));
  }
  return button;
}

// The number in a row's box (counts[key]), kept while the rows are drawn again but within what the row allows now
export function keep(counts, key, start, most) {
  counts[key] = Math.min(most, Math.max(1, counts[key] ?? start));
  return counts[key];
}

// A box for how many, typed or stepped, from 1 to `most`, holding counts[key]. `changed(count)` runs with each new
// count
export function countBox(ctx, counts, key, most, changed = () => {}) {
  const { make } = ctx.hud;
  const box = make("span", "stepper");
  const input = make("input", "shop-count");
  Object.assign(input, { type: "number", inputMode: "numeric", min: "1", max: String(most) });
  input.value = String(counts[key]);
  input.setAttribute("aria-label", "How many");
  const set = (n, typing = false) => {
    counts[key] = Math.min(most, Math.max(1, n));
    if (!typing || n > most) {
      input.value = String(counts[key]);
    }
    changed(counts[key]);
  };
  const step = (words, label, by) => {
    const button = make("button", `step ${label}`, words);
    button.type = "button";
    button.setAttribute("aria-label", label === "more" ? "One more" : "One fewer");
    button.addEventListener("click", ctx.safe("the count box", () => set(counts[key] + by)));
    return button;
  };
  // While typing, the box only changes when it goes past the most; an empty box waits for the player to finish
  const typed = () => parseInt(input.value, 10) >= 1 && set(parseInt(input.value, 10), true);
  input.addEventListener("input", ctx.safe("the count box", typed));
  input.addEventListener("change", ctx.safe("the count box", () => set(parseInt(input.value, 10) || 1)));
  box.append(step("−", "fewer", -1), input, step("+", "more", 1));
  return box;
}

// The first frame of a look's front idle, as a picture fitted to the row
export function animalPicture(ctx, look) {
  return ctx.hud.icon(`${look}/${ctx.scene.art.animation(look).clips.idle_front.start}`, PICTURE, true);
}

// The pens with room. `last.pen` is the one picked last, shown first and kept as the player changes it
export function penPicker(ctx, open, last) {
  const size = ctx.catalog().constants.pen_size;
  const select = ctx.hud.make("select", "shop-pen");
  select.setAttribute("aria-label", "Which pen");
  for (const plot of open) {
    const option = ctx.hud.make("option", "", `Plot ${plot.number} (${plot.animals.length} of ${size})`);
    option.value = String(plot.number);
    select.append(option);
  }
  if (open.some((plot) => plot.number === last.pen)) {
    select.value = String(last.pen);
  }
  const picked = () => {
    last.pen = Number(select.value);
  };
  select.addEventListener("change", ctx.safe("the pen picker", picked));
  return select;
}
