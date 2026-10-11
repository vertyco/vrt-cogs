# Activities for dummies: making a game for ActivityHub

**The bottom line:** you can put your own game inside Discord by writing a normal Red cog with one extra method and a folder of web files. ActivityHub does all the hard parts for you.

The hard parts ActivityHub does:

- It puts your game in its menu.
- It runs the web server that sends your game to players.
- It logs players in with Discord, so you always know who is playing.
- It opens your game when a player picks it.

What you write:

- **A web page** (HTML, CSS and JavaScript) that draws your game.
- **A few Python methods** for anything that must be trusted, like saving a score or paying credits.

## Start here

### Who this guide is for

You know how to write a basic Red cog, and a little HTML and JavaScript. That's all you need.

You don't need to know anything about Discord Activities, web servers or Discord logins. This guide explains each one when it comes up. (Never made a cog? Red's own guide, [Creating cogs for Red](https://docs.discord.red/en/stable/guide_cog_creation.html), comes first.)

### How to read this guide

1. **Read [Before you start](#2-before-you-start), then do the [Quick start](#3-quick-start-click-counter).** The quick start builds a small, complete game one step at a time. After every step it says what you should see, and what to check when you don't.
2. **Then read only what your game needs.** The table below says where to go.
3. **When something breaks, go to [Common problems](#13-common-problems).** Most messages you will ever see are listed there, word for word, each with its fix.
4. **To look up one field or call, use [REFERENCE.md](REFERENCE.md).** It lists every option in one place.

### Find what you need

| I want to... | Go to |
|---|---|
| Build my first game | [3. Quick start](#3-quick-start-click-counter) |
| Understand what happens when my page calls my Python | [4. How one click travels](#4-how-one-click-travels) |
| Pay players credits without getting cheated | [5. What to trust, and paying out](#5-what-to-trust-and-paying-out) |
| Let players play together, live | [6. Multiplayer](#6-multiplayer-with-live-connections) |
| Make a fast action game | [Speed and fast-paced games](#speed-and-fast-paced-games) |
| Show who is playing what | [7. Who's here](#7-whos-here) |
| Let players upload files | [8. Uploads](#8-uploads-and-other-raw-requests) |
| Use extra Discord features, like the player's Discord status | [9. Extra Discord permissions](#9-extra-discord-permissions) |
| Open my game from my own command or button | [10. Opening your game from a command or button](#10-opening-your-game-from-a-command-or-button) |
| Use a bundler (Vite, esbuild) or a game engine (Godot, Unity) | [11. Files and caching](#11-files-and-caching) and [14. Discord's limits](#14-discords-limits) |
| Test my Python without Discord | [Testing your Python without Discord](#testing-your-python-without-discord) |
| Fix an error message | [13. Common problems](#13-common-problems) |
| Share my game with other bots | [15. Checklist before you share your game](#15-checklist-before-you-share-your-game) |
| Read the code of a real, finished game | [16. Bigger examples](#16-bigger-examples-the-included-games) |
| Look up one field or call | [REFERENCE.md](REFERENCE.md) |

### Words you'll see

- **Activity**: a game window that opens inside Discord, usually in a voice channel. Discord lets a bot have only one. ActivityHub turns that one Activity into a menu of games.
- **The hub**: ActivityHub, the cog that holds the menu and runs your game.
- **Red**: Red-DiscordBot, the bot framework this cog runs on. A **cog** is one Red plugin.
- **`[p]`**: your bot's command prefix, like `!`. `[p]load activityhub` means typing `!load activityhub` on a bot whose prefix is `!`.
- **Page**: the web page of your game (your `index.html` and the files it loads), running in the player's Discord window.
- **Window**: everyone who opened the Activity from the same voice channel. They can see each other and play together.
- **Preview**: the hub's menu opened in a normal web browser, outside Discord. Good for working on how your game looks. Calls to your Python actions don't work there.

There is a full [glossary](#17-glossary) at the end.

### Ten rules that save you hours

Most problems people hit come from breaking one of these.

1. **Every method the hub calls is an `async def`,** `activityhub_game()` included.
2. **List your methods without brackets:** `"actions": {"click": self.click}`, never `self.click()`.
3. **Always `await` the helper:** `const hub = await connect();`, never `const hub = connect();`.
4. **Open your page through the hub's address, never as a file.** Double-clicking `index.html` gives you a blank page.
5. **Never start a path in your page with `/`.** Write `game.js` and `art/ship.png`, not `/game.js`.
6. **Never trust what the page sends.** Players can change your page in their browser. Work out scores and payouts in Python.
7. **Everything in your web folder is public.** Anyone can download it. Keep secrets and payout rules in Python.
8. **Leave your game with `backToMenu()`,** never with a link.
9. **Use `hub.discord` for Discord's features.** Never create your own `DiscordSDK`: inside the hub it never finishes starting.
10. **After a change, reload the right thing.** Changed Python: run `[p]reload yourcog`. Changed web files: close your game and open it again.

**Contents**

Part 1, your first game:

1. [What you are building](#1-what-you-are-building), and [how it compares with making your own Activity](#compared-with-making-your-own-activity)
2. [Before you start](#2-before-you-start)
3. [Quick start: Click Counter](#3-quick-start-click-counter)
4. [How one click travels](#4-how-one-click-travels)

Part 2, making it a real game:

5. [What to trust, and paying out](#5-what-to-trust-and-paying-out)
6. [Multiplayer with live connections](#6-multiplayer-with-live-connections), and [speed and fast-paced games](#speed-and-fast-paced-games)
7. [Who's here](#7-whos-here)

Part 3, extras you only need sometimes:

8. [Uploads and other raw requests](#8-uploads-and-other-raw-requests)
9. [Extra Discord permissions](#9-extra-discord-permissions)
10. [Opening your game from a command or button](#10-opening-your-game-from-a-command-or-button)
11. [Files and caching](#11-files-and-caching)

Part 4, when things go wrong:

12. [Testing and debugging](#12-testing-and-debugging)
13. [Common problems](#13-common-problems)
14. [Discord's limits](#14-discords-limits)

Part 5, finishing up:

15. [Checklist before you share your game](#15-checklist-before-you-share-your-game)
16. [Bigger examples: the included games](#16-bigger-examples-the-included-games)
17. [Glossary](#17-glossary)

The reference, in [REFERENCE.md](REFERENCE.md):

1. [`activityhub_game()`](REFERENCE.md#1-activityhub_game): the fields that describe your game
2. [`ctx`](REFERENCE.md#2-ctx): who is playing and where
3. [Handlers](REFERENCE.md#3-handlers): your Python methods the hub calls, and `conn` and `room`
4. [The page side](REFERENCE.md#4-the-page-side): `connect()`, the `hub` object and a live connection's `conn`

## 1. What you are building

Your game has two halves:

- **The page.** HTML, CSS and JavaScript in a folder. It draws the game and reacts to the player.
- **The Python.** Methods on your cog. The page calls them by name to do anything that must be trusted: save a score, pay credits, read Config (Red's settings storage).

ActivityHub sits between the two. It sends your page to the player and logs the player in. Then it passes each call from the page to your Python, with a `ctx` that says who the player is and where.

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

The hub finds your game by itself when your cog loads, and drops it when your cog unloads.

### Compared with making your own Activity

> **Skip this part if you have never made a Discord Activity.** It is for people coming from Discord's own Activity guides, who want to know which of those steps still apply.

**In short:** a game cog is a web page plus a few Python methods. Everything that makes it an Activity (the Discord setup, the web server, the login, launching) is the hub's job. The hub does it once, for every game on the bot.

Most steps in Discord's own Activity guides don't apply here. This table shows who does each job:

| Job | Your own Activity | A game cog in ActivityHub |
| --- | --- | --- |
| Discord setup | You create an application in the Developer Portal (Discord's site for bot settings), turn on Activities, and set its URL mapping and client secret. | The bot owner does this once for the hub (see [README.md](README.md)). Your cog needs no setup. |
| How many games | One per application. A second game needs a second bot, or a menu you build yourself. | As many as you like, from any number of cogs. Each one is a tab in the hub's menu. |
| Web server | You run one, reachable at a secure `https://` address, and serve your files from it. | The hub serves your `web_dir`. You never start a server. |
| Discord toolkit | Your page creates `DiscordSDK` and waits for `ready()`. | The menu already did. Your page calls `connect()` and uses `hub.discord`. Your own `DiscordSDK` would never finish its `ready()` inside the hub. |
| Login | Your page asks Discord for a login code, your server trades it for an access token using the client secret, then checks which server and window the player is in. | Done before your game opens. `hub.player` says who is playing, and your Python gets a checked `ctx`. Neither side ever sees the access token. |
| Your server's endpoints | You write each request handler, and check the login on every one. | You write `async def` methods and list them in `activityhub_game()`. The hub checks the login, and that your game is on in this server, before calling them. |
| Multiplayer | You run your own WebSocket server and group players by window yourself. | List `socket` handlers. The hub groups connections by `ctx.instance_id` and gives you `conn.broadcast()` and `conn.peers()`. |
| Discord permissions | You choose the scopes in your own login. | List them in `scopes`. They join the one login every game shares. |
| Opening it | The Entry Point command (the Play button in Discord's App Launcher) or a launch reply to a command. | The Entry Point command opens the hub's menu, and players pick your game there. `hub.launch()` opens your game straight from your own button or slash command. |
| Turning it off | Up to you. | Server admins can turn your game off in their server, and the bot owner in every server, from the menu's settings. The hub enforces it. |
| Phone layout | Your page reads Discord's safe area sizes (the room Discord's own buttons take) from CSS. | The same, under the same names: the hub copies them into your frame. |

What stays the same:

- **It is still a web page in Discord's Activity window,** with the same limits: outside websites are blocked and service workers can't register. It runs on Discord's phone apps as well as desktop. See [Discord's limits](#14-discords-limits).
- **Discord's toolkit commands still work** through `hub.discord`, like `openExternalLink` or `setActivity`.

What you give up:

- **Your page shares the window.** It runs in a frame inside the menu. Leave with `backToMenu()`, never navigate the top page, and undo your changes to Discord when the game closes.
- **Your game uses the bot's identity.** It shows in Discord as the bot's Activity, with the bot's name and art. URL mappings are the bot owner's to set.
- **No direct Discord token.** If you need the player's token for your own calls to Discord's API, a game cog can't get it.

## 2. Before you start

You need:

- **A Red bot with ActivityHub loaded.** Run `[p]load activityhub`.
- **Nothing else to begin with.** You can build most of a game in a normal web browser, without Discord.

> **Bot owner commands.** `[p]activityhub games`, `view`, `check` and `webserver` are for the bot owner (the person who runs the bot). On your own test bot, that's you.

There are two places to try your game.

**1. The browser preview (fastest).** The hub's web server shows its menu to any web browser. By default it is at **`http://127.0.0.1:8742/`** on the computer the bot runs on. If the bot runs on a different computer, open your public address instead, for example `https://games.example.com/`.

In the preview:

- The menu shows every game, with a "Preview" notice at the top.
- Your game opens inside the menu, like it would in Discord.
- `hub.offline` is `true`, so calls to your Python throw an error instead of running. That is how your page can tell it is in the preview.

The address doesn't open? `[p]activityhub view` shows where the web server listens and whether it is running. `[p]activityhub webserver <host> <port>` changes the address.

**2. Inside Discord (the real thing).** The bot owner must finish the one-time setup in [README.md](README.md) first: turn on Activities, give the bot its client secret, and give the web server a public `https://` address. Not sure it is done? `[p]activityhub check` goes through every setup step and says which one is missing. For a test bot, a free Cloudflare tunnel (a small program that gives a computer at home a public web address) is enough: see [Getting a public HTTPS address](README.md#getting-a-public-https-address). You only need Discord for the last steps of the quick start.

## 3. Quick start: Click Counter

**What you'll have at the end:** a game called Click Counter in the hub's menu. Each click pays the player one credit, up to 100 clicks a day.

It is small, but it has every basic piece:

- the description that tells the hub about your game,
- an action (a Python method the page calls),
- the page,
- and a friendly error message.

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

`info.json` describes the cog for Red's cog installer. You only need it when you share the cog, but it costs nothing to add now. `install_msg` is shown after someone installs your cog. It is the place to say your game needs ActivityHub:

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

`clickcounter.py` is the cog itself:

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

What this code does:

- **`activityhub_game()` tells the hub about your game.** The hub calls it by itself when your cog loads.
  - `key` is your game's short id. Pick it once and keep it.
  - `name` and `description` show in the menu.
  - `web_dir` is the folder that holds your page.
  - `actions` lists what the page is allowed to call. Here, the page's `hub.api("click")` runs `self.click`.
- **`click()` runs each time the page calls `hub.api("click")`.**
  - `ctx` says who clicked and in which server. The hub checked it with Discord, so you can trust it.
  - `ctx` is not the `ctx` of a Red command. It has no `ctx.send()`, because the player isn't typing a command. It has `ctx.author`, `ctx.guild`, `ctx.channel` and `ctx.instance_id` (the full list is in [REFERENCE.md](REFERENCE.md#2-ctx)). Use `self.bot` for the bot.
  - `data` is whatever the page sent. Here it is `{}`, because the page sends nothing.
  - Returning a dict sends it to the page.
  - Returning `{"error": "some text"}` shows that text to the player instead.
- **`self.config` is Red's Config,** where cogs save data. It keeps each player's click count for today.
- **`bank.deposit_credits()` adds credits** to the player's balance in Red's bank (Red's built-in currency).
- **The lock makes fast clicks wait their turn,** so two clicks can't both read the same count and pay twice.
- **`red_delete_data_for_user()` is how Red asks a cog to delete a player's data.**

`web/index.html` is the page. Notice it has no `<base>` tag and no address for `"activityhub"`: the hub adds both when it sends the page.

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

`web/game.js` is the page's code:

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

What this code does:

- **`connect()` waits until the hub has logged the player in,** then gives you the `hub` object. Everything your page does with the hub goes through that object.
- **`hub.api("click")` runs your Python `click()` method** and gives back the dict it returned.
- **When your Python returns `{"error": "..."}`, `hub.api()` throws.** The `catch` then shows your text, as `e.message`.
- **`backToMenu()` closes your game** and shows the menu again.

`"activityhub"` in the `import` line is not a file in your folder. When the hub sends your page, it tells the browser where its helper script is. That is also why the page only works when the hub sends it (see [Common problems](#13-common-problems)).

### Step 2: load the cog

1. Tell Red where your cog lives: `[p]addpath <the folder that holds clickcounter>`. Give the folder **above** `clickcounter`, not `clickcounter` itself.
2. Load it: `[p]load clickcounter`.
3. Check the hub saw it: `[p]activityhub games`.

You should now see `clickcounter: Click Counter (ClickCounter)` in the list.

If you don't:

- **It is under "Refused:".** The line says what is wrong. [Your game isn't in the menu](#your-game-isnt-in-the-menu) has the fix for each message.
- **It isn't in the list at all.** Check that `[p]load clickcounter` said it loaded, and that the method is spelled exactly `activityhub_game`.

### Step 3: try it in a browser

1. On the bot's computer, open `http://127.0.0.1:8742/` (or your public address).
2. Click the **Click Counter** card.
3. Press **Click me**, then **Back to the menu**.

You should now see:

- the menu, with a "Preview" notice at the top,
- then your page, saying "Open this from Discord to earn credits.",
- then, after **Click me**, "Open this activity from Discord to use this.". That is correct: the preview has no logged-in player, so it doesn't run your actions.
- **Back to the menu** takes you back.

If you don't:

- **The address doesn't open.** Run `[p]activityhub view`. It shows where the web server listens and whether it is running.
- **Your page is blank.** Press F12 to open the browser's developer tools, and read the Console tab. [Your page doesn't work](#your-page-doesnt-work) lists the usual messages.

### Step 4: try it in Discord

This step needs the bot owner's one-time setup (see [Before you start](#2-before-you-start)).

1. In a server, run `/activities` (or `[p]activities` and press the button).
2. Pick **Click Counter**.
3. Press **Click me** a few times.

You should now see "Hi" and your name in that server, then "Clicks today: 1. Balance: ..." going up by one per click. Your bank balance in that server goes up too.

If you don't:

- **There is no `/activities` command.** The bot owner hasn't added it yet: `[p]slash enable activities`, then `[p]slash sync`. Until then, `[p]activities` works.
- **The Activity doesn't open, or shows an error.** `[p]activityhub check` says which setup step is missing.
- **Click Counter isn't in the menu.** An admin may have turned it off in this server: see the last rows of [Your game isn't in the menu](#your-game-isnt-in-the-menu).

### Step 5: change something

- **A web file** (HTML, CSS, JavaScript, images): save it, then close your game and open it again. No reload needed.
- **Python**: run `[p]reload clickcounter`.

You should now see your change. That's the whole loop: change, reopen or reload, look.

### Step 6: show what you're doing

This step shows your friends what you're doing in your game. It needs two Discord accounts in the same voice channel, both in that voice channel's Activity. Accounts in different channels don't see each other.

Keep both accounts' windows on screen side by side, for example two browser windows. An account whose window is in the background shows as "Away" instead of what it is doing.

1. In `game.js`, add one line to the click handler, right after the line that shows `Clicks today`:

   ```js
   hub.status(`Clicked ${result.clicks} times today`);
   ```

2. On your first account, in the voice channel's Activity, close Click Counter and open it again so it picks up the change. Press **Click me** a few times.
3. On a second account, join the same voice channel, open the Activity there (see [two players](#12-testing-and-debugging)), and stay in the menu.

You should now see, on the second account, a **1** bubble on Click Counter's corner. Resting the mouse on its card shows your first account with "Clicked 3 times today" (or however many). In the Orb theme, the default, select Click Counter instead: its big screen lists the same line under **Playing now**. [Who's here](#7-whos-here) covers the rest.

**You've made a game.** Next, read [How one click travels](#4-how-one-click-travels) to see what just happened, or pick a topic from [Find what you need](#find-what-you-need).

## 4. How one click travels

This is what happens between `hub.api("click")` in the page and `click()` in Python. You never write any of it. Knowing it makes errors easier to read.

1. **The page sends a request.** `hub.api("click", data)` sends `data` (an object, `{}` when left out) to `/games/clickcounter/api/click` as JSON (the text format browsers and Python both use for data). The player's session pass (proof they logged in) rides along with it.
2. **The hub finds the player.** The session pass maps to a `ctx` the hub proved with Discord when the player logged in. If the pass is missing or expired (after a bot restart, an ActivityHub reload, or 12 hours), the hub answers "Your session expired. Go back to the menu to log in again." without running anything. `hub.api()` then logs the player in again through the menu and sends the request once more, so the game keeps running. Only if that fails is the player taken back to the menu.
3. **The hub checks your game is on.** If the bot owner turned it off, or a server admin turned it off in this server, the page gets "This activity is turned off in this server."
4. **The hub checks the request.** The action name must be in your `actions`, and `data` must be an object.
5. **Your method runs.** The hub calls `await self.click(ctx, data)`.
6. **Your dict goes back.** `hub.api()` resolves with it. If it has an `"error"` text, `hub.api()` throws instead, and `e.message` is your error text.

**How the login works.** You never deal with it, but this is what happens:

1. When Discord opens the Activity, the hub's menu page asks Discord for a one-time login code.
2. The bot trades that code with Discord for the player's identity.
3. The bot asks Discord which server and channel the Activity runs in.
4. The bot gives the page a session pass.
5. Your page borrows that login through `connect()`.

## 5. What to trust, and paying out

**The rule:** `ctx` is real; everything the page sends is not. A player can change your page in their browser, or send any request by hand. So:

- **Never trust a score, a count or an amount from the page.** Check it against what is possible. For example, check a score against how long the game ran on the bot's clock.
- **Decide payouts in Python,** with limits (per game, per day).
- **Use `ctx.author` for the bank,** never an id the page sent.

**Paying per event.** Click Counter does this: each action checks a daily limit before it pays, under a lock.

**Paying at the end of a round.** The idea, in four steps:

1. When a round starts, the page calls a `start` action. Python writes down the time, on the bot's own clock.
2. When the round ends, the page calls `finish` with the score.
3. Python checks the score is possible in the time that passed. A 10-second round can't score a million.
4. Python pays, within a limit per round and a limit per day.

This is the Python side of a game called Space Race, in its own cog folder as `spacerace/spacerace.py`. Its `__init__.py` is Click Counter's, with `SpaceRace` and `.spacerace` in place of `ClickCounter` and `.clickcounter`. The page is your own game.

The three limits at the top are examples: pick numbers that fit your game. This example pays at once with fixed limits, to show the checks in a small space. A game you share works better the Neopets way (see [below](#paying-for-scores-neopets-style)): the player chooses when to cash in, and server admins set the limits.

```python
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from redbot.core import Config, bank, commands, errors

# Example limits: pick numbers that fit your own game
MAX_POINTS_PER_SECOND = 20  # the most points an honest player can score in one second
PAYOUT_LIMIT = 50  # the most credits one round can pay
DAILY_LIMIT = 200  # the most credits one player can earn in one day


class SpaceRace(commands.Cog):
    """Dodge the rocks, grab the stars"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891, force_registration=True)
        self.config.register_member(day="", paid=0)
        self.lock = asyncio.Lock()
        # When each round started, on the bot's clock: {(server id, player id): seconds}
        self.runs = {}

    async def activityhub_game(self) -> dict:
        return {
            "key": "space-race",
            "name": "Space Race",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"start": self.start, "finish": self.finish},
        }

    async def start(self, ctx, data: dict) -> dict:
        self.runs[(ctx.guild_id, ctx.author.id)] = time.monotonic()
        return {"started": True}

    async def finish(self, ctx, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": "This game only works in a server."}
        started = self.runs.pop((ctx.guild_id, ctx.author.id), None)
        points = data.get("points")
        # In Python True counts as an int, so the bool check stops a page sending true as a score
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
            # Every 10 points earn 1 credit, up to both limits
            payout = min(points // 10, PAYOUT_LIMIT, left)
            try:
                await bank.deposit_credits(ctx.author, payout)
            except errors.BalanceTooHigh:
                return {"error": "Your balance is already at this server's maximum."}
            await ledger.day.set(today)
            await ledger.paid.set(paid + payout)
        return {"paid": payout}

    async def red_delete_data_for_user(self, *, requester, user_id):
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
```

Your game's page calls `start` when a round begins and `finish` when it ends. `score` and `showMessage` stand for your game's own score and message box:

```js
// When a round begins
await hub.api("start");

// When it ends
const result = await hub.api("finish", { points: score });
showMessage(`You earned ${result.paid} credits!`);
```

**With a global bank** (one balance shared by every server, turned on with `[p]bankset toggleglobal`), member Config gives each player a fresh daily limit in every server. Count it per player instead: `self.config.register_user(day="", paid=0)` and `self.config.user(ctx.author)` in place of the member versions.

Runs are kept per server and player, so a round started in one server can't be finished in another. You can also refuse rounds too short to be real, for example a finish less than 5 seconds after its start.

**Limit how often.** A page can call an action, or send live messages, as fast as it likes. A daily limit on credits doesn't stop an action that posts in a channel from being called a thousand times. Put a cooldown on anything with side effects. discord.py's own cooldowns work with the hub's `ctx`.

This example is a `share` action that posts the player's best score in the channel, at most once every 30 seconds. It assumes your cog saves that score as `best` in member Config, and lists the action as `"share": self.share`:

```python
import discord
from redbot.core import commands

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

For a stronger check, see how the included games [replay the player's moves](#16-bigger-examples-the-included-games).

### Paying for scores, Neopets style

Your cog keeps its own payout settings and pays from its own code: the hub doesn't pay for you. For a game with a score, the way Neopets pays for its games works well. The included games and Marble Munch do it this way:

- **The player chooses.** After a round, the page shows what the score is worth and a **Cash in** button. Playing another round first gives that score up, so players spend their cash-ins on their best rounds.
- **Every cash-in is capped.** Each point pays a rate, up to a most-per-cash-in, and each player gets a few cash-ins a day. A faked score can't earn more than a strong honest round. Admins can balance their economy, because the most a game can pay a day is known.
- **Admins set the numbers.** The rate, the cap and the cash-ins a day are settings, with payouts off until an admin turns them on.

Marble Munch is a full example to copy:

- `common/payouts.py` holds the settings, the daily count and the bank deposit.
- `main.py` offers each player their last round, and lets it cash in only once.
- Its page has a settings dialog that only server admins see.
- With a global bank (one balance shared by every server), only the bot owner can change the settings, and each player's cash-ins are counted across servers.

## 6. Multiplayer with live connections

**In short:** a live connection lets players see each other's moves right away. Your Python gets three methods: `join` when a player connects, `message` when their page sends something, and `leave` when they go.

A live connection is a WebSocket: a connection that stays open, so both sides can send at any time. Use one when one player's action must reach other players right away: a shared board, a race, a card table.

A game where each player plays alone doesn't need one, even when friends play side by side. [Who's here](#7-whos-here) can show them each other's scores without it.

This example adds a shared counter to Click Counter. Everyone in the same Activity window (for example, the same voice channel) bumps it together.

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

What the three methods do:

- **`join(ctx, conn)` runs when a player's page connects.** `conn` is that player's connection. Here, `conn.send()` sends the newcomer the current total, and `conn.broadcast()` tells everyone else how many play now.
- **`message(ctx, conn, data)` runs each time a page sends something.** `data` is what it sent. Here, a bump adds one and tells everyone, the sender included (`include_self=True`).
- **`leave(ctx, conn)` runs when a connection closes** (only for a connection whose `join` didn't raise). `conn.peers()` then lists who is still connected. Here, the last player out clears the total.
- **`ctx.instance_id` is the window's id.** Everyone in the same window has the same one, so the game keeps one total per window.

In the page, add `<p id="together"></p><button id="bump" type="button">Bump the shared counter</button>` to `index.html`, and this to the end of `game.js`:

```js
const together = document.getElementById("together");
const bump = document.getElementById("bump");
let shared = { total: 0, players: 1 };

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

function closed(code) {
  together.textContent = CLOSED_BECAUSE[code] || "The shared game ended.";
}

async function goLive() {
  try {
    const conn = await hub.socket();
    conn.on((data) => {
      shared = { ...shared, ...data };
      showShared();
    });
    // After a restart or a dropped network the helper reconnects by itself, and join sends the total again
    conn.onReconnecting(() => {
      together.textContent = "Reconnecting...";
    });
    conn.onClose(closed);
    bump.onclick = () => conn.send({ bump: true });
  } catch (e) {
    closed(e.status);
  }
}

if (!hub.offline) {
  goLive();
}
```

What the page does:

- `hub.socket()` opens the live connection. Your Python's `join` runs for it.
- `conn.on()` gets every message your Python sends.
- `conn.send()` sends to your Python's `message`.
- `conn.onReconnecting()` and `conn.onClose()` say when the connection dropped (the next part explains them).

Run `[p]reload clickcounter`, then open Click Counter inside Discord. (In the browser preview the live connection never starts, so the new line stays empty.)

You should now see "Together: 0 (1 playing)". Open the Activity on a second account in the same voice channel and pick Click Counter there too: both pages show "2 playing", and a bump on one shows on both.

Friends who open the Activity land in the menu, not in your game: each of them picks it there. A [Play button](#10-opening-your-game-from-a-command-or-button) opens your game straight away for each player who presses it.

### When a connection closes

**Close codes** are numbers that tell you why a connection closed. The page gets them in `conn.onClose`, or as `e.status` when `hub.socket()` fails:

| Code | Why | Reconnect? |
|---|---|---|
| `1000` | Closed on purpose: your Python's `conn.close()` or the page's `conn.close()`. | No. |
| `1001` | Your cog or ActivityHub was unloaded or reloaded, the bot is stopping, or the player stopped answering or fell behind (see below). | The helper does it by itself. |
| `1006` | The connection dropped without a goodbye: the network, a proxy that blocks WebSockets, or your game isn't loaded. | The helper does it by itself, for up to a minute. |
| `1009` | A message of 1 MB or more. The hub closes the whole connection, and `leave` still runs. | Not until you send less. |
| `1011` | Your `join` handler raised. | No. |
| `4001` | The login expired while connecting, and logging in again failed. The hub takes the player back to the menu by itself. | No. |
| `4003` | Your game was turned off in this server, or by the bot owner for every server. | No. |
| `4004` | Your `activityhub_game()` has no `"socket"`. | No. |
| `4029` | The page sent more than the message limit allows (see below). The bot's log names the player. | No. |
| `4100`-`4999` | Your own codes, from `conn.close(code)` in your Python. | Your call. |

Codes `4000` to `4099` are ActivityHub's, and `conn.close()` refuses them. Send a message saying why before you close, because the close code is all the page gets.

- **Drops happen**: a proxy restart, a phone going to sleep, a reload of your cog. The helper reconnects by itself, and your `join` runs again for the new connection. Show that it's reconnecting from `conn.onReconnecting`, like the example does. `conn.onClose` only runs once the connection is gone for good.
- **Heartbeat** (a check that the player is still there): when a connection has been quiet for 30 seconds, the hub pings it and sends a small message. That also stops proxies closing the quiet connection. The helper script answers by itself, and neither side passes these messages to your code. A player whose page doesn't answer within another 30 seconds is disconnected, and your `leave` runs. Until then, `peers()` can still include a player whose network vanished.
- **Slow players:** each player's messages wait in their own queue, so one stalled phone never holds up your code or the other players. A player who can't take a message for 10 seconds, or falls 4 million characters behind, is disconnected with `1001`.
- **Message limit:** a page may send up to 300 messages and 1 MB a second, on average over 5 seconds, so a short burst is fine. That is far more than a game needs, even one that sends an input every frame on a 240 Hz screen. Only a page someone changed to flood the bot goes over it. It is disconnected with `4029`, without reconnecting, and the bot's log names the player.

### Rules for your handlers

- **Your game needs `"socket"` in its description,** or `hub.socket()` fails with `4004`.
- **Reserved field:** don't send objects with an `activityhub` field from Python. The hub uses that field for its own messages, and `conn.send()` and `conn.broadcast()` refuse it with a `ValueError`.
- **Who is in your game:** use `conn.peers()` in Python. Discord's own participant list (`hub.discord.commands.getInstanceConnectedParticipants()`, the `ACTIVITY_INSTANCE_PARTICIPANTS_UPDATE` event) lists everyone in the Activity, including players in the menu or in other games. To show everyone in the window and where they are, use `hub.people` (see [Who's here](#7-whos-here)).
- **Waiting for an opponent:** remember `conn` and return from `join`. Start the match from the second player's `join`.
- **Other players' broadcasts already reach a connection while its `join` runs.** Read your state and send the snapshot with no other `await` in between. Or guard the state with an `asyncio.Lock` that `message` also takes.
- **Refusing a player** (the room is full, they were kicked): `await conn.send({"error": "This table is full."})`, then `await conn.close(4100)`. `leave` still runs for that connection, so only undo what `join` did.
- **Key per-player state by `conn`,** or check `self.players.get(ctx.author.id) is conn` before deleting it in `leave`. A player who reconnects can have a new `conn` before the old one's `leave` runs.
- **When your cog unloads or reloads,** `leave` still runs for every connected player, after your `cog_unload`, on the old cog object. Keep what `leave` needs alive until then.

### Rooms: reaching everyone at once

To reach everyone from an action, a timer or a command, keep the window's room. `conn.room` is one object shared by everyone playing your game in that window:

- `await room.broadcast(data)` sends to all of them.
- `room.connections` lists them.

For example, with `self.rooms = {}` in `__init__`:

```python
async def join(self, ctx, conn):
    self.rooms[ctx.instance_id] = conn.room


async def leave(self, ctx, conn):
    if not conn.peers():
        self.rooms.pop(ctx.instance_id, None)


async def poke(self, ctx, data: dict) -> dict:
    room = self.rooms.get(ctx.instance_id)
    if room:
        await room.broadcast({"poked_by": ctx.author.display_name})
    return {}
```

A room stays the same object while anyone is in it. When everyone leaves and someone comes back, they get the same room again as long as your code still holds it. So a loop holding the room reaches them.

### Speed and fast-paced games

> **Skip this unless your game is fast-paced:** things move on screen all the time and players react in a split second, like a racer or a shooter. Turn-based, card, party and casual games never notice any of it.

**In short:** a game in the hub is as quick as the same game on its own server. The page's live connection goes straight to the bot through Discord's proxy, like every Activity's does. The hub's own work on a message takes microseconds.

Two things set the limit:

- Your Python runs inside the bot, on one worker shared with everything else.
- Messages are JSON (text), which is bigger and slower than packed binary data.

A fast action game should be built with the tips below.

**Keep the bot's worker free.** Your handlers, every other cog and the bot's Discord connection share one worker, the asyncio event loop. While any code runs without reaching an `await`, every game on the bot waits.

- Slow calls that wait on something (the `requests` library, `time.sleep`, big file reads, `sqlite3`) block it. Use the async version, or `await asyncio.to_thread(function, ...)`.
- Heavy number crunching (pathfinding on a big map, an AI search) blocks it too. `to_thread` doesn't help there, because Python runs one thread at a time. Use a process pool: `await asyncio.get_running_loop().run_in_executor(self.pool, function, ...)`, with `self.pool = concurrent.futures.ProcessPoolExecutor()` made in `__init__` and shut down in `cog_unload`.
- The hub writes a warning in the bot's log when the bot froze for a quarter of a second or more while players were in live games: "The bot froze for ... ms while players were in live games". discord.py's "heartbeat blocked" warning means the same thing, for longer freezes.
- To find which code froze it, the bot owner can start the bot with `--dev` and run `[p]eval bot.loop.set_debug(True); bot.loop.slow_callback_duration = 0.05`. The log then names anything that ran for more than 50 milliseconds, in a line like `Executing <Task ... coro=<MyCog.message()>> took 0.300 seconds`. Turn it off afterwards with `[p]eval bot.loop.set_debug(False)`, since debug mode slows everything down a little.

**Run the game at a steady pace, and let the page smooth it.** Don't move things in Python 60 times a second. Instead:

- Update the game 10 to 30 times a second in Python.
- Let the page draw at full speed, sliding each thing smoothly from its last position to its newest one (this is called interpolation).
- Time each update from a fixed start, so small delays don't add up.

```python
import asyncio

TICK = 1 / 20  # 20 updates a second


async def run_room(self, room):
    loop = asyncio.get_running_loop()
    next_tick = loop.time()
    while room.connections:
        self.step(room.instance_id)  # move everything one update forward, using the inputs players sent
        # One broadcast reaches the whole window, and turns the state into JSON once
        await room.broadcast(self.snapshot(room.instance_id))
        next_tick += TICK
        await asyncio.sleep(max(0.0, next_tick - loop.time()))
```

How to run it:

- Start it in `join` when the window has no loop running yet, with `asyncio.create_task(self.run_room(conn.room))`.
- Keep the task in a dict keyed by `ctx.instance_id`. Start a new one only when the old one is done (`task is None or task.done()`).
- Cancel them all in `cog_unload`.

The loop ends by itself once its room is empty. A player who comes back before then gets the same room, so the loop simply keeps going for them.

**Expect a little wobble.** The loop keeps its average pace, but single updates arrive a little early or late. Two things cause it:

- The network adds its own small delays.
- On Windows with Python 3.11 or 3.12, the bot's clock moves in steps of about 16 ms. So at 30 updates a second, single gaps range from about 15 to 48 ms. (Linux, and Python 3.13 or later on Windows, have a much finer clock.)

Two habits hide it:

- Draw about two updates behind the newest one, timed by when updates arrive, instead of sliding between only the last two.
- Measure your update rate as an average over a second, like the `hub.stat()` example under "Show your update rate" below does.

**Send what the player pressed, not where they are.** The page sends inputs (`{"move": "left"}`) and moves the player's own character right away, without waiting for the bot. Python is the judge: it applies the inputs in its next update. If the two disagree, the page corrects itself from the next snapshot. That is how the player's own movement feels instant on a slow connection (this is called client-side prediction).

**Keep messages small.** Compression is already on. On top of that:

- Send one message per window per update, not one per change.
- Use arrays instead of named fields, and whole numbers instead of decimals: `{"p": [[12, 340, 220], [7, 90, 410]]}` (id, x, y) rather than a list of `{"id": 12, "x": 340.25, "y": 220.5}`.
- Send only what changed since the last update, plus a full snapshot when a player joins.
- Load big things (levels, images, sounds) as files from `web_dir`, not over the live connection, which refuses messages of 1 MB or more.

**Keep `message` quick.** One player's messages reach `message` one at a time, so a slow handler holds up that player's next inputs. Store the input and return, and let the update loop use it:

```python
async def message(self, ctx, conn, data):
    if isinstance(data, dict) and data.get("move") in ("left", "right", "up", "down"):
        self.inputs[conn] = data["move"]
```

For slow side work, like saving to Config or calling Discord, start a task with `asyncio.create_task()`. Keep a reference to it until it finishes, or Python can delete it halfway. Save scores when a round ends, not on every input.

**Measure the delay players feel.** The helper does this for you:

- While your game has a live connection open, it times a message to the bot and back every 2 seconds.
- The hub's frame rate counter in the corner shows the result, like `60 FPS · 85 ms` (FPS: frames drawn per second).
- `conn.latency` holds the latest number, in milliseconds.

It includes everything a player feels: the network, the proxies, a busy bot, and your own messages queued ahead of it.

**Show your update rate** with `hub.stat()`, to check your loop keeps its pace. This counts the updates that arrive each second. The counter then shows `60 FPS · 85 ms · 30 TPS` (TPS: ticks, or updates, per second):

```js
let updates = 0;
conn.on(() => {
  updates += 1;
});
setInterval(() => {
  hub.stat(`${updates} TPS`);
  updates = 0;
}, 1000);
```

**Survive restarts.** Reloading your cog or ActivityHub closes every live connection with `1001`, and the helper reconnects each page by itself. So:

- Keep the game's state in your cog, keyed by `ctx.instance_id`, never on `conn`.
- Send the full state in `join`.

Then, after a dropped network or a reload of ActivityHub, a page picks up where it was. A reload of your own cog, or a bot restart, starts your cog fresh, with its state gone. Save anything that must survive those (to Config, say) and load it back.

**Tell your bot owner where the bot should run.** Discord's proxy runs close to each player, then carries the connection to wherever the bot is. Most of the delay is that distance, so a bot hosted near most of its players is fastest. The public address should go through one tunnel or one reverse proxy, not a chain of both: each one adds a step, and its own timer for closing quiet connections. The hub's heartbeat (every 30 seconds of silence) keeps connections open through common defaults like nginx's 60 seconds.

**When the bot isn't enough (advanced).** A game that needs a dedicated server (in a faster language, or near its players) can still use the hub for its menu, login and launching. It connects to its own server for the fast part:

1. The bot owner adds a URL mapping in the Developer Portal for a path like `/rt`, pointing at your game server. Discord tries mappings in order, so it goes above the hub's `/`.
2. An action in your cog returns a ticket: the player's id, `ctx.instance_id`, an expiry about 60 seconds away and a random one-time value, signed with HMAC (a signature made with a secret only your cog and your game server know).
3. The page opens a WebSocket to `/rt/...` and sends the ticket as its first message. Not in the address, since addresses end up in logs.
4. Your game server checks the signature with `hmac.compare_digest`, and refuses expired or reused tickets.

Your game server then has to do its own checks. The hub's login and on/off switches don't reach it.

## 7. Who's here

**In short:** the hub shows everyone who is playing what, in the menu and inside every game, with no code from you. A few calls let your game say what its player is doing, and show the others in its own way.

Friends usually open the Activity together, from one voice channel, and then spread out over different games. A **window** is everyone who opened the Activity from the same voice channel (or the same DM call). They share one `ctx.instance_id`. Everything in this section is about the people in the player's window.

**What every game should do** (the details follow):

1. **Say what the player is doing** with `hub.status("...")`, each time it changes.
2. **Say when leaving would cost them:** `hub.busy(true)` when a round starts, `hub.busy(false)` when it ends.
3. **Make sure the people button covers nothing.** If it does, place it yourself with `hub.peopleButton()`.

What players get without you writing anything:

- **In the menu,** a game that people in this window are playing has a number bubble on its corner. Resting the mouse on the game (or tapping the bubble on a phone) lists them, with what each one is doing and a **Join** button, plus how many play it in other channels of the same server. The Orb theme lists them on its big screen for the selected game, under **Playing now**. The menu's header shows everyone else in the window.
- **In your game,** a **people button** floats in the top-right corner. It opens the **people panel**: who is in your game, who is in each other game, who is in the menu, how many play in other channels, and an **Invite friends** button that opens Discord's invite window. When someone opens your game, a short "Ann joined" note slides out of the button.
- **Join** opens the other person's game for the player. If your game says its player is mid-round, the hub asks first: "Leave Tanks to join Ann in Snake?", with **Stay** picked by default.
- **Away:** people whose Discord is in the background (a locked phone, another app or tab in front) show dimmed, with "Away" in place of what they're doing.

None of this needs a live connection in your game: the menu keeps its own connection to the bot for it. It works the same for a single-player game played side by side and for a multiplayer one.

Each example below is a small `game.js` on its own, so each one starts with `connect()`. In your own game, call `connect()` once and reuse that `hub`.

### Say what the player is doing: `hub.status()`

```js
import { connect } from "activityhub";

const hub = await connect();
let clicks = 0;

document.getElementById("click").addEventListener("click", () => {
  clicks += 1;
  hub.status(`Clicked ${clicks} times`, { clicks });
});
```

The first argument is the **status line**: a short text everyone in the window sees next to the player's name, in the menu, the people panel and other games. Write what they're doing in a few words, like `Wave 4 · 1,230`, `Watching` or `Blackjack · bet 200`. Without one, the hub shows "Playing".

The second argument is optional **data**: any JSON value, for your own game's pages to read in `hub.people` (a live score, a table number). The hub's own lists never show it.

- Call it as often as you like, even every frame. The hub sends at most 4 updates a second, and the latest one wins.
- Each call sets both. `hub.status("Watching")` also clears the data.
- The text is one line of plain text, always shown as text (`<b>` shows as typed). Longer than 60 characters, it is cut. Characters are counted like `Array.from(text).length`, so 🎉 counts as one. The bot also removes line breaks, other control characters and the spaces at each end.
- The data can be up to 1,024 characters once turned into JSON (`JSON.stringify`). The hub copies it when you call, so changing your object afterwards changes nothing until you call again. Data that is too big, isn't JSON, or has half an emoji in a text is left out, with a warning in the browser console. The text still goes through.
- Your Python never sees either of them. When the bot needs a score, send it through your own action or live connection.
- Both reset when your game closes. In the browser preview, `hub.status()` does nothing.
- Everyone in the window sees both, whatever game they're in. Never put anything private in them.

### Say when leaving would cost them: `hub.busy()`

```js
function startRound() {
  hub.busy(true);
}

function endRound() {
  hub.busy(false);
}
```

While busy is on, Join asks the player before taking them out of your game, and **Stay** is the default answer. Turn it on when a round starts and off when it ends. Leave it off in menus, lobbies and results screens, so Join stays one tap there.

- Only `true` turns it on. Anything else, like `1` or `"yes"`, counts as off.
- It resets when your game closes. In the browser preview it does nothing.
- Other pages see it as `busy` in `hub.people`.

### Who else is here: `hub.people` and `hub.onPeople()`

`hub.people` is everyone in the window right now, the player included, in the order they arrived.

- Each read gives a new array of new person objects, so you can sort and filter it freely.
- A person's `data` is the same object on every read, though: copy it before you change it.

`hub.onPeople(fn)` calls `fn(people)` each time a new list arrives (at most 4 times a second). It returns a function that stops it.

- `onPeople` doesn't call `fn` straight away. Draw once from `hub.people`, then again in `onPeople`, like the example below.
- A new list doesn't always change what you show: someone in another game may only have changed their data. If drawing is costly, check what changed first.
- Don't rebuild buttons on every list. A click whose press and release land on different elements is lost. Change the parts in place, or skip a redraw that would show the same thing. The strip example below rebuilds its rows each time only because nothing in it can be clicked.
- Right after `connect()`, the list can still be empty or a moment old, for example when a Play button opened your game straight away. `onPeople` brings the next one.
- The list can also go empty later: when the menu loses its connection to the bot for more than a minute, everyone leaves the list until it's back. Your page should cope with an empty list at any time.
- The hub removes your listeners when your game closes.
- `onPeople` throws a `TypeError` when `fn` isn't a function, like `hub.onPeople(draw())` with the brackets.
- In the browser preview, `hub.people` is always empty and `fn` is never called.

Each person is an object:

| Field | What it is |
|---|---|
| `id` | Their Discord user id, as text. |
| `name` | The name Discord shows for them in this server: their nickname, else their display name. |
| `avatar` | The address of their Discord picture. Show the first letter of their name instead when it fails to load. |
| `game` | The key of the game they're in, or `null` in the menu. |
| `gameName` | That game's name, or `null` in the menu. |
| `status` | Their status line, or `""` when their game set none. |
| `data` | The data their game set with `hub.status()`, or `null`. It comes from whatever game they're in, so check `here` before reading it as your own game's. |
| `busy` | `true` while their game says they're mid-round. |
| `away` | `true` while Discord hides their Activity (a locked phone, another app or tab in front). Also `true` for 15 seconds after their menu loses its own connection to the bot; if it isn't back by then, they leave the list. Your game's live connection has nothing to do with it. |
| `you` | `true` for the player on this page. |
| `here` | `true` for people in your game, the player included. |

This is the pattern for a solo game played side by side: a strip of everyone's live score. It needs a `<ul id="strip"></ul>` in your `index.html`.

```js
import { connect } from "activityhub";

const hub = await connect();
const strip = document.getElementById("strip");

function showScores(people) {
  const rows = people
    .filter((person) => person.here && person.data && typeof person.data.score === "number")
    .sort((a, b) => b.data.score - a.data.score);
  strip.replaceChildren(
    ...rows.map((person) => {
      const row = document.createElement("li");
      // Names come from Discord: always text, never HTML
      row.textContent = `${person.you ? "You" : person.name}: ${person.data.score}`;
      return row;
    }),
  );
  // Nothing to compare with when the player is alone
  strip.hidden = rows.length < 2;
}

showScores(hub.people);
hub.onPeople(showScores);
```

Each page sets its own score with `hub.status(text, { score })`. The player's own entry comes back from the bot a moment after that call. So for a strip that keeps up with every point, show the player's own score from your game instead, like `arcade.js` does (below).

Other pages' data is for showing only. A changed page can send any score it likes, so never pay out or rank a leaderboard from it: that's your Python's job (see [What to trust](#5-what-to-trust-and-paying-out)).

`hub.people` is about the window, not your live connection. Someone can be in your game before their `hub.socket()` connects, or after it dropped. For who is connected right now, use `conn.peers()` in Python.

Your Python sees none of the people list. Status lines, data, busy flags and who is where stay on the pages, and there is no Python call to read them. The one thing Python gets is `conn.follow`, after a Join (below).

### Put the people button in your layout: `hub.peopleButton()`

The floating button in the top-right corner can cover something of yours. Place it yourself instead. This example puts it in the page's `<header>` element:

```js
import { connect } from "activityhub";

const hub = await connect();
document.querySelector("header").append(hub.peopleButton());
```

- **Call it right after `connect()`,** before anything else you `await`, and the floating button never shows. The hub shows the floating one a frame after `connect()` resolves, and hides it as soon as you call `hub.peopleButton()`. A page that never calls `connect()` gets the floating one 2 seconds after it loads.
- It returns one element: the button, plus the spot its arrival notes slide out of. Put it anywhere in your page. Notes appear under it, lined up with whichever side of the screen it is nearer. Keep it out of boxes with `overflow: hidden`, which cut the notes off.
- Call it once. Only the newest button it returned keeps up with the list.
- The button shows up to 3 faces of the others in your game, and how many others are in the window. With nobody else there, it shows an invite icon.
- Its size follows the CSS variable `--hub-people-size` (36px by default). Set it on anything above the button, like `header { --hub-people-size: 30px; }` or `:root`.
- It takes its colors from your page's `--accent` and `--on-accent` CSS variables when your page sets them, and Discord's blurple and white otherwise. `--accent` colors the hover border, the keyboard focus ring, the arrival notes and the first-letter circles shown when a picture can't load; `--on-accent` colors the text on them. If your page uses `--accent` for something else, the button takes that color too.
- `hub.openPeople()` opens the people panel, for your own button or menu entry.
- In the browser preview it still returns a button, which opens a panel saying "Open this from Discord to see who's here.". A page opened in a tab of its own, without the menu around it, gets a button that does nothing.

### Join: `hub.follow` and `conn.follow`

When a player presses **Join** next to Ann, the hub opens Ann's game for them. What "joining Ann" means inside your game is up to you:

- **One match per window** (most multiplayer games): nothing to do. Opening your game already puts them in Ann's match.
- **Several tables or rooms in one window:** put them where Ann is. Your Python knows who they followed as `conn.follow` in `join`, and the page knows it as `hub.follow`.

`conn.follow` is Ann's user id as an `int`, or `None`. It is only set:

- on the player's first live connection after the Join: the first `hub.socket()` call, or the next one if that one failed to open,
- and when Ann is in the same window (in any game or the menu) as the connection opens.

A connection that drops and comes back has `None`, so a player who moved on isn't pulled back to Ann. The hub has checked that Ann is in the window. Whether Ann still sits at a table is up to your own state. For example, with `self.tables = {}` in `__init__`, and both handlers listed in `"socket"`:

```python
async def join(self, ctx, conn):
    # Who sits at which table in this window: {user_id: table number}
    seated = self.tables.setdefault(ctx.instance_id, {})
    # Joined from the hub's people list: sit at the friend's table. Otherwise keep this player's own seat (a
    # reconnect has no follow), or start a newcomer at table 1
    table = seated.get(conn.follow) or seated.get(ctx.author.id, 1)
    seated[ctx.author.id] = table
    await conn.send({"table": table})


async def leave(self, ctx, conn):
    seated = self.tables.get(ctx.instance_id, {})
    # A reconnect that opened before this leave ran is already in peers(): its player keeps the seat
    if not any(peer.ctx.author.id == ctx.author.id for peer in conn.peers()):
        seated.pop(ctx.author.id, None)
    if not seated:
        self.tables.pop(ctx.instance_id, None)
```

`leave` frees the seat, so nobody is sent to a table its player has left. A player whose connection dropped and came back after `leave` ran starts over at table 1. To hold seats through a drop, keep them for a short while after `leave` (20 seconds), like [Marble Munch](#a-multiplayer-example-marble-munch) does.

`hub.follow` is `{ id, name }` (both text) of the person whose Join opened your game, or `null`. It stays the same while your page is open. The same idea on the page, for a game that moves between rooms itself:

```js
import { connect } from "activityhub";

const hub = await connect();
const friend = hub.follow ? hub.people.find((person) => person.id === hub.follow.id) : null;
if (friend && friend.here && friend.data && friend.data.room) {
  // goToRoom is your game's own function
  goToRoom(friend.data.room);
}
```

`friend.data.room` comes from Ann's page. So it says where to go, not that the player may go there: your Python still decides that.

Join also closes the game the player was in, by removing its frame, and that cancels any request the page hadn't finished. To keep a player's progress, save on `pagehide` (the browser's event for a page going away) with `hub.api(name, data, { keepalive: true })`, the way the included games save a round. `keepalive` tells the browser to finish sending the request even after the page is gone. Mark the round as over before you save it, so a round your own Menu button (the one that calls `backToMenu()`) already saved isn't saved a second time when the page goes away.

### A full example

The included games do all of this in `activityhub/web/arcade.js`:

- `report` sets the status line, the data and busy.
- `rivals` and `showLive` draw the live strip from `hub.people`.
- `buildBar` places the people button in the top bar.

### Older hubs

These calls came in ActivityHub 0.5.0. On an older hub they are missing, and calling one throws an error like `hub.status is not a function`. A game that should still run there checks first, and reads the list as `hub.people || []`:

```js
if (hub.status) {
  hub.status("Getting ready");
}
```

## 8. Uploads and other raw requests

> **Most games never need this.** Actions cover anything that fits in a JSON message under 1 MB. Read on when you need file uploads, binary data or streaming.

A raw route handles what actions don't cover. Your handler gets the raw web request from aiohttp (the web library the hub runs on) and returns any aiohttp response, so you have full control.

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

Watch the order: a raw route takes **`request` first, then `ctx`**. Actions are the other way round.

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
- **`ctx` can be `None`.** Raw routes run without a login too, so check for it, like the example does. It is `None` only for requests with no login (the browser preview, or a request not made with `hub.fetch`). When a player's login expired, the hub answers 401 itself and `hub.fetch` logs in again and retries, so your handler never sees an expired login.
- **Your own tokens go in another header.** The hub uses the `Authorization` header for the player's login (`hub.fetch()` sets it). It answers any `Authorization: Bearer ...` it doesn't know with 401, before your route runs. If your route checks its own tokens (a webhook from another service, say), have them sent in another header, like `X-Api-Key`.
- **Turned off still applies.** For a logged-in player, the hub answers "This activity is turned off in this server." before your handler runs.
- **Raising works.** aiohttp's ready-made responses, like `raise web.HTTPForbidden()`, reach the page as they are. Any other error is logged and the page gets "Something went wrong.". These ready-made errors, and the hub's own 413 and 404 for raw routes, arrive as plain text, not JSON. So check `resp.ok` before `resp.json()`, like the page example does.
- **Paths match exactly.** `"GET item"` answers `item` and `item?id=7`, not `item/7`. There are no `{parameters}`: send values in the query string, `hub.fetch("item?id=7")`, and read `request.query["id"]`. There is no `HEAD`.
- **Showing what a route returns.** For a logged-in read, fetch it and make a local address for it:

  ```js
  const resp = await hub.fetch(`avatar?user=${id}`);
  img.src = URL.createObjectURL(await resp.blob());
  ```

  A public `GET` route (one that is fine with `ctx` being `None`) also works straight from HTML, as `<img src="../raw/avatar?user=2">`. The hub's `<base>` tag puts plain relative paths in your file folder, so `raw/...` alone doesn't reach your routes.

## 9. Extra Discord permissions

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
- **One wrong scope stops every game.** A scope Discord doesn't accept stops every game on the bot from logging in. Copy names exactly from Discord's OAuth2 scope list (Discord's list of every permission a login can ask for). The hub refuses names that can't be scopes (like `"identify guilds"` in one string) and scopes a login can't ask for (`bot`, `webhook.incoming`). It warns in the bot log about names it doesn't know. `[p]activityhub games` shows which game asks for what.
- **Only scopes used through `hub.discord` help.** Neither your page nor your Python gets the player's Discord access token.
- **Scopes are read when the Activity opens.** Reopen it after adding one.

## 10. Opening your game from a command or button

> **You don't need this.** Players open your game from the Activity menu. Server admins can also pin a button that opens your game on any message the bot sent, with `[p]activityhub pin <message link> game: <your key or name>`, and that needs no code from you.

If you want a shortcut of your own anyway, the hub can open your game straight from a button or a slash command:

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

## 11. Files and caching

The hub serves every file in your `web_dir`. A few rules keep that working.

**The rules everyone needs:**

- **Use relative paths** in your page: `game.js`, `./levels.json`, `art/ship.png`. Never start a path with `/`. The bot log warns when `index.html` has a `src` or `href` starting with `/`.
- **Bundle everything** in `web_dir`: scripts, styles, images, sounds, fonts. Nothing from other websites (see [Discord's limits](#14-discords-limits)).
- **Everything in `web_dir` is public.** Anyone can download it. Keep secrets and payout rules in Python. Files and folders whose names start with a dot (`.git`, `.env`) are the exception: the hub never serves them.
- **Keep your game in one page.** Only `index.html` gets the `<base>` tag and the `"activityhub"` import. Other `.html` files are served as they are.
- **Watch out for `#` links.** Because of the `<base>` tag, `href="#"` and `href="#rules"` leave your game for a "This page isn't part of the game." notice, and `href="index.html"` starts your page over. Use `<button type="button">`, `element.scrollIntoView()`, or `event.preventDefault()`.
- **Storage is shared.** Every game and the menu share one web address, so `localStorage` and `sessionStorage` (the browser's saved data for a site) are shared too. Prefix your keys with your game key (`"clickcounter:best"`), and keep anything that matters in Config. (Game cogs are fully trusted code, like any Red cog.)
- **Links (symlinks, `npm link`) to files outside `web_dir` aren't served.** Copy the files in.

**Caching is handled for you.** A cache is a saved copy of a file, kept so it loads faster next time. The hub serves your files under a versioned folder, like `/games/<key>/<code>/game.js`. The code changes whenever any of your files change. So a caching service (like Cloudflare, which keeps copies of files to serve them faster) never serves an old copy.

**Details for bigger projects:**

- **Prefer `.js` and `.css` files** over code inside the HTML: they cache and debug better. Inline `<script>` isn't blocked, though. The hub's own import map (the small inline script that tells the browser where `"activityhub"` is) is one, so any page that can import `"activityhub"` can run inline code.
- **Keep `web_dir` to your built page.** Point it at your build output (for example `dist/`), not a project folder with `node_modules`. Every file in it is public and is fingerprinted (checked for changes) each time the game opens, so the bot log warns about a `node_modules` folder or more than 2000 files.
- **`index.html` should have a `<head>` tag.** The hub puts two tags right after it: a `<base>` tag that points relative paths at your versioned folder, and the import map that tells the browser where `"activityhub"` is. Without a `<head>`, it puts them right after the doctype.
- **Single-page app routers must use memory or hash mode.** A router is a library that switches screens by changing the address, like React Router or Vue Router. Use its memory or hash mode (for example `createMemoryRouter`, `createMemoryHistory` or `createWebHashHistory`). Your page lives at `/games/<key>/`, and a reload of any other path misses. When the game frame does land on an address that isn't a file, it shows "This page isn't part of the game." with a Back button, and the bot log names the address.
- **Using a bundler** (a tool that packs your code into a few files)? Mark `activityhub` as external (esbuild `--external:activityhub`; Vite `build.rollupOptions.external: [/^activityhub/]` plus `base: './'`), output ES modules (JavaScript files that use `import` and `export`), and point `web_dir` at the build output folder.
- **File types are set for you.** The hub serves `.html`, `.js`, `.mjs`, `.css`, `.json`, `.wasm`, `.svg`, `.woff2` and `.mp3` with the exact type browsers require. Other files get their usual type. Files ending in `.gz` or `.br` are sent compressed: see [engine builds](#14-discords-limits).

## 12. Testing and debugging

**Where to look when something's wrong,** in this order:

1. **Is your game loaded?** Run `[p]activityhub games`. A problem with your description shows there, under "Refused:".
2. **Is the page failing?** Press F12 in the browser and read the Console tab.
3. **Is your Python failing?** Read the bot's log. Every error in your handlers is there in full. Players only see "Something went wrong." (the bot owner also sees the reason).

Then look the message up in [Common problems](#13-common-problems).

**In a normal browser (fastest).** Open the hub's address, for example `http://127.0.0.1:8742/`. The menu shows in preview mode, and your game opens inside it with `hub.offline` set to `true`. Make your page handle that, so you can work on the look without Discord. Press F12 to open the browser's developer tools: the Console tab shows JavaScript errors, the Network tab shows each request.

**Inside Discord.** Open the Activity in a server and pick your game. The easiest way to see errors there is Discord's web app:

1. Open `https://discord.com/app` in a normal browser like Chrome.
2. Start the Activity there.
3. Press F12. The developer tools show your game frame's console messages and network requests too. In the Console tab, the frame picker at the top switches between the menu and your game.

Don't open the game frame's own address, the one with `?frame_id=...`, in a tab of its own. It only works inside Discord, and after 10 seconds the page says "Discord hasn't answered yet".

**Two players.** Open the Activity on a second account in Discord's web app, in a second browser profile, in the same voice channel. Then pick your game there too.

### Testing your Python without Discord

Your handlers are plain async methods, so tests can call them directly with stand-ins for `ctx` and `conn`. Nothing here imports ActivityHub.

1. Install `pytest` and `pytest-asyncio` in the bot's Python environment.
2. Put the files below in a `tests` folder next to `clickcounter/`.
3. Run `python -m pytest tests` from the folder that holds both.

`tests/conftest.py` borrows Red's own test fixtures (ready-made test helpers):

```python
from redbot.pytest.core import *  # Red's own fixtures: a temporary data folder, member_factory...
```

`tests/test_clickcounter.py` tests the quick start's action, and the live connection handlers from [multiplayer](#6-multiplayer-with-live-connections):

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


class FakeRoom:
    """Stands in for conn.room: everyone in one window"""

    def __init__(self, instance_id="test"):
        self.instance_id, self.connections = instance_id, []

    async def broadcast(self, data):
        for conn in list(self.connections):
            await conn.send(data)


class FakeConn:
    """Stands in for a live connection. Keeps what was sent, and refuses what the hub would refuse"""

    def __init__(self, ctx, room, follow=None):
        self.ctx, self.room, self.sent, self.closed = ctx, room, [], None
        # The friend's user id when this player came in with Join, like the real conn.follow
        self.follow = follow
        room.connections.append(self)

    async def send(self, data):
        self.sent.append(json.loads(json.dumps(data, allow_nan=False)))

    async def broadcast(self, data, include_self=False):
        for conn in list(self.room.connections):
            if include_self or conn is not self:
                await conn.send(data)

    def peers(self):
        return [conn for conn in self.room.connections if conn is not self]

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
    cog, room = ClickCounter(bot=None), FakeRoom()
    alice = FakeConn(player(1), room)
    await cog.join(alice.ctx, alice)
    bob = FakeConn(player(2), room)
    await cog.join(bob.ctx, bob)
    await cog.message(alice.ctx, alice, {"bump": True})
    assert alice.sent[-1] == bob.sent[-1] == {"total": 1, "by": "Player 1"}
    # The hub takes a closing connection out of its room before leave runs
    room.connections.remove(alice)
    await cog.leave(alice.ctx, alice)
    assert bob.sent[-1] == {"players": 1}
```

The hub's own tests (`activityhub/tests/fakes.py`) use the same kind of stand-ins for Discord's users and servers.

**Python errors** go to the bot's log, like any other cog's. Look for lines starting with `Action <key>.<name>` (followed by "failed", "returned ... instead of a dict", "returned something that isn't JSON", "returned an empty error" or "returned an error that isn't text"), `Live connection ... handler of <key> failed`, or `Raw route ... of <key>` (followed by "failed" or "returned ..., not a response"). When you test as the bot owner, "Something went wrong." on the page also includes the reason, like "(Only you see this, as the bot owner: KeyError: 'points'. The bot's log has the full error.)". Other players only see "Something went wrong."

**Is my game loaded?** `[p]activityhub games` lists every game the hub knows with the Discord scopes it asks for, marks games the owner turned off with `[turned off]`, and lists refused cogs under "Refused:" with the reason.

**After changes:**

- Web files: close your game and open it again.
- Python: `[p]reload <yourcog>`. Players who are connected with a live connection get disconnected with code `1001`, and the helper reconnects them by itself. Your `leave` still runs for each of them, on the old copy of your cog.

**Restarts.** The hub keeps logins in memory only, so a bot restart, or a reload or update of ActivityHub, forgets them. Here is what happens then:

- `hub.api()`, `hub.fetch()` and `hub.socket()` log the player in again by themselves and retry once, and the game keeps running.
- Live connections still close with `1001`, and the helper reconnects them by itself.
- If Discord refuses the new login, the player is taken back to the menu.
- If the menu can't log in either, it shows "Your session expired. Close this activity and open it again."

## 13. Common problems

**How to use this section:** find the message you see in the left column, word for word. `...` stands for a part that changes, like a name or a number. Most problems come from breaking one of the [ten rules](#ten-rules-that-save-you-hours).

The tables, by where you see the problem:

- [Your game isn't in the menu](#your-game-isnt-in-the-menu): messages from `[p]activityhub games`.
- [Warnings in the bot log](#warnings-in-the-bot-log): your game works, but something will likely break.
- [Your page doesn't work](#your-page-doesnt-work): messages on the page or in the browser console.
- [Who's here problems](#whos-here-problems): status lines, the people list and the people button.

### Your game isn't in the menu

| What you see | Why | Fix |
|---|---|---|
| The game isn't in `[p]activityhub games` at all | Your cog isn't loaded, it has no `activityhub_game` method, or `activityhub_game()` is still waiting on something. | `[p]load yourcog`. Check the method name is spelled exactly `activityhub_game`. A game whose method waits shows up once it returns. |
| `activityhub_game must be an async def` | You wrote `def activityhub_game`. | Write `async def activityhub_game(self)`. |
| `activityhub_game must return a dict, got ...` | The method returns something else, or nothing (`got NoneType`). | `return {...}`. |
| `activityhub_game must return one dict (one game per cog), got ...` | The method returns several games, in a list or a tuple. | One cog gives one game. Make a cog for each. |
| `Unknown field 'action' (did you mean 'actions'?)` | A field name in your dict has a typo. | Use the field it suggests. |
| `Unknown fields: ...` | A field name isn't a real field, or the game was made for a newer ActivityHub. | Use only the fields in [the table](REFERENCE.md#1-activityhub_game), or update ActivityHub with `[p]cog update`. |
| `Missing fields: ...` | `key`, `name` or `web_dir` is missing. | Add them. |
| `key must be 2-32 characters of a-z, 0-9 and hyphens, got 'Click_Counter' (try 'click-counter')` | The key has capitals, spaces or `_`. | Use the key it suggests. |
| `<field> must be ...`, like `name must be a non-empty string` | A field has the wrong type. | See the types in [the table](REFERENCE.md#1-activityhub_game). |
| `web_dir has no index.html: looked for ...` | The folder path is wrong, or `index.html` is missing. The message shows the full path the hub looked in. | Use `Path(__file__).parent / "web"`. A relative path starts at your cog's folder. |
| `web_dir holds your cog's Python code, and everything in web_dir is public.` | `web_dir` is your cog's folder, or a folder above it. | Keep the page in its own folder, like `Path(__file__).parent / "web"`. |
| `index.html isn't UTF-8 text ...` | Your editor saved it in another encoding. | Save it as UTF-8. |
| `icon must be a file inside web_dir, written relative to it (like 'icon.png'): ...` (or `thumbnail`) | The picture's path is wrong, or points outside `web_dir`. | Use a path relative to `web_dir`, like `"art/icon.png"`. |
| `icon has a name starting with a dot in its path, and the hub never serves those: ...` | The picture is in a folder like `.assets`. | Move it to a folder whose name doesn't start with a dot. |
| `actions key 'x' must be ...`, `socket keys can only be ...` or `routes key 'x' must be "METHOD path": ...` | A name breaks the naming rule in [the table](REFERENCE.md#1-activityhub_game). The message says the rule. | Rename it. |
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

### Warnings in the bot log

Your game still registers, but something will likely break:

| What you see | Why | Fix |
|---|---|---|
| `asks for the scope 'x', which ActivityHub doesn't know` | A scope name the hub doesn't know, often a typo. Every installed game's scopes go into one login, so a wrong one stops every game from logging in. | Copy the name exactly from Discord's OAuth2 scope list. |
| `index.html refers to ... with an absolute path, which the hub can't serve` | A `src` or `href` starts with `/`. | Use relative paths. Built with Vite? Set `base: './'`. To go back to the menu, call `backToMenu()`. |
| `web_dir has a node_modules folder` (or `more than 2000 files`) | `web_dir` is your project folder, not your built page. | Point `web_dir` at your build output, like `dist/`. |
| `the game frame went to ..., which isn't a file in web_dir` | Your page went to an address that isn't a file: an `href="#"` link, a router path, a reload after `history.pushState`, or a typo. The player saw "This page isn't part of the game." | See [Files and caching](#11-files-and-caching): use buttons, and memory or hash routing. |
| `the page opened a live connection, but activityhub_game() has no "socket"` | The page called `hub.socket()`. | Add `"socket"` to `activityhub_game()` and `[p]reload yourcog`, or don't call `hub.socket()`. |

### Your page doesn't work

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
| The game frame shows "This page isn't part of the game." | The frame went to an address that isn't a file in `web_dir`: an `href="#"` link, a router path, or a reload after `history.pushState`. The bot log names the address. | See [Files and caching](#11-files-and-caching): use buttons, and memory or hash routing. |
| `hub.socket()` throws "This game has no live connection. Add "socket" to activityhub_game() and reload the cog." | Your description has no `"socket"` field. | Add `"socket"`, then `[p]reload yourcog`. |
| `hub.socket()` throws "The live connection closed (1006)." | A proxy in front of the bot blocks WebSockets, the network dropped, or your game isn't loaded. | Ask the bot owner to allow WebSockets through the proxy. Check `[p]activityhub games`. |
| The page never gets a message, and the bot console says `coroutine 'Connection.send' was never awaited` | `conn.send()` was called without `await`. | `await conn.send(...)`. |
| The bot log shows `ValueError: Out of range float values are not JSON compliant` (or `The 'activityhub' field is reserved for the hub's own messages`) from a socket handler | You sent NaN or Infinity, or an object with an `activityhub` field. | Send finite numbers, and use another field name. |
| An id from Python is off by a few | JavaScript rounds whole numbers above 2\*\*53. | Send ids as text: `str(ctx.author.id)`. |
| `sdk.ready()` never finishes, and the console says "this game created its own DiscordSDK" | Your page made its own `DiscordSDK`. Inside the hub, only the menu talks to Discord. | Use `hub.discord` from `connect()`. |
| The menu says "Discord hasn't answered yet" | You opened the game's address with `?frame_id=...` in a tab of its own. It only works inside Discord. | For the preview, open `/` without the `?frame_id=...` part. |
| A picture or script from another website doesn't load inside Discord | Discord blocks outside websites. | Put the file in `web_dir`. |
| Your change doesn't show | The page was still open, or the Python wasn't reloaded. | Reopen the game. For Python, `[p]reload yourcog`. |

### Who's here problems

| What you see | Why | Fix |
|---|---|---|
| Your status line never shows | You're in the browser preview, where `hub.status()` does nothing. Or you're looking from an account in another voice channel, which only sees a count. Or the player is away (their Discord tab or app is in the background), and lists show "Away" instead. | Test inside Discord, with both accounts in the same voice channel and both windows in front. |
| `hub.status is not a function` | `connect()` returns a promise, or the bot runs an ActivityHub older than 0.5.0. | `const hub = await connect();`. For older hubs, update ActivityHub, or check `if (hub.status)` first. |
| `hub.status() data is ... characters, over the 1024 the hub passes on` in the browser console | The data is longer than 1,024 characters as JSON, so the hub left it out. The text still went through. | Send less: a score and a state, not a whole board. |
| `hub.status() data isn't JSON, so it was left out` in the browser console | The data holds something JSON can't, like a `BigInt` or an object that contains itself, or the data itself is a function. (A function or `undefined` inside an object is left out without any warning: that's how `JSON.stringify` works.) | Send plain objects, arrays, text, numbers, booleans and `null`. |
| `hub.status() data has half an emoji in it, which the hub can't pass on` in the browser console | A text in the data was cut through the middle of an emoji, for example with `.slice()`. | Cut text by whole characters: `Array.from(text).slice(0, 20).join("")`. |
| `hub.onPeople() needs a function, got ...` | You passed something else, often a call: `hub.onPeople(draw())`. | Pass the function itself: `hub.onPeople(draw)`. |
| `hub.people` is empty | You're in the browser preview, the first list hasn't arrived yet, or the menu lost its connection to the bot for more than a minute. | Draw from `hub.people` once, then again in `hub.onPeople()`, and show something sensible for an empty list. |
| The people panel says "Open this from Discord to see who's here." | You're in the browser preview. | Open the Activity from Discord. |
| The people button covers one of your buttons | The floating button sits in the top-right corner. | Place it yourself with `hub.peopleButton()`. |
| The floating people button shows for a moment, then goes away | You called `hub.peopleButton()` after another `await`. | Call it right after `connect()`. |
| `conn.follow` is `None` after a Join | Only the first live connection after a Join has it. A reconnect, a later `hub.socket()`, or a friend who left the window before it opened gives `None`. | Read it in `join`, and keep what you need from it in your own state. |

## 14. Discord's limits

Discord runs Activities with some rules of its own. ActivityHub can't change them.

- **One Discord toolkit per Activity.** Discord's toolkit is the Embedded App SDK: the script a page uses to talk to Discord. The menu owns it. Your page runs in a frame inside the menu and borrows it as `hub.discord`.
  - Never create your own `DiscordSDK`: its `ready()` never finishes inside the hub, and the console says so.
  - Never navigate the top page (no `window.top.location`, no links with `target="_top"`).
  - Use `backToMenu()` to leave, not a link to `/` or another address. The hub closes a game whose frame leaves its page, and warns in the console.
- **Outside websites are blocked** unless the bot owner adds a URL mapping for them in the Developer Portal. Bundle what you need instead. Images from `cdn.discordapp.com` and `media.discordapp.net` (avatars, server icons) load fine.
- **Open links** with `hub.discord.commands.openExternalLink({ url })`.
- **Networking:** use `hub.api()`, `hub.fetch()` and `hub.socket()`. WebRTC and WebTransport (other ways browsers connect) are switched off inside Activities.
- **WebAssembly and engine builds work** (Godot, Unity).
  - Put the whole export in `web_dir`, with the page named `index.html`. Godot names it `<project>.html` by default: rename it.
  - For Godot 4, export with Thread Support turned off, because Activities can't turn on the browser isolation that threads need.
  - Unity's Gzip, Brotli and uncompressed builds work as exported, without Decompression Fallback. The hub sends files ending in `.gz` or `.br` with `Content-Encoding`, so the browser unpacks them. That also means your code never sees those files packed: if you unpack a file yourself (with `DecompressionStream`, say), give it another extension, like `.bin`.
  - From a script that isn't a module (an engine loader, a Unity `.jslib`, Godot's `JavaScriptBridge`), reach the helper inside an async function with `const { connect } = await import("activityhub");`, and set `window.hub = await connect();` if the engine needs a global.
- **Discord's buttons cover the top of the screen on phones.** Discord's back button and **Leave** button float over the top of your page, and a phone's notch can cover an edge too. Discord gives the room they take as `--discord-safe-area-inset-top`, `-right`, `-bottom` and `-left`, and the hub copies them into your page. So pad your top bar, and anything else along an edge, the way Discord's own guide does. The included games do this (`activityhub/web/arcade.css`):

  ```css
  .top-bar {
    padding-top: var(--discord-safe-area-inset-top, env(safe-area-inset-top, 0px));
  }
  ```

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

## 15. Checklist before you share your game

### Tell people your game needs ActivityHub

Your users need ActivityHub too, and Red doesn't install required cogs by itself. Say how to get it in `info.json`'s `install_msg`, like the quick start does, and in your README: `[p]repo add vrt-cogs https://github.com/vertyco/vrt-cogs`, then `[p]cog install vrt-cogs activityhub` and `[p]load activityhub`.

- ActivityHub is hidden from `[p]cog list` while it's in beta, but `[p]cog install` still finds it.
- A field added in a later ActivityHub is refused by older ones. So say which version your game needs. `[p]help ActivityHub` shows the version, and so does `bot.get_cog("ActivityHub").__version__`.

### The checklist

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
- [ ] Your page works on a phone-sized screen and with touch, since Activities run on Discord's phone apps too, and nothing you tap sits under Discord's buttons at the top ([safe areas](#14-discords-limits)).
- [ ] If you use a live connection: the page shows when it's reconnecting (`conn.onReconnecting`), `join` sends the full state, and the page says something useful in `conn.onClose`.
- [ ] Your game sets a status line (`hub.status`), and `hub.busy(true)` while a round is on.
- [ ] The people button doesn't cover anything, on a computer and on a phone.
- [ ] `info.json` has an `end_user_data_statement`, and your cog deletes a player's data when Red asks it to (`red_delete_data_for_user`).
- [ ] `info.json`'s `install_msg` (or your README) says how to get ActivityHub.

## 16. Bigger examples: the included games

ActivityHub comes with three games: Snake, Brick Breaker and 2048. They use the same `activityhub_game()` API as any game cog, so they are full working examples to read.

- **Python:** `activityhub/bundled/` (`games.py` has the descriptions and actions).
- **Pages:** `activityhub/bundled/web/`, one folder per game.

Snake and 2048 show a stronger anti-cheat pattern than checking against the clock:

1. When a round starts, the bot picks a random seed (a starting number) and sends it to the page.
2. The page uses that seed for every random roll, like where the next apple or tile appears.
3. When the round ends, the page sends its moves, not its score.
4. The bot replays those moves with the same seed and the same rules, and works out the score itself.

A changed page can't fake a score that way, because the bot never uses the page's score. The cost is that the rules exist twice, once in JavaScript and once in Python, and must match exactly.

The included pages also import `"activityhub/arcade.js"`, the hub's shared title, pause, results and leaderboard frame. That is the file `activityhub/web/arcade.js` in the cog's folder, the same one [Who's here](#7-whos-here) points to: any import starting with `"activityhub/"` reaches a file in the hub's `web` folder. `arcade.js` isn't part of the API yet and may change: copy what you need instead of importing it.

Read them for ideas. Their internals are not part of the API and may change.

### A multiplayer example: Marble Munch

Marble Munch is a separate cog in the same repo (`marblemunch/`): a hungry-hippos game for up to four players, with computer hippos in empty seats. It is built on [live connections](#6-multiplayer-with-live-connections) and the [speed advice](#speed-and-fast-paced-games) in this guide, and is meant to be read. Each pattern lives in one place:

| Pattern | Where |
|---|---|
| One match per window, holding `conn.room` | `marblemunch/main.py` (`match_for`), `common/match.py` (`Match`) |
| A locked 30-a-second update loop | `common/match.py` (`run`, `tick`) |
| Seats, and settling two taps on one seat | `common/match.py` (`sit`) |
| Accepting only exact messages, applied on the next update | `common/match.py` (`message`, `steer`) |
| Reconnecting into your seat, a grace period, and a computer player taking over | `common/match.py` (`join`, `leave`, `expire_drops`) |
| Computer players that send the same inputs as people | `common/npc.py` |
| Game rules with nothing about Discord in them, so tests drive them directly | `common/rules.py`, `tests/` |
| Drawing two updates behind, and the player's own hippo answering at once | `web/scene.js` (`sample`, `drawMine`) |
| The update rate in the hub's frame rate counter | `web/game.js` (`showRate`) |

### A turn-based example: Tanks

Tanks is another cog in the same repo (`tanks/`): turn-based artillery for up to five players and computer tanks, ported from a Flash game. Marble Munch streams every update. Tanks shows the other common shape: one player acts at a time, and the slow, exact part (a shot) is worked out by the bot all at once and played back on every screen.

| Pattern | Where |
|---|---|
| A 20-a-second loop that runs one player's turn, with a turn clock | `tanks/common/match.py` (`run`, `tick_playing`) |
| Small live updates sent only when the turn's numbers change | `common/match.py` (`live`, `tick`) |
| A host who sets up the match, and handing the host on | `common/match.py` (`fix_host`, `set_cpu`, `start_match`) |
| Working a whole shot out at once and sending it as a script | `common/physics.py` (`Shot.run`, `script`), `common/match.py` (`shoot`) |
| Holding every snapshot back until a shot has played | `common/match.py` (`tick`), `web/game.js` (`receive`, `runShot`) |
| Playing a script back on a fixed clock | `web/playback.js` |
| A browser preview recorded from the real match code | `tests/demo.py`, `web/demo.json` |

### A single-player example: Boulder Bash

Boulder Bash is a cog in the same repo (`boulderbash/`): a remake of Neopets' Destruct-O-Match III, a block-smashing puzzle. Each player plays their own game, and the bot owns the board: the page only says where the player tapped. It also shows Neopets-style payouts with an admin settings dialog inside the game.

| Pattern | Where |
|---|---|
| One game per player, kept running while they're away, and a newer page taking over | `boulderbash/main.py` (`join`, `leave`, `tick`) |
| Working a move out at once, then holding the board busy for as long as its animation lasts | `common/board.py` (`smash`), `common/timing.py`, `common/game.py` (`tap`) |
| The page playing the same motion for exactly that long, checked by a test | `web/motion.js`, `tests/test_page.py` |
| Score payouts and their settings dialog | `common/payouts.py`, `web/game.js` (`showOffer`, `showPayouts`) |

## 17. Glossary

| Word | What it means here |
|---|---|
| **Action** | A Python method your page calls by name with `hub.api(name, data)`. It gets `ctx` and `data` and returns a dict. |
| **Activity** | A game window that opens inside Discord, usually in a voice channel. A bot can have only one, so ActivityHub turns it into a menu. |
| **Bank** | Red's built-in currency. Your cog pays credits with `bank.deposit_credits()`. |
| **Bot owner** | The person who runs the bot. They do the one-time setup and can turn any game off everywhere. |
| **Busy** | A game's flag that its player is mid-round (`hub.busy(true)`), so Join asks before taking them away. |
| **Config** | Red's settings storage, where a cog saves its data. |
| **ctx** | The object every handler gets, saying who the player is and where (`ctx.author`, `ctx.guild`, `ctx.channel`, `ctx.instance_id`). The hub proved it with Discord. |
| **Follow** | The person a player joined with **Join**: `hub.follow` on the page, `conn.follow` in Python. |
| **Frame** | A page inside a page (an HTML `iframe`). Your game runs in one, inside the hub's menu page. |
| **Handler** | Any of your `async def` methods the hub calls: actions, live connection handlers and raw routes. |
| **Hub** | ActivityHub, the cog that holds the menu and runs your game. |
| **Instance** | One running Activity window. Everyone in the same window shares its `instance_id`. |
| **Key** | Your game's short id, like `clickcounter`. It's in your game's address, `/games/<key>/`. |
| **Live connection** | A WebSocket: a connection between the page and the bot that stays open, so both can send at any time. Used for multiplayer. |
| **Page** | Your game's web side: `index.html` and the files it loads. |
| **People button** | The hub's button in your game that opens the people panel. It floats in the top-right corner unless you place it with `hub.peopleButton()`. |
| **People panel** | The hub's list of everyone in the window, grouped by where they are, with Join and Invite buttons. |
| **Preview** | The menu and your game opened in a normal browser, outside Discord. `hub.offline` is `true` there. |
| **Raw route** | A handler that gets the raw web request and returns any response. Used for uploads and anything actions can't do. |
| **Room** | Everyone playing your game in one Activity window, as `conn.room`. Its `broadcast` reaches all of them. |
| **Scope** | One extra Discord permission the player approves at login, like changing their Discord status. |
| **Server admin** | A server's owner, or a member with the Manage Server permission or Red's admin role. They can turn games on or off in their own server. |
| **Session** | The player's login with the hub. The page carries a session pass with every request. It lasts up to 12 hours and ends when the bot restarts or ActivityHub reloads; `hub.api()`, `hub.fetch()` and `hub.socket()` then log the player in again by themselves. |
| **Status line** | A short text your game sets for its player with `hub.status()`, like `Wave 4 · 1,230`. Everyone in the window sees it. |
| **web_dir** | The folder holding your page: `index.html` and everything it loads. |
| **Window** | Everyone who opened the Activity from the same voice channel (or the same DM call). They share one `ctx.instance_id`. |
