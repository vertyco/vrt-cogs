// The chip tray: chips add up to a bet within the table's range, the game's call (heads, a cup, low), and the
// Bet and Go buttons. All In swaps the chips for a multiplier, since it always bets the whole balance.
import { chipLabel, make, money } from "./format.js";
import { confirmBox } from "./panels.js";

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
    this.closed = false;
    // Set while All In's "are you sure?" box is up, so a second tap doesn't open another
    this.confirming = false;
    this.bind();
    this.renderChoices();
    $("multiplier").hidden = game !== "allin";
    $("all-in-warning").hidden = game !== "allin";
    $("chips").hidden = game === "allin";
    $("bet-line").hidden = game === "allin";
    $("place").textContent = game === "allin" ? "Pull" : "Bet";
    // All In's button spends the whole balance, so it is red instead of gold
    $("place").classList.toggle("danger", game === "allin");
    $("place").classList.toggle("primary", game !== "allin");
  }

  // Buttons in the page are shared by every table, so each tray removes its handlers when it closes
  listen(id, handler, event = "click") {
    const node = $(id);
    node.addEventListener(event, handler);
    this.bound.push([node, handler, event]);
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
    this.listen("mult-value", () => this.showAllIn(), "input");
  }

  close() {
    this.closed = true;
    for (const [node, handler, event] of this.bound) {
      node.removeEventListener(event, handler);
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
    this.showAllIn();
  }

  // All In's warning and button: how much a pull bets, its chance, and what a win pays
  showAllIn() {
    const multiplier = this.multiplier();
    $("all-in-stake").textContent = `Bets your whole balance: ${money(this.balance)}`;
    $("all-in-odds").textContent =
      multiplier < 2
        ? "The multiplier must be 2 or higher."
        : `1 in ${multiplier + 2} chance to win ${money(this.balance * multiplier)}. Lose and your balance is 0.`;
    $("place").textContent = `Bet all ${money(this.balance)}`;
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
      this.pull();
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

  // A pull bets the whole balance, so every pull asks first. A multiplier under 2 goes straight to the bot, which
  // refuses it and says why
  async pull() {
    if (this.confirming) {
      return;
    }
    const multiplier = this.multiplier();
    if (multiplier >= 2) {
      this.confirming = true;
      const sure = await confirmBox(
        `Bet your whole balance of ${money(this.balance)}? You have a 1 in ${multiplier + 2} chance to win ` +
          `${money(this.balance * multiplier)}. If you lose, your balance goes to 0.`,
        "Yes, go all in",
      );
      this.confirming = false;
      if (!sure || this.closed || this.blocked) {
        return;
      }
    }
    this.onBet({ t: "pull", multiplier });
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
    if (this.game === "allin") {
      this.showAllIn();
    }
    if (!blocked) {
      this.showAmount();
    }
  }
}
