// The "How to play" card. It opens by itself the first time the page runs on this device (the browser remembers that
// it has been shown) and again from the bar's help button.
import { addBarButton } from "./bar.js";
import { icon } from "./icons.js";

const HELPED_KEY = "sandfall:helped";
const STEPS = [
  ["Pick an element", "Open a tab, like Powders or Liquids, and tap what you want to pour."],
  ["Paint", "Drag across the world with your finger or the mouse. The slider sets how big the brush is."],
  [
    "Mix and watch",
    "Try water on fire, or lava on wood, and see what happens. Hover or press and hold an element to read what it does.",
  ],
];

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

function wasShown() {
  try {
    return localStorage.getItem(HELPED_KEY) === "1";
  } catch (e) {
    console.warn("Sandfall: couldn't read whether the help card was shown", e);
    return false;
  }
}

function markShown() {
  try {
    localStorage.setItem(HELPED_KEY, "1");
  } catch (e) {
    console.warn("Sandfall: couldn't remember that the help card was shown", e);
  }
}

/** Adds the help button (bar order 65) and the card. Returns { open, close } */
export function buildHelp() {
  const scrim = make("div", "scrim");
  scrim.hidden = true;
  const card = make("section", "help glass");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-modal", "true");
  card.setAttribute("aria-labelledby", "help-title");
  const title = make("h2", "menu-title", "How to play");
  title.id = "help-title";
  const steps = make("ol", "help-steps");
  for (const [head, text] of STEPS) {
    const item = make("li", "help-step");
    item.append(make("strong", "", head), make("span", "", text));
    steps.append(item);
  }
  const done = make("button", "menu-action accent help-done", "Got it");
  done.type = "button";
  card.append(title, steps, done);
  scrim.append(card);
  document.body.append(scrim);

  const button = addBarButton({
    id: "help",
    label: "How to play",
    icon: icon("help"),
    order: 65,
    onClick: () => (scrim.hidden ? open() : close()),
  });

  function open() {
    scrim.hidden = false;
    done.focus();
  }

  function close() {
    if (scrim.hidden) {
      return;
    }
    scrim.hidden = true;
    markShown();
    button.focus();
  }

  done.addEventListener("click", close);
  scrim.addEventListener("pointerdown", (event) => {
    if (event.target === scrim) {
      close();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !scrim.hidden) {
      close();
    }
  });
  if (!wasShown()) {
    open();
  }
  return { open, close };
}
