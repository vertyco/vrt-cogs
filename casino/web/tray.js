// The chip tray: chips add up to a bet within the table's range, the game's call (heads, a cup, low), and the
// Bet and Go buttons. All In swaps the chips for a multiplier, since it always bets the whole balance.
import { chipLabel, make, money } from "./format.js";

export const DENOMINATIONS = [1, 5, 10, 25, 100, 500, 1000, 5000, 10000, 50000, 100000];
// The calls a game needs before a bet, in the order the buttons show
export const CHOICES = {
  coin: [
    ["heads", "Heads"],
    ["tails", "Tails"],
  ],
  cups: [
    [1, "Cup 1"],
    [2, "Cup 2"],
    [3, "Cup 3"],
  ],
  hilo: [
    ["low", "Low"],
    ["seven", "Seven"],
    ["high", "High"],
  ],
};

// The chips a table shows: every denomination up to its max
export function chipsFor(max) {
  return DENOMINATIONS.filter((value) => value <= max);
}

function $(id) {
  return document.getElementById(id);
}

export class Tray {
  constructor(game, { onBet, onGo, sound }) {
    this.game = game;
    this.onBet = onBet;
    this.onGo = onGo;
    this.sound = sound;
    this.min = 0;
    this.max = 0;
    this.amount = 0;
    this.choice = null;
    // The last bet placed at this table, for Repeat
    this.last = null;
    this.balance = 0;
    // Why the player can't bet now, from the last render ("" when they can)
    this.blocked = "";
    this.range = null;
    this.bound = [];
    this.bind();
    this.renderChoices();
    $("multiplier").hidden = game !== "allin";
    $("chips").hidden = game === "allin";
    $("bet-line").hidden = game === "allin";
    $("place").textContent = game === "allin" ? "Pull" : "Bet";
  }

  // Buttons in the page are shared by every table, so each tray removes its handlers when it closes
  listen(id, handler) {
    const node = $(id);
    node.addEventListener("click", handler);
    this.bound.push([node, handler]);
  }

  bind() {
    this.listen("clear", () => this.set(0));
    this.listen("min", () => this.set(this.min));
    this.listen("max", () => this.set(Math.min(this.max, this.balance)));
    this.listen("repeat", () => this.repeat());
    this.listen("place", () => this.place());
    this.listen("go", () => this.onGo());
    this.listen("mult-down", () => this.stepMultiplier(-1));
    this.listen("mult-up", () => this.stepMultiplier(1));
  }

  close() {
    for (const [node, handler] of this.bound) {
      node.removeEventListener("click", handler);
    }
    $("choices").replaceChildren();
    $("chips").replaceChildren();
  }

  // The table's bet range. The bet starts at the minimum, or stays where it was if it still fits. The chips are only
  // rebuilt when the range changes, so a tap is never lost to a redraw
  configure(game) {
    const range = `${game.min}-${game.max}`;
    if (range === this.range) {
      return;
    }
    this.range = range;
    this.min = game.min ?? 0;
    this.max = game.max ?? 0;
    if (this.amount < this.min || this.amount > this.max) {
      this.amount = this.min;
    }
    const fixed = this.game !== "allin" && this.min === this.max;
    $("chips").hidden = this.game === "allin" || fixed;
    $("clear").hidden = $("min").hidden = $("max").hidden = $("repeat").hidden = fixed;
    $("chips").replaceChildren(
      ...chipsFor(this.max).map((value) => {
        const chip = make("button", "chip", chipLabel(value));
        chip.type = "button";
        chip.dataset.value = String(value);
        chip.setAttribute("aria-label", `Add ${money(value)}`);
        chip.addEventListener("click", () => this.add(value));
        const item = make("li");
        item.append(chip);
        return item;
      }),
    );
    this.showAmount();
  }

  renderChoices() {
    const options = CHOICES[this.game] || [];
    $("choices").hidden = !options.length;
    $("choices").replaceChildren(
      ...options.map(([value, label]) => {
        const node = make("button", "button", label);
        node.type = "button";
        node.dataset.choice = String(value);
        node.setAttribute("aria-pressed", "false");
        node.addEventListener("click", () => this.choose(value));
        return node;
      }),
    );
  }

  choose(value) {
    this.choice = value;
    this.sound.play("click");
    for (const node of $("choices").children) {
      node.setAttribute("aria-pressed", String(node.dataset.choice === String(value)));
    }
    this.showAmount();
  }

  add(value) {
    this.sound.play("chip");
    this.set(this.amount + value);
  }

  set(amount) {
    this.amount = Math.max(0, Math.min(amount, this.max));
    this.showAmount();
  }

  repeat() {
    if (!this.last) {
      return;
    }
    this.set(this.last.amount);
    if (this.last.choice !== null) {
      this.choose(this.last.choice);
    }
  }

  multiplier() {
    const value = Math.floor(Number($("mult-value").value));
    return Number.isFinite(value) ? value : 0;
  }

  stepMultiplier(by) {
    $("mult-value").value = String(Math.max(2, this.multiplier() + by));
    this.sound.play("click");
  }

  showAmount() {
    $("amount").textContent = money(this.amount);
    const needsChoice = Boolean(CHOICES[this.game]) && this.choice === null;
    $("place").disabled = this.game !== "allin" && (needsChoice || this.amount < this.min || this.amount <= 0);
    if (this.game !== "allin") {
      $("place").textContent = needsChoice ? "Make your call" : `Bet ${money(this.amount)}`;
    }
  }

  // Scenes call this too (All In's lever), so it refuses whatever the greyed-out Place button would
  place() {
    if (this.blocked) {
      return;
    }
    if (this.game === "allin") {
      const multiplier = this.multiplier();
      this.onBet({ t: "pull", multiplier });
      return;
    }
    const bet = { t: "bet", amount: this.amount };
    if (CHOICES[this.game]) {
      bet.choice = this.choice;
    }
    this.last = { amount: this.amount, choice: this.choice };
    this.sound.play("bet");
    this.onBet(bet);
  }

  // blocked: why the player can't bet now ("" when they can). canGo: they bet, and others are still betting
  render({ blocked, canGo, balance }) {
    this.balance = balance;
    this.blocked = blocked || "";
    $("tray").classList.toggle("blocked", Boolean(blocked));
    $("why").hidden = !blocked;
    $("why").textContent = blocked;
    $("go").hidden = !canGo;
    $("place").hidden = canGo || Boolean(blocked);
    for (const chip of $("chips").querySelectorAll(".chip")) {
      chip.disabled = Number(chip.dataset.value) > balance;
    }
    if (!blocked) {
      this.showAmount();
    }
  }
}
