// Short toasts along the world's top edge, under the bar. They sit on the left so the people button's arrival notes,
// which slide out under the button at the right, stay clear.
const MAX_NOTES = 2;
const SHOW_MS = 5000;
const FADE_MS = 250;

let box = null;

function boxNode() {
  if (box === null) {
    box = document.createElement("div");
    box.id = "notes";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  return box;
}

function remove(node) {
  if (node.dataset.leaving) {
    return;
  }
  node.dataset.leaving = "1";
  clearTimeout(Number(node.dataset.timer));
  node.classList.add("leaving");
  setTimeout(() => node.remove(), FADE_MS);
}

/**
 * Shows `text` for 5 seconds (`ms` changes that). With `action`, the note carries a button that runs onClick and closes
 * the note. With `dismiss` as well, a plain button of that name beside it closes the note and does nothing else
 */
export function note(text, { action, dismiss, ms = SHOW_MS } = {}) {
  const host = boxNode();
  const node = document.createElement("p");
  node.className = "note";
  const words = document.createElement("span");
  words.textContent = text;
  node.append(words);
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      remove(node);
      action.onClick();
    });
    node.append(button);
    if (dismiss) {
      const later = document.createElement("button");
      later.type = "button";
      later.className = "quiet";
      later.textContent = dismiss;
      later.addEventListener("click", () => remove(node));
      node.append(later);
    }
  }
  host.append(node);
  const live = [...host.children].filter((child) => !child.dataset.leaving);
  for (const old of live.slice(0, Math.max(0, live.length - MAX_NOTES))) {
    remove(old);
  }
  node.dataset.timer = String(setTimeout(() => remove(node), ms));
  return node;
}
