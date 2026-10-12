// One keyboard listener for the whole page. Parts of the page register the keys they care about with onKey.
const handlers = new Map();

function typing(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

window.addEventListener("keydown", (event) => {
  // Browser and Discord shortcuts keep their keys
  if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) {
    return;
  }
  for (const fn of [...(handlers.get(event.key) ?? [])]) {
    fn(event);
  }
});

/** Calls fn(event) when `key` (an event.key value: " ", ".", "[", "z") is pressed outside a text box. Returns an undo */
export function onKey(key, fn) {
  if (!handlers.has(key)) {
    handlers.set(key, []);
  }
  handlers.get(key).push(fn);
  return () => {
    const list = handlers.get(key);
    const at = list.indexOf(fn);
    if (at >= 0) {
      list.splice(at, 1);
    }
  };
}
