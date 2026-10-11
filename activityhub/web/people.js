// The drawn parts of "who's here": the people panel, the floating people button over a game, arrival notes, the
// question before Join takes a player out of a round, and the pieces the menu reuses (rows, avatars, the button's
// face). Names and status lines come from players, so they only ever go in as text.
const NOTE_MS = 3000;
// The space an arrival note leaves between itself and the edge of the screen
const NOTE_GUTTER = 16;
// Arrivals this close together share one note
const MERGE_MS = 1000;
// A game page that never calls connect() still gets the floating button this long after it loads
const FLOAT_FALLBACK_MS = 2000;
const STACK = 3;
// What a page says where the real list would be, with no Discord around it
export const PREVIEW_TEXT = "Open this from Discord to see who's here.";
// Marks that keep a player's name apart from the words around it, so a right-to-left mark in the name can't turn
// those words around
const ISOLATE_START = "\u2068";
const ISOLATE_END = "\u2069";
// Static markup only, never player text
const ICONS = {
  invite: '<path d="M15 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1"/><circle cx="8.5" cy="7" r="3.5"/><path d="M19 8v6M16 11h6"/>',
  people:
    '<path d="M17 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1"/><circle cx="10" cy="7" r="3.5"/>' +
    '<path d="M21 19v-1a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
};

function make(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

export function icon(doc, name) {
  const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "hub-icon");
  svg.innerHTML = ICONS[name];
  return svg;
}

export function initial(name) {
  return (name || "?").trim().charAt(0).toUpperCase() || "?";
}

// A person's round picture, or the first letter of their name when Discord's picture can't load
export function avatar(doc, person, className = "hub-avatar") {
  const box = make(doc, "span", className);
  box.classList.toggle("away", Boolean(person.away));
  const letter = make(doc, "span", "hub-letter", initial(person.name));
  if (!person.avatar) {
    box.append(letter);
    return box;
  }
  const img = make(doc, "img");
  img.alt = "";
  img.addEventListener("error", () => img.replaceWith(letter));
  img.src = person.avatar;
  box.append(img);
  return box;
}

export function statusText(person) {
  if (person.away) {
    return "Away";
  }
  if (person.status) {
    return person.status;
  }
  return person.game ? "Playing" : "In the menu";
}

// One person in a list: picture, name, what they're doing, and a Join button when `join` is given
export function personRow(doc, person, join) {
  const row = make(doc, "li", "hub-person");
  const text = make(doc, "span", "hub-person-text");
  text.append(
    make(doc, "span", "hub-person-name", person.you ? `${person.name} (you)` : person.name),
    make(doc, "span", "hub-person-status", statusText(person)),
  );
  row.append(avatar(doc, person), text);
  if (join) {
    const button = make(doc, "button", "hub-join", "Join");
    button.type = "button";
    button.dataset.join = person.id;
    button.setAttribute("aria-label", `Join ${person.name}`);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      join(person);
    });
    row.append(button);
  }
  return row;
}

// Join shows next to someone in a game other than the one the player is in (null in the menu)
export function canJoin(person, myGame) {
  return !person.you && Boolean(person.game) && person.game !== myGame;
}

export function elsewhereLine(count) {
  return count === 1 ? "+1 playing in another channel" : `+${count} playing in other channels`;
}

function isolate(name) {
  return `${ISOLATE_START}${name}${ISOLATE_END}`;
}

export function arrivalText(names) {
  if (names.length === 1) {
    return `${isolate(names[0])} joined`;
  }
  const rest = names.length - 1;
  return `${isolate(names[0])} and ${rest} ${rest === 1 ? "other" : "others"} joined`;
}

// Everyone sorted into the panel's groups: here in the player's game, each other game, and the menu
export function groups(people, myGame) {
  const here = [];
  const menu = [];
  const games = new Map();
  for (const person of people) {
    if (myGame && person.game === myGame) {
      here.push(person);
    } else if (!person.game) {
      menu.push(person);
    } else {
      if (!games.has(person.game)) {
        games.set(person.game, []);
      }
      games.get(person.game).push(person);
    }
  }
  return { here, games, menu };
}

// A click only counts when the pointer (or Space) goes down and up on the same button. Lists come up to 4 times a
// second, and drawing one again replaces its buttons, which loses a click that is half done. So while a press is held
// inside the lists `inside(node)` recognises, redraws wait, and `draw` runs with the newest list once it ends
export class PressHold {
  constructor(inside, draw) {
    this.inside = inside;
    this.draw = draw;
    // The presses under way ("pointer", "key"), and whether a newer list waits
    this.pressed = new Set();
    this.held = false;
    this.watch();
  }

  // Only the main pointer button counts: another one can open a menu that swallows its release. A button is pressed
  // by Space on key up, so Space counts too (Enter acts on key down)
  watch() {
    document.addEventListener(
      "pointerdown",
      (event) => {
        if (event.button === 0 && this.inside(event.target)) {
          this.pressed.add("pointer");
        }
      },
      true,
    );
    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key === " " && this.inside(event.target) && event.target.closest("button")) {
          this.pressed.add("key");
        }
      },
      true,
    );
    // The pointer can be let go anywhere, and a scroll on a touch screen ends the press with a cancel
    for (const name of ["pointerup", "pointercancel"]) {
      document.addEventListener(name, () => this.release("pointer"), true);
    }
    document.addEventListener(
      "keyup",
      (event) => {
        if (event.key === " ") {
          this.release("key");
        }
      },
      true,
    );
    // A key held while focus moves away, or any press when the window loses focus, may never see its release
    document.addEventListener(
      "focusout",
      (event) => {
        if (this.inside(event.target)) {
          this.release("key");
        }
      },
      true,
    );
    window.addEventListener("blur", () => {
      this.pressed.clear();
      this.catchUpSoon();
    });
  }

  // A newer list is ready: draw it now, or once the press ends
  request() {
    if (this.pressed.size) {
      this.held = true;
    } else {
      this.draw();
    }
  }

  // The lists are going away, so nothing is waiting once they are shown again
  cancel() {
    this.pressed.clear();
    this.held = false;
  }

  release(source) {
    if (this.pressed.delete(source)) {
      this.catchUpSoon();
    }
  }

  // The click that ends a press is sent right after the pointer or key comes up, to the buttons still shown
  catchUpSoon() {
    if (this.held && !this.pressed.size) {
      setTimeout(() => this.catchUp(), 0);
    }
  }

  catchUp() {
    if (this.held && !this.pressed.size) {
      this.held = false;
      this.draw();
    }
  }
}

// The stylesheet, once per page. A game's frame can't see the menu's, so the button brings its own
export function useStyles(doc) {
  if (doc.querySelector("link[data-hub-people]")) {
    return;
  }
  const link = doc.createElement("link");
  link.rel = "stylesheet";
  link.href = new URL("./people.css", import.meta.url).href;
  link.dataset.hubPeople = "";
  doc.head.append(link);
}

// The people button and the spot its notes slide out of, as one element to place
export function buttonWrap(doc, onClick) {
  const wrap = make(doc, "span", "hub-people");
  const button = make(doc, "button", "hub-people-button");
  button.type = "button";
  button.addEventListener("click", onClick);
  wrap.append(button);
  return wrap;
}

// The button's face: the others in this game, then how many others are in the window. Alone, an invite icon
export function fillButton(button, people) {
  const doc = button.ownerDocument;
  const others = people.filter((person) => !person.you);
  const here = others.filter((person) => person.here);
  // The lists come up to 4 times a second, mostly with new status lines. The face only changes with who it shows,
  // and drawing it again would reload the pictures
  const shown = JSON.stringify([
    others.length,
    here.slice(0, STACK).map((person) => [person.id, person.name, person.avatar, Boolean(person.away)]),
  ]);
  if (button.dataset.face === shown) {
    return;
  }
  button.dataset.face = shown;
  const face = make(doc, "span", "hub-people-face");
  if (!others.length) {
    face.append(icon(doc, "invite"));
    button.setAttribute("aria-label", "Invite friends");
  } else {
    if (here.length) {
      const stack = make(doc, "span", "hub-stack");
      here.slice(0, STACK).forEach((person) => stack.append(avatar(doc, person, "hub-avatar small")));
      face.append(stack);
    } else {
      face.append(icon(doc, "people"));
    }
    face.append(make(doc, "span", "hub-count", String(others.length)));
    button.setAttribute("aria-label", `Who's here: ${others.length} ${others.length === 1 ? "other" : "others"}`);
  }
  button.replaceChildren(face);
}

// A short note under a people button, lined up with whichever side of the screen the button is nearer
export function showNote(wrap, text) {
  const doc = wrap.ownerDocument;
  const view = doc.defaultView;
  wrap.querySelector(".hub-note")?.remove();
  const note = make(doc, "span", "hub-note");
  note.setAttribute("role", "status");
  const box = wrap.getBoundingClientRect();
  const start = box.left + box.width / 2 < view.innerWidth / 2;
  note.classList.add(start ? "start" : "end");
  // The note runs from the button's edge toward the far side of the screen, so it gets the room on that side
  const room = start ? view.innerWidth - box.left : box.right;
  note.style.maxWidth = `${Math.max(0, room - NOTE_GUTTER)}px`;
  wrap.append(note);
  // Screen readers often skip a live region that already has its words when it appears, so they go in a frame later
  view.requestAnimationFrame(() => {
    note.textContent = text;
  });
  view.setTimeout(() => note.remove(), NOTE_MS);
}

// The menu page's half: the panel, the floating button, notes and the Join question, all drawn over the game frame
export class PeopleUI {
  constructor(host) {
    this.host = host;
    useStyles(document);
    this.floating = buttonWrap(document, () => this.open());
    this.floating.classList.add("floating");
    this.floating.hidden = true;
    // A game's own button, in its frame, once it calls hub.peopleButton()
    this.placed = null;
    this.floatTimer = null;
    this.noted = [];
    this.noteStarted = 0;
    this.answer = null;
    // The rows the panel shows now, and what had keyboard focus before it opened
    this.shown = null;
    this.opener = null;
    this.scrim = make(document, "div", "hub-people-scrim");
    this.scrim.hidden = true;
    this.scrim.addEventListener("click", () => this.dismiss());
    this.panel = this.buildPanel();
    this.confirmBox = this.buildConfirm();
    document.body.append(this.floating, this.scrim, this.panel, this.confirmBox);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        this.dismiss();
      }
    });
    // Redraws wait while a button in the panel is being pressed
    this.hold = new PressHold(
      (node) => this.panel.contains(node),
      () => this.isOpen() && this.render(),
    );
    host.presence.listen((people, arrived) => this.update(arrived));
    this.update([]);
  }

  buildPanel() {
    const panel = make(document, "aside", "hub-people-panel");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Who's here");
    panel.hidden = true;
    this.closeButton = make(document, "button", "hub-panel-close");
    this.closeButton.type = "button";
    this.closeButton.setAttribute("aria-label", "Close");
    this.closeButton.append(icon(document, "close"));
    this.closeButton.addEventListener("click", () => this.close());
    const head = make(document, "header", "hub-panel-head");
    head.append(make(document, "h2", "", "Who's here"), this.closeButton);
    this.body = make(document, "div", "hub-panel-body");
    panel.append(head, this.body);
    return panel;
  }

  buildConfirm() {
    const box = make(document, "div", "hub-confirm");
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-modal", "true");
    box.hidden = true;
    this.confirmText = make(document, "p", "hub-confirm-text");
    this.confirmText.id = "hub-confirm-text";
    // The question names the dialog. It isn't its description too, or screen readers would read it twice
    box.setAttribute("aria-labelledby", this.confirmText.id);
    this.leaveButton = make(document, "button", "hub-confirm-leave", "Leave");
    this.leaveButton.type = "button";
    this.stayButton = make(document, "button", "hub-confirm-stay primary", "Stay");
    this.stayButton.type = "button";
    const actions = make(document, "div", "hub-confirm-actions");
    actions.append(this.leaveButton, this.stayButton);
    box.append(this.confirmText, actions);
    return box;
  }

  myGame() {
    return this.host.presence.state.where;
  }

  people() {
    return this.host.presence.view(this.myGame());
  }

  isOpen() {
    return !this.panel.hidden;
  }

  open() {
    // Where keyboard focus goes back to in the menu, like the header's row of faces. Over a game it goes to the game
    if (!this.isOpen()) {
      this.opener = document.activeElement;
    }
    this.render();
    this.panel.hidden = false;
    this.scrim.hidden = false;
    document.body.classList.add("people-open");
    this.closeButton.focus();
  }

  close() {
    // Opening again draws the list as it is then, so nothing is waiting once the panel is gone
    this.hold.cancel();
    if (!this.isOpen()) {
      return;
    }
    this.panel.hidden = true;
    this.scrim.hidden = this.confirmBox.hidden;
    document.body.classList.remove("people-open");
    const back = this.host.frame || this.opener;
    this.opener = null;
    if (back?.isConnected) {
      back.focus({ preventScroll: true });
    }
  }

  // Escape or a tap outside: the Join question counts it as Stay, otherwise the panel closes
  dismiss() {
    if (this.answer) {
      this.answer(false);
    } else {
      this.close();
    }
  }

  update(arrived) {
    const people = this.people();
    fillButton(this.floating.querySelector("button"), people);
    if (this.placed) {
      fillButton(this.placed.querySelector("button"), people);
    }
    if (this.isOpen()) {
      this.hold.request();
    }
    if (arrived.length) {
      this.noteArrivals(arrived.map((person) => person.name));
    }
  }

  // What the panel's rows say, as text, so a list that changes nothing shown (a game's data, the order of updates)
  // doesn't replace the buttons under a pointer
  signature(people, myGame) {
    const rows = people.map((person) => [
      person.id,
      person.name,
      person.avatar,
      person.game,
      statusText(person),
      Boolean(person.away),
      Boolean(person.you),
    ]);
    const elsewhere = this.host.presence.elsewhere;
    const keys = new Set([myGame, ...people.map((person) => person.game), ...Object.keys(elsewhere)]);
    const games = [...keys].filter(Boolean).map((key) => [key, this.host.gameName(key), this.host.gameIcon(key)]);
    return JSON.stringify([myGame, rows, games, elsewhere]);
  }

  render() {
    if (!this.host.inDiscord) {
      if (this.shown !== PREVIEW_TEXT) {
        this.body.replaceChildren(make(document, "p", "hub-panel-note", PREVIEW_TEXT));
        this.shown = PREVIEW_TEXT;
      }
      return;
    }
    const myGame = this.myGame();
    const people = this.people();
    const shown = this.signature(people, myGame);
    if (shown === this.shown) {
      return;
    }
    // The list redraws as status lines change, so keyboard focus on a button in it is put back after: on the Join for
    // the same person, or on the button with the same first class, such as Invite friends
    const active = this.body.contains(document.activeElement) ? document.activeElement : null;
    const joinId = active?.dataset.join;
    const refocus = joinId === undefined ? active && `.${active.classList[0]}` : `[data-join="${CSS.escape(joinId)}"]`;
    const { here, games, menu } = groups(people, myGame);
    const alone = !people.some((person) => !person.you);
    const join = (person) => this.host.join(person);
    const sections = alone ? [this.inviteSection(true)] : [];
    if (here.length) {
      sections.push(this.section(`Here in ${this.host.gameName(myGame)}`, here, null));
    }
    for (const [key, list] of games) {
      sections.push(this.section(this.host.gameName(key), list, join, key));
    }
    if (menu.length) {
      sections.push(this.section("In the menu", menu, null));
    }
    const elsewhere = Object.entries(this.host.presence.elsewhere);
    if (elsewhere.length) {
      sections.push(this.elsewhereSection(elsewhere));
    }
    if (!alone) {
      sections.push(this.inviteSection(false));
    }
    this.body.replaceChildren(...sections);
    this.shown = shown;
    if (refocus) {
      this.body.querySelector(refocus)?.focus();
    }
  }

  section(title, people, join, key = null) {
    const box = make(document, "section", "hub-group");
    const heading = make(document, "h3", "hub-group-title");
    const picture = key ? this.host.gameIcon(key) : null;
    if (picture) {
      const img = make(document, "img", "hub-game-icon");
      img.alt = "";
      img.addEventListener("error", () => img.remove());
      img.src = picture;
      heading.append(img);
    }
    heading.append(make(document, "span", "", title));
    if (key) {
      heading.append(make(document, "span", "hub-group-count", String(people.length)));
    }
    const list = make(document, "ul", "hub-people-list");
    const myGame = this.myGame();
    list.append(...people.map((person) => personRow(document, person, join && canJoin(person, myGame) ? join : null)));
    box.append(heading, list);
    return box;
  }

  elsewhereSection(entries) {
    const box = make(document, "section", "hub-group");
    box.append(make(document, "h3", "hub-group-title", "Playing in other channels"));
    const list = make(document, "ul", "hub-elsewhere");
    for (const [key, count] of entries) {
      list.append(make(document, "li", "", `${this.host.gameName(key)} · ${count}`));
    }
    box.append(list);
    return box;
  }

  inviteSection(alone) {
    const box = make(document, "section", alone ? "hub-invite alone" : "hub-invite");
    if (alone) {
      box.append(make(document, "p", "hub-panel-note", "Nobody else is here yet."));
    }
    const button = make(document, "button", alone ? "hub-invite-button primary" : "hub-invite-button", "Invite friends");
    button.type = "button";
    button.addEventListener("click", () => this.host.invite());
    box.append(button);
    return box;
  }

  noteArrivals(names) {
    const now = performance.now();
    if (now - this.noteStarted > MERGE_MS) {
      this.noted = [];
      this.noteStarted = now;
    }
    this.noted.push(...names);
    const wrap = this.placed || (this.floating.hidden ? null : this.floating);
    if (wrap) {
      showNote(wrap, arrivalText(this.noted));
    }
  }

  // ---------- The button's place over a game ----------

  // The game's page called connect(). Unless it places its own button straight after, the floating one shows
  connected() {
    requestAnimationFrame(() => this.float());
  }

  gameLoaded() {
    // A button from a page the frame has since left is gone with it
    if (this.placed && this.placed.ownerDocument !== this.host.frame?.contentDocument) {
      this.placed = null;
    }
    clearTimeout(this.floatTimer);
    this.floatTimer = setTimeout(() => this.float(), FLOAT_FALLBACK_MS);
  }

  float() {
    if (this.host.frame && !this.placed) {
      this.floating.hidden = false;
    }
  }

  gameClosed() {
    clearTimeout(this.floatTimer);
    this.floating.hidden = true;
    this.placed = null;
    this.close();
    // A question about leaving a game that is already gone has no answer to wait for
    this.answer?.(false);
  }

  // hub.peopleButton(): the button built in the game's own page, for the game to place
  frameButton(doc) {
    useStyles(doc);
    const wrap = buttonWrap(doc, () => this.open());
    this.placed = wrap;
    this.floating.hidden = true;
    clearTimeout(this.floatTimer);
    fillButton(wrap.querySelector("button"), this.people());
    return wrap;
  }

  // ---------- Join's question ----------

  confirmLeave(person) {
    // A question still open is answered as Stay, so the join that asked it ends
    this.answer?.(false);
    const here = this.host.gameName(this.myGame());
    const there = this.host.gameName(person.game);
    this.confirmText.textContent = `Leave ${here} to join ${isolate(person.name)} in ${there}?`;
    this.confirmBox.hidden = false;
    this.scrim.hidden = false;
    // Stay first, so a stray Enter never drops anyone out of a match
    this.stayButton.focus();
    return new Promise((resolve) => {
      this.answer = (leave) => {
        this.answer = null;
        this.confirmBox.hidden = true;
        this.scrim.hidden = !this.isOpen();
        if (!leave) {
          this.refocus(person);
        }
        resolve(leave);
      };
      this.leaveButton.onclick = () => this.answer(true);
      this.stayButton.onclick = () => this.answer(false);
    });
  }

  // After Stay, keyboard focus goes back to the Join button that asked, or the panel if the list has moved on
  refocus(person) {
    if (!this.isOpen()) {
      return;
    }
    const button = this.body.querySelector(`[data-join="${CSS.escape(person.id)}"]`);
    (button || this.closeButton).focus();
  }
}
