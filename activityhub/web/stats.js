// The Stats tab: how much each game gets played, on phones or computers, by day and by hour, from the bot's play
// log. Read-only: nothing here changes a setting
const PERIODS = [
  [7, "7 days"],
  [30, "30 days"],
  [0, "All time"],
];
const CHART_TITLES = { day: "Plays per day", week: "Plays per week", month: "Plays per month" };
// The table's columns, each with the tip its heading shows on hover
const COLUMNS = [
  ["Game"],
  ["Plays"],
  ["Players", "Different people"],
  ["Typical", "The middle play length"],
  ["Phone", "Plays on phones"],
];
const HOUR_MARKS = new Set([0, 6, 12, 18, 23]);
// The bot sends each bar's first day as a plain date ("2026-10-16") already in the viewer's time, so it's read and
// shown in UTC to stay that same day
const DAY_NAME = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const SHORT_DAY = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
const MONTH_NAME = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric", timeZone: "UTC" });

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function option(value, label) {
  const node = el("option", "", label);
  node.value = value;
  return node;
}

function count(n, word) {
  return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
}

export function duration(seconds) {
  const total = Math.round(seconds);
  if (total < 60) {
    return `${total}s`;
  }
  const minutes = Math.floor(total / 60);
  if (minutes < 60) {
    return `${minutes}m ${String(total % 60).padStart(2, "0")}s`;
  }
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function percent(share) {
  return share === null ? "-" : `${Math.round(share * 100)}%`;
}

function dateOf(start) {
  return new Date(`${start}T00:00:00Z`);
}

// What a bar's tip says it covers
export function barName(kind, start) {
  if (kind === "week") {
    return `Week of ${SHORT_DAY.format(dateOf(start))}`;
  }
  return (kind === "month" ? MONTH_NAME : DAY_NAME).format(dateOf(start));
}

// Only the first, middle and last bars get a mark under them, so the marks fit on a phone
function marked(index, total) {
  return index === 0 || index === total - 1 || index === Math.floor((total - 1) / 2);
}

function barChart(title, bars) {
  const most = Math.max(1, ...bars.map((bar) => bar.plays));
  const figure = el("figure", "stats-chart");
  const row = el("div", "stats-bars");
  const marks = el("div", "stats-marks");
  const tip = el("p", "stats-tip");
  for (const bar of bars) {
    const column = el("span", "stats-bar");
    const text = `${bar.tip}: ${count(bar.plays, "play")}`;
    column.dataset.plays = String(bar.plays);
    column.style.setProperty("--fill", String(bar.plays / most));
    column.setAttribute("role", "img");
    column.setAttribute("aria-label", text);
    // Hovering shows the count with a mouse, pressing shows it on a phone
    column.addEventListener("pointerenter", () => (tip.textContent = text));
    column.addEventListener("click", () => (tip.textContent = text));
    row.append(column);
    marks.append(el("span", "", bar.mark));
  }
  figure.append(el("figcaption", "field-label", title), row, marks, tip);
  return figure;
}

export class StatsPanel {
  // load(query) asks the bot for the numbers. expired() runs when the login is gone for good
  constructor(load, expired) {
    this.load = load;
    this.expired = expired;
    this.days = 7;
    // A server id, "all" or "none". Null asks for wherever the Activity is running
    this.server = null;
    // The chart picker's game, or "" for all games
    this.game = "";
    this.asked = 0;
    this.data = null;
    this.root = el("div", "stats");
    this.root.append(el("p", "stats-note", "Loading…"));
    this.refresh();
  }

  async refresh() {
    const asked = ++this.asked;
    const query = new URLSearchParams({ days: String(this.days), offset: String(-new Date().getTimezoneOffset()) });
    if (this.server !== null) {
      query.set("server", this.server);
    }
    let data;
    try {
      data = await this.load(query.toString());
    } catch (e) {
      if (asked === this.asked) {
        this.failed(e);
      }
      return;
    }
    // A slower answer to an earlier choice must not replace the latest one
    if (asked !== this.asked) {
      return;
    }
    this.data = data;
    this.server = data.server;
    if (!(this.game in data.charts)) {
      this.game = "";
    }
    this.draw();
  }

  failed(e) {
    if (e.status === 401) {
      this.expired();
      return;
    }
    this.root.replaceChildren(el("p", "stats-note", e.message));
  }

  draw() {
    const parts = [this.controls()];
    if (this.data.games.length) {
      parts.push(this.overallLine(), this.table(), this.chartPicker(), this.chartBox());
    } else {
      parts.push(el("p", "stats-note stats-empty", "No plays in this period yet."));
    }
    this.root.replaceChildren(...parts);
  }

  controls() {
    const bar = el("div", "stats-controls");
    const periods = el("div", "stats-periods");
    periods.setAttribute("role", "group");
    periods.setAttribute("aria-label", "Period");
    for (const [days, name] of PERIODS) {
      const button = el("button", "stats-period", name);
      button.type = "button";
      button.dataset.days = String(days);
      button.setAttribute("aria-pressed", String(days === this.days));
      button.addEventListener("click", () => {
        for (const other of periods.children) {
          other.setAttribute("aria-pressed", String(other === button));
        }
        this.days = days;
        this.refresh();
      });
      periods.append(button);
    }
    bar.append(periods);
    if (this.data.servers) {
      bar.append(this.serverPicker());
    }
    return bar;
  }

  serverPicker() {
    const select = el("select", "stats-server");
    select.id = "stats-server";
    select.setAttribute("aria-label", "Server");
    select.append(option("all", "All servers"), ...this.data.servers.map((server) => option(server.id, server.name)));
    // The server the Activity runs in may have no plays yet, so it isn't in the list
    if (![...select.options].some((known) => known.value === this.server)) {
      select.append(option(this.server, "This server"));
    }
    select.value = this.server;
    select.addEventListener("change", () => {
      this.server = select.value;
      this.refresh();
    });
    return select;
  }

  overallLine() {
    const { plays, players, phone } = this.data.overall;
    const parts = [count(plays, "play"), count(players, "player")];
    if (phone !== null) {
      parts.push(`${percent(phone)} on phones`);
    }
    return el("p", "stats-overall", parts.join(" · "));
  }

  table() {
    const table = el("table", "stats-table");
    const head = el("tr");
    for (const [name, tip] of COLUMNS) {
      const cell = el("th", "", name);
      cell.scope = "col";
      if (tip) {
        cell.title = tip;
      }
      head.append(cell);
    }
    const thead = el("thead");
    thead.append(head);
    const body = el("tbody");
    for (const game of this.data.games) {
      const row = el("tr");
      row.dataset.key = game.key;
      row.append(
        el("td", "stats-game", game.name),
        el("td", "", game.plays.toLocaleString()),
        el("td", "", game.players.toLocaleString()),
        el("td", "", duration(game.typical)),
        el("td", "", percent(game.phone)),
      );
      body.append(row);
    }
    table.append(thead, body);
    return table;
  }

  chartPicker() {
    const select = el("select");
    select.id = "stats-game";
    select.append(option("", "All games"), ...this.data.games.map((game) => option(game.key, game.name)));
    select.value = this.game;
    select.addEventListener("change", () => {
      this.game = select.value;
      this.root.querySelector(".stats-charts").replaceWith(this.chartBox());
    });
    const label = el("label", "field-label", "Charts for");
    label.htmlFor = select.id;
    const box = el("div", "field");
    box.append(label, select);
    return box;
  }

  chartBox() {
    const chart = this.data.charts[this.game];
    const { kind, starts } = this.data.bars;
    const box = el("div", "stats-charts");
    const days = chart.bars.map((plays, i) => ({
      plays,
      tip: barName(kind, starts[i]),
      mark: marked(i, starts.length) ? (kind === "month" ? MONTH_NAME : SHORT_DAY).format(dateOf(starts[i])) : "",
    }));
    const hours = chart.hours.map((plays, hour) => ({
      plays,
      tip: `${hour}:00 to ${hour + 1}:00`,
      mark: HOUR_MARKS.has(hour) ? String(hour) : "",
    }));
    box.append(barChart(CHART_TITLES[kind], days), barChart("Busiest hours", hours));
    return box;
  }
}
