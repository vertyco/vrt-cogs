// The settings panel for casino admins: the casino, its games, memberships, players, and the danger zone.
// The bot checks every change again and says what's wrong, so this page only helps fill the forms in.
import { TIER_COLORS, avatar, button, duration, make, money } from "./format.js";

const ZERO_MULTIPLIER = "Wait a minute... zero?! Really... I'm a bot and that's more heartless than me! Who hurt you, human?";
const RESETS = [
  ["settings", "The casino's settings"],
  ["games", "Every game's settings"],
  ["cooldowns", "Everyone's cooldowns"],
  ["memberships", "Every membership"],
  ["all", "All four"],
];

function $(id) {
  return document.getElementById(id);
}

function field(label, input) {
  const node = make("label");
  node.append(label, input);
  return node;
}

function input(type, value, extra = {}) {
  const node = make("input");
  node.type = type;
  if (type === "checkbox") {
    node.checked = Boolean(value);
  } else {
    node.value = value === null || value === undefined ? "" : String(value);
  }
  Object.assign(node, extra);
  return node;
}

function toggle(label, on) {
  const box = input("checkbox", on);
  const node = make("label", "switch");
  node.append(box, label);
  return [node, box];
}

function choose(options, value) {
  const node = make("select");
  for (const [optionValue, label] of options) {
    const option = make("option", "", label);
    option.value = optionValue;
    option.selected = String(optionValue) === String(value ?? "");
    node.append(option);
  }
  return node;
}

export function settingsTabs(settings, tools) {
  const view = { settings, tools, tab: "Casino" };
  const tabs = {
    Casino: casinoTab,
    Games: gamesTab,
    Memberships: tiersTab,
    Players: playersTab,
    "Danger zone": dangerTab,
  };
  const nav = $("panel-tabs");
  nav.hidden = false;
  view.show = (name) => {
    view.tab = name;
    for (const node of nav.children) {
      node.setAttribute("aria-selected", String(node.textContent === name));
    }
    const body = $("panel-body");
    body.replaceChildren();
    tabs[name](body, view);
  };
  nav.replaceChildren(...Object.keys(tabs).map((name) => button(name, "", () => view.show(name))));
  view.show("Casino");
}

// Saves through the bot. A refusal shows its reason; a success shows "Saved." and returns the bot's answer
async function save(view, name, data) {
  try {
    const result = await view.tools.ask(name, data);
    if (result) {
      view.tools.toast("Saved.");
    }
    return result;
  } catch (e) {
    view.tools.toast(e.message);
    return null;
  }
}

// ---------- Casino ----------

function casinoTab(body, view) {
  const s = view.settings;
  const name = input("text", s.name, { maxLength: 30 });
  const [openSwitch, open] = toggle("The casino is open", s.open);
  const [limitSwitch, limitOn] = toggle("Hold big wins for review", s.limit_on);
  const amount = input("number", s.limit_amount, { min: 0, step: 1 });
  const form = make("div", "form");
  form.append(field("Name", name), openSwitch, limitSwitch, field("Payout limit", amount));
  const store = button("Save", "button primary", async () => {
    const data = { name: name.value, is_open: open.checked, limit_on: limitOn.checked, limit_amount: amount.value };
    const result = await save(view, "save_casino", data);
    if (result) {
      Object.assign(view.settings, result);
    }
  });
  body.append(
    form,
    make("p", "dim", "Closing the casino stops every game. Wins over the payout limit wait for an admin to release them."),
    make("div", "actions"),
  );
  body.lastChild.append(store);
}

// ---------- Games ----------

function gameRow(view, key, game) {
  const noRange = key === "allin";
  const noMultiplier = key === "allin" || key === "double";
  const open = input("checkbox", game.open);
  const access = input("number", game.access, { min: 0, step: 1 });
  const cooldown = input("text", game.cooldown, { title: duration(game.cooldown), placeholder: "seconds or HH:MM:SS" });
  const min = noRange ? "-" : input("number", game.min, { min: 0, step: 1 });
  const max = noRange ? "-" : input("number", game.max, { min: 0, step: 1 });
  const multiplier = noMultiplier ? "-" : input("number", game.multiplier, { min: 0, step: 0.1 });
  const store = button("Save", "button small", async () => {
    const data = { game: key, is_open: open.checked, access: access.value, cooldown: cooldown.value };
    if (!noRange) {
      Object.assign(data, { min_bet: min.value, max_bet: max.value });
    }
    if (!noMultiplier) {
      data.multiplier = multiplier.value;
    }
    const result = await save(view, "save_game", data);
    if (result) {
      Object.assign(view.settings, result);
      if (!noMultiplier && Number(multiplier.value) === 0) {
        view.tools.toast(ZERO_MULTIPLIER);
      }
    }
  });
  return [game.name, open, access, cooldown, min, max, multiplier, store];
}

function gamesTab(body, view) {
  const rows = Object.entries(view.settings.games).map(([key, game]) => gameRow(view, key, game));
  body.append(
    view.tools.grid(["Game", "Open", "Access", "Cooldown", "Min", "Max", "Payout", ""], rows),
    make("p", "dim", "Cooldowns take seconds or HH:MM:SS. The payout multiplier is what a win pays back, bet included."),
  );
}

// ---------- Memberships ----------

function tiersTab(body, view) {
  const add = button("New membership", "button primary", () => tierForm(body, view, null));
  body.append(make("div", "actions"));
  body.lastChild.append(add);
  if (!view.settings.tiers.length) {
    body.append(make("p", "dim", "There are no memberships yet. Everyone plays as Basic."));
  }
  for (const tier of view.settings.tiers) {
    const card = view.tools.tierCard(tier);
    const actions = make("div", "actions");
    actions.append(
      button("Edit", "button small", () => tierForm(body, view, tier)),
      button("Delete", "button small danger", () => deleteTier(view, tier)),
    );
    card.append(actions);
    body.append(card);
  }
}

function tierForm(body, view, tier) {
  const t = tier || { name: "", color: "blue", access: 0, reduction: 0, bonus: 1.0 };
  const global = view.settings.global;
  const parts = {
    name: input("text", t.name, { maxLength: 32 }),
    color: choose(
      Object.keys(TIER_COLORS)
        .filter((name) => name !== "grey")
        .map((name) => [name, name]),
      t.color,
    ),
    access: input("number", t.access, { min: 0, step: 1 }),
    reduction: input("number", t.reduction, { min: 0, step: 1 }),
    bonus: input("number", t.bonus, { min: 0, step: 0.1 }),
    req_credits: input("number", t.req_credits, { min: 0, step: 1 }),
    req_days: input("number", t.req_days, { min: 0, step: 1 }),
    req_role_id: choose(roleOptions(view.settings.roles, t.req_role_id), t.req_role_id),
  };
  const form = make("div", "form");
  form.append(
    field("Name", parts.name),
    field("Color", parts.color),
    field("Access level", parts.access),
    field("Cooldown reduction (seconds)", parts.reduction),
    field("Bonus payout multiplier", parts.bonus),
    field("Needs credits", parts.req_credits),
    field(global ? "Needs days on Discord" : "Needs days in the server", parts.req_days),
  );
  if (!global) {
    form.append(field("Needs role", parts.req_role_id));
  }
  // A membership with no requirements goes to every player, so the form says so while it has none
  const warning = make("p", "warn", view.settings.open_tier_warning || "");
  const needs = global ? [parts.req_credits, parts.req_days] : [parts.req_credits, parts.req_days, parts.req_role_id];
  const checkNeeds = () => {
    warning.hidden = needs.some((node) => node.value !== "" && node.value !== "0");
  };
  for (const node of needs) {
    node.addEventListener("input", checkNeeds);
    node.addEventListener("change", checkNeeds);
  }
  checkNeeds();
  const store = button("Save", "button primary", async () => {
    const data = Object.fromEntries(Object.entries(parts).map(([key, node]) => [key, node.value]));
    if (tier) {
      data.id = tier.id;
    }
    const result = await save(view, "save_membership", data);
    if (result) {
      view.settings.tiers = result.tiers;
      view.show("Memberships");
    }
  });
  const cancel = button("Cancel", "button", () => view.show("Memberships"));
  const actions = make("div", "actions");
  actions.append(store, cancel);
  body.replaceChildren(make("h3", "", tier ? `Edit ${tier.name}` : "New membership"), form, warning, actions);
}

// The tier keeps a role that was deleted from the server, so saving without touching it doesn't drop it
function roleOptions(roles, current) {
  const options = [["", "No role"], ...roles.map((role) => [role.id, role.name])];
  if (current && !roles.some((role) => String(role.id) === String(current))) {
    options.push([String(current), "Deleted role"]);
  }
  return options;
}

async function deleteTier(view, tier) {
  if (!(await view.tools.confirmBox(`Delete ${tier.name}? Its players go back to Basic. This can't be undone.`))) {
    return;
  }
  const result = await save(view, "delete_membership", { id: tier.id });
  if (result) {
    view.settings.tiers = result.tiers;
    view.show("Memberships");
  }
}

// ---------- Players ----------

function playersTab(body, view) {
  const query = input("search", "", { placeholder: "Search by name" });
  const found = make("ol", "found");
  const card = make("div");
  const search = async () => {
    const result = await save(view, "find_players", { query: query.value });
    found.replaceChildren(
      ...(result ? result.players : []).map((player) => {
        const item = make("li");
        const pick = button("", "", () => playerCard(card, view, player.id));
        pick.append(avatar(player.avatar), make("span", "", `${player.name} (${player.username})`));
        item.append(pick);
        return item;
      }),
    );
  };
  query.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      search();
    }
  });
  const row = make("div", "actions");
  row.append(query, button("Search", "button", search));
  body.append(row, found, card);
}

async function playerCard(card, view, userId) {
  let stats;
  try {
    stats = await view.tools.ask("player_card", { user_id: userId });
  } catch (e) {
    view.tools.toast(e.message);
    return;
  }
  if (!stats) {
    return;
  }
  const update = async (op, extra = {}, question = "") => {
    if (question && !(await view.tools.confirmBox(question))) {
      return;
    }
    const result = await save(view, "player_update", { user_id: userId, op, ...extra });
    if (result) {
      playerCard(card, view, userId);
    }
  };
  const tiers = choose(
    view.settings.tiers.map((tier) => [tier.id, tier.name]),
    stats.membership_id,
  );
  const membership = make("div", "actions");
  membership.append(
    tiers,
    button("Give", "button small", () => update("assign", { membership_id: tiers.value })),
    button("Revoke", "button small", () => update("revoke")),
  );
  const resets = make("div", "actions");
  resets.append(
    button(`Release ${money(stats.pending)} held`, "button small", () => update("release")),
    button("Reset cooldowns", "button small", () => update("reset_cooldowns", {}, `Reset ${stats.name}'s cooldowns?`)),
    button("Reset stats", "button small danger", () => update("reset_stats", {}, `Reset ${stats.name}'s stats?`)),
    button("Reset everything", "button small danger", () =>
      update("reset_all", {}, `Reset all of ${stats.name}'s casino data?`),
    ),
  );
  resets.firstChild.disabled = !stats.pending;
  const handNote = stats.by_hand ? "Given by hand: the automatic update leaves it alone." : "Set by the automatic update.";
  card.replaceChildren(view.tools.statsView(stats), make("h3", "", "Membership"), make("p", "dim", handNote));
  if (view.settings.tiers.length) {
    card.append(membership);
  }
  card.append(make("h3", "", "Credits and resets"), resets);
}

// ---------- Danger zone ----------

function dangerTab(body, view) {
  const what = choose(RESETS, "settings");
  const reset = button("Reset", "button danger", async () => {
    const label = RESETS.find(([value]) => value === what.value)[1];
    if (!(await view.tools.confirmBox(`Reset ${label.toLowerCase()}? Players' stats are kept. This can't be undone.`))) {
      return;
    }
    const result = await save(view, "reset_casino", { what: what.value });
    if (result) {
      Object.assign(view.settings, result);
    }
  });
  const row = make("div", "actions");
  row.append(what, reset);
  body.append(make("h3", "", "Reset the casino"), row);
  if (view.settings.owner) {
    ownerZone(body, view);
  }
}

function ownerZone(body, view) {
  const global = view.settings.global;
  const mode = button(global ? "Switch to server mode" : "Switch to global mode", "button danger", async () => {
    const question = global
      ? "Switch to one casino per server? The global casino's data is kept for when you switch back."
      : "Switch to one global casino for every server? Each server's data is kept for when you switch back.";
    if (await view.tools.confirmBox(question)) {
      const result = await save(view, "set_mode", { global: !global });
      if (result) {
        view.settings.global = result.global;
        view.show("Danger zone");
      }
    }
  });
  const wipe = button("Wipe all casino data", "button danger", async () => {
    if (await view.tools.confirmBox("Delete all casino data in every server, including players? This can't be undone.")) {
      await save(view, "wipe", {});
    }
  });
  body.append(
    make("h3", "", "Bot owner"),
    make("p", "", global ? "The casino is global: one casino for every server." : "Each server has its own casino."),
    make("div", "actions"),
  );
  body.lastChild.append(mode, wipe);
}
