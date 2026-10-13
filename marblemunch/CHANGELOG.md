# Marble Munch Changelog

## 0.5.0

Needs ActivityHub 0.8.0 or later.

- The payout settings dialog shows what was paid today and to how many players, like "Today: 1,170 credits paid to 2 players." It starts over at midnight UTC.

## 0.4.1

Needs ActivityHub 0.8.0 or later.

- Works with ActivityHub 0.8.0, which changed how games check for server admins and show their menu card's currency line. An older ActivityHub refuses Marble Munch with a message saying to update it.

## 0.4.0

Needs ActivityHub 0.7.0 or later.

- While payouts are on in a server, Marble Munch's card in the ActivityHub menu says how much a cash-in can pay, like "Cash in up to 1,000 credits".

## 0.3.0

Needs ActivityHub 0.5.0 or later.

- Each hippo has a name tag on the board, so people watching know who's who. Computer hippos show their own names.
- "3 watching" is now a row of the watchers' pictures. Hover one (or tap it on a phone) to see who it is. Watchers who are away are dimmed.
- The hub's people button sits in the side panel, and the menu and people panel show what you're doing: "Blue hippo · 12 marbles", "Won with 14 marbles" or "Watching".
- Join from the hub's people list asks first while you're in a round.

## 0.2.0

- Marble Munch can pay players in the bot's currency for their marbles, the way Neopets pays for its games. After a round, a box beside the scores shows what it's worth, how many cash-ins are left today, and a **Cash in** button. The next round a player finishes replaces an unsent one. A player who comes back after a dropped connection still sees their round.
- Server admins set it up from a new settings button in the game's top corner: payouts on or off, the credits per marble (100 by default), the most per cash-in (1,000) and the cash-ins a day (3). Payouts start off. With a global bank only the bot owner sees the button, the settings apply in every server, and cash-ins count across servers.
- On a phone held upright, the board shrinks to fit when the panel under it grows, instead of the panel covering the board.

## 0.1.0

- First release: a hungry-hippos style marble game for ActivityHub. Up to four players stretch their hippos out to munch the most marbles, NPC hippos fill empty seats, and a global leaderboard ranks players by wins.
