# ActivityHub Changelog

## 0.1.6

- A frame rate counter shows in the bottom left corner, over the menu and every game. Each player can hide it with **Frame rate** in **My look**. Server admins and the bot owner can change whether it starts on, like the other look settings. It is on by default.

For game developers:

- `DEVELOPERS.md` has a new part in section 1 comparing a game cog with making your own Activity: which jobs the hub does for you, what stays the same, and what you give up.

## 0.1.5

- On phones, the menu's header, the settings panel and the included games' top bar now sit below Discord's own back button and **Leave** button instead of under them. The hub passes Discord's spacing on to every game: see `DEVELOPERS.md`.
- **Retry save** in the included games now works when the save failed on the bot, and when the bot saved the score but its answer never arrived. Before, the retry was told the round wasn't found.
- Saving **My order** in a server with every game turned off no longer wipes the order you set for other servers.
- Reloading a game cog keeps its key. Before, another cog that wanted the same key could take it during the reload.
- A cog load that Red cancels while the web server starts no longer leaves parts of the cog running.
- A game cog whose old copy fails late during a reload no longer hides why its new copy was refused in `[p]activityhub games`.

## 0.1.4

- Logins pause when Discord rate limits them, instead of asking again. The login address is public, so a flood of fake logins could otherwise get the bot's address banned from Discord for a while.
- Reset then Save in **My order** now goes back to alphabetical order. Before, the old order came back.
- A game whose cog was unloaded after the menu listed it opens a page with a **Back to the menu** button instead of a dead end.
- The included games keep a score whose save failed on the way, with a **Retry save** button, and leaving with **Menu** waits for a save still on its way. Clicking a top bar button no longer catches the next Space or Enter meant for the game, a cancelled swipe can't turn into a move later, and a round stays open as long as the login (12 hours) so one paused for a while still counts.
- The menu forgets the player's Discord access token once Discord accepts the login, logins needed at the same moment share one, a file or text dropped on the order list leaves the order alone, and a menu sound that fails to load is tried again.

For game developers:

- `activityhub_game()` is checked when a game registers, and every refusal says how to fix it: handlers that don't take the arguments the hub passes (raw routes are `(request, ctx)`), `self.x()` written for `self.x`, misspelled fields (with "did you mean"), bad keys (with a suggested key), routes listed twice, scope names Discord can't accept, pictures outside `web_dir`, a `web_dir` holding the cog's own code, and an `index.html` that isn't UTF-8. Absolute paths in the page, unknown scopes and a huge `web_dir` get a warning in the bot log. `[p]activityhub games` shows each game's scopes.
- A relative `web_dir` starts at the cog's own folder. Files and folders whose names start with a dot are never served. `.gz` and `.br` files are sent with `Content-Encoding`, so engine builds load as exported. A page with no `<head>` keeps its doctype first. A game frame that lands on a missing page gets a Back button instead of a bare 404, and a link to `index.html` gets the page with the helper.
- A game cog whose `activityhub_game()` waits (for the bot to be ready, say) no longer holds up loading. A cog refused because another cog held its key gets the key once that cog unloads.
- Actions: `{"error"}` must be text (`{"error": None}` is no error), NaN and Infinity are refused, a missing action names itself, and the bot owner sees the reason behind "Something went wrong.".
- Live connections: `leave` sees an empty room when the last player leaves, players whose network vanished are dropped after about a minute (the helper answers the hub's heartbeat itself, so this works behind proxies that drop WebSocket pings), one player who stops reading can't hold up everyone's broadcasts, close codes 4000-4099 are kept for the hub, a game without `"socket"` closes with 4004, and `conn.send()` refuses the hub's own `activityhub` field.
- `hub.api()`, `hub.fetch()` and `hub.socket()` log the player in again and retry once, so a bot restart or an ActivityHub reload no longer throws players out of their game. The page also gets `hub.player.displayName`, listeners added with `hub.discord.subscribe()` are removed when the game closes, and the console says when a game makes its own `DiscordSDK` or a link leaves the game.
- `hub.launch()` takes a hybrid command's `ctx`, explains a text command or an earlier reply, forgets the game when the launch fails, and returns whether the Activity opened.
- `DEVELOPERS.md` now covers testing your Python without Discord, how handlers run at the same time, every close code, uploads over 1 MB, bundlers and engine builds, cooldowns, a Play button that survives restarts, and sharing your game.

## 0.1.3

- The Orb menu now fits phone screens. Game descriptions wrap inside their tabs instead of running off the edge and letting the whole menu slide sideways, the picked game stays lined up with the others, and the server name's glow no longer shows a box around it.

## 0.1.2

- The Orb menu's sounds and background loop are half as loud, closer to the included games' sound effects.

## 0.1.1

- `[p]slash sync` no longer fails once Activities are on. Discord refuses a sync that leaves out the app's launch command (the one that starts the Activity from a voice channel), so the hub adds it to every sync. If the launch command is missing, the next sync creates it.

## 0.1.0

Initial release.

- Comes with three games: Snake, Brick Breaker (with power-ups) and 2048. Each keeps every player's best score per server and shows the server's top 10 on a leaderboard. The bot replays Snake and 2048 rounds from their moves, and checks Brick Breaker rounds against the levels and the clock, so a changed page can't fake a score. Brick Breaker replaces the separate BrickBreaker cog, without its credit payouts.
- The included games share one frame: a title screen with the controls, pause (Esc or P, and by itself when a moving game loses focus), sound with a mute button, and a results screen with your rank.
- One Discord Activity with a menu of games. Any loaded cog with an `activityhub_game()` method shows up in the menu by itself, and disappears when it unloads. No Developer Portal, tunnel or slash sync step per game.
- The hub runs the web server, the Discord login and launching. Game cogs only bring their game page and their Python actions.
- `/activities` and `[p]activities` (a button that survives restarts) open the menu. Game cogs can open their own game straight from a command.
- Players pick their own look and game order, and they follow them to every server. The Standard theme looks like Discord, with a choice of layout, color and background. The Orb theme is a green glowing console-style menu: games sit on pods along a ring around a big orb, with a large preview of the selected game, arrow key and mouse wheel movement, and menu sounds that can be turned off. Server admins set a server look and turn games on or off; a game that is off can't be played in that server at all. The bot owner sets the defaults.
- The bot owner's Defaults tab in the menu settings can turn games off in every server. A game the owner turned off leaves every menu, can't be opened, stops anyone playing it, and has no switch in the server settings. Each server's own on/off choice is kept for when the owner turns it back on.
- Games can give a wide `thumbnail` picture as well as an `icon`. The menu shows it on grid and list cards and in the Orb theme's preview.
- Game cogs describe themselves with an `async def activityhub_game()`. Their handlers get a `ctx` proven with Discord (`ctx.author`, `ctx.guild`, `ctx.channel` and the activity session), plus simple actions, live connections for multiplayer, and raw routes for uploads.
- The menu opens faster: its scripts load together, the login settings come with the page, the first menu comes back with the login, and the bot checks the login and the activity session with Discord at the same time. The browser console shows how long each loading step took.
- Picking a game fades the menu away and fades the game in once its page has fully loaded, so a game never shows up half built.
- `[p]activityhub check <public host>` checks every setup step and says what to fix. `[p]activityhub games` lists installed games and why a game cog was refused.
- File addresses carry a version code, so a caching service like Cloudflare never serves an old copy.
- `DEVELOPERS.md` walks through building a game step by step, with a complete example, a full reference, and fixes for common problems.
