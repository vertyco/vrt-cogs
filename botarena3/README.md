# Bot Arena 3

Build a team of up to five robots from chassis, plating and weapons, then fight through 15 arenas, for [ActivityHub](../activityhub/README.md). A port of the Flash game "Bot Arena 3" (originally on Armor Games), with its art, sounds and music.

- **The whole original game.** The same parts, prices, shop, 15 arenas, 7 challenges and win screen, with the original's numbers. Robots look for targets, aim and fight on their own. You give orders by dragging: go there, or follow a robot.
- **Careers follow players around.** Each player has one career, shared across every server on the bot. It saves itself after every change, so you never need to press Save. A battle cut short by a reload or restart gives the entry fee back.
- **Watch battles.** Anyone in the same window can watch a battle that is running, whether it is a career arena, a challenge or a fight between players.
- **1 vs 1 fights.** A player opens a fight in one of 3 arenas with a weight limit, or no limit, and anyone else in the window can join it. Nothing is at stake. A fight where neither side loses health for 60 seconds is a draw.
- **Global leaderboard.** Ranks players by 1 vs 1 wins across every server on the bot.
- **No Red credits.** Arena prizes are in-game cash that only buys parts. The cog never touches the bot's economy, so there is nothing to set up for it.
- **Desktop and phones.** The original's screens, scaled to fit the window. Works held upright or sideways. Sound and music volumes are kept on each device.

## Setup

Bot Arena 3 needs ActivityHub 0.5.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs botarena3
[p]load botarena3
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs every battle: each robot, shot and hit. A player's page only sends orders for its own robots, and the bot checks every shop and arena request against the original's rules. Battle results can't be faked from the page.

## Credits

Bot Arena 3 is a port of the Flash game "Bot Arena 3", originally on Armor Games, and uses its art, sounds and music. The text is drawn in the 04b_03 pixel font by Yuji Oshimoto (04.jp.org). Drawing uses PixiJS (MIT License).
