# Activity Cookiecutter

**The bottom line:** a tiny two-player game for ActivityHub that already works, made to be copied. Load it, try it, then copy the folder and grow your own game from it.

What it does: two players each steer a dot around a shared field. Anyone else who opens it watches. That's all, on purpose. It is the smallest game that still has every piece a live two-player game needs:

- a bot that runs the game, so every screen shows the same thing and nobody can cheat,
- a page that draws it smoothly on a computer or a phone,
- seats, so two people play and the rest watch,
- controls for a keyboard, a mouse and a finger,
- a line in the hub's people lists saying who is playing whom,
- picking up again by itself after a dropped connection.

It needs ActivityHub 0.10.0 or later.

## Try it

1. Load it: `[p]load activitycookiecutter`. ActivityHub must be loaded too.
2. Check the hub found it: `[p]activityhub games` lists `activitycookiecutter: Activity Cookiecutter`.
3. In Discord, open the Activity in a voice channel and pick **Activity Cookiecutter**. You get the left seat, and the bottom line says it's waiting for a second player.
4. On a second account in the same voice channel, open it too. That account gets the right seat. Each of you steers your own dot, and both screens show both dots.
5. A third account that opens it watches.

The browser preview at `http://127.0.0.1:8742/` shows the page, but nothing moves there. The preview has no Discord login, so it can't open the live connection.

## What's in the box

| File | What it does |
| --- | --- |
| `__init__.py` | How Red loads the cog. You rarely touch it. |
| `main.py` | The bot's half. It tells the hub about the game (`activityhub_game`), seats players as they connect (`join`), takes their key presses (`message`), frees a seat when someone goes (`leave`), and runs the game 20 times a second (`run`). |
| `hubtypes.py` | Type hints for the hub's `ctx` and `conn`, so your editor can autocomplete them. Copied from ActivityHub's `devkit` folder. |
| `info.json` | Describes the cog for Red's cog installer. |
| `web/index.html` | The page: a top bar, the playfield and a line of text at the bottom. |
| `web/style.css` | How the page looks, and the spacing that keeps it clear of Discord's buttons on phones. |
| `web/game.js` | The page's half. It draws what the bot sends and sends what the player presses. |
| `web/activityhub.d.ts` | Type hints for the hub's page helper, so your editor can autocomplete `hub.` and `conn.`. The browser never loads it. |

Everything in `web/` is public: anyone can download it. Keep secrets and anything about money in `main.py`.

## How one move travels

Here is what happens when a player holds the right arrow key:

```
game.js, steer():        sees the key and sends {"move": [1, 0]}
        |
        |  the live connection (it stays open, so either side can send at any time)
        v
main.py, message():      checks the message is exactly what the page is meant to send,
                         and stores it in match.moves
        |
main.py, run():          20 times a second: match.step() moves every dot by its player's move,
                         then room.broadcast() sends {"spots": [...]} to every page
        |
        v
game.js, receive():      keeps the newest spots
game.js, draw():         60 or more times a second, slides each dot toward its newest spot
```

Two ideas carry the whole design:

- **The bot is the judge.** The page never says where its dot is, only what its player is pressing. The bot moves every dot, so a player who changes their page can't teleport.
- **The page smooths it out.** The bot sends 20 updates a second, but screens draw 60 or more frames. So the page slides each dot between its last two spots instead of letting it jump.

These are all the messages, so you can see the whole conversation at once:

| Message | From | To | When |
| --- | --- | --- | --- |
| `{"move": [x, y]}`, each -1, 0 or 1 | a seated player's page | the bot | when what they press changes |
| `{"you": seat, "field": {...}}` | the bot | only the page that just connected | when it connects |
| `{"seats": [name, name]}` | the bot | every page | when someone sits or stands up |
| `{"spots": [[x, y], [x, y]]}` | the bot | every page | every update |

## Start your own game from it

Say your game is called Pong.

1. Copy the whole `activitycookiecutter` folder, and name the copy `pong`. Red only loads folder names made of letters, numbers and `_`, with no hyphens or spaces.
2. In `__init__.py` and `main.py`, rename the class `ActivityCookiecutter` to `Pong`.
3. In `main.py`, change the `key`, `name` and `description` in `activityhub_game()` (the key becomes `"pong"`, the same as the folder), and the logger's name at the top.
4. In `info.json`, rewrite `short`, `description` and `install_msg` for your game.
5. In `web/index.html`, change the `<title>` and the `<h1>`.
6. Start a fresh `CHANGELOG.md` and write your own `README.md`.
7. Load it: `[p]load pong`. This game and yours can both be loaded at once, since their keys differ.

Then it's a loop of change, reload, look:

- **Changed Python:** `[p]reload pong`. Players who are connected drop for a moment, and reconnect by themselves.
- **Changed a web file:** close your game and open it again. No reload needed.

## Growing it into a real game

Grow it in small steps, and make sure each step plays before starting the next. For Pong, the steps could be:

1. **Paddles.** Each dot only moves up and down, and stays at its own side of the field.
2. **A ball.** The bot moves it in `Match.step()`, and it bounces off the top and bottom walls.
3. **Hits.** The ball bounces off the paddles.
4. **Points.** A ball that gets past a paddle scores for the other player. Send the score only when it changes, not on every update.
5. **Rounds.** A round starts when both seats are filled, and ends when someone reaches the winning score.

Some habits that keep a game easy to change:

- **Keep the rules away from Discord.** `Match` knows nothing about Discord, so you could run it from a plain Python script to try things out.
- **Keep the game's state in the cog, never on `conn`.** Send all of it when a page connects (in `join`). Then a page that reconnects after a dropped network simply carries on.
- **Never make the bot wait.** No `time.sleep()` and no `requests` in your handlers: the whole bot stops while they run. Use `await asyncio.sleep()` and async libraries instead.

## Where to read more

ActivityHub's own guide, [DEVELOPERS.md](../activityhub/DEVELOPERS.md), explains every part in plain words. The parts this game uses:

- [Ten rules that save you hours](../activityhub/DEVELOPERS.md#ten-rules-that-save-you-hours): read these first.
- [Multiplayer with live connections](../activityhub/DEVELOPERS.md#6-multiplayer-with-live-connections): `join`, `message`, `leave`, rooms and close codes.
- [Speed and fast-paced games](../activityhub/DEVELOPERS.md#speed-and-fast-paced-games): the update loop and smooth drawing.
- [Who's here](../activityhub/DEVELOPERS.md#7-whos-here): `hub.status()`, `hub.busy()` and the people button.
- [Common problems](../activityhub/DEVELOPERS.md#13-common-problems): most error messages you will ever see, each with its fix.

Other things you may want later:

- **Paying credits for a score:** the guide's [Quick start](../activityhub/DEVELOPERS.md#3-quick-start-click-counter) and [What to trust, and paying out](../activityhub/DEVELOPERS.md#5-what-to-trust-and-paying-out).
- **Every field and call in one place:** [REFERENCE.md](../activityhub/REFERENCE.md).
- **A bigger multiplayer game to read:** [Marble Munch](../marblemunch/). It adds smoother drawing (two updates behind), seats held for a while after a drop, and computer players in empty seats.
