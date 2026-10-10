// Tanks' screens around the field: the tank cards, the info bar, setup, the shop and the results.
// Each render function draws from the bot's latest snapshot; buttons only send requests, the bot decides.

// The same tables as tanks/common/items.py (tests/test_page.py checks they match): name, price, pack
export const WEAPONS = [
  ["Small missile", 0, 0],
  ["Missile", 2000, 10],
  ["Small atom bomb", 5000, 2],
  ["Atom bomb", 13000, 1],
  ["Volcano bomb", 8000, 2],
  ["Shower", 9000, 2],
  ["Hot shower", 30000, 1],
  ["Small ball", 5000, 5],
  ["Ball", 6000, 2],
  ["Large ball", 15000, 1],
  ["Small ball V2", 6500, 5],
  ["Ball V2", 7500, 2],
  ["Large ball V2", 18000, 1],
  ["Air strike", 25000, 1],
];
export const EXTRAS = [
  ["Parachutes", 5000, 5],
  ["Repair kit", 4000, 5],
  ["Fuel", 3000, 50],
  ["Weak shield", 5000, 2],
  ["Shield", 10000, 1],
  ["Strong shield", 15000, 1],
  ["Super shield", 20000, 1],
  ["Teleport", 15000, 1],
  ["Upgrade energy", 5000, 1],
  ["Upgrade armor", 10000, 1],
  ["Upgrade engine", 7000, 1],
  ["Upgrade hill move", 5000, 1],
];
export const AIR_STRIKE = 13;
export const REPAIR = 1;
export const SHIELDS = [3, 4, 5, 6];
export const TELEPORT = 7;
const LEVELS = [
  ["very_easy", "Very easy"],
  ["easy", "Easy"],
  ["normal", "Normal"],
  ["hard", "Hard"],
  ["very_hard", "Very hard"],
];
const LEVEL_NAMES = Object.fromEntries(LEVELS);

let send = () => false;

export function setSender(sender) {
  send = sender;
}

function $(id) {
  return document.getElementById(id);
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    // Names come from Discord, so they only ever go in as text
    node.textContent = text;
  }
  return node;
}

function button(text, onClick, className = "button") {
  const node = make("button", className, text);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

export function money(amount) {
  return `$${Math.round(amount).toLocaleString("en-US")}`;
}

export function plural(count, word) {
  return `${count} ${count === 1 ? word : `${word}s`}`;
}

export function seatName(seat, index) {
  if (seat.kind === "empty") {
    return `Seat ${index + 1}`;
  }
  return seat.name;
}

function tag(text) {
  return make("span", "tag", text);
}

function seatTags(seat, index, state) {
  const tags = [];
  if (state.host === index) {
    tags.push(tag("Host"));
  }
  if (seat.kind === "cpu") {
    tags.push(tag(LEVEL_NAMES[seat.level]));
  }
  if (seat.standIn) {
    tags.push(tag("CPU playing"));
  } else if (seat.away) {
    tags.push(tag("Away"));
  }
  return tags;
}

function avatar(seat) {
  if (seat.kind === "human" && seat.avatar) {
    const image = make("img", "avatar");
    image.alt = "";
    image.src = seat.avatar;
    return image;
  }
  return make("span", "avatar", seat.kind === "cpu" ? "CPU" : "");
}

// ---------- Tank cards ----------

export function renderCards(state, mySeat) {
  const cards = state.seats.map((seat, index) => card(state, seat, index, mySeat));
  $("cards").replaceChildren(...cards.filter(Boolean));
}

function card(state, seat, index, mySeat) {
  const playing = state.stage !== "setup";
  // Empty seats show in the setup panel, and only tanks in the match show once it starts
  if (playing ? !state.kits[index] : seat.kind === "empty") {
    return null;
  }
  const node = make("li", `card seat-${index}`);
  node.dataset.kind = seat.kind;
  node.classList.toggle("mine", index === mySeat);
  node.classList.toggle("turn", state.turn === index);
  const name = make("span", "name", seatName(seat, index));
  name.append(...seatTags(seat, index, state));
  node.append(avatar(seat), name);
  if (playing) {
    node.append(numbers(state, index));
  }
  return node;
}

function numbers(state, index) {
  const kit = state.kits[index];
  const tank = state.tanks[index];
  const box = make("span", "numbers");
  if (tank) {
    const bar = make("span", "health");
    const fill = make("span", "fill");
    fill.style.width = `${Math.max(0, Math.min(100, (tank.health / tank.max) * 100))}%`;
    bar.append(fill);
    bar.title = `Health ${tank.health} of ${tank.max}`;
    box.append(bar);
  }
  box.append(make("span", "score", `Score ${kit.score.toLocaleString("en-US")}`));
  box.append(make("span", "money", money(kit.money)));
  box.append(make("span", "kills", plural(kit.kills, "kill")));
  return box;
}

// Health, money and score change during a shot; the playback updates the card before the next snapshot
export function updateCard(index, view) {
  const node = $("cards").querySelector(`.seat-${index}`);
  if (!node) {
    return;
  }
  const fill = node.querySelector(".health .fill");
  if (fill) {
    fill.style.width = `${Math.max(0, Math.min(100, (view.health / view.max) * 100))}%`;
  }
  node.querySelector(".score").textContent = `Score ${view.score.toLocaleString("en-US")}`;
  node.querySelector(".money").textContent = money(view.money);
  node.querySelector(".kills").textContent = plural(view.kills, "kill");
}

// ---------- The info bar ----------

// `aim` is the turn's barrel and power as drawn; `live` the bot's latest turn update
export function renderInfo(state, live, aim) {
  const turn = state.stage === "playing" ? state.turn : null;
  $("info").hidden = state.stage !== "playing";
  if (turn === null || !state.tanks[turn]) {
    $("info-turn").textContent = state.stage === "playing" ? "Waiting for a player" : "";
    return;
  }
  const seat = state.seats[turn];
  const tank = state.tanks[turn];
  const kit = state.kits[turn];
  const weapon = live ? live[6] : kit.weapon;
  $("info-turn").textContent = `${seatName(seat, turn)}'s turn`;
  $("info-turn").className = `turn seat-${turn}`;
  $("info-angle").textContent = `${aim.angle}°`;
  $("info-power").textContent = String(Math.round(aim.power));
  $("info-health").textContent = String(tank.health);
  $("info-fuel").textContent = String(live ? live[5] : tank.fuel);
  $("info-weapon").textContent = `${WEAPONS[weapon][0]} ${weapon === 0 ? "∞" : kit.guns[weapon]}`;
  const wind = state.field ? Math.round(state.field.wind) : 0;
  $("info-wind").textContent = wind === 0 ? "0" : `${wind > 0 ? "→" : "←"} ${Math.abs(wind)}`;
  const clock = live ? live[7] : state.clock;
  $("info-clock").textContent = clock === null ? "" : `${clock}s`;
  $("info-clock").classList.toggle("low", clock !== null && clock <= 5);
}

// ---------- Setup ----------

export function renderSetup(state, mySeat) {
  const isHost = mySeat !== null && state.host === mySeat;
  $("setup").hidden = state.stage !== "setup";
  $("seats").replaceChildren(...state.seats.map((seat, index) => setupRow(state, seat, index, mySeat, isHost)));
  $("rounds").value = String(state.rounds);
  $("landscape").value = String(state.landscape);
  $("timer").value = String(state.timer);
  $("rounds").disabled = !isHost;
  $("landscape").disabled = !isHost;
  $("timer").disabled = !isHost;
  const filled = state.seats.filter((seat) => seat.kind !== "empty").length;
  $("start").hidden = !isHost;
  $("start").disabled = filled < 2;
  $("stand").hidden = mySeat === null;
}

function setupRow(state, seat, index, mySeat, isHost) {
  const row = make("li", `seat seat-${index}`);
  row.dataset.kind = seat.kind;
  row.classList.toggle("mine", index === mySeat);
  const name = make("span", "name", seat.kind === "empty" ? "Empty seat" : seat.name);
  name.append(...seatTags(seat, index, state));
  row.append(make("span", "swatch"), name);
  if (seat.kind === "empty" && mySeat === null) {
    row.append(button("Sit here", () => send({ sit: index })));
  }
  if (isHost && seat.kind !== "human") {
    row.append(levelPicker(seat, index));
  }
  return row;
}

function levelPicker(seat, index) {
  const select = make("select", "button");
  select.setAttribute("aria-label", `Seat ${index + 1}`);
  select.append(new Option("Empty", ""));
  for (const [key, label] of LEVELS) {
    select.append(new Option(`CPU: ${label}`, key));
  }
  select.value = seat.kind === "cpu" ? seat.level : "";
  select.addEventListener("change", () => send({ cpu: [index, select.value || null] }));
  return select;
}

// ---------- The shop ----------

export function renderShop(state, mySeat) {
  const kit = mySeat === null ? null : state.kits[mySeat];
  $("shop").hidden = state.stage !== "shop";
  if (state.stage !== "shop") {
    return;
  }
  $("shop-clock").textContent = state.clock === null ? "" : `${state.clock}s`;
  // Watchers, and players who are done, see who the round is waiting on instead of the shelves
  const shopping = kit !== null && !state.done[mySeat];
  $("store").hidden = !shopping;
  $("done").hidden = !shopping;
  $("shoppers").hidden = shopping;
  if (!shopping) {
    const next = `Round ${state.round + 1} of ${state.rounds} starts when everyone is done.`;
    $("money").textContent = kit ? `${money(kit.money)} left. ${next}` : next;
    $("shoppers").replaceChildren(...shopperRows(state));
    return;
  }
  $("money").textContent = `${money(kit.money)} to spend`;
  $("weapons").replaceChildren(...WEAPONS.slice(1).map((item, i) => good("weapon", i + 1, item, kit.guns[i + 1], kit)));
  $("extras").replaceChildren(...EXTRAS.map((item, i) => good("item", i, item, kit.extras[i], kit)));
}

// Every tank in the match: computer tanks never shop, so they're always ready
function shopperRows(state) {
  return state.seats.flatMap((seat, index) => {
    const kit = state.kits[index];
    if (!kit) {
      return [];
    }
    let status = "Shopping";
    if (seat.kind === "cpu" || seat.standIn) {
      status = "Ready";
    } else if (state.done[index]) {
      status = "Done";
    } else if (seat.away) {
      status = "Away";
    }
    const row = make("li", `seat seat-${index}`);
    row.classList.toggle("ready", status === "Ready" || status === "Done");
    row.append(make("span", "swatch"), make("span", "name", seat.name), make("span", "detail", money(kit.money)));
    row.append(make("span", "status", status));
    return [row];
  });
}

function good(kind, index, [name, price, pack], owned, kit) {
  const node = make("li", "good");
  const picture = make("img", "icon");
  picture.alt = "";
  picture.src = `art/${kind === "weapon" ? "weapon" : "item"}_${String(index).padStart(2, "0")}.svg`;
  const label = make("span", "label", name);
  const detail = make("span", "detail", `${money(price)} for ${pack} · have ${owned}`);
  const buy = button("Buy", () => send({ buy: [kind, index] }));
  buy.disabled = kit.money < price;
  node.append(picture, label, detail, buy);
  return node;
}

// ---------- Results ----------

export function renderResults(state, mySeat) {
  $("results").hidden = state.stage !== "results";
  if (state.stage !== "results" || !state.results) {
    return;
  }
  const rows = [...state.results].sort((a, b) => b.score - a.score);
  const winners = rows.filter((row) => row.won);
  $("results-title").textContent =
    winners.length > 1 ? "It's a tie!" : `${winners[0] ? winners[0].name : "Nobody"} wins the match!`;
  $("standings").replaceChildren(...rows.map((row) => standing(row)));
  $("continue").hidden = !(mySeat !== null && state.host === mySeat);
}

function standing(row) {
  const node = make("li", `standing seat-${row.seat}`);
  node.classList.toggle("won", row.won);
  node.append(make("span", "swatch"), make("span", "name", row.name));
  node.append(make("span", "score", row.score.toLocaleString("en-US")));
  node.append(make("span", "kills", plural(row.kills, "kill")));
  return node;
}

// ---------- Your turn's controls ----------

export function renderWeapons(kit, weapon) {
  const options = WEAPONS.map(([name], index) => [name, index])
    .filter(([, index]) => index === 0 || kit.guns[index] > 0)
    .map(([name, index]) => new Option(`${name} ${index === 0 ? "∞" : kit.guns[index]}`, String(index)));
  $("weapon").replaceChildren(...options);
  $("weapon").value = String(weapon);
}

// Repair, the shields and teleport, each shown while there's at least one
export function renderItems(kit, tank, use) {
  const buttons = [];
  if (kit.extras[REPAIR] > 0) {
    const repair = button(`Repair ${kit.extras[REPAIR]}`, () => use("repair"));
    repair.disabled = tank.health >= tank.max;
    buttons.push(repair);
  }
  SHIELDS.forEach((item, n) => {
    if (kit.extras[item] > 0) {
      const shield = button(`${EXTRAS[item][0]} ${kit.extras[item]}`, () => use(["shield", n + 1]));
      shield.disabled = tank.shield !== null;
      buttons.push(shield);
    }
  });
  if (kit.extras[TELEPORT] > 0) {
    buttons.push(button(`Teleport ${kit.extras[TELEPORT]}`, () => use("teleport")));
  }
  $("items").replaceChildren(...buttons);
}

// ---------- Leaderboard ----------

export function renderLeaders(board, myId) {
  $("leaders").replaceChildren(...board.top.map((row) => leaderRow(row, myId)));
  if (!board.top.length) {
    $("you").textContent = "No matches yet. Be the first!";
  } else if (board.you) {
    $("you").textContent = `You: #${board.you.rank} with ${plural(board.you.wins, "win")}`;
  } else {
    $("you").textContent = "Finish a match to get on the board.";
  }
}

function leaderRow(row, myId) {
  const item = make("li");
  item.classList.toggle("mine", row.id === myId);
  item.append(make("span", "place", `#${row.rank}`), make("span", "name", row.name));
  const text = `${plural(row.wins, "win")} · ${plural(row.kills, "kill")} · ${plural(row.matches, "match")}`;
  item.append(make("span", "numbers", text));
  return item;
}
