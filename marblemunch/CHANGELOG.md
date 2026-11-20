# Marble Munch Changelog

## 0.6.1

Needs ActivityHub 0.8.0 or later.

- Phones held sideways: the page always fits the screen. A crowded score panel scrolls on its own, so Start, Stand up, Cash in, Back and Sound can always be reached, and the round's Hold to munch button no longer covers the panel.
- Upright phones: the cash-in box takes one row, so the board stays big enough to read the name tags. The Hold to munch button shows from "Get ready", so the board no longer jumps when play starts, and the Reconnecting note sits on the board instead of over the title.
- A cash-in note with nothing to cash in ("Munch some marbles to earn credits." or "No cash-ins left today.") steps aside while a round is on, so the board keeps its room. A round that can still be cashed in stays up, as before.
- Long messages wrap inside the board instead of running off the screen, and taps go through them to the hippos. A long winner's name is shortened the same way as on the board.
- Taps answer at once on iPhones, with no wait for a possible double tap.
- The Leaderboard and Payouts windows fit on phones, their Reset and Close buttons look like buttons, and the payout boxes are easier to tap. On a phone held sideways the Payouts window is wider, so its buttons show without scrolling.
- When the game's connection closes for good, Cash in, Start, Stand up and Hold to munch go away, and the "Sorry!" message stays on the board.
- Computer players are labeled CPU. A player alone no longer sees "1 watching" with their own face, and the page says "Loading..." until the game arrives.
- The people button matches the game's buttons in size and color, watcher faces are easier to tap, and Back, Sound, the payout gear and faces show when pressed. Back is always the first button, and closing a window puts the keyboard back on the button that opened it.

## 0.6.0

Needs ActivityHub 0.8.0 or later.

- The music and sound effects buttons are now one sound button. It opens a small panel with an on/off switch and a volume slider for sound effects and for music. Letting go of the sound effects slider plays a sound at the new level. The volumes are saved on each device, and the button shows crossed out when both sounds are off.

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
