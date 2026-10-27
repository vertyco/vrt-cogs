// The menu's side of ActivityHub: the only place that starts the Discord toolkit. Discord accepts one
// toolkit handshake per Activity frame, so games run in an inner frame and borrow this login, and this
// page must never navigate or reload itself while inside Discord.
import { DiscordSDK } from "./vendor/discord-sdk.js";
import { HEAT_EVENT, request } from "./sdk.js";
import { PeopleUI } from "./people.js";
import { Presence } from "./presence.js";

export const GAME_FRAME_ID = "game-frame";
// How long a game takes to fade in over the menu
const FADE_MS = 200;
// A game whose page never finishes loading still shows after this long, so the screen never just stays empty
const SHOW_ANYWAY_MS = 4000;
// Discord answers the toolkit within a few seconds. The page warns after this long, but keeps waiting, since
// Discord can be slow to start on a phone
const DISCORD_WAIT_MS = 10000;
const DISCORD_SILENT =
  "Discord hasn't answered yet. This address only works inside Discord; for the browser preview, " +
  "open / without the ?frame_id=... part.";
// The message a Discord toolkit sends first, to the page around it: [HANDSHAKE, {..., frame_id}]
const HANDSHAKE = 0;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const SAFE_SIDES = ["top", "right", "bottom", "left"];
// The longest text a game can add to the frame rate counter, which is one small pill
const STAT_MAX = 40;
// What hub.status() passes on. The bot cuts or drops anything longer too
const STATUS_MAX = 60;
const DATA_MAX = 1024;
// Half an emoji in JSON text: JSON.stringify writes a lone surrogate as an escape like \ud83d, which the bot can't
// turn back into text. A backslash that is itself escaped (\\ud83d) is only text, so the escapes are paired off
const LONE_SURROGATE = /(?:^|[^\\])(?:\\\\)*\\u[dD][89a-fA-F]/;
// What Discord says a device is, in the platform part of the Activity's address
const PLATFORMS = ["desktop", "mobile"];
// A game's card note, and the message shown instead of opening it, on a device the game doesn't work on, or outside
// the bot's servers for a game that only opens in them
const ONLY_ON = { desktop: "Desktop only", mobile: "Mobile only", server: "Servers only" };
const WORKS_ON = {
  desktop: "only works on desktop: Discord's computer app or discord.com in a browser.",
  mobile: "only works on mobile: Discord's phone and tablet app.",
  server: "only opens in a Discord server this bot is in.",
};

// An invisible box padded by the room Discord's own buttons (the back pill and Leave) and the phone's notch take
// at each edge. Discord sets --discord-safe-area-inset-* on this page only; iOS gives only the browser's env()
function safeAreaProbe() {
  const probe = document.createElement("div");
  probe.setAttribute("aria-hidden", "true");
  const padding = SAFE_SIDES.map((side) => `var(--discord-safe-area-inset-${side}, env(safe-area-inset-${side}, 0px))`);
  probe.style.cssText = `position: fixed; top: 0; left: 0; visibility: hidden; pointer-events: none; padding: ${padding.join(" ")}`;
  document.body.append(probe);
  return probe;
}

function gamePath(key) {
  return `/games/${encodeURIComponent(key)}/`;
}

// Whether the frame went somewhere other than the game's own pages. Another website's address can't be read
function leftGame(frame, key) {
  try {
    return !frame.contentWindow.location.pathname.startsWith(gamePath(key));
  } catch (e) {
    return true;
  }
}

// How long each loading step took, in the browser console, for finding what makes the menu slow to open
export function mark(step) {
  console.info(`ActivityHub: ${step} at ${Math.round(performance.now())} ms`);
}

// The page carries the login settings, so it doesn't wait on a request for them
async function loginConfig() {
  const tag = document.getElementById("hub-config");
  return tag ? JSON.parse(tag.textContent) : request("/hub/api/config");
}

async function authorize(sdk, scopes) {
  const { code } = await sdk.commands.authorize({
    client_id: sdk.clientId,
    response_type: "code",
    state: "",
    prompt: "none",
    scope: scopes,
  });
  return code;
}

// Every game's scopes share this one login, so one scope Discord refuses (or the player pressing Cancel) would stop
// every game from logging in. The login is then tried once more with identify alone, which stays for later logins
// too. Only the first login tells the bot what was dropped, so its log can name the games that asked. A later login
// (after a bot restart) never calls authenticate again, so the toolkit keeps the permissions of the first one, and
// reporting a refusal then would make the bot's log say something untrue
async function getLogin(host, first = false) {
  const extra = host.scopes.filter((scope) => scope !== "identify");
  let code;
  let dropped = null;
  try {
    code = await authorize(host.sdk, host.scopes);
  } catch (e) {
    if (!extra.length) {
      throw e;
    }
    console.warn(`ActivityHub: Discord refused the login with ${extra.join(", ")}, so it asks for identify only`, e);
    dropped = first ? { scopes: extra, reason: String(e?.message ?? e) } : null;
    code = await authorize(host.sdk, ["identify"]);
    // Only once Discord takes the smaller login, so a retry that fails for another reason asks again next time
    host.scopes = ["identify"];
  }
  mark("Discord authorized the login");
  const body = { code, instance_id: host.sdk.instanceId, ...(dropped ? { dropped } : {}) };
  const login = await request("/hub/api/token", { body });
  mark("the bot logged the player in");
  return { session: login.session, accessToken: login.access_token, player: login.player, menu: login.menu };
}

// A copy of the data a game passed to hub.status() when the bot can pass it on, else null. It is a copy so the game
// changing its object later can't push it over the limit or break it, since it is sent up to 250 ms after the call
// and again after every reconnect
function statusData(data) {
  let text;
  try {
    text = JSON.stringify(data ?? null);
    if (text === undefined) {
      throw new TypeError("not a JSON value");
    }
  } catch (e) {
    console.warn("ActivityHub: hub.status() data isn't JSON, so it was left out", e);
    return null;
  }
  if (text.length > DATA_MAX) {
    console.warn(`ActivityHub: hub.status() data is ${text.length} characters, over the ${DATA_MAX} the hub passes on`);
    return null;
  }
  if (LONE_SURROGATE.test(text)) {
    console.warn("ActivityHub: hub.status() data has half an emoji in it, which the hub can't pass on");
    return null;
  }
  return JSON.parse(text);
}

export class Host {
  constructor(params, events) {
    this.events = events;
    this.inDiscord = params.has("frame_id");
    // "desktop" or "mobile" inside Discord. The preview has none, so every game opens there
    const platform = params.get("platform");
    this.platform = this.inDiscord && PLATFORMS.includes(platform) ? platform : null;
    this.sdk = null;
    this.scopes = ["identify"];
    this.login = null;
    this.relogging = null;
    this.frame = null;
    this.gameKey = null;
    this.showTimer = null;
    // Discord's last word on how hot the phone is, as it sent it: { thermal_state }
    this.heat = null;
    this.safeArea = safeAreaProbe();
    // Padding changes resize the empty probe, and a phone turning sideways resizes the window
    new ResizeObserver(() => this.shareSafeArea()).observe(this.safeArea, { box: "border-box" });
    window.addEventListener("resize", () => this.shareSafeArea());
    window.addEventListener("message", (event) => this.checkGameMessage(event));
    // The person whose Join opened the current game, and the menu's games by key, for names and icons
    this.follow = null;
    this.games = new Map();
    this.presence = new Presence(this);
    this.people = new PeopleUI(this);
    // Discord hides the whole Activity at once, so this page sees it for every game
    document.addEventListener("visibilitychange", () => this.presence.set({ away: document.hidden }));
    // loggedIn is enough to show the menu. ready also waits for Discord to accept the login, which games need
    // before they use the toolkit, so the menu shows while that last step runs.
    this.loggedIn = this.start();
    this.ready = this.loggedIn.then((login) => this.authenticate(login));
    this.loggedIn.then(
      (login) => login && this.presence.start(),
      (e) => console.debug("ActivityHub: no menu link without a login", e),
    );
  }

  async start() {
    if (!this.inDiscord) {
      return null;
    }
    const config = await loginConfig();
    this.scopes = config.scopes;
    this.sdk = new DiscordSDK(config.client_id);
    // Outside Discord nothing ever answers, like when a game frame's address is opened in a tab of its own
    const warning = setTimeout(() => this.discordSilent(), DISCORD_WAIT_MS);
    try {
      await this.sdk.ready();
    } finally {
      clearTimeout(warning);
    }
    mark("Discord toolkit ready");
    this.login = await getLogin(this, true);
    return this.login;
  }

  async authenticate(login) {
    if (!login) {
      return null;
    }
    await this.sdk.commands.authenticate({ access_token: login.accessToken });
    // Game pages share this page's origin and read this.login, and nothing needs the Discord token again
    delete login.accessToken;
    mark("Discord accepted the login");
    this.watchHeat();
    return login;
  }

  // Discord says how hot a phone is running, at once and after every change: 0 cool, 1 warm, 2 hot, 3 critical. Only
  // its phone apps say
  watchHeat() {
    if (this.platform !== "mobile") {
      return;
    }
    this.sdk
      .subscribe(HEAT_EVENT, (update) => {
        this.heat = update;
        this.events.onHeat?.(update.thermal_state);
      })
      .catch((e) => console.warn("ActivityHub: Discord didn't say how hot the phone is", e));
  }

  discordSilent() {
    console.warn(`ActivityHub: ${DISCORD_SILENT}`);
    if (this.events.onDiscordSilent) {
      this.events.onDiscordSilent(DISCORD_SILENT);
    }
  }

  // A game that starts its own Discord toolkit sends the toolkit's handshake to this page, and nothing answers
  // it, so the game's ready() never finishes. Only the game's own pages count: the menu loaded inside the frame
  // by a link sends one too, and is reported when the frame loads.
  checkGameMessage(event) {
    const data = event.data;
    if (
      this.frame &&
      event.source === this.frame.contentWindow &&
      Array.isArray(data) &&
      data[0] === HANDSHAKE &&
      data[1] !== null &&
      typeof data[1] === "object" &&
      "frame_id" in data[1] &&
      !leftGame(this.frame, this.gameKey)
    ) {
      console.error(
        "ActivityHub: this game created its own DiscordSDK. Inside the hub only the menu talks to Discord, " +
          "so its ready() never finishes. Use hub.discord from connect() instead.",
      );
    }
  }

  // A frame can't see this page's CSS, so the game's page gets the safe area sizes under Discord's own names,
  // and a game padded the way Discord's guide says (var(--discord-safe-area-inset-top, ...)) works unchanged
  shareSafeArea() {
    const root = this.frame?.contentDocument?.documentElement;
    if (!root) {
      return;
    }
    const sizes = getComputedStyle(this.safeArea);
    for (const side of SAFE_SIDES) {
      root.style.setProperty(`--discord-safe-area-inset-${side}`, sizes.getPropertyValue(`padding-${side}`));
    }
  }

  // After a bot restart the hub has forgotten every session. The toolkit is still connected and
  // authenticated, so a fresh code is enough: no second handshake and no second authenticate.
  // Several requests can find the session expired at once, so they share one login.
  relogin() {
    if (!this.relogging) {
      this.relogging = getLogin(this)
        .then((login) => {
          delete login.accessToken;
          this.login = login;
          this.loggedIn = Promise.resolve(login);
          this.ready = Promise.resolve(login);
          return login;
        })
        .finally(() => {
          this.relogging = null;
        });
    }
    return this.relogging;
  }

  // The menu fades out at once, and the game stays hidden until its page has loaded
  openGame(key, follow = null) {
    this.closeGame(false);
    this.follow = follow;
    this.presence.set({ where: key, status: "", data: null, busy: false });
    const frame = document.createElement("iframe");
    frame.id = GAME_FRAME_ID;
    frame.className = "game-frame loading";
    frame.title = key;
    frame.allow = "autoplay; fullscreen";
    frame.src = `${gamePath(key)}${location.search}`;
    frame.addEventListener("load", () => {
      // A link like href="/" would load a second menu, offline, inside the game frame
      if (leftGame(frame, key)) {
        console.warn(
          "ActivityHub: the game left its page (a link to another address?). " +
            "Use backToMenu() to go back to the menu.",
        );
        if (frame === this.frame) {
          this.closeGame();
        }
        return;
      }
      // Each page the frame loads is a new document, without the sizes the last one had
      this.shareSafeArea();
      frame.focus();
      this.showGame(frame);
      this.people.gameLoaded();
    });
    this.showTimer = setTimeout(() => this.showGame(frame), SHOW_ANYWAY_MS);
    document.body.append(frame);
    document.body.classList.add("opening");
    this.frame = frame;
    this.gameKey = key;
  }

  // A page's load waits for its scripts and stylesheets, so the game appears already built instead of
  // assembling itself on screen. The menu goes away under it once the fade ends.
  showGame(frame) {
    if (frame !== this.frame || !frame.classList.contains("loading")) {
      return;
    }
    clearTimeout(this.showTimer);
    frame.classList.remove("loading");
    const fade = frame.animate([{ opacity: 0 }, { opacity: 1 }], {
      duration: reducedMotion.matches ? 0 : FADE_MS,
      easing: "ease-out",
    });
    fade.finished.then(() => {
      if (frame === this.frame) {
        document.body.classList.replace("opening", "playing");
      }
    });
  }

  closeGame(notify = true) {
    if (!this.frame) {
      return;
    }
    clearTimeout(this.showTimer);
    this.frame.remove();
    this.frame = null;
    this.gameKey = null;
    this.follow = null;
    this.presence.set({ where: null, status: "", data: null, busy: false });
    this.people.gameClosed();
    this.setStat("");
    this.setLatency(null);
    document.body.classList.remove("opening", "playing");
    if (notify && this.events.onGameClosed) {
      this.events.onGameClosed();
    }
  }

  // A game's own figure after the frame rate, like "30 TPS". The next game starts without it
  setStat(text) {
    if (this.events.onStat) {
      this.events.onStat(text === null || text === undefined ? "" : String(text).slice(0, STAT_MAX));
    }
  }

  // The round trip of the open game's live connection, timed by sdk.js, or null. The next game starts without it
  setLatency(ms) {
    if (this.events.onLatency) {
      this.events.onLatency(Number.isFinite(ms) ? Math.max(0, Math.round(ms)) : null);
    }
  }

  // The menu's games, so people lists can say "Snake" with its icon instead of "snake"
  setGames(games) {
    this.games = new Map(games.map((game) => [game.key, game]));
  }

  gameName(key) {
    return this.games.get(key)?.name || key || "";
  }

  gameIcon(key) {
    return this.games.get(key)?.icon || null;
  }

  // Why the player can't open the game here: the one platform it works on when this device isn't it, "server" for a
  // game that only opens in the bot's servers when this isn't one, else null. The preview opens every game
  blocker(key) {
    const game = this.games.get(key);
    if (this.platform && game?.platforms && !game.platforms.includes(this.platform)) {
      return game.platforms[0];
    }
    if (this.inDiscord && game?.opensIn === "server" && !this.login?.player?.guildId) {
      return "server";
    }
    return null;
  }

  // Whether the player can open the game on this device, in this place
  canOpen(key) {
    return !this.blocker(key);
  }

  // "Desktop only", "Mobile only" or "Servers only" for a game the player can't open here, else null
  onlyOn(key) {
    const blocker = this.blocker(key);
    return blocker ? ONLY_ON[blocker] : null;
  }

  // Shown instead of opening a game the player can't open here. The player stays where they are
  refuseOpen(key) {
    this.people.tell(`${this.gameName(key)} ${WORKS_ON[this.blocker(key)]}`);
  }

  // hub.status(): the open game's line about its player, and data for its own pages. Cut by whole characters, so an
  // emoji at the limit is kept or dropped as one, never split
  setStatus(text, data = null) {
    const status = text === null || text === undefined ? "" : Array.from(String(text)).slice(0, STATUS_MAX).join("");
    this.presence.set({ status, data: statusData(data) });
  }

  // hub.busy(): the open game's player is mid-round, so Join asks before taking them away
  setBusy(on) {
    this.presence.set({ busy: on === true });
  }

  // Discord's own window for inviting friends into this Activity
  invite() {
    if (!this.sdk) {
      return;
    }
    this.sdk.commands
      .openInviteDialog()
      .catch((e) => console.warn("ActivityHub: Discord didn't open its invite window", e));
  }

  // Join from a people list: open the game they're in, with them as the follow. Mid-round, ask first
  async join(person) {
    // Before the leave question, since nobody leaves for a game this device can't open
    if (!this.canOpen(person.game)) {
      this.refuseOpen(person.game);
      return;
    }
    if (this.frame && this.presence.state.busy && !(await this.people.confirmLeave(person))) {
      return;
    }
    this.people.close();
    const follow = { id: person.id, name: person.name };
    if (this.events.onJoin) {
      this.events.onJoin(person.game, follow);
    } else {
      this.openGame(person.game, follow);
    }
  }

  sessionExpired() {
    this.closeGame(false);
    if (this.events.onSessionExpired) {
      this.events.onSessionExpired();
    }
  }
}

export function startHost(events = {}) {
  const host = new Host(new URLSearchParams(location.search), events);
  window.activityhubHost = host;
  return host;
}
