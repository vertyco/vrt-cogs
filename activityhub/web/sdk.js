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
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new HubError(data.error || `Request failed (${resp.status})`, resp.status);
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

function openSocket(root, session, onExpired) {
  return new Promise((resolve, reject) => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}${root}ws`);
    const handlers = [];
    const closers = [];
    const held = [];
    let ready = false;
    const conn = {
      send: (data) => ws.send(JSON.stringify(data)),
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
      } else if (!(data && data.activityhub === "ping")) {
        if (handlers.length) {
          handlers.forEach((handler) => handler(data));
        } else {
          held.push(data);
        }
      }
    });
    ws.addEventListener("close", (event) => {
      if (event.code === 4001) {
        onExpired();
      }
      if (!ready) {
        reject(new HubError(`The live connection closed (${event.code}).`, event.code));
        return;
      }
      closers.forEach((handler) => handler(event.code));
    });
  });
}

function onlineHub(host, login) {
  const root = gameRoot();
  const expired = () => host.sessionExpired();
  return {
    player: login.player,
    discord: host.sdk,
    offline: false,
    async api(name, data) {
      try {
        return await request(`${root}api/${encodeURIComponent(name)}`, {
          body: data ?? {},
          session: host.login.session,
        });
      } catch (e) {
        if (e.status === 401) {
          expired();
        }
        throw e;
      }
    },
    fetch: (path, options = {}) => fetch(`${root}raw/${path}`, withSession(options, host.login.session)),
    socket: () => openSocket(root, host.login.session, expired),
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
