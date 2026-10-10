// Numbers, times and names the way the bot's chat commands write them, so the page and chat read the same.

export const GAMES = ["allin", "blackjack", "coin", "craps", "cups", "dice", "hilo", "war", "double"];

// The membership colors from casino/common/catalog.py, plus Basic's grey
export const TIER_COLORS = {
  blue: "#3366ff",
  red: "#ff0000",
  green: "#00cc33",
  orange: "#ff6600",
  purple: "#a220bd",
  yellow: "#ffff00",
  turquoise: "#00ffff",
  teal: "#009999",
  magenta: "#ba2586",
  pink: "#fe01d1",
  white: "#ffffff",
  grey: "#666666",
};

export function money(amount) {
  return amount === null || amount === undefined ? "-" : Number(amount).toLocaleString("en-US");
}

// A chip's face: 1, 5, 25, 1K, 50K
export function chipLabel(value) {
  return value >= 1000 ? `${value / 1000}K` : String(value);
}

// 1 hour, 2 minutes and 5 seconds
export function duration(seconds) {
  let left = Math.max(0, Math.ceil(seconds));
  const parts = [];
  for (const [size, word] of [
    [3600, "hour"],
    [60, "minute"],
    [1, "second"],
  ]) {
    const count = Math.floor(left / size);
    left -= count * size;
    if (count) {
      parts.push(`${count} ${word}${count === 1 ? "" : "s"}`);
    }
  }
  if (!parts.length) {
    return "0 seconds";
  }
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

export function tierColor(name) {
  return TIER_COLORS[name] || TIER_COLORS.grey;
}

// A tag with a class and text, the small helper every panel uses
export function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

export function button(label, className = "button", onClick = null) {
  const node = make("button", className, label);
  node.type = "button";
  if (onClick) {
    node.addEventListener("click", onClick);
  }
  return node;
}

// A player's picture, or an empty circle when Discord can't send it
export function avatar(url) {
  if (!url) {
    return make("span", "avatar");
  }
  const image = make("img", "avatar");
  image.alt = "";
  image.src = url;
  image.addEventListener("error", () => image.replaceWith(make("span", "avatar")));
  return image;
}
