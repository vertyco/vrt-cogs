// The server gallery: the Save to gallery dialog and the gallery panel, both opened from the top bar. Everyone in the
// Discord server sees the same worlds. A card has the world's picture, name, maker, date and likes, with Load, and
// Delete for the maker and for server admins. Lists come from the bot when the panel opens or the sort changes, never
// live, so nothing clickable is rebuilt under a finger. On an upright phone the gallery takes the bottom sheet's place,
// so the world stays in view above it, and gives the sheet back when it closes.
import { note } from "../notes.js";
import { blobBase64 } from "../render/gl.js";
import { decodeWorld, encodeWorld, packWorld, unpackWorld } from "../sim/index.js";
import { addBarButton } from "./bar.js";
import { cut } from "./cursors.js";
import { icon } from "./icons.js";

const NAME_MAX = 40;
const MAKER_MAX = 18;
const TITLE_MAX = 24;
const SAVE_W = 320;
const SAVE_H = 180;
const SORTS = [
  ["new", "Newest"],
  ["liked", "Most liked"],
  ["mine", "Mine"],
];
const EMPTY = {
  new: "Nobody has saved a world to this server yet. Use Save to gallery to add yours.",
  liked: "Nobody has saved a world to this server yet. Use Save to gallery to add yours.",
  mine: "You haven't saved any worlds to this server yet.",
};
const CANT_REACH = "Couldn't reach the gallery. Try again in a moment.";

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

function button(label, className, onClick) {
  const node = make("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function reason(e) {
  return e instanceof Error && e.message ? e.message : CANT_REACH;
}

function dateText(seconds) {
  const date = new Date(seconds * 1000);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, sameYear ? { month: "short", day: "numeric" } : { dateStyle: "medium" });
}

/** Builds the dialog and the panel and puts their buttons in the bar. Returns { open, toggle, close, closeAll } */
export function buildGallery(state) {
  const { hub } = state;

  // ---------- Save to gallery ----------

  const saveDialog = make("section", "gallery-save glass");
  saveDialog.hidden = true;
  saveDialog.setAttribute("role", "dialog");
  saveDialog.setAttribute("aria-label", "Save to gallery");
  const savePic = make("img", "save-pic");
  savePic.alt = "Your world";
  const nameInput = make("input", "save-name");
  nameInput.type = "text";
  nameInput.maxLength = NAME_MAX;
  nameInput.placeholder = "Name your world";
  nameInput.autocomplete = "off";
  nameInput.setAttribute("aria-label", "World name");
  const saveMessage = make("p", "gallery-message");
  saveMessage.hidden = true;
  saveMessage.setAttribute("role", "status");
  const saveGo = button("Save", "menu-action accent", () => submitSave());
  const saveMine = button("Show mine", "menu-action", () => {
    closeSave();
    openGallery("mine");
  });
  saveMine.hidden = true;
  const saveCancel = button("Cancel", "menu-action", () => closeSave());
  const saveFields = make("div", "save-fields");
  saveFields.append(nameInput, make("p", "save-hint", `Up to ${NAME_MAX} characters.`), saveMessage);
  const saveBody = make("div", "save-body");
  saveBody.append(savePic, saveFields);
  const saveButtons = make("div", "save-buttons");
  saveButtons.append(saveGo, saveMine, saveCancel);
  saveDialog.append(make("h2", "menu-title", "Save to gallery"), saveBody, saveButtons);

  // The world as it was when the dialog opened, so the picture and the saved world are the same one
  let snapshot = null;
  let pictureBlob = null;
  let pictureUrl = null;
  let saveRun = 0;
  let saving = false;

  function showSaveMessage(text) {
    saveMessage.textContent = text;
    saveMessage.hidden = text === "";
  }

  function setFull(limit) {
    saveGo.textContent = "Gallery full";
    saveGo.disabled = true;
    saveMine.hidden = false;
    showSaveMessage(`You have ${limit} worlds here already. Delete one to make room.`);
  }

  async function openSave() {
    closeGallery();
    state.toolbar?.close();
    const run = ++saveRun;
    snapshot = unpackWorld(packWorld(state.world));
    pictureBlob = null;
    saving = false;
    savePic.removeAttribute("src");
    nameInput.value = "";
    saveGo.textContent = "Save";
    saveGo.disabled = true;
    saveMine.hidden = true;
    showSaveMessage("");
    saveDialog.hidden = false;
    nameInput.focus({ preventScroll: true });
    try {
      pictureBlob = await state.renderer.picture(snapshot, SAVE_W, SAVE_H);
    } catch (e) {
      console.warn("Sandfall: couldn't make the picture to save", e);
      if (run === saveRun) {
        showSaveMessage("Couldn't make a picture of your world.");
      }
      return;
    }
    if (run !== saveRun) {
      return;
    }
    if (pictureUrl !== null) {
      URL.revokeObjectURL(pictureUrl);
    }
    pictureUrl = URL.createObjectURL(pictureBlob);
    savePic.src = pictureUrl;
    saveGo.disabled = false;
    // Learn now whether the player has room, so the button can say so before they type a name
    try {
      const { mine, limit } = await hub.api("gallery", { sort: "mine" });
      if (run === saveRun && mine >= limit) {
        setFull(limit);
      }
    } catch (e) {
      console.warn("Sandfall: couldn't count the player's gallery worlds", e);
      if (run === saveRun) {
        saveGo.disabled = true;
        showSaveMessage(reason(e));
      }
    }
  }

  async function submitSave() {
    const name = nameInput.value.trim();
    if (saving || pictureBlob === null) {
      return;
    }
    if (name === "") {
      showSaveMessage("Give the world a name first.");
      nameInput.focus();
      return;
    }
    const run = saveRun;
    saving = true;
    saveGo.disabled = true;
    showSaveMessage("Saving...");
    try {
      const [snap, png] = await Promise.all([encodeWorld(snapshot), blobBase64(pictureBlob)]);
      const result = await hub.api("gallery_save", { name, snap, png });
      if (run !== saveRun) {
        return;
      }
      if (result.ok === false && result.reason === "full") {
        setFull(result.limit);
        return;
      }
      closeSave();
      note(`Saved "${cut(name, TITLE_MAX)}" to the gallery.`);
    } catch (e) {
      console.warn("Sandfall: couldn't save to the gallery", e);
      if (run === saveRun) {
        showSaveMessage(reason(e));
        saveGo.disabled = false;
      }
    } finally {
      saving = false;
    }
  }

  function closeSave() {
    saveRun += 1;
    saveDialog.hidden = true;
    snapshot = null;
    pictureBlob = null;
    if (pictureUrl !== null) {
      URL.revokeObjectURL(pictureUrl);
      pictureUrl = null;
    }
  }

  nameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitSave();
    }
  });

  // ---------- The gallery ----------

  const panel = make("section", "gallery glass");
  panel.id = "gallery";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Gallery");
  const head = make("div", "gallery-head");
  const closeButton = button("", "gallery-close", () => closeGallery());
  closeButton.setAttribute("aria-label", "Close the gallery");
  closeButton.title = "Close";
  closeButton.append(icon("close"));
  head.append(make("h2", "menu-title", "Gallery"), closeButton);
  const tabs = make("div", "seg gallery-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "Sort");
  const tabButtons = SORTS.map(([value, label]) => {
    const tab = button(label, "", () => openGallery(value));
    tab.dataset.sort = value;
    tabs.append(tab);
    return tab;
  });
  const message = make("p", "gallery-message");
  message.hidden = true;
  message.setAttribute("role", "status");
  const list = make("ul", "gallery-list");
  const empty = make("p", "world-empty");
  panel.append(head, tabs, message, list, empty);

  let isOpen = false;
  let sort = "new";
  let listRun = 0;
  let confirming = null;
  // Cards by world id, and the picture addresses already fetched for them
  const cards = new Map();
  const pictures = new Map();
  const lazy =
    typeof IntersectionObserver === "function"
      ? new IntersectionObserver(
          (seen) => {
            for (const item of seen) {
              if (item.isIntersecting) {
                lazy.unobserve(item.target);
                showPicture(cards.get(item.target.dataset.id));
              }
            }
          },
          { root: panel, rootMargin: "240px" },
        )
      : null;
  // One picture at a time, so opening a long gallery doesn't flood the bot with requests
  let pictureQueue = Promise.resolve();

  function showMessage(text) {
    message.textContent = text;
    message.hidden = text === "";
  }

  function showPicture(entry) {
    if (!entry || entry.pic.src) {
      return;
    }
    const known = pictures.get(entry.id);
    if (known) {
      entry.pic.src = known;
      return;
    }
    pictureQueue = pictureQueue.then(async () => {
      if (cards.get(entry.id) !== entry || pictures.has(entry.id)) {
        return;
      }
      try {
        const resp = await hub.fetch(`thumb?id=${entry.id}`);
        if (!resp.ok) {
          return;
        }
        const url = URL.createObjectURL(await resp.blob());
        pictures.set(entry.id, url);
        if (cards.get(entry.id) === entry) {
          entry.pic.src = url;
        }
      } catch (e) {
        console.warn("Sandfall: couldn't fetch a gallery picture", e);
      }
    });
  }

  function closeConfirm() {
    if (confirming !== null) {
      confirming.confirm.hidden = true;
      confirming.actions.hidden = false;
      confirming = null;
    }
  }

  function askFirst(entry, question, yes, run) {
    closeConfirm();
    confirming = entry;
    entry.question.textContent = question;
    entry.yes.textContent = yes;
    entry.run = run;
    entry.actions.hidden = true;
    entry.confirm.hidden = false;
    entry.yes.focus({ preventScroll: true });
  }

  function setLikes(entry, world) {
    entry.world.likes = world.likes;
    entry.world.liked = world.liked;
    entry.like.setAttribute("aria-pressed", String(world.liked));
    entry.count.textContent = String(world.likes);
    entry.like.title = world.liked ? "Take your like back" : "Like";
    entry.like.setAttribute("aria-label", `${entry.like.title}, ${world.likes} likes`);
  }

  async function toggleLike(entry) {
    entry.like.disabled = true;
    try {
      setLikes(entry, await hub.api("like", { id: entry.id }));
      showMessage("");
    } catch (e) {
      showMessage(reason(e));
    } finally {
      entry.like.disabled = false;
    }
  }

  function askLoad(entry) {
    const { shared } = state;
    if (shared.locked) {
      closeConfirm();
      showMessage(`Only ${shared.ownerName || "the owner"} can load a world here.`);
      return;
    }
    showMessage("");
    askFirst(entry, "Replace your world with this one?", "Replace", () => load(entry));
  }

  async function load(entry) {
    const { shared } = state;
    try {
      const { snap } = await hub.api("gallery_load", { id: entry.id });
      if (shared.locked) {
        throw new Error(`Only ${shared.ownerName || "the owner"} can load a world here.`);
      }
      if (shared.inWorld !== null) {
        if (!shared.send({ t: "load", snap })) {
          throw new Error("Lost the connection. Try again in a moment.");
        }
      } else {
        const world = await decodeWorld(snap);
        state.undo.push();
        state.setWorld(world);
      }
    } catch (e) {
      console.warn("Sandfall: couldn't load the gallery world", e);
      closeConfirm();
      showMessage(reason(e));
      return;
    }
    closeGallery();
    note(`Loaded "${cut(entry.world.name, TITLE_MAX)}".`);
  }

  async function remove(entry) {
    try {
      await hub.api("delete", { id: entry.id });
    } catch (e) {
      closeConfirm();
      showMessage(reason(e));
      return;
    }
    confirming = null;
    cards.delete(entry.id);
    entry.node.remove();
    const url = pictures.get(entry.id);
    if (url) {
      URL.revokeObjectURL(url);
      pictures.delete(entry.id);
    }
    empty.hidden = cards.size > 0;
  }

  function card(world) {
    const node = make("li", "gallery-card");
    node.dataset.id = world.id;
    const pic = make("img", "gallery-pic");
    pic.alt = "";
    pic.width = 144;
    pic.height = 81;
    const name = make("strong", "gallery-name", world.name);
    name.title = world.name;
    const by = make("span", "gallery-by", `by ${cut(world.maker.name, MAKER_MAX)} · ${dateText(world.made)}`);
    const like = button("", "gallery-like", () => toggleLike(entry));
    like.append(icon("heart"));
    const count = make("span", "gallery-count");
    like.append(count);
    const actions = make("div", "gallery-actions");
    actions.append(like, button("Load", "menu-action", () => askLoad(entry)));
    if (world.can_delete) {
      const trash = button("", "menu-action menu-danger gallery-delete", () =>
        askFirst(entry, "Delete this world? This can't be undone.", "Delete", () => remove(entry)),
      );
      trash.append(icon("trash"));
      trash.title = "Delete";
      trash.setAttribute("aria-label", "Delete this world");
      actions.append(trash);
    }
    const question = make("span", "gallery-question");
    const yes = button("", "menu-action accent", () => entry.run());
    const confirm = make("div", "gallery-confirm");
    confirm.hidden = true;
    confirm.append(question, yes, button("Cancel", "menu-action", () => closeConfirm()));
    const text = make("div", "gallery-text");
    text.append(name, by, actions, confirm);
    node.append(pic, text);
    const entry = {
      id: world.id,
      world: { ...world },
      node,
      pic,
      like,
      count,
      actions,
      confirm,
      question,
      yes,
      run: null,
    };
    setLikes(entry, world);
    return entry;
  }

  function render(worlds) {
    closeConfirm();
    cards.clear();
    const entries = worlds.map(card);
    for (const entry of entries) {
      cards.set(entry.id, entry);
    }
    list.replaceChildren(...entries.map((entry) => entry.node));
    empty.textContent = EMPTY[sort];
    empty.hidden = entries.length > 0;
    for (const entry of entries) {
      if (lazy) {
        lazy.observe(entry.node);
      } else {
        showPicture(entry);
      }
    }
  }

  async function refresh() {
    const run = ++listRun;
    showMessage("");
    closeConfirm();
    lazy?.disconnect();
    cards.clear();
    list.replaceChildren();
    empty.textContent = "Loading the gallery...";
    empty.hidden = false;
    try {
      const data = await hub.api("gallery", { sort });
      if (run !== listRun) {
        return;
      }
      render(data.worlds);
    } catch (e) {
      console.warn("Sandfall: couldn't read the gallery", e);
      if (run === listRun) {
        empty.hidden = true;
        showMessage(reason(e));
      }
    }
  }

  function showSort() {
    for (const tab of tabButtons) {
      tab.setAttribute("aria-pressed", String(tab.dataset.sort === sort));
    }
  }

  /** Opens the gallery on a sort (Newest, Most liked or Mine) and reads its list again */
  function openGallery(next = "new") {
    closeSave();
    state.toolbar?.close();
    sort = next;
    showSort();
    isOpen = true;
    panel.hidden = false;
    state.toolbar?.holdSheet(panel);
    refresh();
  }

  function closeGallery() {
    if (!isOpen) {
      return;
    }
    isOpen = false;
    listRun += 1;
    panel.hidden = true;
    state.toolbar?.releaseSheet();
    lazy?.disconnect();
    closeConfirm();
  }

  const saveBar = addBarButton({
    id: "save",
    label: "Save to gallery",
    icon: icon("save"),
    order: 30,
    onClick: () => (saveDialog.hidden ? openSave() : closeSave()),
  });
  const galleryBar = addBarButton({
    id: "gallery",
    label: "Gallery",
    icon: icon("gallery"),
    order: 40,
    onClick: () => (isOpen ? closeGallery() : openGallery(sort)),
  });

  document.addEventListener("pointerdown", (event) => {
    if (isOpen && !panel.contains(event.target) && !galleryBar.contains(event.target)) {
      closeGallery();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (isOpen) {
      closeGallery();
      galleryBar.focus();
    } else if (!saveDialog.hidden) {
      closeSave();
      saveBar.focus();
    }
  });
  document.body.append(saveDialog, panel);

  return {
    get open() {
      return isOpen;
    },
    openSave,
    openGallery,
    close: closeGallery,
  };
}
