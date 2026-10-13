# Warfare 1944

Lead the American or German army across the battlefields of 1944, for [ActivityHub](../activityhub/README.md). A port of the Flash game "Warfare 1944", with its original art, sounds and music. Spend resource points to send riflemen, machine guns, bazookas, snipers, mortars, officers and tanks down three lanes, give your squads orders, take cover and win the morale war.

- **Both campaigns.** Eight missions as the Americans and eight as the Germans, with the original's map, units, objectives and mission briefings. Win a mission to move on, lose it to retry. Winning the last one ends the campaign with your campaign stats.
- **Orders and cover.** Select a squad to advance it, throw grenades or smoke, or call in artillery, air support and smoke rounds. Squads take cover behind walls, fences, sandbags and log piles.
- **Upgrades that work.** Kills earn experience, experience earns levels, and levels buy upgrades from the original's two upgrade trees. Every upgrade does what its description says, including the ones that were broken in the original.
- **Custom Battle.** Pick a side, difficulty, units, supports, map and starting resource points, and fight it out.
- **Solo, watching or 1 vs 1.** Play alone, watch any battle running in your Discord server, or open a versus battle for anyone in the server (or only your voice channel) to take the other side. Anyone in the server can watch your battles. Battles and games from your own voice channel are listed first.
- **The tutorial.** The original's narrated tutorial, offered when you start your first campaign and on the Instructions page.
- **One campaign save per person.** Your campaign follows your Discord account, so you can pick it up from any server or device.
- **Desktop and phones.** The original's menus and screens, drawn from its own art. Works held upright or sideways.

There are no Red currency payouts.

## Setup

Warfare 1944 needs ActivityHub 0.10.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs warfare1944
[p]load warfare1944
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs every battle: each squad, shot, shell, smoke screen and kill. A player's page only sends orders (deploy in a lane, a squad's order, pause, surrender), and the bot checks each one against the original's rules, including the resource points it costs. The campaign save lives on the bot, so a page cannot grant itself levels or upgrades.

## Credits

Warfare 1944 is a port of the Flash game "Warfare 1944", made by Con Artist Games and published by Armor Games in 2009 (the original's own credits read "Developed by: Armor Games" and "© Armor Games 2009"). It uses the original's art, sounds, music and tutorial narration. Drawing uses PixiJS (MIT License).
