// ActivityHub helper for game pages. Games import it with: import { connect } from "activityhub";
// Inside Discord a game runs in a frame inside the hub menu, which owns the only Discord toolkit
// connection Discord allows per Activity. This file borrows that login through window.parent.

const GAME_PATH = /^\/games\/([a-z0-9-]+)\//;

export class HubError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "HubError";
    this.status = status;
  }
}

// Internal: host.js and menu.js use this. Games use hub.api()
export async function request(path, { body, session } = {}) {
  const headers = {};
  if (session) {
    headers.Authorization = `Bearer ${session}`;
  }
  const options = { method: body === undefined ? "GET" : "POST", headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const resp = await fetch(path, options);
  const text = await resp.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    if (resp.ok) {
      // Something other than the bot answered, like a proxy's error page. Returning {} would hide that
      throw new HubError("The bot's reply wasn't valid JSON.", resp.status);
    }
    data = null;
  }
  if (!resp.ok) {
    throw new HubError(data?.error || `Request failed (${resp.status})`, resp.status);
  }
  return data;
}

function findHost() {
  if (window.parent === window) {
    return null;
  }
  try {
    return window.parent.activityhubHost || null;
  } catch (e) {
    console.warn("ActivityHub: the surrounding page isn't the hub menu", e);
    return null;
  }
}

export function backToMenu() {
  const host = findHost();
  if (host) {
    host.closeGame();
  } else {
    location.href = `/${location.search}`;
  }
}

function gameRoot() {
  const match = location.pathname.match(GAME_PATH);
  return match ? `/games/${match[1]}/` : "/";
}

function withSession(options, session) {
  const headers = new Headers(options.headers || {});
  if (session) {
    headers.set("Authorization", `Bearer ${session}`);
  }
  return { ...options, headers };
}

function unavailable() {
  return Promise.reject(new HubError("Open this activity from Discord to use this.", 0));
}

function offlineHub() {
  return {
    player: null,
    discord: null,
    offline: true,
    api: unavailable,
    socket: unavailable,
    fetch: (path, options = {}) => fetch(`${gameRoot()}raw/${path}`, options),
    backToMenu,
  };
}

// Close codes the hub sends before a live connection is ready
const CLOSE_SESSION = 4001;
const CLOSE_NO_SOCKET = 4004;

// Why a live connection closed before it was ready, for the game's catch
function closedEarly(code) {
  if (code === CLOSE_NO_SOCKET) {
    const message = 'This game has no live connection. Add "socket" to activityhub_game() and reload the cog.';
    return new HubError(message, code);
  }
  return new HubError(`The live connection closed (${code}).`, code);
}

function openSocket(root, session) {
  return new Promise((resolve, reject) => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}${root}ws`);
    const handlers = [];
    const closers = [];
    const held = [];
    let ready = false;
    const conn = {
      send(data) {
        const text = JSON.stringify(data);
        // The socket would send the word "undefined", which the hub drops without telling anyone
        if (text === undefined) {
          throw new TypeError(
            `conn.send() needs a JSON value (an object, array, string, number, boolean or null), got ${typeof data}`,
          );
        }
        ws.send(text);
      },
      on(handler) {
        handlers.push(handler);
        held.splice(0).forEach((data) => handler(data));
      },
      onClose(handler) {
        closers.push(handler);
      },
      close: () => ws.close(1000),
    };
    ws.addEventListener("open", () => ws.send(JSON.stringify({ session })));
    ws.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.warn("ActivityHub: dropped a live message that isn't JSON", e);
        return;
      }
      if (data && data.activityhub === "ready") {
        ready = true;
        resolve(conn);
      } else if (data && data.activityhub === "ping") {
        // The hub's heartbeat. Answering it shows the hub this player is still here, even through a proxy that
        // drops the browser's own WebSocket pings
        ws.send(JSON.stringify({ activityhub: "pong" }));
      } else {
        if (handlers.length) {
          handlers.forEach((handler) => handler(data));
        } else {
          held.push(data);
        }
      }
    });
    ws.addEventListener("close", (event) => {
      if (!ready) {
        reject(closedEarly(event.code));
        return;
      }
      closers.forEach((handler) => handler(event.code));
    });
  });
}

// The menu's Discord toolkit as one game page sees it. The toolkit outlives this frame, so a listener left
// behind keeps running after the game closes, and one that throws stops later listeners too, since the
// toolkit's event bus has no try/catch. Every listener this page added is removed when the page goes away.
function frameDiscord(sdk) {
  // event name -> listener -> the arguments it was subscribed with
  const subscribed = new Map();
  const subscribe = (event, listener, ...args) => {
    // The toolkit adds the listener before asking Discord, so it stays even when Discord refuses
    if (typeof listener === "function") {
      if (!subscribed.has(event)) {
        subscribed.set(event, new Map());
      }
      subscribed.get(event).set(listener, args);
    }
    return sdk.subscribe(event, listener, ...args);
  };
  const unsubscribe = (event, listener, ...args) => {
    subscribed.get(event)?.delete(listener);
    return sdk.unsubscribe(event, listener, ...args);
  };
  window.addEventListener("pagehide", () => {
    for (const [event, listeners] of subscribed) {
      for (const [listener, args] of listeners) {
        sdk.unsubscribe(event, listener, ...args).catch((e) => console.warn("ActivityHub: couldn't unsubscribe", e));
      }
    }
    subscribed.clear();
  });
  // Methods run with the toolkit itself as `this`: called on the wrapper, one that uses private class state throws
  const bound = new Map();
  return new Proxy(sdk, {
    get(target, name) {
      if (name === "subscribe") {
        return subscribe;
      }
      if (name === "unsubscribe") {
        return unsubscribe;
      }
      const value = Reflect.get(target, name);
      if (typeof value !== "function") {
        return value;
      }
      if (!bound.has(value)) {
        bound.set(value, value.bind(target));
      }
      return bound.get(value);
    },
  });
}

function onlineHub(host, login) {
  const root = gameRoot();
  // A bot restart or an ActivityHub reload forgets every login. The menu's Discord connection is still good,
  // so a fresh login fixes it without leaving the game. Requests refused together share one login.
  async function freshSession(used) {
    if (host.login.session !== used) {
      return host.login.session;
    }
    try {
      return (await host.relogin()).session;
    } catch (e) {
      host.sessionExpired();
      throw e;
    }
  }
  const expiredFetch = (resp) => resp.status === 401 && resp.headers.get("X-ActivityHub") === "session-expired";
  return {
    player: login.player,
    discord: frameDiscord(host.sdk),
    offline: false,
    async api(name, data) {
      const path = `${root}api/${encodeURIComponent(name)}`;
      const body = data ?? {};
      const used = host.login.session;
      try {
        return await request(path, { body, session: used });
      } catch (e) {
        if (e.status !== 401) {
          throw e;
        }
      }
      // Actions answer 401 before any handler runs, so sending it again can't run the action twice
      const session = await freshSession(used);
      try {
        return await request(path, { body, session });
      } catch (e) {
        if (e.status === 401) {
          host.sessionExpired();
        }
        throw e;
      }
    },
    async fetch(path, options = {}) {
      const url = `${root}raw/${path}`;
      const used = host.login.session;
      const resp = await fetch(url, withSession(options, used));
      if (!expiredFetch(resp)) {
        return resp;
      }
      const session = await freshSession(used);
      if (options.body instanceof ReadableStream) {
        // A stream is used up once sent. Later requests have the fresh login, but this one can't go again
        console.warn("ActivityHub: the login expired and a streamed body can't be sent twice, so this got 401");
        return resp;
      }
      const retried = await fetch(url, withSession(options, session));
      if (expiredFetch(retried)) {
        host.sessionExpired();
      }
      return retried;
    },
    async socket() {
      const used = host.login.session;
      try {
        return await openSocket(root, used);
      } catch (e) {
        if (e.status !== CLOSE_SESSION) {
          throw e;
        }
      }
      const session = await freshSession(used);
      try {
        return await openSocket(root, session);
      } catch (e) {
        if (e.status === CLOSE_SESSION) {
          host.sessionExpired();
        }
        throw e;
      }
    },
    backToMenu,
  };
}

export async function connect() {
  const host = findHost();
  if (host) {
    const login = await host.ready;
    return login ? onlineHub(host, login) : offlineHub();
  }
  if (new URLSearchParams(location.search).has("frame_id")) {
    // Inside Discord only the menu may start the Discord toolkit, so a game opened on its own goes there
    location.replace(`/${location.search}`);
    return new Promise(() => {});
  }
  return offlineHub();
}
