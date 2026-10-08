# Making a game for ActivityHub

**The short version:** you write a normal Red cog with one extra method, `activityhub_game()`, and a folder of web files. ActivityHub finds your cog, puts your game in its menu, and runs everything else: the web server, the Discord login and launching.

This guide assumes you have never seen ActivityHub. It starts with a small complete game you can copy, then explains every option, then covers the bigger topics: multiplayer, payouts, uploads, testing and the problems people usually hit.

A few words used everywhere below:

- **Activity**: a game window that opens inside Discord, usually in a voice channel. Discord lets a bot have only one. ActivityHub turns that one Activity into a menu of games.
- **Red**: Red-DiscordBot, the bot framework this cog runs on. A **cog** is one Red plugin.
- **Page**: the web page of your game (your `index.html` and the files it loads), running in the player's Discord window.

There is a full [glossary](#20-glossary) at the end.

**Contents**

1. [What you are building](#1-what-you-are-building)
2. [Before you start](#2-before-you-start)
3. [Quick start: Click Counter](#3-quick-start-click-counter)
4. [How one click travels](#4-how-one-click-travels)
5. [Reference: `activityhub_game()`](#5-reference-activityhub_game)
6. [Reference: `ctx`](#6-reference-ctx)
7. [Reference: handlers](#7-reference-handlers)
8. [Reference: the page side](#8-reference-the-page-side)
9. [What to trust, and paying out](#9-what-to-trust-and-paying-out)
10. [Multiplayer with live connections](#10-multiplayer-with-live-connections)
11. [Uploads and other raw requests](#11-uploads-and-other-raw-requests)
12. [Extra Discord permissions](#12-extra-discord-permissions)
13. [Opening your game from a command or button](#13-opening-your-game-from-a-command-or-button)
14. [Files and caching](#14-files-and-caching)
15. [Testing and debugging](#15-testing-and-debugging)
16. [Common problems](#16-common-problems)
17. [Discord's limits](#17-discords-limits)
18. [Checklist before you share your game](#18-checklist-before-you-share-your-game)
19. [Bigger examples: the included games](#19-bigger-examples-the-included-games)
20. [Glossary](#20-glossary)

## 1. What you are building

Your game has two halves:

- **The page.** HTML, CSS and JavaScript in a folder. It draws the game and reacts to the player.
- **The Python.** Methods on your cog. The page calls them by name to do anything that must be trusted: save a score, pay credits, read Config (Red's settings storage).

ActivityHub sits between the two. It serves your page, logs the player in, and passes each call from the page to your Python with a `ctx` that says who the player is and where.

```
  Discord                              Your bot
  -------                              --------
  The player opens the Activity
        |
        v
  ActivityHub's menu page  <------->  ActivityHub web server
        |                             (logs the player in with Discord)
        |  the player picks your game
        v
  Your page, in a frame inside the menu
        |
        |  hub.api("click", {...})
        +------------------------->   ActivityHub checks the login
                                      and that your game is on in this server
                                            |
                                            v
                                      your cog: async def click(self, ctx, data)
                                            |
        <-----------------------------------+
        the dict your method returned arrives in your page
```

A "frame" here is a page inside a page (an HTML `iframe`). Your game runs in one, inside the menu. That is how one Activity can hold many games.

What your cog does **not** do:

- It never imports ActivityHub.
- It never runs a web server.
- It never touches the Discord login.

The hub finds your game when your cog loads, and drops it when your cog unloads.

## 2. Before you start

You need:

- **A Red bot with ActivityHub loaded.** `[p]load activityhub`. (`[p]` means your bot's command prefix.)
- **Nothing else to begin with.** You can build most of a game in a normal web browser, without Discord.

The hub's web server serves a preview of the menu to any browser. By default it is at **`http://127.0.0.1:8742/`** on the computer the bot runs on. (`[p]activityhub webserver` changes the address.) If the bot runs on a different computer, open your public address instead, for example `https://games.example.com/`.

In the preview:

- The menu shows every game, with a "Preview" notice at the top.
- Your game opens inside the menu like it would in Discord.
- `hub.offline` is `true`, so calls to your Python throw an error instead of running. That is how you can tell your page is in preview.

To test inside Discord, the bot owner must finish the one-time setup in [README.md](README.md) (turn on Activities, set the client secret, expose the web server). You only need that for the last step of the quick start.

## 3. Quick start: Click Counter

Click Counter pays one credit per click, up to 100 clicks a day per player. It is small, but it shows every basic piece: the description, an action, the page, and an error message.

### Step 1: make the files

Make this folder layout. `clickcounter` is the cog. `web` holds the page.

```
clickcounter/
  __init__.py
  info.json
  clickcounter.py
  web/
    index.html
    style.css
    game.js
```

`__init__.py` is how Red loads the cog:

```python
from .clickcounter import ClickCounter


async def setup(bot):
    await bot.add_cog(ClickCounter(bot))
```

`info.json` describes the cog for Red's cog installer. You only need it when you share the cog, but it costs nothing to add now:

```json
{
  "author": ["Your name"],
  "short": "Click a button, earn a credit",
  "description": "A tiny ActivityHub game: click a button, earn a credit.",
  "end_user_data_statement": "This cog stores how many times each player clicked today.",
  "requirements": [],
  "tags": ["activityhub", "games"],
  "type": "COG"
}
```

`clickcounter.py` is the cog. `activityhub_game()` describes the game. `click()` is the action the page calls.

```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from redbot.core import Config, bank, commands

DAILY_LIMIT = 100


class ClickCounter(commands.Cog):
    """Click a button, earn a credit"""

    def __init__(self, bot):
        self.bot = bot
        # Pick your own random number for identifier, so your data never mixes with another cog's
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_member(day="", clicks=0)
        self.lock = asyncio.Lock()

    async def activityhub_game(self) -> dict:
        return {
            "key": "clickcounter",
            "name": "Click Counter",
            "description": "One click, one credit",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"click": self.click},
        }

    async def click(self, ctx, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": "Open this in a server to earn credits."}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Fast clicks arrive together; the lock stops two of them reading the same count
        async with self.lock:
            ledger = self.config.member(ctx.author)
            clicks = await ledger.clicks() if await ledger.day() == today else 0
            if clicks >= DAILY_LIMIT:
                return {"error": "That's all the clicks for today. Come back tomorrow!"}
            await bank.deposit_credits(ctx.author, 1)
            await ledger.day.set(today)
            await ledger.clicks.set(clicks + 1)
        return {"clicks": clicks + 1, "balance": await bank.get_balance(ctx.author)}
```

`web/index.html` is the page. Notice it has no `<base>` tag and no address for `"activityhub"`: the hub adds both when it serves the page.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Click Counter</title>
    <link rel="stylesheet" href="style.css" />
  </head>
  <body>
    <p id="status">Loading...</p>
    <button id="click" type="button">Click me</button>
    <button id="back" type="button">Back to the menu</button>
    <script type="module" src="game.js"></script>
  </body>
</html>
```

`web/style.css` is the look:

```css
body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-content: center;
  gap: 12px;
  text-align: center;
  background: #2b2d31;
  color: #f2f3f5;
  font-family: system-ui, sans-serif;
}

button {
  padding: 12px 20px;
  border: 0;
  border-radius: 8px;
  font: inherit;
  cursor: pointer;
}

#click {
  background: #5865f2;
  color: #ffffff;
  font-size: 1.25rem;
}
```

`web/game.js` is the code. `connect()` waits for the hub's login and gives you the `hub` object. `hub.api("click")` runs the Python `click()` method.

```js
import { backToMenu, connect } from "activityhub";

const status = document.getElementById("status");
document.getElementById("back").addEventListener("click", backToMenu);

const hub = await connect();
status.textContent = hub.offline ? "Open this from Discord to earn credits." : `Hi ${hub.player.username}!`;

document.getElementById("click").addEventListener("click", async () => {
  try {
    const result = await hub.api("click");
    status.textContent = `Clicks today: ${result.clicks}. Balance: ${result.balance}`;
  } catch (e) {
    status.textContent = e.message;
  }
});
```

`"activityhub"` in the `import` line is not a file in your folder. The hub tells the browser where its helper script is when it serves your page. That is also why the page only works when the hub serves it (see [Common problems](#16-common-problems)).

### Step 2: load the cog

1. Tell Red where your cog lives: `[p]addpath <the folder that holds clickcounter>`. Give the folder **above** `clickcounter`, not `clickcounter` itself.
2. Load it: `[p]load clickcounter`.
3. Check the hub saw it: `[p]activityhub games`.

You should now see `clickcounter: Click Counter (ClickCounter)` in the list. If it is under "Refused:" instead, the line says what to fix.

### Step 3: try it in a browser

1. On the bot's computer, open `http://127.0.0.1:8742/` (or your public address).
2. Click the **Click Counter** card.
3. Press **Click me**, then **Back to the menu**.

You should now see the menu with a "Preview" notice, then your page saying "Open this from Discord to earn credits.". Pressing **Click me** shows "Open this activity from Discord to use this.", because in the preview there is no logged-in player. **Back to the menu** takes you back.

### Step 4: try it in Discord

1. In a server, run `/activities` (or `[p]activities` and press the button).
2. Pick **Click Counter**.
3. Press **Click me** a few times.

You should now see "Hi" and your Discord username, then "Clicks today: 1. Balance: ..." going up by one per click. Your bank balance in that server goes up too.

### Step 5: change something

- **A web file** (HTML, CSS, JavaScript, images): save it, then close your game and open it again. No reload needed.
- **Python**: run `[p]reload clickcounter`.

You should now see your change. That's the whole loop.

## 4. How one click travels

This is what happens between `hub.api("click")` in the page and `click()` in Python. You never write any of it, but knowing it makes errors easier to read.

1. **The page sends a request.** `hub.api("click", data)` sends `data` (an object, `{}` when left out) to `/games/clickcounter/api/click` as JSON (the text format browsers and Python both use for data). The player's session pass rides along with it.
2. **The hub finds the player.** The session pass maps to a `ctx` the hub proved with Discord when the player logged in. No pass, or an expired one, and the page gets "Your session expired. Go back to the menu to log in again." and the player is taken back to the menu.
3. **The hub checks your game is on.** If the bot owner turned it off, or a server admin turned it off in this server, the page gets "This activity is turned off in this server."
4. **The hub checks the request.** The action name must be in your `actions`, and `data` must be an object.
5. **Your method runs.** The hub calls `await self.click(ctx, data)`.
6. **Your dict goes back.** `hub.api()` resolves with it. If it has an `"error"` key, `hub.api()` throws instead, and `e.message` is your error text.

How the login works, in one breath: when Discord opens the Activity, the hub's menu page asks Discord for a one-time login code. The bot trades that code with Discord for the player's identity, asks Discord which server and channel the Activity runs in, and gives the page a session pass. Your page borrows that login through `connect()`, so you never deal with it.

## 5. Reference: `activityhub_game()`

This method tells the hub about your game. The hub calls it when your cog loads, and again on every `[p]reload`. If ActivityHub itself loads after your cog, it checks every cog that is already loaded, so the load order doesn't matter.

```python
async def activityhub_game(self) -> dict:
```

It must be an `async def`. It may await things, like reading Config, but keep it quick: the hub waits for it. If anything in the dict is wrong, the hub skips your game and `[p]activityhub games` says why.

These are the fields the dict can have. Any other field name is refused, so a typo can't slip through quietly.

| Field | Type | Required | What it does |
|---|---|---|---|
| `key` | `str` | yes | Your game's id: 2 to 32 characters of `a-z`, `0-9` and `-`. Your game lives at the address `/games/<key>/`. Two cogs can't share a key: the first one loaded keeps it. |
| `name` | `str` | yes | The name shown in the menu. Can't be empty. |
| `web_dir` | `str` or `pathlib.Path` | yes | The folder holding `index.html` and every file your page uses. `Path(__file__).parent / "web"` is the usual way to write it. |
| `description` | `str` | no | One line shown under the name. Defaults to `""`. |
| `icon` | `str` | no | A path inside `web_dir` to a small square picture, shown next to the name. For example `"icon.png"`. |
| `thumbnail` | `str` | no | A path inside `web_dir` to a wide picture (16:9, for example 640x360), like box art or a screenshot. The grid and list layouts show it in place of the icon, and the Orb theme shows it large next to the menu. Without one, the menu uses the icon. |
| `actions` | `dict[str, handler]` | no | Python methods the page calls with `hub.api(name, data)`. Names use letters, digits, `_`, `.` and `-`, 1 to 64 characters. See [handlers](#7-reference-handlers). |
| `socket` | `dict[str, handler]` | no | Handlers for a live connection. The keys can only be `"join"`, `"message"` and `"leave"`. See [multiplayer](#10-multiplayer-with-live-connections). |
| `routes` | `dict[str, handler]` | no | Raw requests, keyed `"METHOD path"`, for example `"POST avatar"`. `METHOD` is one of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. The path uses letters, digits, `_`, `.`, `-` and `/`. See [raw requests](#11-uploads-and-other-raw-requests). |
| `scopes` | `list[str]` | no | Extra Discord permissions to ask the player for at login. See [permissions](#12-extra-discord-permissions). |

Every handler (in `actions`, `socket` and `routes`) must be an `async def`.

A fuller example:

```python
async def activityhub_game(self) -> dict:
    return {
        "key": "space-race",
        "name": "Space Race",
        "description": "Dodge the rocks, grab the stars",
        "web_dir": Path(__file__).parent / "web",
        "icon": "art/icon.png",
        "thumbnail": "art/cover.png",
        "actions": {"start": self.start, "finish": self.finish},
    }
```

## 6. Reference: `ctx`

Every handler gets a `ctx` that says who is playing and where. The hub proved it with Discord: the player really logged in, and Discord itself said which server and channel the Activity runs in. The page can't change it. It works like Red's `commands.Context` where the two overlap.

| Attribute | Type | What it is |
|---|---|---|
| `ctx.author` | `discord.Member` or `discord.User` | The player. A `discord.Member` in a server. A `discord.User` anywhere else (a DM, or a server your bot isn't in). |
| `ctx.guild` | `discord.Guild` or `None` | The server the Activity was opened in. `None` in a DM, or in a server your bot isn't in. |
| `ctx.guild_id` | `int` or `None` | `ctx.guild.id`, or `None` outside a server. |
| `ctx.channel` | server channel, thread or `None` | The channel the Activity runs in, when it's in a server the bot can see. `None` otherwise. |
| `ctx.channel_id` | `int` or `None` | The channel's id, also in a DM. |
| `ctx.instance_id` | `str` | The id of this Activity window. Everyone in the same Activity window (for example, the same voice channel) has the same one. Use it to group players into one game. |

`if ctx.guild is None` is the check for "not in a server". When it's false, `ctx.author` is a `discord.Member`, ready for the bank and for member Config.

## 7. Reference: handlers

A handler is one of your `async def` methods that the hub calls. There are three kinds: actions (the page asks, Python answers), live connection handlers (for multiplayer), and raw routes (for anything else, like uploads).

| Kind | Signature | Gets | Returns |
|---|---|---|---|
| Action | `async def name(self, ctx, data: dict) -> dict` | `data`: the object the page sent, or `{}`. | A dict the page receives. Return `{"error": "text"}` to make `hub.api()` throw with that text. Returning `None` sends `{}`. |
| Socket `join` | `async def join(self, ctx, conn) -> None` | `conn`: this player's live connection. | Nothing. If it raises, the connection closes with code `1011`. |
| Socket `message` | `async def message(self, ctx, conn, data) -> None` | `data`: any JSON value the page sent (dict, list, str, number, bool or `None`). | Nothing. If it raises, the error is logged and the connection stays open. |
| Socket `leave` | `async def leave(self, ctx, conn) -> None` | `conn`: the connection that just closed. | Nothing. Not called when `join` raised. |
| Raw route | `async def name(self, request: aiohttp.web.Request, ctx) -> aiohttp.web.StreamResponse` | `request`: the raw request from aiohttp (the web library the hub uses). `ctx`: `None` when the request has no valid login. You decide what that means. | Any aiohttp response, for example `web.json_response(...)`. |

Rules the hub enforces for you:

- **Actions and socket handlers only run for a logged-in player**, and only while your game is on in that server.
- **Raw routes also run without a login.** `ctx` is then `None`.
- **Errors stay private.** If a handler raises, or an action returns something that isn't a dict (or can't be turned into JSON), the hub logs it in the bot's log and the page gets "Something went wrong.". Your error text never reaches the player. Only `{"error": "..."}` text does.
- **Size limit.** Request bodies and live messages over 1 MB are refused.

**`conn`, a live connection,** as your Python sees it:

| Member | Type | What it does |
|---|---|---|
| `await conn.send(data)` | `data`: any JSON value | Sends a message to this player. Does nothing once the connection has closed. |
| `await conn.broadcast(data, include_self=False)` | `data`: any JSON value | Sends to everyone connected to your game with the same `instance_id`. Pass `include_self=True` to send to this player too. |
| `conn.peers()` | `list` of connections | The other connections to your game with the same `instance_id`. |
| `await conn.close(code=1000)` | `code`: `int` | Closes the connection. |
| `conn.ctx` | `ctx` | The same `ctx` the handlers get. |

## 8. Reference: the page side

Your page talks to the hub through a small helper script. Import it by the name `"activityhub"`:

```js
import { backToMenu, connect, HubError } from "activityhub";
```

These are the three things it exports:

| Name | What it is |
|---|---|
| `connect()` | Returns a promise of the `hub` object below. Inside Discord it waits for the menu's login first. |
| `backToMenu()` | Closes your game and shows the menu. |
| `HubError` | The error type `hub.api()` and `hub.socket()` throw. `e.message` is readable text. `e.status` is the HTTP status (the number a web server answers with, like `400` or `401`) or the live connection's close code. |

**The `hub` object** is what `connect()` gives you:

| Member | Type | What it is |
|---|---|---|
| `hub.offline` | `boolean` | `true` outside Discord, for example in the browser preview. `hub.api()` and `hub.socket()` then throw "Open this activity from Discord to use this." |
| `hub.player` | object or `null` | `{ id, username, avatar, guildId, guildName, guildIcon }`, all strings. The `guild` ones are `null` outside a server, and `guildIcon` is `null` for a server without an icon. `null` when offline. It's for showing, not for trusting. |
| `hub.api(name, data)` | `Promise<object>` | Calls your action `name` with `data` (an object, default `{}`). Resolves with what the action returned. |
| `hub.fetch(path, options)` | `Promise<Response>` | Calls a raw route, like the browser's own `fetch`, with the player's login attached. `path` is the route path, for example `"avatar"`. Works offline too, without a login. |
| `hub.socket()` | `Promise<conn>` | Opens your game's live connection. Resolves once the hub has checked the login. |
| `hub.discord` | Discord toolkit or `null` | The menu's Discord Embedded App SDK object (the toolkit Discord gives Activity pages), for calls like `hub.discord.commands.openExternalLink(...)`. `null` outside Discord. |
| `hub.backToMenu()` | function | Same as the `backToMenu` export. |

Catching an error from an action looks like this:

```js
try {
  const result = await hub.api("buy", { item: "sword" });
  showInventory(result.items);
} catch (e) {
  showMessage(e.message); // your {"error": "..."} text, or a hub message
}
```

**A live connection, page side,** is what `hub.socket()` resolves with:

| Member | What it does |
|---|---|
| `conn.send(data)` | Sends any JSON value to your `message` handler. |
| `conn.on(handler)` | Calls `handler(data)` for every message from your Python code. Messages that arrived before you called `on` are handed to the first handler, so none are lost. |
| `conn.onClose(handler)` | Calls `handler(code)` when the connection closes. |
| `conn.close()` | Closes it. |

## 9. What to trust, and paying out

**The rule:** `ctx` is real; everything the page sends is not. A player can change your page in their browser, or send any request by hand. So:

- **Never trust a score, a count or an amount from the page.** Check it against what is possible. For example, check a score against how long the game ran on the bot's clock.
- **Decide payouts in Python,** with limits (per game, per day).
- **Use `ctx.author` for the bank,** never an id the page sent.

**Paying per event.** Click Counter is this pattern: each action checks a daily limit before it pays, under a lock.

**Paying at the end of a game.** Start a "run" in Python when the game starts, so the clock is yours and not the page's. When it ends, compare the score with the time that passed. This sketch assumes `self.runs = {}` in `__init__`, `import time`, and two limits you pick, `MAX_POINTS_PER_SECOND` and `PAYOUT_LIMIT`:

```python
async def start(self, ctx, data: dict) -> dict:
    self.runs[ctx.author.id] = time.monotonic()
    return {"started": True}


async def finish(self, ctx, data: dict) -> dict:
    if ctx.guild is None:
        return {"error": "This game only works in a server."}
    started = self.runs.pop(ctx.author.id, None)
    points = data.get("points")
    if started is None or not isinstance(points, int) or isinstance(points, bool):
        return {"error": "No game to finish."}
    seconds = time.monotonic() - started
    if points < 0 or points > seconds * MAX_POINTS_PER_SECOND:
        return {"error": "That score doesn't add up."}
    payout = min(points // 10, PAYOUT_LIMIT)
    await bank.deposit_credits(ctx.author, payout)
    return {"paid": payout}
```

Both go in `"actions": {"start": self.start, "finish": self.finish}`. The page calls `hub.api("start")` when a round begins and `hub.api("finish", { points })` when it ends.

For a stronger check, see how the included games [replay the player's moves](#19-bigger-examples-the-included-games).

## 10. Multiplayer with live connections

A live connection (a WebSocket: a connection that stays open, so both sides can send at any time) lets players see each other. Use it when one player's action must reach other players right away.

This adds a shared counter to Click Counter. Everyone in the same Activity window (for example, the same voice channel) bumps it together.

In `clickcounter.py`, add `self.totals = {}` to `__init__`, add `"socket"` to the description, and add three methods:

```python
    async def activityhub_game(self) -> dict:
        return {
            "key": "clickcounter",
            "name": "Click Counter",
            "description": "One click, one credit",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"click": self.click},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
        }

    async def join(self, ctx, conn):
        await conn.send({"total": self.totals.get(ctx.instance_id, 0), "players": len(conn.peers()) + 1})
        await conn.broadcast({"players": len(conn.peers()) + 1})

    async def message(self, ctx, conn, data):
        if data != {"bump": True}:
            return
        total = self.totals.get(ctx.instance_id, 0) + 1
        self.totals[ctx.instance_id] = total
        await conn.broadcast({"total": total, "by": ctx.author.name}, include_self=True)

    async def leave(self, ctx, conn):
        await conn.broadcast({"players": len(conn.peers())})
```

In the page, add `<p id="together"></p><button id="bump" type="button">Bump the shared counter</button>` to `index.html`, and this to the end of `game.js`:

```js
const together = document.getElementById("together");
const bump = document.getElementById("bump");
let shared = { total: 0, players: 1 };

function showShared() {
  together.textContent = `Together: ${shared.total} (${shared.players} playing)`;
}

function retry(code) {
  if (code === 4003) {
    together.textContent = "This game was turned off in this server.";
    return;
  }
  if (code === 1011) {
    together.textContent = "Couldn't join the shared game.";
    return;
  }
  together.textContent = "Reconnecting...";
  setTimeout(goLive, 5000);
}

async function goLive() {
  try {
    const conn = await hub.socket();
    conn.on((data) => {
      shared = { ...shared, ...data };
      showShared();
    });
    conn.onClose(retry);
    bump.onclick = () => conn.send({ bump: true });
  } catch (e) {
    retry(e.status);
  }
}

if (!hub.offline) {
  goLive();
}
```

You should now see "Together: 0 (1 playing)". Open the Activity on a second account in the same voice channel: both pages show "2 playing", and a bump on one shows on both.

Things to know:

- **Close codes** tell you why a connection closed:

  | Code | Why |
  |---|---|
  | `1001` | Your cog was unloaded or reloaded, ActivityHub was unloaded, or the bot is stopping. |
  | `1011` | Your `join` handler raised. |
  | `4001` | The player's login expired. The hub takes the player back to the menu by itself. |
  | `4003` | Your game was turned off in this server, or by the bot owner for every server. |

- **Drops happen**: a proxy restart, a phone going to sleep. Reconnect from `conn.onClose`, like the example does.
- **Heartbeat:** when the page has sent nothing for 30 seconds, the hub sends a small message so proxies don't close the quiet connection. The helper script drops it, so your code never sees it.
- **Reserved field:** don't send objects with an `activityhub` field from Python. The hub uses that field for its own messages.
- **Your game needs `"socket"` in its description,** or `hub.socket()` fails.

## 11. Uploads and other raw requests

A raw route handles anything actions don't cover: file uploads, binary data, streaming. Your handler gets aiohttp's `request` and returns any aiohttp response, so you have full control.

```python
from aiohttp import web
from redbot.core.data_manager import cog_data_path

# in activityhub_game(): "routes": {"POST avatar": self.upload_avatar}

async def upload_avatar(self, request: web.Request, ctx) -> web.Response:
    if ctx is None:
        return web.json_response({"error": "Open this from Discord first."}, status=401)
    body = await request.read()  # the hub refuses bodies over 1 MB
    if not body.startswith(b"\x89PNG"):
        return web.json_response({"error": "Send a PNG image."}, status=400)
    (cog_data_path(self) / f"{ctx.author.id}.png").write_bytes(body)
    return web.json_response({"saved": len(body)})
```

In the page:

```js
const file = document.querySelector("input[type=file]").files[0];
const resp = await hub.fetch("avatar", { method: "POST", body: file });
const result = await resp.json();
```

Things to know:

- **The address** is `/games/<key>/raw/avatar`. Always call it through `hub.fetch("avatar")`, not with a path of your own. Your page's relative paths point at its file folder, not at its routes.
- **`ctx` can be `None`.** Raw routes run without a login too. Check for it, like the example does.
- **Turned off still applies.** For a logged-in player, the hub answers "This activity is turned off in this server." before your handler runs.
- **Raising works.** aiohttp's ready-made responses, like `raise web.HTTPForbidden()`, reach the page as they are. Any other error is logged and the page gets "Something went wrong.".

## 12. Extra Discord permissions

By default the login only asks for the player's name and avatar. `"scopes": [...]` asks for more. A scope is one permission the player approves, like "show what I'm playing in my Discord status". You then use it through `hub.discord`.

For example, to show the game in the player's Discord status:

```python
# in activityhub_game(): "scopes": ["rpc.activities.write"]
```

```js
await hub.discord.commands.setActivity({ activity: { details: "Level 3", state: "Clicking away" } });
```

Every scope that any installed game lists is asked for at login, for every game. Adding a scope makes Discord ask every player to approve again, so only list what you use.

## 13. Opening your game from a command or button

Players open your game from the Activity menu, so you don't need a command. If you want a shortcut anyway, the hub can open your game straight from a button or a slash command:

```python
import discord


class PlayView(discord.ui.View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    @discord.ui.button(label="Play Click Counter", style=discord.ButtonStyle.primary)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        hub = self.cog.bot.get_cog("ActivityHub")
        if hub is None:
            await interaction.response.send_message("Click Counter needs the ActivityHub cog.", ephemeral=True)
            return
        await hub.launch(interaction, "clickcounter")
```

`await hub.launch(interaction, key)` opens the Activity for whoever pressed the button or ran the command. After the login, the menu opens your game directly. Two rules:

- **Don't reply to the interaction before `launch`.** No `defer()`, no `send_message()`. Discord only accepts the launch as the first reply.
- **`launch` handles the problems itself.** It replies privately (only the player sees it) when Activities aren't turned on for the bot, when your game isn't loaded, or when it's turned off in that server or by the bot owner.

## 14. Files and caching

The hub serves every file in your `web_dir`. A few rules keep that working:

- **Use relative paths** in your page: `game.js`, `./levels.json`, `art/ship.png`. Never start a path with `/`.
- **Caching is handled for you.** The hub serves your files under a versioned folder, like `/games/<key>/<code>/game.js`. The code changes whenever any of your files change. So a caching service (like Cloudflare, which keeps copies of files to serve them faster) never serves an old copy.
- **Bundle everything** in `web_dir`: scripts, styles, images, sounds, fonts. Nothing from other websites (see [Discord's limits](#17-discords-limits)).
- **Use `.js` and `.css` files**, not inline `<script>` code or `style="..."` attributes. Discord's content security policy (its rules for what a page may run) may block inline code.
- **Everything in `web_dir` is public.** Anyone can download it. Keep secrets and payout rules in Python.
- **`index.html` needs a `<head>` tag.** The hub puts two tags right after it: a `<base>` tag that points relative paths at your versioned folder, and the import map that tells the browser where `"activityhub"` is.
- **File types are set for you.** The hub serves `.html`, `.js`, `.mjs`, `.css`, `.json`, `.wasm`, `.svg`, `.woff2` and `.mp3` with the exact type browsers require. Other files get their usual type.

## 15. Testing and debugging

**In a normal browser (fastest).** Open the hub's address, for example `http://127.0.0.1:8742/`. The menu shows in preview mode, and your game opens inside it with `hub.offline` set to `true`. Make your page handle that, so you can work on the look without Discord. Press F12 to open the browser's developer tools: the Console tab shows JavaScript errors, the Network tab shows each request.

**Inside Discord.** Open the Activity in a server and pick your game. The easiest way to see errors there is Discord's web app: open `https://discord.com/app` in a normal browser like Chrome, start the Activity, and press F12. The developer tools then show your game frame's console messages and network requests too. (In the Console tab, the frame picker at the top switches between the menu and your game.)

**Python errors** go to the bot's log, like any other cog's. Look for lines starting with `Action <key>.<name> failed`, `Live connection ... handler of <key> failed` or `Raw route ... of <key> failed`.

**Is my game loaded?** `[p]activityhub games` lists every game the hub knows, marks games the owner turned off with `[turned off]`, and lists refused cogs under "Refused:" with the reason.

**After changes:**

- Web files: close your game and open it again.
- Python: `[p]reload <yourcog>`. Players who are connected with a live connection get disconnected with code `1001` and should reconnect.

**Restarts.** The hub keeps logins in memory only. After a bot restart, the menu logs the player in again by itself the next time it talks to the bot. If Discord refuses that, the player sees "Your session expired. Close this activity and open it again." and has to reopen the Activity.

## 16. Common problems

**Your game isn't in the menu:**

| What you see | Why | Fix |
|---|---|---|
| The game isn't in `[p]activityhub games` at all | Your cog isn't loaded, or it has no `activityhub_game` method. | `[p]load yourcog`. Check the method name is spelled exactly `activityhub_game`. |
| `activityhub_game must be an async def` | You wrote `def activityhub_game`. | Write `async def activityhub_game(self)`. |
| `activityhub_game must return a dict` | The method returns something else, or nothing. | `return {...}`. |
| `Unknown fields: ...` | A field name in your dict has a typo, or isn't a real field. | Use only the fields in [the table](#5-reference-activityhub_game). |
| `Missing fields: ...` | `key`, `name` or `web_dir` is missing. | Add them. |
| `key must be 2-32 characters of a-z, 0-9 and hyphens` | The key has capitals, spaces or `_`. | For example, `"click-counter"`, not `"Click_Counter"`. |
| `web_dir has no index.html: ...` | The folder path is wrong, or `index.html` is missing. | Use `Path(__file__).parent / "web"`. The path in the message is the one the hub tried. |
| `icon must name a file inside web_dir: ...` (or `thumbnail`) | The picture's path is wrong, or points outside `web_dir`. | Use a path relative to `web_dir`, like `"art/icon.png"`. |
| `actions handler 'x' must be an async def` | One of your handlers is a plain `def`. | Make it `async def`. |
| `The key 'x' is already used by OtherCog` | Another loaded cog took that key first. | Pick a different key. |
| `activityhub_game() raised ...` | Your method crashed. | The bot's log has the full error. |
| Listed, but not in the menu in one server | A server admin turned it off there. | The server's **This server** settings tab turns it back on. |
| Listed with `[turned off]` | The bot owner turned it off everywhere. | The owner's **Defaults** settings tab turns it back on. |

**Your page doesn't work:**

| What you see | Why | Fix |
|---|---|---|
| A blank page, and the console says the module specifier `"activityhub"` can't be resolved | The page wasn't served by the hub. You opened `index.html` as a file, or from another web server. | Open it through the hub's address, for example `http://127.0.0.1:8742/`, and pick your game. |
| Files your page loads give 404 (not found) | A path starts with `/`, or the file isn't in `web_dir`. | Use relative paths like `art/ship.png`. |
| `hub.api()` throws "Open this activity from Discord to use this." | The page is in preview mode (`hub.offline` is `true`). | Expected outside Discord. Test actions inside Discord. |
| `hub.api()` throws "Something went wrong." | Your Python raised, or returned something that isn't a dict or can't be turned into JSON. | Read the bot's log: `Action <key>.<name> failed`. |
| `hub.api()` throws "That action doesn't exist." | The name isn't in your `actions`, or you added it and didn't reload. | Check the spelling, then `[p]reload yourcog`. |
| `hub.api()` throws "Bad request." | `data` wasn't an object, for example an array or a string. | Send an object: `hub.api("save", { items: [1, 2] })`. |
| `hub.api()` throws "Request failed (413)" | The request was over 1 MB. | Send less, or split it up. |
| `hub.api()` throws "This activity is turned off in this server." | An admin or the bot owner turned your game off. | Turn it back on in the menu settings. |
| The player lands back in the menu mid-game | Their login expired (a bot restart, or 12 hours passed). | Nothing to fix. They log in again and pick your game. |
| `hub.socket()` throws "The live connection closed (1006)." | Your description has no `"socket"` field, or a proxy in front of the bot blocks WebSockets. | Add `"socket"`. Ask the bot owner to allow WebSockets through the proxy. |
| A picture or script from another website doesn't load inside Discord | Discord blocks outside websites. | Put the file in `web_dir`. |
| Your change doesn't show | The page was still open, or the Python wasn't reloaded. | Reopen the game. For Python, `[p]reload yourcog`. |

## 17. Discord's limits

Discord runs Activities with some rules of its own. ActivityHub can't change them.

- **One Discord toolkit per Activity.** The menu owns it. Your page runs in a frame inside the menu and borrows it as `hub.discord`. Never create your own `DiscordSDK`. Never navigate the top page (no `window.top.location`, no links with `target="_top"`). Use `backToMenu()` to leave.
- **Outside websites are blocked** unless the bot owner adds a URL mapping for them in the Developer Portal. Bundle what you need instead. Images from `cdn.discordapp.com` and `media.discordapp.net` (avatars, server icons) load fine.
- **Open links** with `hub.discord.commands.openExternalLink({ url })`.
- **Networking:** use `hub.api()`, `hub.fetch()` and `hub.socket()`. WebRTC and WebTransport (other ways browsers connect) are switched off inside Activities.
- **WebAssembly works** (Godot and Unity web builds). Put the `.wasm` files in `web_dir`. For Godot 4, export with Thread Support turned off, because Activities can't turn on the browser isolation that threads need.
- **Service workers can't register.** (A service worker is a background script some web apps use for offline caching.)

## 18. Checklist before you share your game

- [ ] `[p]activityhub games` lists your game, with no "Refused" line.
- [ ] The page works in the browser preview, and shows a sensible message when `hub.offline` is `true`.
- [ ] The page works inside Discord, in a server and (if you support it) in a DM.
- [ ] Every action checks what the page sent, and never trusts a score or amount from it.
- [ ] Payouts use `ctx.author` and have limits.
- [ ] Your actions return `{"error": "..."}` with friendly text for every expected problem.
- [ ] The page has a way back to the menu (`backToMenu()`).
- [ ] Every file the page needs is inside `web_dir`, loaded with a relative path.
- [ ] Nothing secret is in `web_dir`.
- [ ] Your page works on a phone-sized screen and with touch, since Activities run on Discord's phone apps too.
- [ ] If you use a live connection: the page reconnects after a drop.
- [ ] `info.json` has an `end_user_data_statement`, and your cog deletes a player's data when Red asks it to (`red_delete_data_for_user`).

## 19. Bigger examples: the included games

ActivityHub comes with three games: Snake, Brick Breaker and 2048. They use the same `activityhub_game()` API as any game cog, so they are full working examples to read.

- **Python:** `activityhub/bundled/` (`games.py` has the descriptions and actions).
- **Pages:** `activityhub/bundled/web/`, one folder per game.

Snake and 2048 show a stronger anti-cheat pattern than checking against the clock:

1. When a round starts, the bot picks a random seed (a starting number) and sends it to the page.
2. The page uses that seed for every random roll, like where the next apple or tile appears.
3. When the round ends, the page sends its moves, not its score.
4. The bot replays those moves with the same seed and the same rules, and works out the score itself.

A changed page can't fake a score that way, because the bot never uses the page's score. The cost is that the rules exist twice, once in JavaScript and once in Python, and must match exactly.

Read them for ideas. Their internals are not part of the API and may change.

## 20. Glossary

| Word | What it means here |
|---|---|
| **Action** | A Python method your page calls by name with `hub.api(name, data)`. It gets `ctx` and `data` and returns a dict. |
| **Activity** | A game window that opens inside Discord, usually in a voice channel. A bot can have only one, so ActivityHub turns it into a menu. |
| **ctx** | The object every handler gets, saying who the player is and where (`ctx.author`, `ctx.guild`, `ctx.channel`, `ctx.instance_id`). The hub proved it with Discord. |
| **Frame** | A page inside a page (an HTML `iframe`). Your game runs in one, inside the hub's menu page. |
| **Handler** | Any of your `async def` methods the hub calls: actions, live connection handlers and raw routes. |
| **Instance** | One running Activity window. Everyone in the same window shares its `instance_id`. |
| **Key** | Your game's short id, like `clickcounter`. It's in your game's address, `/games/<key>/`. |
| **Live connection** | A WebSocket: a connection between the page and the bot that stays open, so both can send at any time. Used for multiplayer. |
| **Page** | Your game's web side: `index.html` and the files it loads. |
| **Preview** | The menu and your game opened in a normal browser, outside Discord. `hub.offline` is `true` there. |
| **Raw route** | A handler that gets the raw web request and returns any response. Used for uploads and anything actions can't do. |
| **Scope** | One extra Discord permission the player approves at login, like changing their Discord status. |
| **Session** | The player's login with the hub. The page carries a session pass with every request. It lasts up to 12 hours and ends when the bot restarts. |
| **web_dir** | The folder holding your page: `index.html` and everything it loads. |
