// The menu's side of "who's here": one live connection to the bot for the whole session, the menu link. It says
// where this player is and what their game says they're doing, and gets back everyone in this Activity window.
// The menu page never reloads inside Discord, so this outlives every game the player opens.
import { liveConnection, liveOpener } from "./sdk.js";

const SEND_EVERY_MS = 250;
// After the link (re)connects the bot's list refills person by person, which must not look like a crowd arriving
const QUIET_MS = 5000;
// After the link comes back, people who were in a game before it dropped aren't arrivals when they show up again.
// Once the bot itself restarted, they reconnect one by one over many seconds, longer than QUIET_MS
const RETURNING_MS = 60000;
// How long to wait before opening the link again once it closed for good or couldn't open. The wait doubles after
// each failed try up to the longest, and starts over from the first after the link opens
const RETRY_MS = 15000;
const RETRY_MAX_MS = 120000;

// People who just came into the game `where`: there in the new list, and not there in the old one
export function arrivals(before, after, where, me) {
  if (!where) {
    return [];
  }
  const already = new Set(before.filter((person) => person.game === where).map((person) => person.id));
  return after.filter((person) => person.game === where && person.id !== me && !already.has(person.id));
}

export class Presence {
  constructor(host) {
    this.host = host;
    // What the bot knows about this player. The whole of it goes out each time, so a reconnect restores it all
    this.state = { where: null, status: "", data: null, busy: false, away: document.hidden };
    this.people = [];
    this.elsewhere = {};
    this.listeners = new Set();
    this.conn = null;
    this.sentAt = 0;
    this.timer = null;
    this.quietUntil = 0;
    this.retryMs = RETRY_MS;
    // Ids that were in a game when the link dropped, until they show up again in one or `returningUntil` passes
    this.returning = new Set();
    this.returningUntil = 0;
  }

  get me() {
    return this.host.login?.player?.id ?? null;
  }

  async start() {
    try {
      // A login the bot refuses to renew must not end the player's session: the menu link waits and tries again
      this.conn = await liveConnection(liveOpener(this.host, "/hub/ws", {}, false), () => {}).start();
    } catch (e) {
      console.warn(`ActivityHub: couldn't open the menu link, trying again in ${this.retryMs / 1000} s`, e);
      this.retryLater();
      return;
    }
    this.retryMs = RETRY_MS;
    this.comeBack();
    this.conn.on((data) => this.receive(data));
    this.conn.onReconnected(() => {
      this.remember(this.people);
      this.comeBack();
      this.send();
    });
    this.conn.onClose((code) => {
      console.warn(`ActivityHub: the menu link closed (${code}), trying again in ${this.retryMs / 1000} s`);
      this.conn = null;
      // With no link the list would only go stale, so pages show nobody until it comes back
      this.remember(this.people);
      this.people = [];
      this.elsewhere = {};
      this.notify([]);
      this.retryLater();
    });
    this.send();
  }

  retryLater() {
    setTimeout(() => this.start(), this.retryMs);
    this.retryMs = Math.min(RETRY_MAX_MS, this.retryMs * 2);
  }

  // The link just opened: the bot's list refills person by person, which isn't a crowd arriving
  comeBack() {
    const now = performance.now();
    this.quietUntil = now + QUIET_MS;
    this.returningUntil = now + RETURNING_MS;
  }

  // People in a game when the link dropped can't be told from newcomers once the bot's list starts over
  remember(people) {
    for (const person of people) {
      if (person.game) {
        this.returning.add(person.id);
      }
    }
  }

  // Merges a change into what the bot knows about this player. At most 4 sends a second; the latest state wins
  set(changes) {
    Object.assign(this.state, changes);
    if (this.timer) {
      return;
    }
    const wait = Math.max(0, this.sentAt + SEND_EVERY_MS - performance.now());
    this.timer = setTimeout(() => this.send(), wait);
  }

  send() {
    // A change waiting for its turn goes out in this message
    clearTimeout(this.timer);
    this.timer = null;
    if (this.conn && this.conn.send(this.state)) {
      this.sentAt = performance.now();
    }
  }

  receive(data) {
    if (!data || !Array.isArray(data.people)) {
      return;
    }
    const before = this.people;
    this.people = data.people;
    this.elsewhere = data.elsewhere || {};
    this.notify(this.newcomers(before));
  }

  // Who just came into this player's game, leaving out the first moments after the link opens and anyone coming back
  newcomers(before) {
    const now = performance.now();
    if (now >= this.returningUntil) {
      this.returning.clear();
    }
    const arrived = now < this.quietUntil ? [] : arrivals(before, this.people, this.state.where, this.me);
    const fresh = arrived.filter((person) => !this.returning.has(person.id));
    // Someone back in a game is back for good. Showing in the menu first doesn't count: the bot lists a player
    // there until their game's first update reaches it
    for (const person of this.people) {
      if (person.game) {
        this.returning.delete(person.id);
      }
    }
    return fresh;
  }

  notify(arrived) {
    for (const listener of this.listeners) {
      // A game's listener lives in its frame; one that throws must not stop the menu's or the others'
      try {
        listener(this.people, arrived);
      } catch (e) {
        console.error("ActivityHub: a people listener failed", e);
      }
    }
  }

  listen(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  // Everyone in the window as a page sees them: with the game's name, and whether each is this player or in `key`
  view(key) {
    const me = this.me;
    return this.people.map((person) => ({
      ...person,
      gameName: person.game ? this.host.gameName(person.game) : null,
      you: person.id === me,
      here: Boolean(key) && person.game === key,
    }));
  }
}
