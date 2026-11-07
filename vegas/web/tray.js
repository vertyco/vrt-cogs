// The chip tray: chips add up to a bet within the table's range, the game's call (heads, a cup, low), and the
// Bet and Go buttons. All In swaps the chips for a multiplier, since it always bets the whole balance. Slots has no
// Bet button: its scene's lever places the bet.
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
  constructor(game, { onBet, onGo, onPreview, sound }) {
    this.game = game;
    this.onBet = onBet;
    this.onGo = onGo;
    // Told the bet (All In's multiplier) whenever it changes, so the scene can show what it would win
    this.onPreview = onPreview;
    this.previewed = null;
    this.sound = sound;
    this.min = 0;
    this.max = 0;
    this.amount = 0;
    this.choice = null;
    // The last bet placed at this table, for Repeat
    this.last = null;
    this.balance = 0;
    // Why the player can't bet now, from the last render ("" when they can), and why the lever was refused at Slots
    // ("" once the bet changes)
    this.blocked = "";
    this.hint = "";
    this.spinning = false;
    // What an All In spin staked, its balance and multiplier, so the tray keeps saying it while the wheel turns
    this.staked = null;
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
    $("place").textContent = game === "allin" ? "Bet all" : "Bet";
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
    this.hint = "";
    this.showWhy();
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

  // All In's warning and button: how much a spin bets, its chance, and what a win pays. While the wheel spins they
  // keep saying what the spin staked. With nothing left to bet, the warning says only why the player can't spin
  showAllIn() {
    const { balance, multiplier } = (this.spinning && this.staked) || {
      balance: this.balance,
      multiplier: this.multiplier(),
    };
    const broke = balance <= 0 && Boolean(this.blocked);
    $("all-in-warning").classList.toggle("plain", broke);
    // The amount is a part of its own, so a narrow dock can put it on a line of its own
    $("all-in-stake").replaceChildren(
      ...(broke ? [this.blocked] : ["Bets your whole balance: ", make("span", "sum", money(balance))]),
    );
    $("all-in-odds").textContent = broke
      ? ""
      : multiplier < 2
        ? "The multiplier must be 2 or higher."
        : `1 in ${multiplier + 2} chance to win ${money(balance * multiplier)}. Lose and your balance is 0.`;
    $("place").textContent = balance > 0 ? `Bet all ${money(balance)}` : "Bet all";
    this.announce();
  }

  // What the scene shows the bet as: the amount, or All In's multiplier
  preview() {
    return this.game === "allin" ? this.multiplier() : this.amount;
  }

  announce() {
    const value = this.preview();
    if (value !== this.previewed) {
      this.previewed = value;
      this.onPreview?.(value);
    }
  }

  showAmount() {
    $("amount").textContent = money(this.amount);
    const needsChoice = Boolean(CHOICES[this.game]) && this.choice === null;
    $("place").disabled = this.game !== "allin" && (needsChoice || this.amount < this.min || this.amount <= 0);
    if (this.game !== "allin") {
      $("place").textContent = needsChoice ? "Make your call" : `Bet ${money(this.amount)}`;
      this.announce();
    }
  }

  // Scenes call this too (the Slots lever), so it refuses whatever the greyed-out Place button would. False when
  // nothing was placed, a Slots pull among them when it couldn't reach the bot. Slots sends how hard the lever was
  // pulled, 0 to 1, with the bet
  place(strength = 0) {
    if (this.blocked) {
      return false;
    }
    if (this.game === "allin") {
      this.pull();
      return true;
    }
    if (this.game === "slots") {
      return this.pullLever(strength);
    }
    const bet = { t: "bet", amount: this.amount };
    if (CHOICES[this.game]) {
      bet.choice = this.choice;
    }
    this.last = { amount: this.amount, choice: this.choice };
    this.sound.play("bet");
    this.onBet(bet);
    return true;
  }

  // A Slots pull: refused with the reason under the tray when the bet is under the minimum or more than the balance
  pullLever(strength) {
    const least = Math.max(1, this.min);
    this.hint = "";
    if (this.amount < least) {
      this.hint = `Pick a bet of at least ${money(least)}.`;
    } else if (this.amount > this.balance) {
      this.hint = "You don't have enough credits for that bet.";
    }
    if (this.hint) {
      this.showWhy();
      return false;
    }
    this.last = { amount: this.amount, choice: null };
    return this.onBet({ t: "pull", amount: this.amount, strength });
  }

  // A spin bets the whole balance, so every spin asks first. A multiplier under 2 goes straight to the bot, which
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
    this.staked = { balance: this.balance, multiplier };
    this.onBet({ t: "pull", multiplier });
  }

  // Why the player can't bet, under the tray. At Slots and All In the status line already says what is spinning, and
  // All In's warning says it when the balance is gone
  showWhy() {
    const why = this.blocked || this.hint;
    const said = ["slots", "allin"].includes(this.game) && this.spinning;
    $("why").hidden = !why || said || (this.game === "allin" && this.balance <= 0);
    $("why").textContent = why;
  }

  // blocked: why the player can't bet now ("" when they can). canGo: they bet, and others are still betting.
  // spinning: a pull is on its way. All In's button stays in its place, greyed, while it can't be pressed, so the dock
  // and the wheel above it hold still
  render({ blocked, canGo, balance, spinning = false }) {
    this.balance = balance;
    this.blocked = blocked || "";
    this.spinning = spinning;
    $("tray").classList.toggle("blocked", Boolean(blocked));
    this.showWhy();
    $("go").hidden = !canGo;
    const allIn = this.game === "allin";
    $("place").hidden = canGo || (Boolean(blocked) && !allIn) || this.game === "slots";
    if (allIn) {
      $("place").disabled = Boolean(blocked);
    }
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
