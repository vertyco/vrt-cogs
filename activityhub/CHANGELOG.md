# ActivityHub Changelog

## 0.13.4

For game developers:

- A game that listens for Discord's `THERMAL_STATE_UPDATE` (how hot the phone is) now hears the phone's current heat as soon as it subscribes, as Discord promises. Before, the menu was already listening, so Discord's toolkit never asked Discord again, and the game heard nothing until the heat next changed.
- DEVELOPERS.md has a new part, "Phone heat, the small window and turning sideways": how to turn effects down on a hot phone, fit Discord's small floating window, and switch layouts when the phone turns.

## 0.13.3

- The hub's web server no longer writes a line to the bot's log for every file a player's game loads. Opening one game used to add dozens of `aiohttp.access` lines.

## 0.13.2

- The Orb menu turns much more smoothly on phones. Swiping the ring used to redraw every game button on every frame; now the buttons slide and light up without being redrawn. On a 120 Hz Android phone a swipe went from about 63 to about 109 frames a second (with the orb change below), and dropped frames went from 45% to 6%.
- The orb in the middle costs the phone far less to draw: its swirl's blur is drawn once instead of every frame, and the swirl and goo no longer use a blend that makes the phone copy what's under them every frame. They look the same.
- The Settings panel shows the hub's version in small letters at the bottom left.
- In the Orb menu on a phone, the step in each tab's top edge now sits the same distance back from its end on every row, and a game name too long for the middle row's tab is cut at that length on every row.

## 0.13.1

- Settings tabs that don't fit on one line now wrap onto the next, so every tab shows. Before, the last tabs (like Stats) sat past the edge of a row you had to scroll sideways, with nothing showing it could scroll.

For game developers:

- DEVELOPERS.md's checklist now asks a game that makes sound to have its own volume controls inside the game. The hub has no volume setting.

## 0.13.0

- The hub can open in DMs, group DMs and servers the bot isn't in. Turn on **User Install** for the app in the Developer Portal, then run `[p]slash sync`: the sync makes Discord's Launch button and `/activities` work in those places too. Until Discord verifies the app, only the bot owner and the app's developer team can open it there.
- `[p]activityhub check` says whether the hub can open outside the bot's servers, and what to do if it can't.
- Outside the bot's servers, a game that needs a server shows a "Servers only" note on its card, and a message instead of opening.
- `[p]activities` now says "Click to open the Activity Hub", and its button (and a pinned button with no label of its own) reads **Open Activity Hub** instead of **Open Activities**. Buttons already on messages keep their old label.

For game developers:

- New `opens_in` field in `activityhub_game()`: `"server"` for a game that only opens in servers the bot is in, `"everywhere"` (the default) for one that also opens in DMs and servers the bot isn't in. Elsewhere the menu marks a `"server"` game and won't open it, and its actions, raw routes and live connection refuse the player. See "Servers only" in DEVELOPERS.md.

## 0.12.0

- Settings has a new **Stats** tab for server admins and the bot owner. It shows how often each game gets played, by how many people, for how long, and how many plays were on phones, plus plays per day and the busiest hours of the day, for the last 7 days, 30 days or all time. Admins see their own server. The bot owner can pick any server, all of them together, or plays outside servers.
- The hub keeps a play log: one line each time someone opens a game, with the server, the game, phone or computer, when it started and how long it lasted. Time with the Activity hidden doesn't count, and time in the menu isn't logged. The log stays on the bot, in a small database file in the hub's data folder.
- ActivityHub now needs `piccolo` and `aiosqlite`. Red installs them with the cog.

## 0.11.0

- Settings no longer has the **Show my name to players from other servers** switch. Games show players' Discord names to everyone they play with.

For game developers:

- `ctx.shows_name()` is gone, along with DEVELOPERS.md's "Players from other servers" part. A game in an `"everywhere"` room shows real names without asking.

## 0.10.1

For game developers:

- DEVELOPERS.md has a new part, "Aiming: locking the mouse", for games where players aim with the mouse, like a shooter. It shows how to hide the cursor and keep it on the game (Pointer Lock) from a click, read how far the mouse moved, pause when Esc lets go, and what to give phones, which have no mouse to lock.

## 0.10.0

- In the Orb theme, the number of people playing a game shows in full on its icon. Before, the small bar joining the icon to the game's name covered half of it.
- Settings has a new **Show my name to players from other servers** switch in the **My look** tab, off until you turn it on. Games that put players from different servers together show everyone else a made-up name for you unless it is on.

For game developers:

- A game can now let players from other channels play together. The new `room` field in `activityhub_game()` says who shares a room: `"window"` (everyone in one Activity window, as before, and still the default), `"server"` (everyone in the same Discord server, whichever channel they opened the Activity in) or `"everywhere"` (everyone, in every server and DM). `conn.room`, `conn.peers()` and `conn.broadcast()` then reach the whole room with no other code. "Who plays together" in DEVELOPERS.md explains what changes with a wider room.
- `ctx.room_id` and `room.id` name the player's room, so a game can keep its state per room. In a window room they are the window's id. `room.instance_id` is `None` in a room that spans windows.
- `room` can also be an `async def` that takes the player's `ctx` and picks their room, so a game can let server admins turn server-wide play on or off, or offer a public mode next to a private one. A function that fails, is slow or answers something else puts the player in their own window and logs a warning.
- `await ctx.shows_name()` says whether the player turned on **Show my name to players from other servers**. DEVELOPERS.md's new "Players from other servers" part explains Discord's rule: in a room that mixes servers, players from other servers see a stand-in name unless the player said yes.
- DEVELOPERS.md also covers keeping a match to one channel inside a wider room, letting latecomers watch, and giving hosts a kick and players a report button.
- The devkit's type hints and test stand-ins know `ctx.room_id`, `room.id` and `ctx.shows_name()`.

## 0.9.0

- On a phone or tablet, the Orb's ring is now a picker wheel, like an iPhone's. The selected game sits in the middle of the ring and the games slide along under your finger: sliding up brings the next ones in. A flick keeps the ring spinning and it slows to rest on a whole game, with a click sound for each game it passes. A finger on a spinning ring stops it. Pulling past the first or last game stretches a little and springs back. The lit look of the selected game slides along with the ring, so a game lights up as it nears the middle instead of the light jumping from game to game, and the panel fades over to each game in place instead of flipping over for every one. A tap on any game still opens it right away. Computers keep the ring as it was.
- A finger on a card, pod or button now shows it pressed, and the look goes as soon as the finger slides.
- When Discord says a phone is running hot, the Orb's moving background pauses until the phone cools down, and a small thermometer shows in the header. Tapping it says why.
- On phones, swiping the Orb menu works from the first touch. Before, nothing moved until you had tapped the screen once: inside Discord, an iPhone ignores the menu's attempts to move the keyboard focus until the first tap, and the selection was waiting on that focus. The mouse wheel and pointing at a game no longer wait on it either.
- An iPhone never holds a tap back to check for a double-tap zoom, which can cost about a third of a second per tap. The menu runs in a frame inside Discord, where phones ignore a page's own zoom settings, so it now says so in a way frames keep. This covers the menu, Settings, the people lists and the included games.
- Each move along the Orb ring does less work, so the ring keeps up with a fast thumb.
- A tapped card, button or pod no longer stays lit up as if the mouse were on it. Hover looks only show for a mouse.
- Scrolling Settings or the people list to its end no longer scrolls the menu behind it.
- In the Standard theme, scrolling the list never waits on the menu's script, and the Gradient background stays put while the list scrolls instead of being redrawn (or, on iPhones, stretched down the whole list).
- The Orb's up and down arrows are easier to hit with a finger, without taking taps meant for the game next to them.
- A long press on the menu no longer picks out text or opens a picture's menu.

For game developers:

- DEVELOPERS.md explains three phone traps every game page runs into: taps that wait unless the page sets `touch-action: manipulation`, `focus()` doing nothing until the player's first tap, and hover looks that stick. The quick start's page and the checklist cover them.

## 0.8.1

- A game your device can't open now dims only its picture and words. Its "Desktop only" (or "Mobile only") note and the bubble showing how many people are playing stay easy to read.
- In the Orb theme, tapping a game your device can't open no longer plays the select sound before the message saying why.
- In the Compact layout, "Desktop only" always shows in full, and a long currency label is the one cut short, down to just its coin on a tight row. A cut label shows in full while the mouse is on it, or while the keyboard is on its game.
- If Discord refused a game's extra permissions and the plain login after that failed too (like a network blip), later logins stayed on the plain login. They now ask for the extra permissions again.

For game developers:

- Each number in `requires` can be at most 9 digits. A longer one gets the usual `requires must be a version like "0.8.0"` refusal instead of a confusing error.
- Clearer DEVELOPERS.md and REFERENCE.md: `ctx.is_admin()` and `ctx.is_mod()` are listed with the rest of `ctx`, the "Discord refused a login" log line has its own table, and the devkit files are linked.

## 0.8.0

- A game asking for a Discord permission that Discord refuses no longer stops everyone from logging in. The menu logs the player in without the extra permissions, every game still opens, and the bot log names the permissions and the games that asked for them. Pressing Cancel on Discord's permission prompt works the same way.
- A game made only for computers (or only for phones) shows "Desktop only" (or "Mobile only") on its card on the other one, dimmed. Tapping it, or Join and launch buttons for it, show a message instead of opening it, and you stay where you were.

For game developers:

- `await ctx.is_admin()` and `await ctx.is_mod()` say whether the player is a server admin or a server mod where the Activity runs. Admins are the bot owner, the server's owner, and members with Manage Server or Red's admin role. Mods are admins plus members with Red's mod role.
- **Breaking:** raw routes take `(ctx, request)`, like every other handler. A route still written `(request, ctx)` is refused with a message saying to swap them.
- New optional `requires` field: the oldest ActivityHub your game works with, like `"0.8.0"`. A bot with an older hub refuses the game with a message saying to update ActivityHub.
- Keys starting with `hub-` are kept for ActivityHub's own games.
- **Breaking:** a game's `economy` function gets the player's `ctx` instead of the server. Read the server from `ctx.guild`. The badge can now differ from one player to the next.
- An action reply with a top-level `activityhub` key fails like a broken reply. The name is kept for the hub's own fields.
- **Breaking:** a game's page can only import `"activityhub"` from the hub. Other `"activityhub/..."` names no longer reach the hub's files.
- New `devkit/` folder with files to copy: the quick start's Click Counter cog, type hints for your Python (`hubtypes.py`) and your page (`activityhub.d.ts`), test stand-ins (`fakes.py`), and the random number generator the included games share between the bot and the page (`rng.py` and `rng.js`).
- New optional `platforms` field: `["desktop"]`, `["mobile"]` or both (the default). Pages get `hub.platform`, `"desktop"` or `"mobile"` inside Discord and `null` in the preview.
- REFERENCE.md says which Python call on the hub cog is promised: `launch()`. Everything else on it may change in any release.

## 0.7.0

- Games that use the server's currency can say so on their menu card: a coin and a short line, like "Cash in up to 1,000 credits". Snake, 2048 and Brick Breaker show it while their payouts are on.
- The labels catch up when you come back to the menu from a game, so turning a game's payouts on or off shows on its card right away.
- Server admins can hide these labels with **Show currency labels** in the menu's server settings. With a global bank, the switch is the bot owner's, in the **Defaults** tab.

For game developers:

- New optional `economy` field in `activityhub_game()`: `None`, a fixed line, or an `async def` that takes the server and returns a line or `None`. At most 40 characters. See "Currency labels on the menu" in DEVELOPERS.md.

## 0.6.1

- In the Orb menu, a long **Who's here** panel scrolls with the mouse wheel and a finger. Before, the wheel, a slide or the arrow keys in it moved the games behind it instead, and the panel stayed stuck at the top.
- Saving settings right after the bot restarted keeps your changes: the menu logs in again by itself and saves them. Before, the panel closed and the changes were lost.
- When the bot can't be reached at all (a dropped network, or the bot is down), the menu and the included games say "Couldn't reach the bot. Check your connection and try again." instead of the browser's own words, like "Failed to fetch".
- In the Standard theme, the list of who's playing a game moves with its card when the page scrolls, instead of staying behind.
- Closing the **Who's here** panel in the menu puts keyboard focus back where it was, like the row of faces in the header. Opening Settings moves keyboard focus into it, and closing Settings puts it back on the gear (or the Settings pod in the Orb).
- In a DM call, the menu's header shows your display name instead of your account handle.

For game developers:

- `hub.api()` throws a `HubError` with status `0` and a plain message when no answer comes back at all, instead of the browser's own `TypeError`. `REFERENCE.md` says so.

## 0.6.0

- The menu's **Payouts** settings tab is gone. Server admins now set each included game's payouts from a gear button in that game's own top bar, the way Marble Munch does it. The gear sits in the bar between rounds: before a round's first move, and on the results screen. During a round, paused or not, an admin's bar is the same as everyone's. Only people who can change the payouts see the gear: server admins, or only the bot owner when the bank is global.
- The gear opens that game's settings: whether it pays out, what one point pays, the most one cash-in pays, and the cash-ins a day. While it is open, no key, tap or swipe reaches the game, so a round can't start behind it.
- Payout settings saved before carry over unchanged.
- On phones the games' top bar packs its buttons a little closer, and your score always shows whole. On small phones with friends in the same game there may not be room for your best score too, so it steps out of the bar (it still shows on the title and results screens).
- In the included games, a round waiting for your first move no longer counts as busy, so a friend's Join takes you along without asking first. Your first move makes it busy.
- Leaving a round of an included game by Join, or by closing the Activity, now saves its score so far, the same as the Menu button.
- The included games' score strip cuts long names the way every other game does: 11 characters and "…", never splitting an emoji.
- In the people panel, keyboard focus on **Invite friends** stays there when the list changes, and screen readers name the question Join asks before taking you out of a round. An arrival note from a people button in the middle of a game's screen stays on the screen.
- In the menu, the list of who's playing a game keeps clear of a phone's notch and Discord's buttons at the sides too. When it closes with keyboard focus in it (Escape, or its last player leaving), focus goes back to that game's card.
- The bot no longer sends everyone in the window a new people list when a player's game reports nothing new.

For game developers:

- The reference (every field of `activityhub_game()`, `ctx`, the handlers and the page side) moved out of `DEVELOPERS.md` into its own page, `REFERENCE.md`. `DEVELOPERS.md` keeps the tutorial and the topics, and its later sections are each numbered four lower.
- `REFERENCE.md` has type declarations for the page side (`activityhub.d.ts`), so editors like VS Code autocomplete `hub.` calls and flag typos in plain JavaScript.
- `DEVELOPERS.md` is now written for someone who has never made an Activity. It opens with a "Start here" part: who the guide is for, a table of which section answers which question, the words used everywhere, and ten rules that prevent the most common mistakes. The quick start explains what each piece of code does and says what to check when a step doesn't give what it should. The pay-at-the-end example is a whole cog you can copy, and the multiplayer and common problems sections are split into smaller parts. Section numbers stay the same.
- `DEVELOPERS.md`'s "Who's here" warns against rebuilding buttons on every people list, which loses clicks.
- `hub.api(name, data, options)` takes an optional third argument. With `{ keepalive: true }` the request still reaches the bot after your page is gone, so your game can save a player's progress on `pagehide` when Join or closing the Activity removes its frame. `REFERENCE.md` and the Join part of `DEVELOPERS.md`'s "Who's here" explain it.

## 0.5.0

You can now see who's playing what. Everyone who opened the Activity from the same voice channel shows up in the menu and in every game.

- In the menu, a game that people from your voice channel are playing has a number bubble on its corner. Resting the mouse on the game lists them, with what each one is doing (like `Playing · 1,230`) and a **Join** button, plus how many play it in other channels of the server. On a phone, tap the bubble; tapping the rest of the card still opens the game.
- The Orb theme lists them on its big screen for the selected game, under **Playing now**.
- The menu's header shows the faces of everyone else in your voice channel, each with a small badge of the game they're in. Press the row to see them all. Alone, it shows **Invite friends** instead, which opens Discord's invite window.
- Every game has a people button. It opens a panel with everyone in your voice channel, grouped by the game they're in, with Join buttons to hop into another game, a count of people playing in other channels, and **Invite friends**.
- When someone opens the game you're in, a short note slides out of the people button: "Ann joined".
- **Join** opens the other person's game. In the middle of a round, it asks first ("Leave Snake to join Ann in Tanks?"), with **Stay** picked by default, so a stray tap doesn't throw away your round.
- People whose Discord is in the background (a locked phone, another app in front) show dimmed, as away.
- Snake, 2048 and Brick Breaker put the people button in their top bar, show a live strip under it with the scores of everyone playing the same game, say "You passed Ann!" when you go above someone, and end with your place among them, like "2nd of 3 here right now".

For game developers:

- New page calls: `hub.status(text, data)` sets what the player is doing for everyone to see, `hub.busy(true)` makes Join ask before taking them out of a round, `hub.people` and `hub.onPeople()` list everyone in the window, `hub.follow` says whose Join opened your game, and `hub.peopleButton()` and `hub.openPeople()` let you place the people button and open the panel yourself. In Python, `conn.follow` is the user id of the friend a player joined. Games that use them need ActivityHub 0.5.0 or later.
- A game that does none of this still gets the people button, the panel, arrival notes and its menu bubble.
- `DEVELOPERS.md` has a new section 11, "Who's here", with examples, and the Click Counter tutorial gains a step that sets a status line. The sections after it are each numbered one higher.

## 0.4.2

- Swiping through the Orb menu on a phone goes the right way now: the highlight follows your finger. Slide down or right for the next game, up or left for the one before.

## 0.4.1

- Pinning moved to `[p]activityhub pin` and `[p]activityhub unpin`, so server admins find them in `[p]activityhub`'s help. They work the same as before. `[p]activityhub` is now open to server admins, who see only `pin` and `unpin` there; the setup commands stay for the bot owner.
- `[p]activities` is a plain command again: it only posts the **Open Activities** button, and its help points to `[p]activityhub pin`.

## 0.4.0

The included games can now pay players in the bot's currency for their scores, the way Neopets pays for its games.

- After a round of Snake, Brick Breaker or 2048, the results show what the score is worth and a **Cash in** button. Each point pays a set rate, up to a most-per-cash-in, and each player gets a few cash-ins per game per day. Playing another round first gives that score up, so players save their cash-ins for their best rounds. Since every cash-in is capped, a faked score can't earn more than a strong honest round.
- Server admins set it up in a new **Payouts** settings tab: for each game, the credits one point pays, the most one cash-in pays (1,000 by default) and the cash-ins a day (3 by default). Payouts start off, so no game pays until an admin turns it on. Cash-ins come back at midnight UTC.
- With a global bank every server shares one balance, so only the bot owner sees the Payouts tab. The owner's settings apply in every server, and the daily cash-ins count across servers.
- A cash-in that can't pay (none left today, a score worth nothing yet, or a balance already at the bank's maximum) doesn't use one up. A cash-in that would go over the maximum pays up to it.

## 0.3.0

- A pinned **Open Activities** button can have its own label, emoji and color. Type them after the message link: `[p]activities pin <message link> Play games emoji: 🎮 color: blurple`. The color can be blurple, grey, green or red, and the emoji can be a normal emoji or one of the server's own. Anything left out keeps the usual look: "Open Activities" in green, with no emoji.
- Pinning again on a message that already has the button changes its look instead of saying it's already there. Only the parts you type change, so `[p]activities pin <message link> color: red` keeps the label and emoji.
- Each pinned button keeps its own look, so different messages can have different buttons.
- A pinned button can open one game instead of the menu: `[p]activities pin <message link> game: Snake`. It works for the bundled games and for any game cog that adds itself to the hub. The game can be typed by its name or its key, with no quotes needed even when the name has spaces, and the button reads "Play Snake" unless you give it a label. Pressing it opens the Activity straight into that game, and like the menu button it keeps working after the bot restarts.
- A message can carry the menu button and a button for each game. `[p]activities unpin <message link> Snake` takes off just that game's button, and leaving out the game takes off the menu button. A game's button can still be taken off after its cog is uninstalled, by typing the game's key.

## 0.2.2

- In the Orb theme on a computer, the mouse wheel scrolls through the whole list of games with the mouse resting on the ring. Before, once the ring had to scroll, the game sliding under the mouse took the selection back, so the wheel never got past the games already showing. A game now takes the selection only when the mouse moves onto it, and the wheel and the arrow keys keep it until the mouse moves away.
- While the wheel or the arrow keys have the selection, the game under the mouse no longer lights up, so only the selected game does.

## 0.2.1

The Orb theme on a phone held upright is laid out again, and sliding works on real phones.

- Sliding a finger on the ring works on phones. Discord's buttons and the phone's home bar made the page taller than the screen, so the phone scrolled the page under the finger instead of moving between games. The menu is now exactly the size of the screen, and a slide holds the page still itself.
- The panel for the selected game hangs at the top under the server's name, from an arm reaching in from the top right corner, like on a big screen. The ring of pods fills the space below it, where a thumb reaches. Before, the panel sat at the bottom, where it covered the arrow under the ring and the arm crossed the bottom tabs.
- Everything fits between Discord's buttons at the top and the home bar at the bottom, and moves down when a notice shows under the header.
- The orb grows to fill the space under the panel, and the pods spread out along the ring when they all fit. Short phones show more games at once.
- The panel is the same height for every game, so the ring never jumps when the selection moves.
- The frame rate counter moves to the bottom right corner, clear of the pods and the arrow.
- The "No games" message sits under the panel instead of on top of it.
- Text on the ring and the header can't be picked out by a long press.

## 0.2.0

The Orb theme is rebuilt to look and move more like the console dashboard it copies.

- Each game's icon sits inside its pod, a glass bubble in a lit socket, on desktop and on phones. Settings gets a cog.
- The tabs are cut like the original's, with a raised strip on top and chamfered corners, in blocky lettering.
- A see-through robot arm holds the panel for the selected game. Every move turns the old panel away on the arm and the new one in, while the arm lights up and its wrist spins in place. The panel gains a **Select** button that opens the selected game.
- The orb sits in a frame of see-through fins with holes punched through them, which turn a notch with every move and swing round when Settings opens or closes. Glowing goo slides over the orb, and a flat band circles it.
- The background is a web of uneven cells curving around the orb, like the inside of a sphere.
- Settings swings in like another panel, in the theme's colors.
- **Glow color** in **My look** (and the server and default tabs) colors the whole Orb theme: the orb, pods, tabs, web and panels. It has the same color choices as the Standard theme's accent, and keeps its own setting, so each theme keeps its own color. Green is the default, and a gray glow gives a silver theme.
- On a phone held upright the Orb theme keeps its ring: the orb rises from the left edge with the pods curving around it, and the panel docks at the bottom with the arm reaching in from the side. Sliding a finger up and down moves between games, like on a phone held sideways. Before, it was a plain list.
- Small screens held sideways show the panel too, with the orb partly off the left edge to make room.
- The menu opens with the pods popping onto the ring one after another, and does again on coming back from a game. Opening a game dives into the orb as the menu fades.

## 0.1.14

- Orb is now the default theme, for every server and player that hasn't picked one.
- The server owner always sees the **This server** settings tab, even without a role that has Manage Server. The tab's theme is the default every member sees until they pick their own in **My look**.
- In the Orb theme on a phone held sideways, sliding a finger up and down the ring or across the screen moves between games, one per step, with the ring gliding along. A tap still opens a game.
- New Orb menu sounds: a soft tick when moving, two rising bell notes when opening a game or Settings, and two quieter falling notes when going back.
- `[p]activityhub check` tests the URL mapping through Discord's own proxy, the same way players load the menu, and names the address the mapping points at. The public host is now optional.
- When a public host is given and the bot can't reach it, the check says why: the name doesn't resolve, nothing accepted the connection, the HTTPS certificate isn't valid, nothing answered within 10 seconds, it answered with an error status, or something other than ActivityHub answered.
- If Discord still reaches the hub, a failed public host is a warning instead of a failure, since players can play. A name that doesn't resolve then gets a note: the bot's DNS server probably remembered a "no such name" answer from before the record existed, which clears by itself.
- The checks that go over the network run at the same time, so the check finishes sooner.

## 0.1.13

- `[p]activities pin <message>` puts the **Open Activities** button on any message the bot sent in the server, keeping the message's text, embeds and other buttons. `[p]activities unpin <message>` takes it off. Both need the Manage Server permission or Red's admin role.
- The button works on any message by its ID alone, so it keeps working after restarts without the bot saving which messages have one. Buttons posted before this update keep working too.

## 0.1.12

- `[p]activityhub view` shows where the web server listens, the default address (`127.0.0.1:8742`), whether it is running, whether a client secret is saved, and how many games are installed.
- `[p]activityhub setup` (or `setuphelp`) walks the bot owner through the whole setup, one page per step: the Developer Portal, the client secret, giving the web server a public HTTPS address (Cloudflare Tunnel, a quick test tunnel, Caddy or nginx), the URL mapping and the final check. The steps are filled in with the bot's own address.
- The README has the same walk-through for each way of getting a public HTTPS address.

## 0.1.11

For game developers:

- `DEVELOPERS.md` section 19 also points at Tanks, a turn-based game cog in the same repo: one player's turn on a slow live loop, and whole shots worked out at once and played back on every screen.

## 0.1.10

For game developers:

- `DEVELOPERS.md` section 19 points at Marble Munch, a full multiplayer game cog in the same repo, with a table of which file shows which pattern: rooms, a locked update loop, seats, reconnects, computer players and smooth drawing.

## 0.1.9

- A page that floods a live connection is cut off: more than 300 messages or 1 MB a second, on average over 5 seconds, closes it with code `4029`, and the bot's log names the player. Real games never get near it, but a page changed to flood the bot could otherwise keep it busy.
- While a game has a live connection open, the frame rate counter also shows its delay, the round trip to the bot and back, like `60 FPS · 85 ms`.

For game developers:

- `conn.room` is everyone playing your game in that window, as one object: `room.broadcast(data)` reaches them all, and `room.connections` lists them. A timer or a loop no longer has to pick one player's connection to broadcast from, and a loop that holds the room keeps reaching players who leave and come back.
- `hub.stat(text)` adds a short text at the end of the frame rate counter, like `60 FPS · 85 ms · 30 TPS`, so a live game can show its update rate. It goes away when the game closes, and players who hid the counter don't see it.
- The page's `conn.latency` holds the latest round trip in milliseconds, timed by the helper every 2 seconds.
- `DEVELOPERS.md`: the update loop example uses `conn.room`, a new note explains why single updates wobble (Windows' 16 ms clock steps and network jitter) and how to hide it, the speed section shows how to display your update rate, and the testing example has a stand-in for the room.

## 0.1.8

For game developers:

- A code comment on the launch command now says it runs from any channel the app launcher opens in (voice, text or DM), not only voice channels.

## 0.1.7

- The bot's log gets a warning when the bot froze for a quarter of a second or more while players were in live games, at most once a minute. A frozen bot stalls every live game, so this points at a cog that needs fixing.
- Replies and live messages are turned into JSON with orjson, which comes with Red: about ten times faster on the worker the whole bot shares, and a little smaller, since it leaves out spaces.

For game developers:

- Live connections reconnect by themselves after a restart, a player who fell behind or a dropped network, trying for up to a minute with growing, partly random waits. `conn.onReconnecting(handler)` and `conn.onReconnected(handler)` tell the page, `conn.onClose` now runs only once the connection is gone for good, and the page's `conn.send()` returns `false` instead of sending while it reconnects.
- Replies and live messages can now hold dataclasses, datetimes, UUIDs and enums. Whole numbers bigger than 64 bits are refused.

- `conn.send()` and `conn.broadcast()` on a live connection now queue the message and return right away. Each player's messages wait in their own queue and still arrive in order, so a player with a stalled network never holds up your code or the other players. Before, a broadcast could wait up to 10 seconds on one stalled player. A player who falls 4 million characters behind is disconnected, like one who can't take a message for 10 seconds. `conn.close()` now waits for the messages queued before it.
- `DEVELOPERS.md` has a new part in section 10, speed and fast-paced games: keeping the bot's worker free, a steady update loop, small messages, measuring delay, surviving restarts, where the bot should run, and connecting to your own game server when the bot isn't enough. The reconnect example now waits a random few seconds.

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
