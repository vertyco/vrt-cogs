# Bloxorz

Roll a tall stone block across floating stages and stand it upright in the hole, for [ActivityHub](../activityhub/README.md). A port of Damien Clarke's 2007 Flash puzzle "Bloxorz", with its original art, sounds and music.

- **The whole original game.** All 33 stages with the original's tiles: fragile ones that break under a standing block, round and cross switches, bridges that open and close, and the split that turns the block into two cubes you swap between and join back together.
- **Passcodes, Load Stage and Continue.** Finish a stage and you get its passcode, as in the original. Load Stage takes a code, and Continue picks up your saved run, even from another server or device.
- **One global leaderboard.** Fewest moves and best time on each stage, across every server on the bot, under real Discord names.
- **Single player.** One run per person. Opening the game somewhere else takes it over.
- **Desktop and phones.** Arrow keys on a computer, swipes on a phone, with a Switch button for the two cubes. Works held upright or sideways.

## Setup

Bloxorz needs ActivityHub 0.11.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs bloxorz
[p]load bloxorz
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs the rules of every roll: where the block lands, what breaks, which bridges move and when the stage is won. A player's page only sends the keys pressed, and the bot works out the moves and the time. A script could still press keys faster and more precisely than a person can, and so set a better time on the leaderboard.

## Credits

Bloxorz is a port of the Flash game by Damien Clarke, DX Interactive (2007), and uses its graphics, audio and stages. Drawing uses PixiJS (MIT License).
