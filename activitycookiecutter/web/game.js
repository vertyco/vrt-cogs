/// <reference path="activityhub.d.ts" />
// The page half of the game. The bot (main.py) runs the game and is its judge: this page only draws what the bot
// sends, and tells the bot what its player is pressing. So every screen shows the same game, and nobody can cheat by
// changing this file in their browser.
import { backToMenu, connect } from "activityhub";

const canvas = document.getElementById("field");
const pen = canvas.getContext("2d");
const hint = document.getElementById("hint");
const invite = document.getElementById("invite");

// Seat 0's colour, then seat 1's
const COLOURS = ["#5865f2", "#f0a232"];
// Names longer than this many letters are cut short on the field
const LONGEST_NAME = 16;
// Names on the field are never smaller than this many screen pixels, so they stay readable on a phone
const SMALLEST_TEXT = 11;
// The keys that steer, and which way each one steers, as [x step, y step]
const KEYS = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  KeyA: [-1, 0],
  KeyD: [1, 0],
  KeyW: [0, -1],
  KeyS: [0, 1],
};
// Why the live connection closed for good, by its close code. ActivityHub's DEVELOPERS.md lists every code
const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open the game again.",
  1011: "Couldn't join the game.",
  4003: "This game was turned off in this server.",
};

// Everything the bot has told this page so far
const game = {
  // This player's seat, 0 or 1, or null while watching
  you: null,
  // The field's size and a dot's size in the bot's units, and the time between updates in seconds
  field: { width: 800, height: 450, radius: 20, tick: 0.05 },
  // Each seat's player name, or null while the seat is free
  seats: [null, null],
  // The dots' spots in the newest update and in the one before it, and when the newest arrived
  newest: null,
  before: null,
  arrived: 0,
};

// The steering keys held down, and where a finger or mouse button is held on the field (in the bot's units) or null
const held = new Set();
let finger = null;
// The last move sent to the bot, as text like "1,0", so the same move is never sent twice
let sent = null;
// The live connection, once it is open
let conn = null;
// What the status line and the busy flag were last set to, so each is only sent again when it changes
let said = null;
let wasBusy = false;
// Cuts names by whole letters, so an emoji or an accented letter is never split in half
const letters = new Intl.Segmenter();

document.getElementById("back").addEventListener("click", backToMenu);

let hub;
try {
  hub = await connect();
} catch (e) {
  // Discord didn't accept the login. The Back button still works
  hint.textContent = e.message;
  throw e;
}
// Right after connect(), before any other await, so the hub's floating people button never shows
document.getElementById("people").append(hub.peopleButton());
invite.addEventListener("click", () => hub.openPeople());
const CONTROLS =
  hub.platform === "mobile"
    ? "Hold a finger where your dot should go."
    : "Steer with the arrow keys or WASD, or hold the mouse button where your dot should go.";

// Says what is going on: on the page, and next to this player's name in the hub's people lists
function showWhatsHappening() {
  const other = game.you === null ? null : game.seats[1 - game.you];
  const waiting = game.you !== null && other === null;
  const playing = game.you !== null && other !== null;
  let status = "Watching";
  hint.textContent = "Watching: both seats are taken.";
  if (waiting) {
    status = "Waiting for a player";
    hint.textContent = `Waiting for a second player. ${CONTROLS}`;
  } else if (playing) {
    status = `Playing vs ${other}`;
    hint.textContent = CONTROLS;
  }
  // A player alone gets an Invite button instead of an empty seat
  invite.hidden = !waiting;
  if (status !== said) {
    said = status;
    hub.status(status);
  }
  // Busy makes the hub ask before a friend's Join pulls this player out. Only on while both seats are filled
  if (playing !== wasBusy) {
    wasBusy = playing;
    hub.busy(playing);
  }
}

// Every message from the bot comes here. Each one holds some of: "you" and "field" (only to this page, when it joins),
// "seats" (to everyone, when someone sits or stands) and "spots" (to everyone, on every update)
function receive(data) {
  if ("you" in data) {
    game.you = data.you;
    game.field = data.field;
    // The bot's join ran afresh (on opening, or after a reconnect), so it needs to hear the current move again
    sent = null;
    fit();
  }
  if ("seats" in data) {
    game.seats = data.seats;
    showWhatsHappening();
  }
  if ("spots" in data) {
    game.before = game.newest || data.spots;
    game.newest = data.spots;
    game.arrived = performance.now();
  }
}

function closed(code) {
  conn = null;
  hint.textContent = CLOSED_BECAUSE[code] || "The game ended.";
  invite.hidden = true;
  said = "Not connected";
  hub.status(said);
  wasBusy = false;
  hub.busy(false);
}

async function goLive() {
  try {
    const live = await hub.socket();
    live.on(receive);
    // After a dropped network or a bot reload, the helper reconnects by itself, and the bot's join sends everything
    // again, which puts the hint back
    live.onReconnecting(() => {
      hint.textContent = "Reconnecting...";
    });
    live.onClose(closed);
    conn = live;
  } catch (e) {
    closed(e.status);
  }
}

// The move the player wants right now, as [x step, y step], each -1, 0 or 1
function wanted() {
  let x = 0;
  let y = 0;
  for (const code of held) {
    x += KEYS[code][0];
    y += KEYS[code][1];
  }
  // A held finger steers toward itself, and stops once the dot is under it
  if (finger !== null && game.newest !== null && game.you !== null) {
    const [dotX, dotY] = game.newest[game.you];
    const near = game.field.radius / 2;
    x = Math.abs(finger.x - dotX) > near ? finger.x - dotX : 0;
    y = Math.abs(finger.y - dotY) > near ? finger.y - dotY : 0;
  }
  // Opposite keys cancel out, and two keys the same way still make one step
  return [Math.sign(x), Math.sign(y)];
}

// Tells the bot when the move changes. The page sends what is pressed, never where the dot is: the bot moves it
function steer() {
  if (conn === null || game.you === null) {
    return;
  }
  const move = wanted();
  const text = move.join(",");
  // send() is false while the connection is reconnecting, so the move is tried again once it is back
  if (text !== sent && conn.send({ move })) {
    sent = text;
  }
}

window.addEventListener("keydown", (e) => {
  if (Object.hasOwn(KEYS, e.code)) {
    held.add(e.code);
    // Arrow keys would scroll the page too
    e.preventDefault();
  }
});
window.addEventListener("keyup", (e) => held.delete(e.code));

// A key let go while another window has the keyboard never reaches this page, so the dot would keep going for ever
function letGo() {
  held.clear();
  finger = null;
}
window.addEventListener("blur", letGo);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    letGo();
  }
});

// Where a pointer is on the field, in the bot's units
function onField(e) {
  const box = canvas.getBoundingClientRect();
  return {
    x: ((e.clientX - box.left) / box.width) * game.field.width,
    y: ((e.clientY - box.top) / box.height) * game.field.height,
  };
}
canvas.addEventListener("pointerdown", (e) => {
  // Keeps the finger's moves coming here even when it slides off the field
  canvas.setPointerCapture(e.pointerId);
  finger = onField(e);
});
canvas.addEventListener("pointermove", (e) => {
  if (finger !== null) {
    finger = onField(e);
  }
});
function lift() {
  finger = null;
}
canvas.addEventListener("pointerup", lift);
canvas.addEventListener("pointercancel", lift);

// Makes the field as big as fits between the bar and the footer, keeping its shape
function fit() {
  const stage = canvas.parentElement;
  const style = getComputedStyle(stage);
  const room = stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const { width, height } = game.field;
  const scale = Math.max(0, Math.min(room / width, stage.clientHeight / height));
  canvas.style.width = `${Math.floor(width * scale)}px`;
  canvas.style.height = `${Math.floor(height * scale)}px`;
  // As many canvas pixels as the screen has there, so it stays sharp on phones
  canvas.width = Math.max(1, Math.round(width * scale * devicePixelRatio));
  canvas.height = Math.max(1, Math.round(height * scale * devicePixelRatio));
}
new ResizeObserver(fit).observe(canvas.parentElement);

// Cuts a long name short, by whole letters
function shortName(name) {
  const parts = Array.from(letters.segment(name), (part) => part.segment);
  return parts.length <= LONGEST_NAME ? name : `${parts.slice(0, LONGEST_NAME - 1).join("")}…`;
}

function drawDot(seat, name, x, y, textSize) {
  const { width, height, radius } = game.field;
  pen.fillStyle = COLOURS[seat];
  pen.beginPath();
  pen.arc(x, y, radius, 0, Math.PI * 2);
  pen.fill();
  if (seat === game.you) {
    pen.lineWidth = 4;
    pen.strokeStyle = "#ffffff";
    pen.stroke();
  }
  // The name goes under the dot, or over it near the bottom, and never past the field's edge
  const label = seat === game.you ? "You" : shortName(name);
  const half = pen.measureText(label).width / 2;
  const below = y + radius + 4 + textSize < height;
  pen.fillStyle = "#f2f3f5";
  pen.textAlign = "center";
  pen.textBaseline = below ? "top" : "bottom";
  pen.fillText(label, Math.min(width - half, Math.max(half, x)), below ? y + radius + 4 : y - radius - 4);
}

// Draws one frame. The bot sends 20 updates a second and the screen shows 60 or more frames, so each dot slides from
// its spot in the update before to its spot in the newest one, instead of jumping
function draw(now) {
  requestAnimationFrame(draw);
  steer();
  const { width, height, tick } = game.field;
  // Everything is drawn in the bot's units, and the canvas scales them to its pixels
  pen.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
  pen.fillStyle = "#2b2d31";
  pen.fillRect(0, 0, width, height);
  if (game.newest === null) {
    return;
  }
  const t = Math.min(1, (now - game.arrived) / (tick * 1000));
  const textSize = Math.max(16, SMALLEST_TEXT / (canvas.clientWidth / width || 1));
  pen.font = `${textSize}px system-ui, sans-serif`;
  game.seats.forEach((name, seat) => {
    if (name === null) {
      return;
    }
    const [fromX, fromY] = game.before[seat];
    const [toX, toY] = game.newest[seat];
    drawDot(seat, name, fromX + (toX - fromX) * t, fromY + (toY - fromY) * t, textSize);
  });
}

if (hub.offline) {
  // The browser preview, outside Discord, has no live connection, so the page shows its look and nothing moves
  hint.textContent = "This is the browser preview. Open the game from Discord to play.";
} else {
  goLive();
}
fit();
requestAnimationFrame(draw);
