# Boulder Bash

A Stone Age block-smashing puzzle for [ActivityHub](../activityhub/README.md). Tap a clump of two or more touching blocks of the same color to smash it. Blocks above fall, empty columns slide together, and bigger clumps score more for every block. Clear enough points to reach each level's goal.

Boulder Bash is a remake of Neopets' Flash game Destruct-O-Match III (2010). The rules, scores, goals, timers and animation speeds follow the original game, read from its code. The name, art, sound and music are all new.

- **Five modes.** Zen (relaxed, no score), Normal (ten levels with goals), Extreme (one tap smashes, and new rows push up faster and faster), and two-board versions of Normal and Extreme.
- **Ten special blocks.** Refill, Countdown, Triple, Bomb, Color wipe, Shifter, Wild, Undo, Shuffle and Column hold, plus the Undo and Shuffle slots they charge.
- **High scores.** Every finished game goes on the server's high score table, shown from the title screen.
- **Credits for scores.** Where a server turns payouts on, players can cash in a finished game's score for the bot's currency, a few times a day.
- **Desktop and phones.** Each player plays their own game, on desktop or on a phone held upright or sideways.

## Setup

Boulder Bash needs ActivityHub 0.5.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs boulderbash
[p]load boulderbash
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Payouts

Boulder Bash can pay players in your bot's currency for their scores, the way Neopets paid for its games. After a game, the game over screen shows what the score is worth and a **Cash in** button. Each point pays a set rate, up to a most-per-cash-in, and each player gets a few cash-ins a day. Starting another game gives up a score that wasn't cashed in, so players save their cash-ins for their best games.

Server admins (the server owner, Manage Server, or Red's admin role) see a gear button on the game's title screen. It turns payouts on and sets the credits per point (0.2 by default, so 5 points a credit), the most per cash-in (1,000) and the cash-ins a day (3). The same dialog shows the most a player can earn in a day and what was paid out today. Payouts start off. Cash-ins come back at midnight UTC. With a global bank every server shares one balance, so only the bot owner sees the button, the settings apply in every server, and the daily cash-ins count across servers.

## Fair play

The bot keeps every board. It picks every block, works out every tap, keeps the score and decides every payout; a player's page only says where they tapped. The page never learns about a block before it appears, so nothing can plan around future rows or refills. Two limits remain:

- A script could read the board and pick strong moves.
- Each extra Discord account gets its own daily cash-ins.

Payouts are capped per cash-in and per day, so even a perfect script earns at most the daily limit. The payout dialog's "paid today" line shows how much the game is costing.

## Credits

The rules come from Neopets' Destruct-O-Match III. All art, sound and music are new. The backdrops and characters were made with Google's Gemini image generation, and the blocks, icons and signs are drawn for this cog. The two songs, "Canyon Stomp" and "Rock Breaker", were made with Google's Lyria 3. The sound effects are from Kenney's Impact Sounds and Interface Sounds (CC0), plus a few voices made in the page. The fonts are Grandstander and Nunito (SIL Open Font License). Drawing uses PixiJS (MIT License).
