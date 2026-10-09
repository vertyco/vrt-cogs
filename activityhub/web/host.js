// The menu's side of ActivityHub: the only place that starts the Discord toolkit. Discord accepts one
// toolkit handshake per Activity frame, so games run in an inner frame and borrow this login, and this
// page must never navigate or reload itself while inside Discord.
import { DiscordSDK } from "./vendor/discord-sdk.js";
import { request } from "./sdk.js";

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

async function getLogin(sdk, scopes) {
  const { code } = await sdk.commands.authorize({
    client_id: sdk.clientId,
    response_type: "code",
    state: "",
    prompt: "none",
    scope: scopes,
  });
  mark("Discord authorized the login");
  const login = await request("/hub/api/token", { body: { code, instance_id: sdk.instanceId } });
  mark("the bot logged the player in");
  return { session: login.session, accessToken: login.access_token, player: login.player, menu: login.menu };
}

export class Host {
  constructor(params, events) {
    this.events = events;
    this.inDiscord = params.has("frame_id");
    this.sdk = null;
    this.scopes = ["identify"];
    this.login = null;
    this.relogging = null;
    this.frame = null;
    this.gameKey = null;
    this.showTimer = null;
    this.safeArea = safeAreaProbe();
    // Padding changes resize the empty probe, and a phone turning sideways resizes the window
    new ResizeObserver(() => this.shareSafeArea()).observe(this.safeArea, { box: "border-box" });
    window.addEventListener("resize", () => this.shareSafeArea());
    window.addEventListener("message", (event) => this.checkGameMessage(event));
    // loggedIn is enough to show the menu. ready also waits for Discord to accept the login, which games need
    // before they use the toolkit, so the menu shows while that last step runs.
    this.loggedIn = this.start();
    this.ready = this.loggedIn.then((login) => this.authenticate(login));
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
    this.login = await getLogin(this.sdk, this.scopes);
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
    return login;
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
      this.relogging = getLogin(this.sdk, this.scopes)
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
  openGame(key) {
    this.closeGame(false);
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
    document.body.classList.remove("opening", "playing");
    if (notify && this.events.onGameClosed) {
      this.events.onGameClosed();
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
