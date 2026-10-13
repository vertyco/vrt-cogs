# ActivityHub reference

**The short version:** every field, attribute and call a game cog uses, in one place for looking things up. New to ActivityHub? Start with the quick start in [DEVELOPERS.md](DEVELOPERS.md#3-quick-start-click-counter), which builds a working game first.

**Contents**

1. [`activityhub_game()`](#1-activityhub_game): the fields that describe your game
2. [`ctx`](#2-ctx): who is playing and where
3. [Handlers](#3-handlers): your Python methods the hub calls, and `conn` and `room`
4. [The page side](#4-the-page-side): `connect()`, the `hub` object and a live connection's `conn`
5. [The hub cog from Python](#5-the-hub-cog-from-python): the one call your Python can rely on

## 1. `activityhub_game()`

This method tells the hub about your game. The hub reads it when your cog loads, and again on every `[p]reload`, and keeps what it got. If it reads settings (say, a name the bot owner can change), run `[p]reload yourcog` after changing them, or the menu keeps showing the old values. If ActivityHub itself loads after your cog, it checks every cog that is already loaded, so the load order doesn't matter.

```python
async def activityhub_game(self) -> dict:
    ...
```

It must be an `async def`. It may await things, like reading Config. It can run while the bot is still starting, before it connects to Discord, so servers and members may not be cached yet. If it waits for something slow (for example `bot.wait_until_red_ready()`), your game appears in the menu once it returns. If anything in the dict is wrong, the hub skips your game and `[p]activityhub games` says why.

These are the fields the dict can have. Any other field name is refused, so a typo can't slip through quietly. The refusal suggests the field you probably meant, or, for a game made for a newer ActivityHub, says to update ActivityHub.

| Field | Type | Required | What it does |
|---|---|---|---|
| `key` | `str` | yes | Your game's id: 2 to 32 characters of `a-z`, `0-9` and `-`. Your game lives at the address `/games/<key>/`. **Pick it once:** server switches and players' menu order remember games by key, so a new key counts as a new game, and servers that turned your game off would see it on again. `snake`, `2048` and `brickbreaker` belong to the included games, even when they are turned off, and keys starting with `hub-` are kept for ActivityHub's own games. Two cogs can't share a key: the first one registered keeps it, and the second is refused until the first unloads. It then gets the key by itself (so reloading the first cog hands the key to the second). |
| `name` | `str` | yes | The name shown in the menu. Can't be empty. |
| `web_dir` | `str` or `pathlib.Path` | yes | The folder holding `index.html` and every file your page uses. `Path(__file__).parent / "web"` is the usual way to write it. A relative path starts at the folder of the file that defines your cog class, and `~` means your home folder. It can't be your cog's own folder (or a folder above it), since everything in it would be public. `index.html` must be saved as UTF-8. |
| `description` | `str` | no | One line shown under the name. Defaults to `""`. |
| `icon` | `str` or `pathlib.Path` | no | A small square picture inside `web_dir`, shown next to the name. The Orb theme shows it inside a round pod, cut to a circle, so keep what matters in the middle. Write it relative to `web_dir`, for example `"icon.png"` (an absolute path inside `web_dir` works too). |
| `thumbnail` | `str` or `pathlib.Path` | no | A wide picture inside `web_dir` (16:9, for example 640x360), like box art or a screenshot, written like `icon`. The grid and list layouts show it in place of the icon, and the Orb theme shows it large on the panel for the selected game. Without one, the menu uses the icon. |
| `actions` | `dict[str, handler]` | no | Python methods the page calls with `hub.api(name, data)`. Names use letters, digits, `_`, `.` and `-`, 1 to 64 characters, and not only dots. See [handlers](#3-handlers). |
| `socket` | `dict[str, handler]` | no | Handlers for a live connection. The keys can only be `"join"`, `"message"` and `"leave"`. See [multiplayer](DEVELOPERS.md#6-multiplayer-with-live-connections). |
| `routes` | `dict[str, handler]` | no | Raw requests, keyed `"METHOD path"`, for example `"POST avatar"`. `METHOD` is one of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, in capitals. The path uses letters, digits, `_`, `.`, `-` and `/`, with no `.` or `..` parts. Paths match exactly, so there are no `{parameters}`, and each route can be listed once (leading and trailing `/` don't count). See [raw requests](DEVELOPERS.md#8-uploads-and-other-raw-requests). |
| `scopes` | `list[str]` | no | Extra Discord permissions to ask the player for at login, one scope name per string. See [permissions](DEVELOPERS.md#9-extra-discord-permissions). |
| `economy` | `None`, `str`, or `async def (ctx)` | no | How your game ties into the server's currency, shown as a badge with a coin on its menu card. `None` (or leaving it out) means no tie and no badge. A string is a fixed line, like `"Bet credits at the tables"`. An `async def` taking the player's `ctx` returns a line or `None`, so the badge can follow your settings (say, only while payouts are on), and can differ from one player to the next. It runs each time a player opens the menu in a server, so `ctx.guild` is never `None` there, and it must answer quickly. At most 40 characters, plain text. A fixed line needs ActivityHub 0.7.0 or later, and a function 0.8.0 or later. See [currency labels](DEVELOPERS.md#currency-labels-on-the-menu). |
| `requires` | `str` | no | The oldest ActivityHub your game works with, as two or three whole numbers, like `"0.8.0"` or `"0.8"`. A bot with an older hub refuses your game with a message saying to update ActivityHub. Hubs older than 0.8.0 don't know this field, so they refuse it as unknown, which also says to update. |
| `platforms` | `list[str]` | no | Where your game works: `"desktop"` (Discord's computer app, or discord.com in a browser), `"mobile"` (Discord's phone and tablet app), or both. Leaving it out means both. On the other platform the menu dims your card with a "Desktop only" or "Mobile only" note, and the hub shows a message instead of opening your game. Those two are all Discord tells the hub, so there's no iOS or Android. Needs ActivityHub 0.8.0 or later. |
| `room` | `str` or `async def (ctx)` | no | Who plays together on a live connection. `"window"` (the default): everyone in the same Activity window, for example the same voice channel. `"server"`: everyone in the same Discord server, whichever channel they opened the Activity in. A window outside a server (a DM call, or a server your bot isn't in) stays a room of its own. `"everywhere"`: everyone, in every server and DM. It sets `conn.room`, `conn.peers()`, `conn.broadcast()` and `ctx.room_id`. An `async def` taking the player's `ctx` returns one of the three for that player, so the choice can follow a server admin's setting or the player's own (a public mode next to a private one). The hub asks it on each new live connection and each action, and gives it 2 seconds: one that fails, is slow or answers something else puts the player in `"window"` and logs a warning. The hub's people lists and **Join** still cover only the player's own window. See [who plays together](DEVELOPERS.md#who-plays-together-room). Needs ActivityHub 0.10.0 or later: set `"requires": "0.10.0"` too, so an older hub says to update. |

Every handler (in `actions`, `socket` and `routes`) must be an `async def` that takes the arguments [the hub passes](#3-handlers). The hub checks both when your game registers, so a mistake shows up in `[p]activityhub games` right away, not when a player first presses a button. Put the method itself in the dict, `self.click`, not `self.click()`.

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

## 2. `ctx`

Every handler gets a `ctx` that says who is playing and where. The hub proved it with Discord: the player really logged in, and Discord itself said which server and channel the Activity runs in. The page can't change it.

| Attribute or method | Type | What it is |
|---|---|---|
| `ctx.author` | `discord.Member` or `discord.User` | The player. A `discord.Member` in a server. A `discord.User` anywhere else (a DM, or a server your bot isn't in). |
| `ctx.guild` | `discord.Guild` or `None` | The server the Activity was opened in. `None` in a DM, or in a server your bot isn't in. |
| `ctx.guild_id` | `int` or `None` | `ctx.guild.id`, or `None` outside a server. |
| `ctx.channel` | server channel, thread or `None` | The channel the Activity runs in, when it's in a server the bot can see. `None` otherwise. |
| `ctx.channel_id` | `int` or `None` | The channel's id, also in a DM. |
| `ctx.instance_id` | `str` | The id of this Activity window. Everyone in the same Activity window (for example, the same voice channel) has the same one. |
| `ctx.room_id` | `str` | The id of the room your game puts the player in, set by your game's `room` field. Everyone who plays your game together has the same one, so use it to group players into one game. In a `"window"` room it is `ctx.instance_id`. Needs ActivityHub 0.10.0 or later. |
| **`await`** `ctx.is_admin()` | `bool` | Whether the player is a server admin where the Activity runs: the bot owner, the server's owner, or a member with the Manage Server permission or Red's admin role. Checked fresh on each call. `False` outside a server. Anyone else who is no longer in the server (not in the bot's member cache) gets `False`. Needs ActivityHub 0.8.0 or later. |
| **`await`** `ctx.shows_name()` | `bool` | Whether the player turned on **Show my name to players from other servers** in the hub's Settings. Off until they do. Checked fresh on each call. In a room that mixes servers, show their Discord name and avatar to players from other servers only when this is `True`: see [players from other servers](DEVELOPERS.md#players-from-other-servers). Needs ActivityHub 0.10.0 or later. |
| **`await`** `ctx.is_mod()` | `bool` | Whether the player is a server mod there: everyone `ctx.is_admin()` counts, and members with Red's mod role. No Discord permission counts on its own. `False` outside a server, and for anyone else who is no longer in the server, like `is_admin()`. Needs ActivityHub 0.8.0 or later. |

`if ctx.guild is None` is the check for "not in a server". When it's false, `ctx.author` is a `discord.Member`, ready for the bank and for member Config.

`ctx` has only the attributes and methods above. It isn't Red's `commands.Context`: there is no `ctx.send`, `ctx.reply` or `ctx.message`, because the player is in an Activity, not typing a command. Use `self.bot` for the bot, and `ctx.channel.send(...)` to post in the channel when `ctx.channel` isn't `None`, with a cooldown (see [What to trust](DEVELOPERS.md#5-what-to-trust-and-paying-out)).

`ctx` can't be a dict key or a set member. Key per-player state by `ctx.author.id`, per-room state by `ctx.room_id`, and per-connection state by `conn`.

## 3. Handlers

A handler is one of your `async def` methods that the hub calls. There are three kinds: actions (the page asks, Python answers), live connection handlers (for multiplayer), and raw routes (for anything else, like uploads).

| Kind | Signature | Gets | Returns |
|---|---|---|---|
| Action | `async def name(self, ctx, data: dict) -> dict` | `data`: the object the page sent, or `{}`. | A dict the page receives. Return `{"error": "text"}` to make `hub.api()` throw with that text. Returning `None` sends `{}`. More below. |
| Socket `join` | `async def join(self, ctx, conn) -> None` | `conn`: this player's live connection. | Nothing. If it raises, the connection closes with code `1011`. |
| Socket `message` | `async def message(self, ctx, conn, data) -> None` | `data`: any JSON value the page sent (dict, list, str, number, bool or `None`). | Nothing. If it raises, the error is logged and the connection stays open. |
| Socket `leave` | `async def leave(self, ctx, conn) -> None` | `conn`: the connection that just closed. It is already out of its room, so `conn.peers()` lists only the players still connected. When that is empty, this was the last connection in this room: clean up there. | Nothing. Not called when `join` raised. |
| Raw route | `async def name(self, ctx, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse` | `ctx`: `None` when the request carries no login. You decide what that means. `request`: the raw request from aiohttp (the web library the hub uses). | Any aiohttp response, for example `web.json_response(...)`. Needs ActivityHub 0.8.0 or later: older hubs call raw routes with `request` first and refuse this order. |

**What an action can return:**

- A dict. The page gets it as a JavaScript object.
- `{"error": "text"}` makes `hub.api()` throw with that text. The text can't be empty. `{"error": None}` counts as no error, and the dict reaches the page as it is.
- Only the error text reaches the page: other keys in an error reply are dropped. To let the page react to a kind of problem, return a normal dict like `{"ok": False, "reason": "no_funds", "need": 50}`.
- `activityhub` is kept for the hub as a top-level key. A reply with one fails like a crash: the page gets "Something went wrong." and the bot log says `Action <key>.<name> returned the reserved field 'activityhub'`. The name is fine deeper inside, like `{"data": {"activityhub": 1}}`.
- Numbers must be finite. NaN and Infinity aren't JSON, so a reply holding them fails like a crash.
- Send Discord ids as strings. JavaScript rounds whole numbers above 2\*\*53, so write `{"user_id": str(ctx.author.id)}`.

Rules the hub enforces for you:

- **Actions and socket handlers only run for a logged-in player**, and only while your game is on in that server.
- **Raw routes also run without a login.** `ctx` is then `None`.
- **Errors stay private.** If a handler raises, or an action returns something that isn't a dict (or can't be turned into JSON, or has a top-level `activityhub` key), the hub logs it in the bot's log and the page gets "Something went wrong.". Your error text never reaches players. Only `{"error": "..."}` text does. When you test as the bot owner, the page also shows you the reason (see [Testing](DEVELOPERS.md#12-testing-and-debugging)).
- **Size limit.** Actions refuse bodies of 1 MB or more (the page sees "Request failed (413)"), and a live message of 1 MB or more closes the connection with `1009`. In raw routes, the limit applies only to `request.read()`, `.json()`, `.text()` and `.post()`. `request.content` and `request.multipart()` aren't limited: check `ctx` first, count bytes as you read, and stop at your own limit, like the [streaming example](DEVELOPERS.md#8-uploads-and-other-raw-requests). That is also how to accept uploads bigger than 1 MB.
- **What turns into JSON.** Replies and live messages are turned into JSON with orjson, a fast JSON library that comes with Red. Besides dicts, lists, text, numbers, booleans and `None`, it takes dataclasses, datetimes (as ISO 8601 text, like `"2026-01-02T00:00:00+00:00"`), UUIDs and enums. Dict keys that are numbers become text, like `{"1": ...}`. NaN, Infinity and whole numbers bigger than 64 bits are refused.

**How your handlers run:**

- **Actions run at the same time,** even two from one player (a double click). Lock any read-modify-write, like Click Counter does.
- **One connection's messages reach `message` one at a time, in order.** Different players' messages run at the same time, so state they share needs a lock too.
- **`join` finishes before any message is handled.** Until it returns, the hub doesn't read that player's messages or notice that they left, so `join` must return quickly.
- **`leave` runs after the last message handler returns.**
- **Everything shares the bot's event loop.** Never block it: use `await asyncio.to_thread(...)` for heavy work, and start a task for anything slow instead of awaiting it in a handler.

**`conn`, a live connection,** as your Python sees it:

| Member | Type | What it does |
|---|---|---|
| **`await`** `conn.send(data)` | `data`: any JSON value | Queues a message to this player and returns right away, so a player with a bad network never holds up your code. One player's messages arrive in the order you sent them. Does nothing once the connection has closed, and never fails because a player dropped. A player who can't take a message for 10 seconds, or falls 4 million characters behind, is disconnected (`1001`). Raises `ValueError` for NaN, Infinity or an `activityhub` field (see [multiplayer](DEVELOPERS.md#6-multiplayer-with-live-connections)). |
| **`await`** `conn.broadcast(data, include_self=False)` | `data`: any JSON value | Queues a message to everyone connected to your game in the same room, and returns right away, like `send`. Pass `include_self=True` to send to this player too. Refuses the same values as `send`, even when no one else is connected. |
| `conn.peers()` | `list` of connections | The other connections to your game in the same room. |
| **`await`** `conn.close(code=1000)` | `code`: `int` | Closes the connection once the messages you queued before it have gone out. Use `1000`, or your own codes from `4100` to `4999`. Codes `4000` to `4099` are ActivityHub's, and `close` refuses them with a `ValueError`. |
| `conn.ctx` | `ctx` | The same `ctx` the handlers get. |
| `conn.room` | room | Everyone playing your game together (the same `ctx.room_id`): the same window, unless your game's `room` field says otherwise. One object their connections share. Keep it to reach them all from a timer, a loop or an action: see [multiplayer](DEVELOPERS.md#6-multiplayer-with-live-connections). |
| `conn.follow` | `int` or `None` | The user id of the person this player joined with **Join** in the hub's people lists, or `None`. Only on the first live connection after a Join, and only when that person is in the same window. Reconnects have `None`. See [Who's here](DEVELOPERS.md#7-whos-here). |

**`room`**, what `conn.room` gives you:

| Member | Type | What it does |
|---|---|---|
| **`await`** `room.broadcast(data)` | `data`: any JSON value | Queues a message to everyone in the room and returns right away, like `send`. The message is turned into JSON once for all of them. Refuses the same values as `send`. |
| `room.connections` | `list` of connections | Everyone in the room right now. A copy, so it's safe to loop over while players leave. Empty once everyone has left. |
| `room.id` | `str` | The room's id, the same as `ctx.room_id`. Needs ActivityHub 0.10.0 or later. |
| `room.instance_id` | `str` or `None` | The window's id, the same as `ctx.instance_id`, when the room is one window. `None` in a `"server"` or `"everywhere"` room, which holds many windows. |

**Type hints.** Don't import from `activityhub` in your cog. Red loads cogs by folder name, so the import fails whenever your cog loads before ActivityHub, and `isinstance` checks go stale after ActivityHub reloads. For your editor, copy [`devkit/hubtypes.py`](devkit/hubtypes.py) into your cog instead. It describes `ctx`, `conn` and `room`, so after `from .hubtypes import HubContext` you can write `async def click(self, ctx: HubContext, data: dict) -> dict:`.

## 4. The page side

Your page talks to the hub through a small helper script. Import it by the name `"activityhub"`, the only name your page can import from the hub:

```js
import { backToMenu, connect, HubError } from "activityhub";
```

These are the three things you use from it:

| Name | What it is |
|---|---|
| `connect()` | Returns a promise of the `hub` object below. Inside Discord it waits for the menu's login first. It rejects, with Discord's message, if Discord didn't accept the login: catch it and show `e.message` next to your Back button, like the quick start does. |
| `backToMenu()` | Closes your game and shows the menu. |
| `HubError` | The error type `hub.api()` and `hub.socket()` throw. `e.message` is readable text. `e.status` is `400` for your own `{"error"}` replies (the same as the hub's "Bad request."), the HTTP status for the hub's other errors (the number a web server answers with, like `401` or `413`), the close code for live connections, and `0` offline or when no answer came at all (a dropped network, or the bot is down), with the message "Couldn't reach the bot. Check your connection and try again." |

A red "400 (Bad Request)" line in the browser console is normal for `{"error"}` replies: that is how they travel.

The helper has a few other exports that the menu itself uses. They aren't part of the API and may change in any release.

**The `hub` object** is what `connect()` gives you:

| Member | Type | What it is |
|---|---|---|
| `hub.offline` | `boolean` | `true` outside Discord, for example in the browser preview. `hub.api()` and `hub.socket()` then throw "Open this activity from Discord to use this." |
| `hub.platform` | `"desktop"`, `"mobile"` or `null` | Where the player is: `"desktop"` (Discord's computer app, or discord.com in a browser) or `"mobile"` (Discord's phone and tablet app). `null` in the preview. Use it to adapt a game that runs everywhere, like showing touch buttons on phones. Needs ActivityHub 0.8.0 or later. |
| `hub.player` | object or `null` | `{ id, username, displayName, avatar, guildId, guildName, guildIcon }`, all strings. `displayName` is the name Discord shows for the player in that server; `username` is their account handle. The `guild` ones are `null` outside a server, and `guildIcon` is `null` for a server without an icon. `null` when offline. It's for showing, not for trusting. |
| `hub.api(name, data, options)` | `Promise<object>` | Calls your action `name` with `data` (an object, default `{}`). Resolves with what the action returned. If the player's login expired (a bot restart, an ActivityHub reload), it logs in again and retries once by itself. `options` is optional: `{ keepalive: true }` lets the request reach the bot even after your page is gone, for saving on `pagehide` (the browser's event for a page going away) when Join or closing the Activity removes your game's frame. Once the page is gone, the log-in-again retry can't run. A keepalive request can carry at most 64 KB of data: the browser refuses a bigger one. |
| `hub.fetch(path, options)` | `Promise<Response>` | Calls a raw route, like the browser's own `fetch`, with the player's login attached. `path` is the route path, for example `"avatar"` or `"item?id=7"`. When the hub says the login expired, it logs in again and sends the request once more (a streamed body can't be sent twice, so that one gets the 401). Works offline too, without a login. |
| `hub.socket()` | `Promise<conn>` | Opens your game's live connection. Resolves once the hub has checked the login. If the login expired, it logs in again and retries once by itself. Once open, it reconnects by itself after a drop (see `conn.onReconnecting`). |
| `hub.discord` | Discord toolkit or `null` | The menu's Discord Embedded App SDK object (the toolkit Discord gives Activity pages), for calls like `hub.discord.commands.openExternalLink(...)`. Listeners you add with `hub.discord.subscribe()` are removed for you when your game closes. Its participant list is everyone in the Activity, not your players: see [multiplayer](DEVELOPERS.md#6-multiplayer-with-live-connections). `null` outside Discord. |
| `hub.stat(text)` | function | Adds a short text at the end of the hub's frame rate counter in the corner, like the `30 TPS` in `60 FPS · 85 ms · 30 TPS`, for a number like your update rate (see [measuring](DEVELOPERS.md#speed-and-fast-paced-games)). The `85 ms` is the hub's own: the delay of your live connection, shown while one is open. Up to 40 characters; longer text is cut. `hub.stat("")` removes it, and so does closing your game. Players who hid the counter (the menu's **Frame rate** setting) don't see it. Works in the preview too. |
| `hub.status(text, data)` | function | Sets the player's status line (up to 60 characters), shown to everyone in the window, and optional data (any JSON value up to 1,024 characters) for your own pages. Each call sets both. Does nothing in the preview. See [Who's here](DEVELOPERS.md#7-whos-here). |
| `hub.busy(on)` | function | `hub.busy(true)` while the player is mid-round, so Join asks before taking them away. `false` when the round ends. |
| `hub.people` | array | Everyone in the window right now, the player included. A new array on each read. Empty in the preview. |
| `hub.onPeople(fn)` | function | Calls `fn(people)` each time a new list arrives (not straight away), and returns a function that stops it. Your listeners are removed when your game closes. |
| `hub.follow` | object or `null` | `{ id, name }` of the person whose Join opened your game, or `null`. |
| `hub.peopleButton()` | function | Returns the people button, for you to place in your layout. The floating one then goes away. |
| `hub.openPeople()` | function | Opens the people panel. |
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
| `conn.send(data)` | Sends any JSON value to your `message` handler, and returns `true`. Returns `false` without sending while the helper reconnects or after the connection closed, since an old input would be stale by the time it arrived. Throws a `TypeError` for something JSON can't hold, like `undefined` or a function. |
| `conn.on(handler)` | Calls `handler(data)` for every message from your Python code. Messages that arrived before you called `on` are handed to the first handler, so none are lost. |
| `conn.onClose(handler)` | Calls `handler(code)` when the connection has closed for good: on purpose, for a reason reconnecting can't fix, or after a minute of failed tries to reconnect. The [close codes](DEVELOPERS.md#6-multiplayer-with-live-connections) say why. |
| `conn.onReconnecting(handler)` | Calls `handler(code)` when the connection dropped and the helper starts reconnecting by itself: after `1001` (a restart, or a player who fell behind), `1006` (a dropped network), or `1012` to `1014` (a proxy restarting). It waits longer after each failed try, up to 15 seconds, with a random part so a whole window doesn't reconnect at the same instant, and gives up after a minute. |
| `conn.onReconnected(handler)` | Calls `handler()` once the helper has reconnected. Your `join` ran again for the new connection, so it can send the full state. The same `conn` keeps working, with the same handlers. |
| `conn.latency` | The latest round trip to the bot and back, in whole milliseconds, or `null` before the first one and while reconnecting. The helper times one every 2 seconds, and the hub's frame rate counter shows it too, like `60 FPS · 85 ms`. |
| `conn.close()` | Closes it, with code `1000`. |

**Type hints for your editor.** The page imports `"activityhub"` by a name the hub sets up when it serves your page, so your editor can't find the helper on its own and has nothing to autocomplete. Copy [`devkit/activityhub.d.ts`](devkit/activityhub.d.ts) next to your `game.js`, and put this line at the top of `game.js`:

```js
/// <reference path="activityhub.d.ts" />
```

Editors like VS Code then autocomplete `hub.` and flag typos, in plain JavaScript, with no build step. The file is only read by your editor, never by the browser, so it's harmless in `web_dir`.

## 5. The hub cog from Python

`bot.get_cog("ActivityHub").launch(...)` is the one Python method of the hub cog your code can rely on. It opens the Activity with your game for whoever pressed a button or ran a command: see [Opening your game from a command or button](DEVELOPERS.md#10-opening-your-game-from-a-command-or-button).

Every other attribute and method of the hub cog may change in any release, without notice. Your game talks to the hub through `activityhub_game()` and the handlers it lists.
