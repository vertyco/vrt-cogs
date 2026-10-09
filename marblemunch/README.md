# Marble Munch

A hungry-hippos style marble game for [ActivityHub](../activityhub/README.md). Up to four players each control a hippo on one side of the board. Hold to stretch your hippo's neck out, let go to snap its mouth shut on any marbles in reach. Whoever munches the most marbles wins.

- **Play alone or with friends.** Computer hippos fill any empty seat, so one player can start a round straight away. Everyone else in the voice channel watches.
- **Global leaderboard.** Wins across every server on the bot, with total marbles breaking ties.
- **Desktop and phones.** Hold Space or the mouse on desktop; phones get a big munch button and work held upright or sideways.

## Setup

Marble Munch needs ActivityHub 0.1.9 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs marblemunch
[p]load marblemunch
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs the whole game. A player's page only sends "pressed" and "let go", so a changed page can't fake a score. Two limits remain:

- A script could read the marble positions the page receives and press at the perfect moment. The hippo's reach speed and the wait after each snap cap how well even a perfect script plays.
- Someone with several Discord accounts could fill the other seats with idle accounts and win every round. That takes four accounts in the same voice channel at once, for a leaderboard with no credits.

## Credits

The background music, "Toy Box", was made with Google's Lyria 3. The font is Fredoka (SIL Open Font License). Drawing uses PixiJS (MIT License).

## For developers

Marble Munch is the worked multiplayer example for ActivityHub's [DEVELOPERS.md](../activityhub/DEVELOPERS.md#19-bigger-examples-the-included-games). Section 19 there lists which file shows which pattern.
