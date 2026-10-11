# Marble Munch

A hungry-hippos style marble game for [ActivityHub](../activityhub/README.md). Up to four players each control a hippo on one side of the board. Hold to stretch your hippo's neck out, let go to snap its mouth shut on any marbles in reach. Whoever munches the most marbles wins.

- **Play alone or with friends.** Computer hippos fill any empty seat, so one player can start a round straight away. Everyone else in the voice channel watches.
- **Global leaderboard.** Wins across every server on the bot, with total marbles breaking ties.
- **Credits for marbles.** Where a server turns payouts on, each player can cash in their last round's marbles for the bot's currency, a few times a day.
- **Desktop and phones.** Hold Space or the mouse on desktop; phones get a big munch button and work held upright or sideways.

## Setup

Marble Munch needs ActivityHub 0.5.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs marblemunch
[p]load marblemunch
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Payouts

Marble Munch can pay players in your bot's currency for the marbles they munch, the way Neopets pays for its games. After a round, a box beside the scores shows what it's worth and a **Cash in** button. Each marble pays a set rate, up to a most-per-cash-in, and each player gets a few cash-ins a day. The next round a player finishes replaces an unsent one, so players save their cash-ins for their best rounds.

Server admins (the server owner, Manage Server, or Red's admin role) see a settings button in the game's top corner. It turns payouts on and sets the credits per marble (100 by default), the most per cash-in (1,000) and the cash-ins a day (3). Payouts start off. Cash-ins come back at midnight UTC. With a global bank every server shares one balance, so only the bot owner sees the button, the settings apply in every server, and the daily cash-ins count across servers.

## Fair play

The bot runs the whole game. A player's page only sends "pressed" and "let go", so a changed page can't fake a score. Two limits remain:

- A script could read the marble positions the page receives and press at the perfect moment. The hippo's reach speed and the wait after each snap cap how well even a perfect script plays.
- Someone with several Discord accounts could fill the other seats with idle accounts, win every round and munch more marbles. That takes four accounts in the same voice channel at once. Payouts are capped per cash-in and per day, so it can't earn more than a strong player does.

## Credits

The background music, "Toy Box", was made with Google's Lyria 3. The font is Fredoka (SIL Open Font License). Drawing uses PixiJS (MIT License).

## For developers

Marble Munch is the worked multiplayer example for ActivityHub's [DEVELOPERS.md](../activityhub/DEVELOPERS.md#20-bigger-examples-the-included-games). Section 20 there lists which file shows which pattern.
