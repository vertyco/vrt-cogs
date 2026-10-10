// A stand-in scene that writes the table out in words. Every game starts with it, so the casino is fully playable
// before its art exists; each game's art task replaces it with that game's real scene.
//
// What every scene is. scenes/<game>.js exports `async createScene(stage)` and returns an object with:
//   show(state)        Draw the table as the bot's latest "table" message describes it, without animating. Called on
//                      every update and to catch up after a drop, so it must be safe to call any number of times.
//   play(event)        Animate one "event" message and resolve when done. Must finish within table.js's PACE for
//                      its kind (the bot waits that long before its next step); the page moves on after that anyway.
//   result(result)     Optional: a flourish for the player's own "result" message. The dock shows the words.
//   layout(w, h)       The scene's space changed size, in CSS pixels. Fit the scene to it (kit.js's fit helps).
//   destroy()          Optional: stop timers. The page destroys the Pixi app and everything in it afterwards.
// The stage it gets:
//   app, root          The Pixi Application and a Container on its stage to draw into.
//   game, title        The game's key ("war") and its display name ("War").
//   sound              sound.play(name), with a name from sound.js's EFFECT_NAMES.
//   me()               The viewer's Discord id as a string, or null.
//   nameOf(id)         A player's display name at this table.
//   actions            For taps inside the scene: choose(value) picks the game's call, sit(seat) and stand() for
//                      Blackjack's seats, move(name) sends an allowed move, place() places the tray's bet.
import { Graphics, Text } from "../vendor/pixi.min.mjs";
import { fit, fitted, wait } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
const SOUNDS = { flip: "coin", shuffle: "cups", roll: "throw", deal: "deal", reveal: "slide", burn: "slide", pull: "lever" };
const SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };

function cardText(card) {
  if (!card) {
    return "[?]";
  }
  const [rank, suit] = card;
  return `[${rank}${SUITS[suit[0]] || suit}]`;
}

function cardsText(cards) {
  return (cards || []).map(cardText).join(" ");
}

// One line per thing on the table, in the words a dealer would say
function describe(state, nameOf) {
  const lines = [];
  if (state.drawn) {
    const drawn = state.drawn;
    lines.push(drawn.side ? `The coin shows ${drawn.side}` : drawn.cup ? `The coin is under cup ${drawn.cup}` : "");
    lines.push(drawn.dice ? `The dice show ${drawn.dice.join(" and ")}` : "");
  }
  if (state.rolls && state.rolls.length) {
    lines.push(`Rolls: ${state.rolls.map((dice) => dice.join("+")).join(", ")}`);
  }
  if (state.point) {
    lines.push(`The point is ${state.point}`);
  }
  if (state.dealer) {
    const dealer = state.dealer.cards ? state.dealer.cards : [state.dealer, state.war_dealer].filter(Boolean);
    lines.push(`Dealer: ${cardsText(dealer)}${state.dealer.total ? ` (${state.dealer.total})` : ""}`);
  }
  for (const [id, hand] of Object.entries(state.hands || {})) {
    const cards = hand.cards ? hand.cards : [hand.card, hand.war_card].filter(Boolean);
    const total = hand.total ? ` (${hand.total})` : "";
    lines.push(`${nameOf(id)}: ${cardsText(cards)}${total} ${hand.status || ""}`);
  }
  if (state.flips && state.flips.length) {
    lines.push(`Flips: ${state.flips.join(", ")}`);
  }
  for (const [id, row] of Object.entries(state.standing || {})) {
    lines.push(`${nameOf(id)}: ${row.amount} (${row.status})`);
  }
  return lines.filter(Boolean).join("\n");
}

function eventText(event, nameOf) {
  switch (event.kind) {
    case "flip":
      return `Flip... ${event.side}!`;
    case "shuffle":
      return "The cups shuffle...";
    case "roll":
      return `Roll: ${event.dice.join(" + ")}${event.shooter ? ` (${nameOf(event.shooter)} threw)` : ""}`;
    case "deal":
      return `${event.to === "dealer" ? "Dealer" : nameOf(event.to)} gets ${cardText(event.card)}`;
    case "reveal":
      return `The dealer turns over ${cardText(event.card)}`;
    case "burn":
      return `The dealer burns ${event.count} cards`;
    case "pull":
      return `The reels spin at ${event.multiplier}x...`;
    default:
      return event.kind;
  }
}

export async function createScene(stage) {
  const root = fitted(WIDTH, HEIGHT);
  const felt = new Graphics().roundRect(0, 0, WIDTH, HEIGHT, 40).fill(0x0b4424).stroke({ width: 10, color: 0xd4af37 });
  const style = {
    fill: 0xf6ecd2,
    fontFamily: "Georgia, serif",
    fontSize: 30,
    align: "center",
    wordWrap: true,
    wordWrapWidth: WIDTH - 80,
  };
  const title = new Text({ text: stage.title, style: { ...style, fill: 0xf3d77a, fontSize: 46, wordWrap: false } });
  title.anchor.set(0.5, 0);
  title.position.set(WIDTH / 2, 30);
  const body = new Text({ text: "", style: { ...style, wordWrapWidth: WIDTH - 80 } });
  body.anchor.set(0.5, 0);
  body.position.set(WIDTH / 2, 120);
  const news = new Text({ text: "", style: { ...style, fill: 0xf3d77a, fontSize: 34 } });
  news.anchor.set(0.5, 1);
  news.position.set(WIDTH / 2, HEIGHT - 40);
  root.addChild(felt, title, body, news);
  stage.root.addChild(root);
  return {
    show(state) {
      body.text = describe(state, stage.nameOf);
    },
    async play(event) {
      news.text = eventText(event, stage.nameOf);
      stage.sound.play(SOUNDS[event.kind] || "click");
      await wait(250);
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {},
  };
}
