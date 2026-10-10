# Tanks

Turn-based artillery for [ActivityHub](../activityhub/README.md), ported from 2DPlay's Flash game "Tanks" (around 2000). Each player aims a barrel, sets the power and fires across hills that blow apart, with the wind shifting every turn. Damage earns money, and money buys weapons and gear between rounds.

- **Up to five tanks.** People take seats; the host can put a computer tank in any empty seat, at one of the original's five difficulties. Everyone else in the voice channel watches.
- **The whole original game.** All 14 weapons (from the small missile to the air strike), shields, parachutes, repair kits, teleports and upgrades, with the original's prices, three landscapes, art and sounds.
- **Turns on a clock.** A minute for each turn and for the shop by default (the host picks 30 seconds to 2 minutes, or no limit), so nobody waits on an idle player. One person against computer tanks keeps nobody waiting, so they get no clock. A player who drops keeps their tank, and a computer plays it for them after a minute away.
- **Global leaderboard.** Match wins across every server on the bot, with kills breaking ties.
- **Desktop and phones.** The original's keys on a keyboard; drag to aim, sliders and buttons on a touch screen. Works held upright or sideways.

## Setup

Tanks needs ActivityHub 0.1.9 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs tanks
[p]load tanks
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs the whole game: the ground, every shot, damage, money and turn order. A player's page only sends what they asked for (aim, drive, fire, buy), and only on their own turn. Two limits remain:

- A script could read every tank's position and the wind from the page and work out a perfect shot. The turn clock is the only cap.
- Someone with several Discord accounts could fill spare seats with idle accounts and win matches. That takes several accounts in the same voice channel at once, for a leaderboard with no credits.

## Credits

Tanks is a port of 2DPlay's Flash game "Tanks", and uses its art and sounds. Drawing uses PixiJS (MIT License).

## For developers

Tanks shows ActivityHub's turn-based pattern: a slow live loop for one player's turn, and whole shots worked out at once and sent to every page as a script to play back. See section 19 of ActivityHub's [DEVELOPERS.md](../activityhub/DEVELOPERS.md#19-bigger-examples-the-included-games).
