// The top bar's right-hand group. Every part of the page adds its own button here and says where it sits, so the
// order of the bar never depends on which script ran first.
import { icon } from "./icons.js";

const group = document.getElementById("bar-right");
// An upright touch phone has room for only so many full-size buttons, so the least used ones move into a More menu
const TUCK_QUERY = "(orientation: portrait) and (max-width: 640px) and (pointer: coarse)";
const TUCKED = ["bar-music", "bar-sound", "bar-settings", "bar-help"];
// Pressing one of these opens a panel of its own, so the More menu gets out of its way
const OPENS_PANEL = new Set(["bar-settings", "bar-help"]);

/** Puts any element into the bar's right-hand group, left to right by `order` (ties keep the order they were added) */
export function addBarItem(order, element) {
  element.dataset.order = String(order);
  const after = [...group.children].find((child) => Number(child.dataset.order) > order);
  group.insertBefore(element, after ?? null);
  return element;
}

/** A round icon button in the bar. `icon` is an element from icons.js; `label` is its name for screen readers */
export function addBarButton({ id, label, icon, order, onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bar-button";
  button.id = `bar-${id}`;
  button.title = label;
  button.setAttribute("aria-label", label);
  if (icon) {
    button.append(icon);
  }
  if (onClick) {
    button.addEventListener("click", onClick);
  }
  return addBarItem(order, button);
}

/** The More button and its menu. Call it once, after every button it may hold is in the bar. */
export function buildBarMore() {
  const query = window.matchMedia(TUCK_QUERY);
  const menu = document.createElement("div");
  menu.className = "bar-more glass";
  menu.id = "bar-more-menu";
  menu.hidden = true;
  menu.setAttribute("role", "group");
  menu.setAttribute("aria-label", "More");
  document.body.append(menu);
  const more = addBarButton({
    id: "more",
    label: "More",
    icon: icon("more"),
    order: 90,
    onClick: () => setOpen(menu.hidden),
  });
  more.setAttribute("aria-controls", menu.id);
  const buttons = TUCKED.map((id) => document.getElementById(id)).filter(Boolean);

  function setOpen(open) {
    menu.hidden = !open;
    more.setAttribute("aria-expanded", String(open));
    if (open) {
      const box = more.getBoundingClientRect();
      menu.style.top = `${box.bottom + 8}px`;
      menu.style.right = `${Math.max(8, document.documentElement.clientWidth - box.right)}px`;
    }
  }

  function place() {
    if (query.matches) {
      menu.append(...buttons);
    } else {
      setOpen(false);
      for (const button of buttons) {
        addBarItem(Number(button.dataset.order), button);
      }
    }
    more.hidden = !query.matches;
  }

  menu.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button && OPENS_PANEL.has(button.id)) {
      setOpen(false);
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !more.contains(event.target)) {
      setOpen(false);
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      setOpen(false);
      more.focus();
    }
  });
  window.addEventListener("resize", () => setOpen(false));
  query.addEventListener("change", place);
  place();
}
