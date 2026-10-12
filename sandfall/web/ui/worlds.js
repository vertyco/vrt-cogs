// The Worlds panel: every shared world open in this Activity window, with a small live picture, whose world it is and
// who is in it. Tapping one joins it; a world you can join says Join on its card. This file also sends the picture of the world this player runs, and handles the
// two sides of "ask to join": asking a friend whose world is private, and being asked.
import { note } from "../notes.js";
import { blobBase64 } from "../render/gl.js";
import { cut } from "./cursors.js";
import { icon } from "./icons.js";

const MAX_PLAYERS = 10;
const PIC_W = 80;
const PIC_H = 45;
const PIC_EVERY_MS = 5000;
const NAMES_SHOWN = 3;
const NAME_MAX = 14;
// An ask card waits this long for an answer, then goes away like Not now
const ASK_MS = 20000;
const PNG_MAX = 20 * 1024;
const PNG_PREFIX = "data:image/png;base64,";

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

function playerLine(players) {
  const shown = players.slice(0, NAMES_SHOWN).map((p) => cut(p.name, NAME_MAX));
  const more = players.length - shown.length;
  return more > 0 ? `${shown.join(", ")} +${more}` : shown.join(", ");
}

/** Builds the panel. Returns { toggle(), close() } */
export function buildWorlds(state) {
  const { hub, shared } = state;
  const button = document.getElementById("world-menu");
  const panel = make("section", "worldspanel glass");
  panel.id = "worldspanel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Worlds");
  const list = make("ul", "world-list");
  const empty = make("p", "world-empty");
  const invite = make("button", "menu-action", "Invite friends");
  invite.type = "button";
  // The same heading and close button as the gallery
  const head = make("div", "gallery-head");
  const closeButton = make("button", "gallery-close");
  closeButton.type = "button";
  closeButton.title = "Close";
  closeButton.setAttribute("aria-label", "Close the worlds list");
  closeButton.append(icon("close"));
  closeButton.addEventListener("click", () => close());
  head.append(make("h2", "menu-title", "Worlds"), closeButton);
  panel.append(head, list, empty, invite);
  // One card per world, kept between lists and updated in place so a tap is never lost to a redraw
  const cards = new Map();

  function card(world) {
    let entry = cards.get(world.id);
    if (entry) {
      return entry;
    }
    const node = make("button", "world-card");
    node.type = "button";
    const pic = make("img", "world-pic");
    pic.alt = "";
    pic.width = PIC_W;
    pic.height = PIC_H;
    const owner = make("span", "world-owner");
    const players = make("span", "world-players");
    const status = make("span", "world-status");
    const text = make("span", "world-text");
    text.append(owner, players, status);
    const cue = make("span", "world-join", "Join");
    cue.setAttribute("aria-hidden", "true");
    node.append(pic, text, cue);
    node.addEventListener("click", () => join(entry.id));
    entry = { id: world.id, node, pic, owner, players, status, cue, picture: null, full: false };
    cards.set(world.id, entry);
    return entry;
  }

  function join(id) {
    close();
    if (id !== shared.inWorld) {
      shared.enter(id);
    }
  }

  function update(world) {
    const entry = card(world);
    const here = world.id === shared.inWorld;
    const mine = world.owner === shared.you;
    setText(entry.owner, mine ? "Your world" : `${cut(ownerName(world), NAME_MAX)}'s world`);
    setText(entry.players, playerLine(world.players));
    const status = here ? "You're here" : world.full ? `Full (${MAX_PLAYERS} players)` : "";
    setText(entry.status, status);
    entry.status.hidden = status === "";
    entry.node.disabled = world.full && !here;
    entry.cue.hidden = here || world.full;
    const png = shared.pics.get(world.id) ?? null;
    if (png !== entry.picture) {
      entry.picture = png;
      if (png === null) {
        entry.pic.removeAttribute("src");
      } else {
        entry.pic.src = png;
      }
    }
    return entry.node;
  }

  function ownerName(world) {
    return world.players.find((p) => p.id === world.owner)?.name ?? "Someone";
  }

  // Writing the same text again would still swap the text node out
  function setText(node, text) {
    if (node.textContent !== text) {
      node.textContent = text;
    }
  }

  function others() {
    return (hub.people ?? []).filter((person) => !person.you);
  }

  function render() {
    const worlds = shared.worldsList;
    const nodes = worlds.map(update);
    const open = new Set(worlds.map((w) => w.id));
    for (const id of cards.keys()) {
      if (!open.has(id)) {
        cards.delete(id);
      }
    }
    const same = nodes.length === list.children.length && nodes.every((node, i) => list.children[i].firstChild === node);
    if (!same) {
      list.replaceChildren(
        ...nodes.map((node) => {
          const item = make("li");
          item.append(node);
          return item;
        }),
      );
    }
    const alone = worlds.length === 0 && others().length === 0;
    list.hidden = worlds.length === 0;
    empty.hidden = worlds.length > 0;
    empty.textContent = alone
      ? "Nobody else is here yet."
      : "No shared worlds are open. Use Open to friends in the world menu to share yours.";
    invite.hidden = !alone;
  }

  // Under the world button, kept on screen
  function place() {
    const edge = 8;
    const room = document.documentElement.clientWidth - panel.offsetWidth - edge;
    panel.style.left = `${Math.max(edge, Math.min(button.getBoundingClientRect().left, room))}px`;
  }

  function setOpen(on) {
    panel.hidden = !on;
    if (on) {
      state.toolbar?.close();
      render();
      place();
    }
  }

  function close() {
    setOpen(false);
  }

  invite.addEventListener("click", () => {
    const dialog = hub.discord?.commands?.openInviteDialog;
    if (dialog) {
      dialog.call(hub.discord.commands).catch((e) => console.warn("Sandfall: Discord didn't open its invite window", e));
    } else {
      hub.openPeople?.();
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
      close();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      close();
    }
  });
  window.addEventListener("resize", () => {
    if (!panel.hidden) {
      place();
    }
  });
  document.body.append(panel);

  let sentFor = null;
  // The world this player runs gets a fresh small picture now and then, for everyone's Worlds panel
  async function sendPicture() {
    if (!shared.isOwner || !state.renderer) {
      sentFor = null;
      return;
    }
    sentFor = shared.inWorld;
    try {
      const png = `${PNG_PREFIX}${await blobBase64(await state.renderer.picture(state.world, PIC_W, PIC_H))}`;
      if (png.length <= PNG_MAX && shared.isOwner) {
        shared.send({ t: "pic", png });
      }
    } catch (e) {
      console.warn("Sandfall: couldn't make the world's picture", e);
    }
  }
  setInterval(sendPicture, PIC_EVERY_MS);

  function asked({ id, name }) {
    note(`${cut(name, NAME_MAX)} wants to join. Open your world?`, {
      action: { label: "Open", onClick: () => shared.invite(id) },
      dismiss: "Not now",
      ms: ASK_MS,
    });
  }

  function followed(message) {
    if (message.world) {
      shared.enter(message.world);
    } else if (message.private) {
      const { id, name } = message.private;
      note(`${cut(name, NAME_MAX)}'s world is private. Ask to join?`, {
        action: {
          label: "Ask",
          onClick: () => {
            shared.send({ t: "ask", to: id });
            note(`Asked ${cut(name, NAME_MAX)} to open their world.`);
          },
        },
      });
    }
  }

  shared.onChange((kind, data) => {
    if (kind === "follow") {
      followed(data);
    } else if (kind === "asked") {
      asked(data);
    } else if (kind === "change" || kind === "pic") {
      if (!panel.hidden) {
        render();
      }
      if (kind === "change" && shared.isOwner && sentFor !== shared.inWorld) {
        sendPicture();
      }
    }
  });
  hub.onPeople?.(() => {
    if (!panel.hidden) {
      render();
    }
  });

  return { toggle: () => setOpen(panel.hidden), close };
}
