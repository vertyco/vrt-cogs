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

To test inside Discord, the bot owner must finish the one-time setup in [README.md](README.md) (turn on Activities, set the client secret, expose the web server). You only need that for the last step of the quick start. For a test bot, a free cloudflared tunnel is enough to expose the web server.

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
from redbot.core.utils import get_end_user_data_statement

from .clickcounter import ClickCounter

# [p]mydata 3rdparty shows this. It is read from info.json
__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot):
    await bot.add_cog(ClickCounter(bot))
```

`info.json` describes the cog for Red's cog installer. You only need it when you share the cog, but it costs nothing to add now. `install_msg` is shown after someone installs your cog, and it is the place to say your game needs ActivityHub:

```json
{
  "author": ["Your name"],
  "short": "Click a button, earn a credit",
  "description": "A tiny ActivityHub game: click a button, earn a credit.",
  "end_user_data_statement": "This cog stores how many times each player clicked today.",
  "install_msg": "Click Counter is an ActivityHub game. It needs the ActivityHub cog: [p]repo add vrt-cogs https://github.com/vertyco/vrt-cogs, then [p]cog install vrt-cogs activityhub and [p]load activityhub.",
  "requirements": [],
  "tags": ["activityhub", "games"],
  "type": "COG"
}
```

`clickcounter.py` is the cog. `activityhub_game()` describes the game. `click()` is the action the page calls. `red_delete_data_for_user()` is how Red asks a cog to delete a player's data.

```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from redbot.core import Config, bank, commands, errors

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
            try:
                await bank.deposit_credits(ctx.author, 1)
            except errors.BalanceTooHigh:
                return {"error": "Your balance is already at this server's maximum."}
            await ledger.day.set(today)
            await ledger.clicks.set(clicks + 1)
        return {"clicks": clicks + 1, "balance": await bank.get_balance(ctx.author)}

    async def red_delete_data_for_user(self, *, requester, user_id):
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
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

let hub;
try {
  hub = await connect();
} catch (e) {
  // Discord didn't accept the login. The Back button still works
  status.textContent = e.message;
  throw e;
}
status.textContent = hub.offline ? "Open this from Discord to earn credits." : `Hi ${hub.player.displayName}!`;

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

You should now see "Hi" and your name in that server, then "Clicks today: 1. Balance: ..." going up by one per click. Your bank balance in that server goes up too.

### Step 5: change something

- **A web file** (HTML, CSS, JavaScript, images): save it, then close your game and open it again. No reload needed.
- **Python**: run `[p]reload clickcounter`.

You should now see your change. That's the whole loop.

## 4. How one click travels

This is what happens between `hub.api("click")` in the page and `click()` in Python. You never write any of it, but knowing it makes errors easier to read.

1. **The page sends a request.** `hub.api("click", data)` sends `data` (an object, `{}` when left out) to `/games/clickcounter/api/click` as JSON (the text format browsers and Python both use for data). The player's session pass rides along with it.
2. **The hub finds the player.** The session pass maps to a `ctx` the hub proved with Discord when the player logged in. If the pass is missing or expired (after a bot restart, an ActivityHub reload, or 12 hours), the hub answers "Your session expired. Go back to the menu to log in again." without running anything. `hub.api()` then logs the player in again through the menu and sends the request once more, so the game keeps running. Only if that fails is the player taken back to the menu.
3. **The hub checks your game is on.** If the bot owner turned it off, or a server admin turned it off in this server, the page gets "This activity is turned off in this server."
4. **The hub checks the request.** The action name must be in your `actions`, and `data` must be an object.
5. **Your method runs.** The hub calls `await self.click(ctx, data)`.
6. **Your dict goes back.** `hub.api()` resolves with it. If it has an `"error"` text, `hub.api()` throws instead, and `e.message` is your error text.

How the login works, in one breath: when Discord opens the Activity, the hub's menu page asks Discord for a one-time login code. The bot trades that code with Discord for the player's identity, asks Discord which server and channel the Activity runs in, and gives the page a session pass. Your page borrows that login through `connect()`, so you never deal with it.

## 5. Reference: `activityhub_game()`

This method tells the hub about your game. The hub reads it when your cog loads, and again on every `[p]reload`, and keeps what it got. If it reads settings (say, a name the bot owner can change), run `[p]reload yourcog` after changing them, or the menu keeps showing the old values. If ActivityHub itself loads after your cog, it checks every cog that is already loaded, so the load order doesn't matter.

```python
async def activityhub_game(self) -> dict:
    ...
```

It must be an `async def`. It may await things, like reading Config. It can run while the bot is still starting, before it connects to Discord, so servers and members may not be cached yet. If it waits for something slow (for example `bot.wait_until_red_ready()`), your game appears in the menu once it returns. If anything in the dict is wrong, the hub skips your game and `[p]activityhub games` says why.

These are the fields the dict can have. Any other field name is refused, so a typo can't slip through quietly. The refusal suggests the field you probably meant, or, for a game made for a newer ActivityHub, says to update ActivityHub.

| Field | Type | Required | What it does |
|---|---|---|---|
| `key` | `str` | yes | Your game's id: 2 to 32 characters of `a-z`, `0-9` and `-`. Your game lives at the address `/games/<key>/`. **Pick it once:** server switches and players' menu order remember games by key, so a new key counts as a new game, and servers that turned your game off would see it on again. `snake`, `2048` and `brickbreaker` belong to the included games, even when they are turned off. Two cogs can't share a key: the first one registered keeps it, and the second is refused until the first unloads. It then gets the key by itself (so reloading the first cog hands the key to the second). |
| `name` | `str` | yes | The name shown in the menu. Can't be empty. |
| `web_dir` | `str` or `pathlib.Path` | yes | The folder holding `index.html` and every file your page uses. `Path(__file__).parent / "web"` is the usual way to write it. A relative path starts at the folder of the file that defines your cog class, and `~` means your home folder. It can't be your cog's own folder (or a folder above it), since everything in it would be public. `index.html` must be saved as UTF-8. |
| `description` | `str` | no | One line shown under the name. Defaults to `""`. |
| `icon` | `str` or `pathlib.Path` | no | A small square picture inside `web_dir`, shown next to the name. Write it relative to `web_dir`, for example `"icon.png"` (an absolute path inside `web_dir` works too). |
| `thumbnail` | `str` or `pathlib.Path` | no | A wide picture inside `web_dir` (16:9, for example 640x360), like box art or a screenshot, written like `icon`. The grid and list layouts show it in place of the icon, and the Orb theme shows it large next to the menu. Without one, the menu uses the icon. |
| `actions` | `dict[str, handler]` | no | Python methods the page calls with `hub.api(name, data)`. Names use letters, digits, `_`, `.` and `-`, 1 to 64 characters, and not only dots. See [handlers](#7-reference-handlers). |
| `socket` | `dict[str, handler]` | no | Handlers for a live connection. The keys can only be `"join"`, `"message"` and `"leave"`. See [multiplayer](#10-multiplayer-with-live-connections). |
| `routes` | `dict[str, handler]` | no | Raw requests, keyed `"METHOD path"`, for example `"POST avatar"`. `METHOD` is one of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, in capitals. The path uses letters, digits, `_`, `.`, `-` and `/`, with no `.` or `..` parts. Paths match exactly, so there are no `{parameters}`, and each route can be listed once (leading and trailing `/` don't count). See [raw requests](#11-uploads-and-other-raw-requests). |
| `scopes` | `list[str]` | no | Extra Discord permissions to ask the player for at login, one scope name per string. See [permissions](#12-extra-discord-permissions). |

Every handler (in `actions`, `socket` and `routes`) must be an `async def` that takes the arguments [the hub passes](#7-reference-handlers). The hub checks both when your game registers, so a mistake shows up in `[p]activityhub games` right away, not when a player first presses a button. Put the method itself in the dict, `self.click`, not `self.click()`.

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

Every handler gets a `ctx` that says who is playing and where. The hub proved it with Discord: the player really logged in, and Discord itself said which server and channel the Activity runs in. The page can't change it.

| Attribute | Type | What it is |
|---|---|---|
| `ctx.author` | `discord.Member` or `discord.User` | The player. A `discord.Member` in a server. A `discord.User` anywhere else (a DM, or a server your bot isn't in). |
| `ctx.guild` | `discord.Guild` or `None` | The server the Activity was opened in. `None` in a DM, or in a server your bot isn't in. |
| `ctx.guild_id` | `int` or `None` | `ctx.guild.id`, or `None` outside a server. |
| `ctx.channel` | server channel, thread or `None` | The channel the Activity runs in, when it's in a server the bot can see. `None` otherwise. |
| `ctx.channel_id` | `int` or `None` | The channel's id, also in a DM. |
| `ctx.instance_id` | `str` | The id of this Activity window. Everyone in the same Activity window (for example, the same voice channel) has the same one. Use it to group players into one game. |

`if ctx.guild is None` is the check for "not in a server". When it's false, `ctx.author` is a `discord.Member`, ready for the bank and for member Config.

`ctx` has only the attributes above. It isn't Red's `commands.Context`: there is no `ctx.send`, `ctx.reply`, `ctx.message` or `ctx.bot`, because the player is in an Activity, not typing a command. Use `self.bot` for the bot, and `ctx.channel.send(...)` to post in the channel when `ctx.channel` isn't `None`, with a cooldown (see [What to trust](#9-what-to-trust-and-paying-out)).

`ctx` can't be a dict key or a set member. Key per-player state by `ctx.author.id`, per-window state by `ctx.instance_id`, and per-connection state by `conn`.

## 7. Reference: handlers

A handler is one of your `async def` methods that the hub calls. There are three kinds: actions (the page asks, Python answers), live connection handlers (for multiplayer), and raw routes (for anything else, like uploads).

| Kind | Signature | Gets | Returns |
|---|---|---|---|
| Action | `async def name(self, ctx, data: dict) -> dict` | `data`: the object the page sent, or `{}`. | A dict the page receives. Return `{"error": "text"}` to make `hub.api()` throw with that text. Returning `None` sends `{}`. More below. |
| Socket `join` | `async def join(self, ctx, conn) -> None` | `conn`: this player's live connection. | Nothing. If it raises, the connection closes with code `1011`. |
| Socket `message` | `async def message(self, ctx, conn, data) -> None` | `data`: any JSON value the page sent (dict, list, str, number, bool or `None`). | Nothing. If it raises, the error is logged and the connection stays open. |
| Socket `leave` | `async def leave(self, ctx, conn) -> None` | `conn`: the connection that just closed. It is already out of its room, so `conn.peers()` lists only the players still connected. When that is empty, this was the last connection in this instance: clean up there. | Nothing. Not called when `join` raised. |
| Raw route | `async def name(self, request: aiohttp.web.Request, ctx) -> aiohttp.web.StreamResponse` | **`request` first, then `ctx`** (actions are the other way round). `request`: the raw request from aiohttp (the web library the hub uses). `ctx`: `None` when the request carries no login. You decide what that means. | Any aiohttp response, for example `web.json_response(...)`. |

**What an action can return:**

- A dict. The page gets it as a JavaScript object.
- `{"error": "text"}` makes `hub.api()` throw with that text. The text can't be empty. `{"error": None}` counts as no error, and the dict reaches the page as it is.
- Only the error text reaches the page: other keys in an error reply are dropped. To let the page react to a kind of problem, return a normal dict like `{"ok": False, "reason": "no_funds", "need": 50}`.
- Numbers must be finite. NaN and Infinity aren't JSON, so a reply holding them fails like a crash.
- Send Discord ids as strings. JavaScript rounds whole numbers above 2\*\*53, so write `{"user_id": str(ctx.author.id)}`.

Rules the hub enforces for you:

- **Actions and socket handlers only run for a logged-in player**, and only while your game is on in that server.
- **Raw routes also run without a login.** `ctx` is then `None`.
- **Errors stay private.** If a handler raises, or an action returns something that isn't a dict (or can't be turned into JSON), the hub logs it in the bot's log and the page gets "Something went wrong.". Your error text never reaches players. Only `{"error": "..."}` text does. When you test as the bot owner, the page also shows you the reason (see [Testing](#15-testing-and-debugging)).
- **Size limit.** Actions refuse bodies of 1 MB or more (the page sees "Request failed (413)"), and a live message of 1 MB or more closes the connection with `1009`. In raw routes, the limit applies only to `request.read()`, `.json()`, `.text()` and `.post()`. `request.content` and `request.multipart()` aren't limited: check `ctx` first, count bytes as you read, and stop at your own limit, like the [streaming example](#11-uploads-and-other-raw-requests). That is also how to accept uploads bigger than 1 MB.

**How your handlers run:**

- **Actions run at the same time,** even two from one player (a double click). Lock any read-modify-write, like Click Counter does.
- **One connection's messages reach `message` one at a time, in order.** Different players' messages run at the same time, so state they share needs a lock too.
- **`join` finishes before any message is handled.** Until it returns, the hub doesn't read that player's messages or notice that they left, so `join` must return quickly.
- **`leave` runs after the last message handler returns.**
- **Everything shares the bot's event loop.** Never block it: use `await asyncio.to_thread(...)` for heavy work, and start a task for anything slow instead of awaiting it in a handler.

**`conn`, a live connection,** as your Python sees it:

| Member | Type | What it does |
|---|---|---|
| **`await`** `conn.send(data)` | `data`: any JSON value | Sends a message to this player. Does nothing once the connection has closed, and never fails because a player dropped. A player who can't receive for 10 seconds is disconnected (`1001`). Raises `ValueError` for NaN, Infinity or an `activityhub` field (see [multiplayer](#10-multiplayer-with-live-connections)). |
| **`await`** `conn.broadcast(data, include_self=False)` | `data`: any JSON value | Sends to everyone connected to your game with the same `instance_id`. Pass `include_self=True` to send to this player too. Refuses the same values as `send`, even when no one else is connected. |
| `conn.peers()` | `list` of connections | The other connections to your game with the same `instance_id`. |
| **`await`** `conn.close(code=1000)` | `code`: `int` | Closes the connection. Use `1000`, or your own codes from `4100` to `4999`. Codes `4000` to `4099` are ActivityHub's, and `close` refuses them with a `ValueError`. |
| `conn.ctx` | `ctx` | The same `ctx` the handlers get. |

**Type hints.** Don't import from `activityhub` in your cog. Red loads cogs by folder name, so the import fails whenever your cog loads before ActivityHub, and `isinstance` checks go stale after ActivityHub reloads. For your editor, copy these descriptions of `ctx` and `conn` instead, and write `async def click(self, ctx: HubContext, data: dict) -> dict:`.

```python
from typing import Any, Protocol, Sequence

import discord


class HubContext(Protocol):
    """ActivityHub's ctx"""

    author: discord.Member | discord.User
    guild: discord.Guild | None
    channel_id: int | None
    instance_id: str

    @property
    def guild_id(self) -> int | None: ...

    @property
    def channel(self) -> discord.abc.GuildChannel | discord.Thread | None: ...


class HubConnection(Protocol):
    """A live connection, as socket handlers get it"""

    @property
    def ctx(self) -> HubContext: ...

    async def send(self, data: Any) -> None: ...

    async def broadcast(self, data: Any, include_self: bool = False) -> None: ...

    def peers(self) -> Sequence["HubConnection"]: ...

    async def close(self, code: int = 1000) -> None: ...
```

## 8. Reference: the page side

Your page talks to the hub through a small helper script. Import it by the name `"activityhub"`:

```js
import { backToMenu, connect, HubError } from "activityhub";
```

These are the three things you use from it:

| Name | What it is |
|---|---|
| `connect()` | Returns a promise of the `hub` object below. Inside Discord it waits for the menu's login first. It rejects, with Discord's message, if Discord didn't accept the login: catch it and show `e.message` next to your Back button, like the quick start does. |
| `backToMenu()` | Closes your game and shows the menu. |
| `HubError` | The error type `hub.api()` and `hub.socket()` throw. `e.message` is readable text. `e.status` is `400` for your own `{"error"}` replies (the same as the hub's "Bad request."), the HTTP status for the hub's other errors (the number a web server answers with, like `401` or `413`), the close code for live connections, and `0` offline. |

A red "400 (Bad Request)" line in the browser console is normal for `{"error"}` replies: that is how they travel.

**The `hub` object** is what `connect()` gives you:

| Member | Type | What it is |
|---|---|---|
| `hub.offline` | `boolean` | `true` outside Discord, for example in the browser preview. `hub.api()` and `hub.socket()` then throw "Open this activity from Discord to use this." |
| `hub.player` | object or `null` | `{ id, username, displayName, avatar, guildId, guildName, guildIcon }`, all strings. `displayName` is the name Discord shows for the player in that server; `username` is their account handle. The `guild` ones are `null` outside a server, and `guildIcon` is `null` for a server without an icon. `null` when offline. It's for showing, not for trusting. |
| `hub.api(name, data)` | `Promise<object>` | Calls your action `name` with `data` (an object, default `{}`). Resolves with what the action returned. If the player's login expired (a bot restart, an ActivityHub reload), it logs in again and retries once by itself. |
| `hub.fetch(path, options)` | `Promise<Response>` | Calls a raw route, like the browser's own `fetch`, with the player's login attached. `path` is the route path, for example `"avatar"` or `"item?id=7"`. When the hub says the login expired, it logs in again and sends the request once more (a streamed body can't be sent twice, so that one gets the 401). Works offline too, without a login. |
| `hub.socket()` | `Promise<conn>` | Opens your game's live connection. Resolves once the hub has checked the login. If the login expired, it logs in again and retries once by itself. |
| `hub.discord` | Discord toolkit or `null` | The menu's Discord Embedded App SDK object (the toolkit Discord gives Activity pages), for calls like `hub.discord.commands.openExternalLink(...)`. Listeners you add with `hub.discord.subscribe()` are removed for you when your game closes. Its participant list is everyone in the Activity, not your players: see [multiplayer](#10-multiplayer-with-live-connections). `null` outside Discord. |
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
| `conn.send(data)` | Sends any JSON value to your `message` handler. Throws a `TypeError` for something JSON can't hold, like `undefined` or a function. |
| `conn.on(handler)` | Calls `handler(data)` for every message from your Python code. Messages that arrived before you called `on` are handed to the first handler, so none are lost. |
| `conn.onClose(handler)` | Calls `handler(code)` when the connection closes. The [close codes](#10-multiplayer-with-live-connections) say why. |
| `conn.close()` | Closes it, with code `1000`. |

## 9. What to trust, and paying out

**The rule:** `ctx` is real; everything the page sends is not. A player can change your page in their browser, or send any request by hand. So:

- **Never trust a score, a count or an amount from the page.** Check it against what is possible. For example, check a score against how long the game ran on the bot's clock.
- **Decide payouts in Python,** with limits (per game, per day).
- **Use `ctx.author` for the bank,** never an id the page sent.

**Paying per event.** Click Counter is this pattern: each action checks a daily limit before it pays, under a lock.

**Paying at the end of a game.** Start a "run" in Python when the game starts, so the clock is yours and not the page's. When it ends, compare the score with the time that passed, then pay within a daily limit. This sketch assumes `import time`, `from datetime import datetime, timezone` and `from redbot.core import bank, errors`; in `__init__`, `self.runs = {}`, `self.lock = asyncio.Lock()` and `self.config.register_member(day="", paid=0)`; and three limits you pick, `MAX_POINTS_PER_SECOND`, `PAYOUT_LIMIT` (per round) and `DAILY_LIMIT` (per player, per day):

```python
async def start(self, ctx, data: dict) -> dict:
    self.runs[(ctx.guild_id, ctx.author.id)] = time.monotonic()
    return {"started": True}


async def finish(self, ctx, data: dict) -> dict:
    if ctx.guild is None:
        return {"error": "This game only works in a server."}
    started = self.runs.pop((ctx.guild_id, ctx.author.id), None)
    points = data.get("points")
    if started is None or not isinstance(points, int) or isinstance(points, bool):
        return {"error": "No game to finish."}
    seconds = time.monotonic() - started
    if points < 0 or points > seconds * MAX_POINTS_PER_SECOND:
        return {"error": "That score doesn't add up."}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with self.lock:
        ledger = self.config.member(ctx.author)
        paid = await ledger.paid() if await ledger.day() == today else 0
        left = DAILY_LIMIT - paid
        if left <= 0:
            return {"error": "You've earned the most you can today. Come back tomorrow!"}
        payout = min(points // 10, PAYOUT_LIMIT, left)
        try:
            await bank.deposit_credits(ctx.author, payout)
        except errors.BalanceTooHigh:
            return {"error": "Your balance is already at this server's maximum."}
        await ledger.day.set(today)
        await ledger.paid.set(paid + payout)
    return {"paid": payout}
```

Both go in `"actions": {"start": self.start, "finish": self.finish}`. The page calls `hub.api("start")` when a round begins and `hub.api("finish", { points })` when it ends. Runs are kept per server and player, so a round started in one server can't be finished in another. You can also refuse rounds too short to be real, for example a finish less than 5 seconds after its start.

**Limit how often.** A page can call an action, or send live messages, as fast as it likes. A daily limit on credits doesn't stop an action that posts in a channel from being called a thousand times. Put a cooldown on anything with side effects. discord.py's own cooldowns work with the hub's `ctx`:

```python
# in __init__:
self.share_cooldown = commands.CooldownMapping.from_cooldown(1, 30, commands.BucketType.member)


async def share(self, ctx, data: dict) -> dict:
    if ctx.channel is None:
        return {"error": "Sharing only works in a server."}
    if self.share_cooldown.get_bucket(ctx).update_rate_limit():
        return {"error": "You just shared. Try again in a bit."}
    best = await self.config.member(ctx.author).best()
    await ctx.channel.send(
        f"{ctx.author.mention} scored {best} in Space Race!", allowed_mentions=discord.AllowedMentions.none()
    )
    return {"shared": True}
```

Use `BucketType.user` or `BucketType.member`. `BucketType.channel` needs `ctx.channel`, which is `None` outside a server.

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
        await conn.broadcast({"total": total, "by": ctx.author.display_name}, include_self=True)

    async def leave(self, ctx, conn):
        if not conn.peers():
            # The last player left this window
            self.totals.pop(ctx.instance_id, None)
            return
        await conn.broadcast({"players": len(conn.peers())})
```

In the page, add `<p id="together"></p><button id="bump" type="button">Bump the shared counter</button>` to `index.html`, and this to the end of `game.js`:

```js
const together = document.getElementById("together");
const bump = document.getElementById("bump");
let shared = { total: 0, players: 1 };
let drops = 0;

function showShared() {
  together.textContent = `Together: ${shared.total} (${shared.players} playing)`;
}

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open the game again.",
  1009: "That was too big to send.",
  1011: "Couldn't join the shared game.",
  4003: "This game was turned off in this server.",
  4004: "This game has no shared mode.",
};

function retry(code) {
  // 1001: the bot or the game restarted. 1006: the network dropped, which is worth a few more tries
  if (code === 1001 || (code === 1006 && ++drops <= 3)) {
    together.textContent = "Reconnecting...";
    setTimeout(goLive, 5000);
    return;
  }
  together.textContent = CLOSED_BECAUSE[code] || "The shared game ended.";
}

async function goLive() {
  try {
    const conn = await hub.socket();
    drops = 0;
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

You should now see "Together: 0 (1 playing)". Open the Activity on a second account in the same voice channel and pick Click Counter there too: both pages show "2 playing", and a bump on one shows on both.

Friends who open the Activity land in the menu, not in your game: each of them picks it there. A [Play button](#13-opening-your-game-from-a-command-or-button) opens your game straight away for each player who presses it.

Things to know:

- **Close codes** tell you why a connection closed. The page gets them in `conn.onClose`, or as `e.status` when `hub.socket()` fails:

  | Code | Why | Reconnect? |
  |---|---|---|
  | `1000` | Closed on purpose: your Python's `conn.close()` or the page's `conn.close()`. | No. |
  | `1001` | Your cog or ActivityHub was unloaded or reloaded, the bot is stopping, or the player stopped answering or fell behind (see below). | Yes, after a few seconds. |
  | `1006` | The connection dropped without a goodbye: the network, a proxy that blocks WebSockets, or your game isn't loaded. | Yes, but give up after a few in a row. |
  | `1009` | A message of 1 MB or more. The hub closes the whole connection, and `leave` still runs. | Not until you send less. |
  | `1011` | Your `join` handler raised. | No. |
  | `4001` | The login expired while connecting, and logging in again failed. The hub takes the player back to the menu by itself. | No. |
  | `4003` | Your game was turned off in this server, or by the bot owner for every server. | No. |
  | `4004` | Your `activityhub_game()` has no `"socket"`. | No. |
  | `4100`-`4999` | Your own codes, from `conn.close(code)` in your Python. | Your call. |

  Codes `4000` to `4099` are ActivityHub's, and `conn.close()` refuses them. Send a message saying why before you close, because the close code is all the page gets.
- **Drops happen**: a proxy restart, a phone going to sleep. Reconnect from `conn.onClose`, like the example does, and give up after a few drops in a row.
- **Heartbeat:** when a connection has been quiet for 30 seconds, the hub pings it (and sends a small message so proxies don't close the quiet connection; the helper script drops it, so your code never sees it). A player whose browser doesn't answer within another 30 seconds is disconnected, and your `leave` runs. Until then, `peers()` can still include a player whose network vanished.
- **Slow players:** a player who can't take a message for 10 seconds is disconnected with `1001`, so one stalled phone never holds up everyone's broadcasts.
- **Reserved field:** don't send objects with an `activityhub` field from Python. The hub uses that field for its own messages, and `conn.send()` and `conn.broadcast()` refuse it with a `ValueError`.
- **Your game needs `"socket"` in its description,** or `hub.socket()` fails with `4004`.
- **Who is in your game:** use `conn.peers()` in Python. Discord's own participant list (`hub.discord.commands.getInstanceConnectedParticipants()`, the `ACTIVITY_INSTANCE_PARTICIPANTS_UPDATE` event) lists everyone in the Activity, including players in the menu or in other games.
- **Waiting for an opponent:** remember `conn` and return from `join`. Start the match from the second player's `join`.
- **Other players' broadcasts already reach a connection while its `join` runs.** Read your state and send the snapshot with no other `await` in between, or guard the state with an `asyncio.Lock` that `message` also takes.
- **Refusing a player** (the room is full, they were kicked): `await conn.send({"error": "This table is full."})`, then `await conn.close(4100)`. `leave` still runs for that connection, so only undo what `join` did.
- **Key per-player state by `conn`,** or check `self.players.get(ctx.author.id) is conn` before deleting it in `leave`. A player who reconnects has a new `conn` before the old one's `leave` runs.
- **When your cog unloads or reloads,** `leave` still runs for every connected player, after your `cog_unload`, on the old cog object. Keep what `leave` needs alive until then.
- **To reach players from an action, a timer or a command,** keep your own record of each window's connections, updated in `join` and `leave`. For example, with `self.rooms = {}` in `__init__`:

  ```python
  async def join(self, ctx, conn):
      self.rooms.setdefault(ctx.instance_id, set()).add(conn)


  async def leave(self, ctx, conn):
      self.rooms.get(ctx.instance_id, set()).discard(conn)


  async def poke(self, ctx, data: dict) -> dict:
      # A copy, since a player can leave while this sends
      for conn in list(self.rooms.get(ctx.instance_id, ())):
          if conn.ctx.author.id != ctx.author.id:
              await conn.send({"poked_by": ctx.author.display_name})
      return {}
  ```

## 11. Uploads and other raw requests

A raw route handles anything actions don't cover: file uploads, binary data, streaming. Your handler gets aiohttp's `request` and returns any aiohttp response, so you have full control.

```python
from aiohttp import web
from redbot.core.data_manager import cog_data_path

# in activityhub_game(): "routes": {"POST avatar": self.upload_avatar}

async def upload_avatar(self, request: web.Request, ctx) -> web.Response:
    if ctx is None:
        return web.json_response({"error": "Open this from Discord first."}, status=401)
    body = await request.read()  # read() refuses bodies of 1 MB or more
    if not body.startswith(b"\x89PNG"):
        return web.json_response({"error": "Send a PNG image."}, status=400)
    (cog_data_path(self) / f"{ctx.author.id}.png").write_bytes(body)
    return web.json_response({"saved": len(body)})
```

For bigger files, read `request.content` yourself, counting as you go. The hub doesn't limit it, so your route must:

```python
UPLOAD_LIMIT = 8 * 1024 * 1024

# in activityhub_game(): "routes": {"POST replay": self.upload_replay}

async def upload_replay(self, request: web.Request, ctx) -> web.Response:
    if ctx is None:
        return web.json_response({"error": "Open this from Discord first."}, status=401)
    chunks, size = [], 0
    async for chunk in request.content.iter_chunked(65536):
        size += len(chunk)
        if size > UPLOAD_LIMIT:
            return web.json_response({"error": "That file is too big."}, status=413)
        chunks.append(chunk)
    (cog_data_path(self) / f"{ctx.author.id}.replay").write_bytes(b"".join(chunks))
    return web.json_response({"saved": size})
```

In the page:

```js
async function uploadAvatar() {
  const file = document.querySelector("input[type=file]").files[0];
  if (!file || file.size >= 1024 * 1024) {
    showMessage("Pick a picture under 1 MB.");
    return;
  }
  const resp = await hub.fetch("avatar", { method: "POST", body: file });
  const result = await resp.json().catch(() => ({ error: `Upload failed (${resp.status})` }));
  if (!resp.ok) {
    showMessage(result.error);
    return;
  }
  showMessage(`Saved ${result.saved} bytes.`);
}
```

Things to know:

- **The address** is `/games/<key>/raw/avatar`. Always call it through `hub.fetch("avatar")`, not with a path of your own. Your page's relative paths point at its file folder, not at its routes.
- **`ctx` can be `None`.** Raw routes run without a login too. Check for it, like the example does. It is `None` only for requests with no login (the browser preview, or a request not made with `hub.fetch`). When a player's login expired, the hub answers 401 itself and `hub.fetch` logs in again and retries, so your handler never sees an expired login.
- **Your own tokens go in another header.** The hub uses `Authorization` for the player's login (`hub.fetch()` sets it), and answers any `Authorization: Bearer ...` it doesn't know with 401 before your route runs. If your route checks its own tokens (a webhook from another service, say), have them sent in another header, like `X-Api-Key`.
- **Turned off still applies.** For a logged-in player, the hub answers "This activity is turned off in this server." before your handler runs.
- **Raising works.** aiohttp's ready-made responses, like `raise web.HTTPForbidden()`, reach the page as they are. Any other error is logged and the page gets "Something went wrong.". These ready-made errors, and the hub's own 413 and 404 for raw routes, arrive as plain text, not JSON, so check `resp.ok` before `resp.json()`, like the page example does.
- **Paths match exactly.** `"GET item"` answers `item` and `item?id=7`, not `item/7`. There are no `{parameters}`: send values in the query string, `hub.fetch("item?id=7")`, and read `request.query["id"]`. There is no `HEAD`.
- **Showing what a route returns.** For a logged-in read, fetch it and make a local address for it:

  ```js
  const resp = await hub.fetch(`avatar?user=${id}`);
  img.src = URL.createObjectURL(await resp.blob());
  ```

  A public `GET` route (one that is fine with `ctx` being `None`) also works straight from HTML, as `<img src="../raw/avatar?user=2">`. The hub's `<base>` tag puts plain relative paths in your file folder, so `raw/...` alone doesn't reach your routes.

## 12. Extra Discord permissions

By default the login only asks for the player's name and avatar. `"scopes": [...]` asks for more. A scope is one permission the player approves, like "show what I'm playing in my Discord status". You then use it through `hub.discord`.

For example, to show the game in the player's Discord status:

```python
# in activityhub_game(): "scopes": ["rpc.activities.write"]
```

```js
await hub.discord.commands.setActivity({ activity: { details: "Level 3", state: "Clicking away" } });
```

Things to know:

- **Every scope that any installed game lists is asked for at login,** for every game. Adding a scope makes Discord ask every player to approve again, so only list what you use.
- **One wrong scope stops every game.** A scope Discord doesn't accept stops every game on the bot from logging in. Copy names exactly from Discord's OAuth2 scope list. The hub refuses names that can't be scopes (like `"identify guilds"` in one string) and scopes a login can't ask for (`bot`, `webhook.incoming`), and warns in the bot log about names it doesn't know. `[p]activityhub games` shows which game asks for what.
- **Only scopes used through `hub.discord` help.** Neither your page nor your Python gets the player's Discord access token.
- **Scopes are read when the Activity opens.** Reopen it after adding one.

## 13. Opening your game from a command or button

Players open your game from the Activity menu, so you don't need a command. If you want a shortcut anyway, the hub can open your game straight from a button or a slash command:

```python
import discord


class PlayView(discord.ui.View):
    """A Play button that keeps working after 3 minutes and after the bot restarts"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Play Click Counter", style=discord.ButtonStyle.primary, custom_id="clickcounter:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        hub = self.cog.bot.get_cog("ActivityHub")
        if hub is None:
            await interaction.response.send_message("Click Counter needs the ActivityHub cog.", ephemeral=True)
            return
        await hub.launch(interaction, "clickcounter")
```

And in your cog, add the view back on every load, plus a command that works both ways:

```python
    async def cog_load(self):
        self.play_view = PlayView(self)
        # Buttons posted before a restart work again once the view is added back
        self.bot.add_view(self.play_view)

    async def cog_unload(self):
        self.play_view.stop()

    @commands.hybrid_command(name="clickcounter")
    async def clickcounter_command(self, ctx: commands.Context):
        """Play Click Counter"""
        hub = self.bot.get_cog("ActivityHub")
        if ctx.interaction is not None and hub is not None:
            # Run as a slash command: open the game straight away
            await hub.launch(ctx, "clickcounter")
        else:
            await ctx.send("Press to play:", view=self.play_view)
```

A hybrid command shows up as a slash command once the bot owner runs `[p]slash enable clickcounter` and `[p]slash sync`.

`await hub.launch(interaction, key)` opens the Activity for whoever pressed the button or ran the command. After the login, the menu opens your game directly. The rules:

- **Don't reply to the interaction before `launch`.** No `defer()`, no `send_message()`. Discord only accepts the launch as the first reply, so `launch` raises `RuntimeError` when the interaction already has one.
- **`launch` takes the `discord.Interaction`,** or a hybrid command's `ctx` when it ran as a slash command. A text command has no interaction, so `launch` raises `TypeError` for it: post the button instead, like the example does.
- **`launch` handles the problems itself.** It replies privately (only the player sees it) when Activities aren't turned on for the bot, when your game isn't loaded, or when it's turned off in that server or by the bot owner.
- **It returns `True` when the Activity opened,** and `False` when it was refused or Discord failed.
- **A button must use `timeout=None` and a fixed `custom_id`, and be added back with `bot.add_view`,** to keep working after 3 minutes and after restarts.

## 14. Files and caching

The hub serves every file in your `web_dir`. A few rules keep that working:

- **Use relative paths** in your page: `game.js`, `./levels.json`, `art/ship.png`. Never start a path with `/`. The bot log warns when `index.html` has a `src` or `href` starting with `/`.
- **Caching is handled for you.** The hub serves your files under a versioned folder, like `/games/<key>/<code>/game.js`. The code changes whenever any of your files change. So a caching service (like Cloudflare, which keeps copies of files to serve them faster) never serves an old copy.
- **Bundle everything** in `web_dir`: scripts, styles, images, sounds, fonts. Nothing from other websites (see [Discord's limits](#17-discords-limits)).
- **Prefer `.js` and `.css` files:** they cache and debug better. Inline `<script>` isn't blocked: the hub's own import map is an inline script, so any page that can import `"activityhub"` can run inline code.
- **Everything in `web_dir` is public.** Anyone can download it. Keep secrets and payout rules in Python. Files and folders whose names start with a dot (`.git`, `.env`) are the exception: the hub never serves them.
- **Keep `web_dir` to your built page.** Point it at your build output (for example `dist/`), not a project folder with `node_modules`. Every file in it is public and is fingerprinted each time the game opens, so the bot log warns about a `node_modules` folder or more than 2000 files.
- **`index.html` should have a `<head>` tag.** The hub puts two tags right after it: a `<base>` tag that points relative paths at your versioned folder, and the import map that tells the browser where `"activityhub"` is. Without a `<head>`, it puts them right after the doctype.
- **Watch out for `#` links.** Because of the `<base>` tag, `href="#"`, `href="#rules"` and `href="index.html"` leave your game: to a "This page isn't part of the game." notice, or a copy of your page without the helper. Use `<button type="button">`, `element.scrollIntoView()`, or `event.preventDefault()`.
- **Keep your game in one page.** Only `index.html` gets the `<base>` tag and the `"activityhub"` import. Other `.html` files are served as they are.
- **Single-page app routers must use memory or hash mode** (for example `createMemoryRouter`, `createMemoryHistory` or `createWebHashHistory`). Your page lives at `/games/<key>/`, and a reload of any other path misses. When the game frame does land on an address that isn't a file, it shows "This page isn't part of the game." with a Back button, and the bot log names the address.
- **Storage is shared.** Every game and the menu share one web address, so `localStorage` and `sessionStorage` are shared too. Prefix your keys with your game key (`"clickcounter:best"`), and keep anything that matters in Config. (Game cogs are fully trusted code, like any Red cog.)
- **Links (symlinks, `npm link`) to files outside `web_dir` aren't served.** Copy the files in.
- **Using a bundler?** Mark `activityhub` as external (esbuild `--external:activityhub`; Vite `build.rollupOptions.external: [/^activityhub/]` plus `base: './'`), output ES modules, and point `web_dir` at the build output folder.
- **File types are set for you.** The hub serves `.html`, `.js`, `.mjs`, `.css`, `.json`, `.wasm`, `.svg`, `.woff2` and `.mp3` with the exact type browsers require. Other files get their usual type. Files ending in `.gz` or `.br` are sent compressed: see [engine builds](#17-discords-limits).

## 15. Testing and debugging

**In a normal browser (fastest).** Open the hub's address, for example `http://127.0.0.1:8742/`. The menu shows in preview mode, and your game opens inside it with `hub.offline` set to `true`. Make your page handle that, so you can work on the look without Discord. Press F12 to open the browser's developer tools: the Console tab shows JavaScript errors, the Network tab shows each request.

**Inside Discord.** Open the Activity in a server and pick your game. The easiest way to see errors there is Discord's web app: open `https://discord.com/app` in a normal browser like Chrome, start the Activity, and press F12. The developer tools then show your game frame's console messages and network requests too. (In the Console tab, the frame picker at the top switches between the menu and your game.) Don't open the game frame's own address, the one with `?frame_id=...`, in a tab of its own: it only works inside Discord, and after 10 seconds the page says "Discord hasn't answered yet".

**Two players.** Open the Activity on a second account in Discord's web app, in a second browser profile, in the same voice channel. Then pick your game there too.

### Testing your Python without Discord

Your handlers are plain async methods, so tests can call them directly with stand-ins for `ctx` and `conn`. Nothing here imports ActivityHub. Install `pytest` and `pytest-asyncio` in the bot's Python environment, put the files below in a `tests` folder next to `clickcounter/`, and run `python -m pytest tests` from the folder that holds both.

`tests/conftest.py` borrows Red's own test fixtures:

```python
from redbot.pytest.core import *  # Red's own fixtures: a temporary data folder, member_factory...
```

`tests/test_clickcounter.py` tests the quick start's action, and the live connection handlers from [multiplayer](#10-multiplayer-with-live-connections):

```python
import json
from types import SimpleNamespace

import pytest
from redbot.core import bank

from clickcounter.clickcounter import ClickCounter


@pytest.mark.asyncio
async def test_click_pays_one_credit(member_factory):
    await bank._init()  # how Red's own tests set up the bank (redbot/pytest/economy.py)
    member = member_factory.get()
    cog = ClickCounter(bot=None)
    ctx = SimpleNamespace(
        author=member, guild=member.guild, guild_id=member.guild.id, channel=None, channel_id=None, instance_id="test"
    )
    assert (await cog.click(ctx, {}))["clicks"] == 1


class FakeConn:
    """Stands in for a live connection. Keeps what was sent, and refuses what the hub would refuse"""

    def __init__(self, ctx, room):
        self.ctx, self.room, self.sent, self.closed = ctx, room, [], None
        room.append(self)

    async def send(self, data):
        self.sent.append(json.loads(json.dumps(data, allow_nan=False)))

    async def broadcast(self, data, include_self=False):
        for conn in list(self.room):
            if include_self or conn is not self:
                await conn.send(data)

    def peers(self):
        return [conn for conn in self.room if conn is not self]

    async def close(self, code=1000):
        if 4000 <= code <= 4099:
            raise ValueError(f"Close code {code} is reserved for ActivityHub")
        self.closed = code


def player(user_id, instance_id="test"):
    author = SimpleNamespace(id=user_id, name=f"player{user_id}", display_name=f"Player {user_id}")
    return SimpleNamespace(
        author=author, guild=None, guild_id=None, channel=None, channel_id=None, instance_id=instance_id
    )


@pytest.mark.asyncio
async def test_a_bump_reaches_everyone():
    cog, room = ClickCounter(bot=None), []
    alice = FakeConn(player(1), room)
    await cog.join(alice.ctx, alice)
    bob = FakeConn(player(2), room)
    await cog.join(bob.ctx, bob)
    await cog.message(alice.ctx, alice, {"bump": True})
    assert alice.sent[-1] == bob.sent[-1] == {"total": 1, "by": "Player 1"}
    # The hub takes a closing connection out of its room before leave runs
    room.remove(alice)
    await cog.leave(alice.ctx, alice)
    assert bob.sent[-1] == {"players": 1}
```

The hub's own tests (`activityhub/tests/fakes.py`) use the same kind of stand-ins for Discord's users and servers.

**Python errors** go to the bot's log, like any other cog's. Look for lines starting with `Action <key>.<name>` (followed by "failed", "returned ... instead of a dict", "returned something that isn't JSON", "returned an empty error" or "returned an error that isn't text"), `Live connection ... handler of <key> failed`, or `Raw route ... of <key>` (followed by "failed" or "returned ..., not a response"). When you test as the bot owner, "Something went wrong." on the page also includes the reason, like "(Only you see this, as the bot owner: KeyError: 'points'. The bot's log has the full error.)". Other players only see "Something went wrong."

**Is my game loaded?** `[p]activityhub games` lists every game the hub knows with the Discord scopes it asks for, marks games the owner turned off with `[turned off]`, and lists refused cogs under "Refused:" with the reason.

**After changes:**

- Web files: close your game and open it again.
- Python: `[p]reload <yourcog>`. Players who are connected with a live connection get disconnected with code `1001` and should reconnect. Your `leave` still runs for each of them, on the old copy of your cog.

**Restarts.** The hub keeps logins in memory only, so a bot restart, or a reload or update of ActivityHub, forgets them. `hub.api()`, `hub.fetch()` and `hub.socket()` then log the player in again by themselves and retry once, and the game keeps running. Live connections still close with `1001` and should reconnect. If Discord refuses the new login, the player is taken back to the menu, and if the menu can't log in either, it shows "Your session expired. Close this activity and open it again."

## 16. Common problems

**Your game isn't in the menu:**

| What you see | Why | Fix |
|---|---|---|
| The game isn't in `[p]activityhub games` at all | Your cog isn't loaded, it has no `activityhub_game` method, or `activityhub_game()` is still waiting on something. | `[p]load yourcog`. Check the method name is spelled exactly `activityhub_game`. A game whose method waits shows up once it returns. |
| `activityhub_game must be an async def` | You wrote `def activityhub_game`. | Write `async def activityhub_game(self)`. |
| `activityhub_game must return a dict, got ...` | The method returns something else, or nothing (`got NoneType`). | `return {...}`. |
| `activityhub_game must return one dict (one game per cog), got ...` | The method returns several games, in a list or a tuple. | One cog gives one game. Make a cog for each. |
| `Unknown field 'action' (did you mean 'actions'?)` | A field name in your dict has a typo. | Use the field it suggests. |
| `Unknown fields: ...` | A field name isn't a real field, or the game was made for a newer ActivityHub. | Use only the fields in [the table](#5-reference-activityhub_game), or update ActivityHub with `[p]cog update`. |
| `Missing fields: ...` | `key`, `name` or `web_dir` is missing. | Add them. |
| `key must be 2-32 characters of a-z, 0-9 and hyphens, got 'Click_Counter' (try 'click-counter')` | The key has capitals, spaces or `_`. | Use the key it suggests. |
| `<field> must be ...`, like `name must be a non-empty string` | A field has the wrong type. | See the types in [the table](#5-reference-activityhub_game). |
| `web_dir has no index.html: looked for ...` | The folder path is wrong, or `index.html` is missing. The message shows the full path the hub looked in. | Use `Path(__file__).parent / "web"`. A relative path starts at your cog's folder. |
| `web_dir holds your cog's Python code, and everything in web_dir is public.` | `web_dir` is your cog's folder, or a folder above it. | Keep the page in its own folder, like `Path(__file__).parent / "web"`. |
| `index.html isn't UTF-8 text ...` | Your editor saved it in another encoding. | Save it as UTF-8. |
| `icon must be a file inside web_dir, written relative to it (like 'icon.png'): ...` (or `thumbnail`) | The picture's path is wrong, or points outside `web_dir`. | Use a path relative to `web_dir`, like `"art/icon.png"`. |
| `icon has a name starting with a dot in its path, and the hub never serves those: ...` | The picture is in a folder like `.assets`. | Move it to a folder whose name doesn't start with a dot. |
| `actions key 'x' must be ...`, `socket keys can only be ...` or `routes key 'x' must be "METHOD path" ...` | A name breaks the naming rule in [the table](#5-reference-activityhub_game). The message says the rule. | Rename it. |
| `routes has 'x' twice (paths ignore leading and trailing /)` | Two routes differ only by a leading or trailing `/`. | Keep one. |
| `actions handler 'x' must be an async def` | One of your handlers is a plain `def`. | Make it `async def`. |
| `actions 'x' is a coroutine, not a method: write self.x without ()` | You wrote `self.click()` in the dict. | Write `self.click`. |
| `actions handler 'x' takes (ctx), but the hub calls it with (ctx, data).` | The handler has the wrong parameters. | Add the missing one. Actions are `(ctx, data)`, socket handlers `(ctx, conn)` and `(ctx, conn, data)`, raw routes `(request, ctx)`. If the message ends with "Use self.x, not ClassName.x.", write `self.x` in the dict. |
| `routes handler 'x' takes (ctx, request), but raw routes get (request, ctx): request first` | The parameters are swapped. | Swap them: `(self, request, ctx)`. |
| `scopes has 'identify guilds', which isn't a Discord scope name.` | Several scopes in one string. | One scope per string: `["identify", "guilds"]`. |
| `scopes can't include 'bot': it isn't a permission an Activity login can ask for` | `bot` and `webhook.incoming` add a bot or a webhook to a server, which a player can't approve while logging in. | Remove it. |
| `The key 'x' is already used by OtherCog` | Another loaded cog took that key first. | Pick a different key. If the other cog unloads, yours gets the key by itself. |
| `activityhub_game() raised ...` | Your method crashed. | The bot's log has the full error. |
| Listed, but not in the menu in one server | A server admin turned it off there. | The server's **This server** settings tab turns it back on. |
| Listed with `[turned off]` | The bot owner turned it off everywhere. | The owner's **Defaults** settings tab turns it back on. |

**Warnings in the bot log.** Your game still registers, but something will likely break:

| What you see | Why | Fix |
|---|---|---|
| `asks for the scope 'x', which ActivityHub doesn't know` | A scope name the hub doesn't know, often a typo. Every installed game's scopes go into one login, so a wrong one stops every game from logging in. | Copy the name exactly from Discord's OAuth2 scope list. |
| `index.html refers to ... with an absolute path, which the hub can't serve` | A `src` or `href` starts with `/`. | Use relative paths. Built with Vite? Set `base: './'`. To go back to the menu, call `backToMenu()`. |
| `web_dir has a node_modules folder` (or `more than 2000 files`) | `web_dir` is your project folder, not your built page. | Point `web_dir` at your build output, like `dist/`. |
| `the game frame went to ..., which isn't a file in web_dir` | Your page went to an address that isn't a file: an `href="#"` link, a router path, a reload after `history.pushState`, or a typo. The player saw "This page isn't part of the game." | See [Files and caching](#14-files-and-caching): use buttons, and memory or hash routing. |
| `the page opened a live connection, but activityhub_game() has no "socket"` | The page called `hub.socket()`. | Add `"socket"` to `activityhub_game()` and `[p]reload yourcog`, or don't call `hub.socket()`. |

**Your page doesn't work:**

| What you see | Why | Fix |
|---|---|---|
| A blank page, and the console says the module specifier `"activityhub"` can't be resolved | The page wasn't served by the hub. You opened `index.html` as a file, or from another web server. | Open it through the hub's address, for example `http://127.0.0.1:8742/`, and pick your game. |
| `Uncaught SyntaxError: Cannot use import statement outside a module` | The `<script>` tag has no `type="module"`. | `<script type="module" src="game.js"></script>` |
| `does not provide an export named 'api'` (or `'default'`) | The helper only exports `connect`, `backToMenu` and `HubError`. | `import { connect } from "activityhub";`, then `const hub = await connect();` and `hub.api(...)`. |
| `hub.api is not a function` | `connect()` returns a promise. | `const hub = await connect();` |
| Files your page loads give 404 (not found) | A path starts with `/`, the file isn't in `web_dir`, its name or a folder's name starts with a dot, or it's a link to a file outside `web_dir`. | Use relative paths like `art/ship.png`, and copy the file into `web_dir`. |
| The page is blank, the console shows 404 for `/assets/...`, and the bot log warns about an absolute path | Your bundler wrote paths from the site's root. | Vite: `base: './'`. webpack: `output.publicPath: './'`. |
| `hub.api()` throws "Open this activity from Discord to use this." | The page is in preview mode (`hub.offline` is `true`). | Expected outside Discord. Unit-test your handlers (see [Testing your Python without Discord](#testing-your-python-without-discord)), and try the page inside Discord once the owner finished the README setup (a cloudflared tunnel is enough for a test bot). |
| `hub.api()` throws "Something went wrong." | Your Python raised, or returned something that isn't a dict, can't be turned into JSON, or has an error that isn't text. | Read the bot's log: look for `Action <key>.<name>`. As the bot owner, the message itself shows the reason. |
| `hub.api()` throws "That action doesn't exist: x." | The name isn't in your `actions`, or you added it and didn't reload. | Check the spelling, then `[p]reload yourcog`. |
| `hub.api()` throws "Bad request." | `data` wasn't an object, for example an array or a string. | Send an object: `hub.api("save", { items: [1, 2] })`. |
| `hub.api()` throws "Request failed (413)" | The request was 1 MB or more. | Send less, or split it up. |
| `hub.api()` throws "This activity is turned off in this server." | An admin or the bot owner turned your game off. | Turn it back on in the menu settings. |
| `hub.api()` throws "The bot's reply wasn't valid JSON." | Something other than the bot answered, like a proxy's error page. | Check the reply in the Network tab, and the proxy in front of the bot. |
| A request with your own token gets 401, and your route never runs | The token was sent as `Authorization: Bearer ...`. The hub uses that header for the player's login, and took your token for an expired one. (Inside Discord, `hub.fetch()` also replaces that header with the player's login.) | Send your own tokens in another header, like `X-Api-Key`. |
| The player lands back in the menu mid-game | Their login expired and Discord refused a fresh one. | Nothing to fix. They open your game again. |
| Pressing a Back link shows the menu again, with a warning in the console | The link went to `/` or another address, and the hub closed your game. | Call `backToMenu()` instead of linking. |
| The game frame shows "This page isn't part of the game." | The frame went to an address that isn't a file in `web_dir`: an `href="#"` link, a router path, or a reload after `history.pushState`. The bot log names the address. | See [Files and caching](#14-files-and-caching): use buttons, and memory or hash routing. |
| `hub.socket()` throws "This game has no live connection. Add "socket" to activityhub_game() and reload the cog." | Your description has no `"socket"` field. | Add `"socket"`, then `[p]reload yourcog`. |
| `hub.socket()` throws "The live connection closed (1006)." | A proxy in front of the bot blocks WebSockets, the network dropped, or your game isn't loaded. | Ask the bot owner to allow WebSockets through the proxy. Check `[p]activityhub games`. |
| The page never gets a message, and the bot console says `coroutine 'Connection.send' was never awaited` | `conn.send()` was called without `await`. | `await conn.send(...)`. |
| The bot log shows `ValueError: Out of range float values are not JSON compliant` (or `The 'activityhub' field is reserved for the hub's own messages`) from a socket handler | You sent NaN or Infinity, or an object with an `activityhub` field. | Send finite numbers, and use another field name. |
| An id from Python is off by a few | JavaScript rounds whole numbers above 2\*\*53. | Send ids as text: `str(ctx.author.id)`. |
| `sdk.ready()` never finishes, and the console says "this game created its own DiscordSDK" | Your page made its own `DiscordSDK`. Inside the hub, only the menu talks to Discord. | Use `hub.discord` from `connect()`. |
| The menu says "Discord hasn't answered yet" | You opened the game's address with `?frame_id=...` in a tab of its own. It only works inside Discord. | For the preview, open `/` without the `?frame_id=...` part. |
| A picture or script from another website doesn't load inside Discord | Discord blocks outside websites. | Put the file in `web_dir`. |
| Your change doesn't show | The page was still open, or the Python wasn't reloaded. | Reopen the game. For Python, `[p]reload yourcog`. |

## 17. Discord's limits

Discord runs Activities with some rules of its own. ActivityHub can't change them.

- **One Discord toolkit per Activity.** The menu owns it. Your page runs in a frame inside the menu and borrows it as `hub.discord`. Never create your own `DiscordSDK`: its `ready()` never finishes inside the hub, and the console says so. Never navigate the top page (no `window.top.location`, no links with `target="_top"`). Use `backToMenu()` to leave, not a link to `/` or another address: the hub closes a game whose frame leaves its page, and warns in the console.
- **Outside websites are blocked** unless the bot owner adds a URL mapping for them in the Developer Portal. Bundle what you need instead. Images from `cdn.discordapp.com` and `media.discordapp.net` (avatars, server icons) load fine.
- **Open links** with `hub.discord.commands.openExternalLink({ url })`.
- **Networking:** use `hub.api()`, `hub.fetch()` and `hub.socket()`. WebRTC and WebTransport (other ways browsers connect) are switched off inside Activities.
- **WebAssembly and engine builds work** (Godot, Unity). Put the whole export in `web_dir`, with the page named `index.html` (Godot names it `<project>.html` by default: rename it). For Godot 4, export with Thread Support turned off, because Activities can't turn on the browser isolation that threads need. Unity's Gzip, Brotli and uncompressed builds work as exported, without Decompression Fallback: the hub sends files ending in `.gz` or `.br` with `Content-Encoding`, so the browser unpacks them. That also means your code never sees those files packed: if you unpack a file yourself (with `DecompressionStream`, say), give it another extension, like `.bin`. From a script that isn't a module (an engine loader, a Unity `.jslib`, Godot's `JavaScriptBridge`), reach the helper inside an async function with `const { connect } = await import("activityhub");`, and set `window.hub = await connect();` if the engine needs a global.
- **Service workers can't register.** (A service worker is a background script some web apps use for offline caching.)
- **Clean up when your game closes.** Your page is removed when the player goes back to the menu, and `pagehide` is the last event it gets. Listeners you added with `hub.discord.subscribe()` are removed for you. Undo anything else you changed on Discord there, like `setActivity` or `setOrientationLockState`, so it doesn't carry into the next game.
- **Pause when the game loses the keyboard.** Clicking Discord's chat or another window takes the keyboard away from your game. Pause real-time games when the window loses focus and when the page is hidden. The included games do this (`activityhub/web/arcade.js`, `listen()`):

  ```js
  window.addEventListener("blur", pause);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      pause();
    }
  });
  ```

## 18. Checklist before you share your game

**Sharing your game.** Your users need ActivityHub too, and Red doesn't install required cogs by itself. Say how to get it in `info.json`'s `install_msg`, like the quick start does, and in your README: `[p]repo add vrt-cogs https://github.com/vertyco/vrt-cogs`, then `[p]cog install vrt-cogs activityhub` and `[p]load activityhub`. ActivityHub is hidden from `[p]cog list` while it's in beta, but `[p]cog install` still finds it. A field added in a later ActivityHub is refused by older ones, so say which version your game needs (`[p]help ActivityHub` shows it, and so does `bot.get_cog("ActivityHub").__version__`).

- [ ] `[p]activityhub games` lists your game, with no "Refused" line.
- [ ] The key is final.
- [ ] The page works in the browser preview, and shows a sensible message when `hub.offline` is `true`.
- [ ] The page works inside Discord, in a server and (if you support it) in a DM.
- [ ] Every action checks what the page sent, and never trusts a score or amount from it.
- [ ] Payouts use `ctx.author` and have limits.
- [ ] Your actions return `{"error": "..."}` with friendly text for every expected problem.
- [ ] The page has a way back to the menu (`backToMenu()`).
- [ ] Every file the page needs is inside `web_dir`, loaded with a relative path.
- [ ] Nothing secret is in `web_dir`.
- [ ] `web_dir` holds only page files: not your cog's `.py` files, `.env` or `node_modules`.
- [ ] Your page works on a phone-sized screen and with touch, since Activities run on Discord's phone apps too.
- [ ] If you use a live connection: the page reconnects after a drop, and gives up after a few in a row.
- [ ] `info.json` has an `end_user_data_statement`, and your cog deletes a player's data when Red asks it to (`red_delete_data_for_user`).
- [ ] `info.json`'s `install_msg` (or your README) says how to get ActivityHub.

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

The included pages also import `activityhub/arcade.js`, the hub's shared title, pause, results and leaderboard frame. Any import starting with `"activityhub/"` reaches the hub's own files. `arcade.js` isn't part of the API yet and may change: copy what you need instead of importing it.

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
| **Session** | The player's login with the hub. The page carries a session pass with every request. It lasts up to 12 hours and ends when the bot restarts or ActivityHub reloads; `hub.api()`, `hub.fetch()` and `hub.socket()` then log the player in again by themselves. |
| **web_dir** | The folder holding your page: `index.html` and everything it loads. |
