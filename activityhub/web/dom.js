// Small helpers for building the menu's own page. Game pages never load this file
export const $ = (id) => document.getElementById(id);

export const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

export function option(value, label) {
  const node = el("option", "", label);
  node.value = value;
  return node;
}
