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
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

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
    this.frame = null;
    this.showTimer = null;
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
    await this.sdk.ready();
    mark("Discord toolkit ready");
    this.login = await getLogin(this.sdk, this.scopes);
    return this.login;
  }

  async authenticate(login) {
    if (!login) {
      return null;
    }
    await this.sdk.commands.authenticate({ access_token: login.accessToken });
    mark("Discord accepted the login");
    return login;
  }

  // After a bot restart the hub has forgotten every session. The toolkit is still connected and
  // authenticated, so a fresh code is enough: no second handshake and no second authenticate.
  async relogin() {
    this.login = await getLogin(this.sdk, this.scopes);
    this.loggedIn = Promise.resolve(this.login);
    this.ready = Promise.resolve(this.login);
    return this.login;
  }

  // The menu fades out at once, and the game stays hidden until its page has loaded
  openGame(key) {
    this.closeGame(false);
    const frame = document.createElement("iframe");
    frame.id = GAME_FRAME_ID;
    frame.className = "game-frame loading";
    frame.title = key;
    frame.allow = "autoplay; fullscreen";
    frame.src = `/games/${encodeURIComponent(key)}/${location.search}`;
    frame.addEventListener("load", () => {
      frame.focus();
      this.showGame(frame);
    });
    this.showTimer = setTimeout(() => this.showGame(frame), SHOW_ANYWAY_MS);
    document.body.append(frame);
    document.body.classList.add("opening");
    this.frame = frame;
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
