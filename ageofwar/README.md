# Age of War

Defend your base and destroy the enemy's, for [ActivityHub](../activityhub/README.md). A port of Louissi's Flash game "Age of War", with its original art, sounds and music. Train units, build turrets, earn experience from every fight, and evolve through five ages, from cavemen with clubs to super soldiers with lasers.

- **The whole original game.** All 16 units and 15 turrets with the original's prices and strengths, extra turret spots, selling turrets, the five ages, and each age's special attack: a meteor shower, a rain of arrows, healing, a bomber plane and a laser from orbit.
- **The original's computer, or a friend.** Take the left or right base. An empty base is played by the original's computer on Normal, Harder or Impossible. Two people can fight each other instead, and everyone else in the voice channel watches.
- **Pauses and drop-outs.** Someone playing the computer alone can pause, as in the original. If they leave, the battle waits a minute for them. In a game between two people, the computer plays the base of anyone away for a minute, and hands it back when they return.
- **Global leaderboard.** Each player's fastest win against the computer on each difficulty, across every server on the bot. Time counts in game time, so pauses and lag don't.
- **Desktop and phones.** The original's menus, drawn from its own art. Works held upright or sideways.

## Setup

Age of War needs ActivityHub 0.1.9 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs ageofwar
[p]load ageofwar
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs the whole battle: every unit, turret, shot, kill and payment. A player's page only sends orders (train, build, sell, add a spot, evolve, special) for its own base, and the bot checks each one against the original's rules. One limit remains:

- A script could send orders faster and more precisely than a person can click, and so set a faster time on the leaderboard.

## Credits

Age of War is a port of Louissi's Flash game "Age of War", and uses its art, sounds and music. Drawing uses PixiJS (MIT License).
