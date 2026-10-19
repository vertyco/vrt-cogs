# Starhold

A sci-fi tower defense for [ActivityHub](../activityhub/README.md). A horde of scrap-built mechs marches down a winding road on a moon base toward your reactor core. Build and upgrade high-tech towers on the spots beside the road, fire two powers, and hold out against endless waves for as long as you can. A good run lasts about 10 to 15 minutes.

- **Four towers.** Blaster, Missile pod, Tesla coil and Drone bay, each with three levels (every upgrade hits harder and reaches further) and a choice of two final forms: Gatling or Railgun, Swarm or Mortar, Storm or Disruptor, Guardians or Strikers.
- **Two powers.** Tap Orbital strike or Stasis field in the bottom corners, then tap the map to fire it there.
- **Endless waves.** Scrappers, fast Skitters, flying Buzzers, armored Brutes and Splitters that burst into Skitters, with a Scrap Colossus every tenth wave. Between waves, a button where the road comes in shows what the next wave brings and calls it early for bonus money.
- **Score.** Each kill scores the robot's points times its wave, so late waves count most.
- **High scores.** Each server keeps a table of every player's best checked score.
- **Credits for scores.** Where a server turns payouts on, players can cash in a finished run's score for the bot's currency, a few times a day.
- **Friends.** Each player plays their own run. Friends in the same Activity window see each other's wave and score live at the top of the screen.
- **Desktop and phones.** The map fills the screen, with a thin bar over it and the powers in its corners. Made for phones held upright first; on desktop and phones held sideways the map turns on its side to fill the wide screen. If Starhold closes mid-run, the run is kept for 30 minutes after it closes, and opening Starhold again in that time picks it up where it left off.

## Setup

Starhold needs ActivityHub 0.8.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs starhold
[p]load starhold
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

Starhold installs [mini-racer](https://pypi.org/project/mini-racer/) (V8 for Python), which the bot uses to check scores. It has ready-made packages for Windows, macOS and Linux on 64-bit Intel/AMD and ARM with Python 3.10 or later. There is none for 32-bit ARM (for example 32-bit Raspberry Pi OS), so Starhold can't be installed there.

## How to play

Tap an empty spot beside the road to build: a ring of the four towers opens with their prices. Tap a tower in the ring to see what it does and its numbers, and tap it again to build it (with a mouse, point at it to see and click once to build). Tap a built tower to see what it is, upgrade it, sell it, or (on a Drone bay) move its wall. At level 3, Upgrade becomes the two final forms. Tap a robot to see what it is, its health and what stops it; the first time each robot type comes in during a run, a note says what it does.

Between waves, a robot-head button sits where the road comes in, with a ring counting down to the next wave. Point at it (or tap it once) to see the robots the next wave brings, and click it (or tap it again) to call the wave early: each second left on the countdown pays bonus money.

A Drone bay's three drones wall off the road at their parking point. Ground robots that reach the wall stop and pile up, and every second each drone hits one of them while every robot in the pile bites the drones, so a big crowd breaks through sooner. Once the last drone falls the pile walks on one by one, and each drone comes back 10 seconds after it fell. Flying robots pass over. Robots that reach the reactor core cost lives; at 0 lives the run is over. Pause any time; the pause menu can also end the run.

## Payouts

Starhold can pay players in your bot's currency for their scores, the way Neopets paid for its games. After a run, the game over screen shows what the score is worth and a **Cash in** button. Each point pays a set rate, up to a most-per-cash-in, and each player gets a few cash-ins a day. Starting another run gives up a score that wasn't cashed in.

Server admins (the server owner, Manage Server, or Red's admin role) see a gear button on the game's title screen. It turns payouts on and sets the credits per point (0.025 by default, so 40 points a credit), the most per cash-in (1,000) and the cash-ins a day (3). The same dialog shows the most a player can earn in a day and what was paid out today. Payouts start off. Cash-ins come back at midnight UTC. With a global bank every server shares one balance, so only the bot owner sees the button, the settings apply in every server, and the daily cash-ins count across servers.

## Fair play

The game runs on each player's own device, so it plays smoothly and the bot does almost no work while people play. The bot hands out each run's random seed, keeps the list of the player's moves, and checks that the run never claims more game time than has really passed. Before it pays credits or puts a score on the high score table, it checks the score itself: a separate short-lived program replays the moves with the same rules files the page runs and works the score out again. The bot pays and ranks only that checked score, never the number the page shows.

Two limits remain:

- A changed page knows its run's seed, so a script could look ahead at what each wave brings and play close to perfectly.
- Each extra Discord account gets its own daily cash-ins.

Payouts are capped per cash-in and per day, so even a perfect script earns at most the daily limit. The payout dialog's "paid today" line shows how much the game is costing.

**What it costs the bot:** while people play, the bot only stores one tiny message per tap, plus one every 5 seconds. A check runs only on a cash-in or a new personal best, one at a time, and takes about a second (about 2.4 seconds for the first check after the bot restarts), and it is stopped after 20 seconds.

## Credits

Starhold is an original game. The moon backdrop was made with Codex's image generator (OpenAI), and the menu icon and menu card with Google's Gemini; the towers, robots, effects and logo are drawn in code. The sound effects are our own mixes, layered and processed from recordings in the Sonniss GDC Game Audio Bundle (see `web/sounds/credits.md` and `web/sounds/License-Sonniss-GDC.txt`). The two songs, "Reactor Watch" and "Scrapfall", were made with Google's Lyria 3. The fonts are Rajdhani and Nunito (SIL Open Font License). Drawing uses PixiJS (MIT License).
