# Warfare 1917

Lead the British or German army across the trenches of 1917, for [ActivityHub](../activityhub/README.md). A port of the Flash game "Warfare 1917", with its original art, sounds and music. Send out riflemen, machine guns, officers, tanks and gas, call in artillery, take the enemy's trenches and win the morale war.

- **Both campaigns.** Nine missions as the British and nine as the Germans, with the original's map, units, fire support and mission briefings. Win a mission to move on, lose it to retry. Winning the ninth ends the campaign with the newspaper and your campaign stats.
- **Upgrades that work.** Kills earn experience, experience earns levels, and levels buy upgrades from the original's two upgrade trees. Every upgrade does what its description says, including the ones that were broken in the original.
- **Custom Battle.** Pick a side, difficulty, units, supports, map size, trenches, wire and mines, and fight it out.
- **Solo, watching or 1 vs 1.** Play alone, watch any battle running in the same Activity, or open a versus battle and let a friend take the other side. Others in the voice channel can watch.
- **One campaign save per person.** Your campaign follows your Discord account, so you can pick it up from any server or device.
- **Desktop and phones.** The original's menus and screens, drawn from its own art. Works held upright or sideways.

There are no Red currency payouts.

## Setup

Warfare 1917 needs ActivityHub 0.5.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs warfare1917
[p]load warfare1917
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs every battle: each squad, shot, shell, gas cloud and kill. A player's page only sends orders (deploy, support, trench, gas masks, pause, surrender), and the bot checks each one against the original's rules. The campaign save lives on the bot, so a page cannot grant itself levels or upgrades.

## Credits

Warfare 1917 is a port of the Flash game "Warfare 1917", made by Con Artist Games and published by Armor Games in 2008 (the original's own credits read "Developed by: Armor Games" and "© Armor Games 2008", and it opens with a Con Artist Games intro). It uses the original's art, sounds and music. Drawing uses PixiJS (MIT License).
