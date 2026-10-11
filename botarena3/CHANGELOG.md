# Changelog

## 0.1.1

- Opening the Activity while your battle runs, or joining a friend's battle, now takes you to the battle even when its art is slow to load. Before, the intro could finish first and leave you on the menu while the battle went on without you.
- A battle of your own that starts while the menu plays out (started from another device) now shows, instead of the menu's choice.
- A window that lost its connection just as your battle in another window ended no longer stays stuck on the battle screen. When it reconnects, the bot says whether you still have a battle, and if not the page moves on.
- A page the bot keeps refusing now waits a little longer between tries, up to 15 seconds, instead of asking every 2 seconds for ever.
- A shop list that gets too short to scroll while you drag its scroller now stops scrolling.
- The battle loop does a little less work each step, and the cog no longer keeps a lock in memory for every player who ever played.

## 0.1.0

First release: Bot Arena 3 for ActivityHub, a port of the Flash game from Armor Games.

- The whole original game: its parts, prices, shop, 15 arenas, 7 challenges and win screen, with the original's numbers.
- The original's art, sounds, music and pixel font.
- The original's sponsor logos and links are left out.
- The original's intro, main menu, instructions and settings, scaled to fit any window, on desktop and phones. Continue picks up your career on any server. New Career asks before replacing one. The back button stays on every screen. Settings leaves out the old Flash quality buttons.
- The original's shop: buying, selling for half price, mounting plating before weapons within what a chassis can carry, at most five robots, renaming, team colors, and the panels that explain why a team can't fight yet.
- The original's arena list, with its locked, too poor and too heavy marks.
- Battles follow the original's rules: robots look for targets, aim, fire at the original's speed, turn away from walls and other robots, and leave burning wrecks that still block shots. Damage hurts only the other side, and repairs heal only your own robots, up to full.
- You give orders by dragging, with mouse or touch: drag to a spot to send a robot there, or onto another robot to follow it.
- The bot runs each battle at the original's speed and sends it to the players and to anyone watching. A page that reconnects gets the whole battle back, even after the Activity was closed and opened again, and its orders still reach the robots.
- One career per player, shared across every server and saved after every change. A battle cut short by a reload or restart gives the entry fee back.
- Watch: anyone in the window can watch a running battle, whether it is a career arena, a challenge or a fight between players, and leave whenever they like.
- 1 vs 1 fights: open a fight in one of 3 arenas with a weight limit or no limit, and anyone in the window can join. A fight where neither side loses health for 60 seconds is a draw.
- A global leaderboard ranks 1 vs 1 wins across every server on the bot.
- The hub's menu and people panel show what each player is doing, like "In the shop", the arena they fight in, or "Watching Ann vs COMPUTER". A friend's Join asks first while you fight a battle of your own.
- The people watching a battle show as faces in the black bars beside it.
- Join puts you with your friend: watching their battle, or on the 1 vs 1 screen when they have a fight open.
- No Red credits: arena prizes are in-game cash that only buys parts.
