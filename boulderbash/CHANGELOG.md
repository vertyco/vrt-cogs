# Boulder Bash Changelog

## 0.3.1

Needs ActivityHub 0.8.0 or later.

- Works with ActivityHub 0.8.0, which changed how games check for server admins and show their menu card's currency line. An older ActivityHub refuses Boulder Bash with a message saying to update it.

## 0.3.0

Needs ActivityHub 0.7.0 or later.

- While payouts are on in a server, Boulder Bash's card in the ActivityHub menu says how much a cash-in can pay, like "Cash in up to 1,000 credits".

## 0.2.0

Needs ActivityHub 0.5.0 or later.

- The menu and the hub's people panel show what you're doing: "Extreme · level 4 · 1,230" (the higher level in a two-board mode), "Playing Zen", "Scored 2,400" or "Finished Zen" after a game, or "Getting ready".
- During a game, a strip shows everyone here with a Boulder Bash score, best first, you included. Your own entry keeps up with every point. It always shows your own place, then "+2" for anyone it has no room for. With room beside the boards it stands there under your score, two lines to an entry, showing up to five people (three on a phone held sideways). Without that room it is a row under your score, showing as many as fit with a few letters of every name, up to three. On an upright phone it sits under your score, showing three. Names longer than 12 characters are cut to 11 and "…" without splitting an emoji, and people who are away are dimmed. It only shows when someone else here has a score. Zen keeps no score, so a Zen game shows no strip, and people playing Zen are not in anyone's strip.
- "You passed Ann!" shows for a moment when your score goes above someone in the strip, whether their game is still on or already over, the same as in the hub's own games. It never covers the boards, and never cuts a name shorter than the strip does: beside the boards under End Game when there's room, otherwise above them between your score and the people button, smaller in a small window, and on an upright phone in the space between the strip and the boards. When a level's popup fills that space on a short phone, the note waits for the popup to close. Passes a moment apart share one note. Nobody already behind you when your game starts is noted, nor anyone after a reload or a dropped connection, and Zen passes nobody.
- The hub's people button sits beside Back on the title, out of the way on the other screens, and next to End Game during a game (under it on an upright phone).
- Join from the hub's people list asks first while you're in a game.

## 0.1.1

- The triceratops on the menus stands on the skull ledge in windows of every shape, instead of floating over the canyon in wide windows. Wide menus now show the bottom of the backdrop, where the ledge is, and crop the sky.
- The cave paintings moved to a clear spot on the cliff, so the menu's stone signs no longer cover them, and tapping them always brings out the caveman.

## 0.1.0

- First release: a Stone Age block-smashing puzzle for ActivityHub, remade from Neopets' Destruct-O-Match III with all-new art, sound and music. Tap clumps of matching stone blocks to smash them across five modes (Zen, Normal, Extreme, and two-board Normal and Extreme), with all ten special blocks, Undo and Shuffle. The rules, scores, goals, timers and animation lengths follow the original. Each player plays their own game, and the bot keeps every board, so the page only reports taps.
- Every finished game goes on its server's high score table, shown from the title screen.
- Payouts, Neopets style, start off. Server admins turn them on from the gear button on the title screen and set the credits per point (0.2 by default, so 5 points a credit), the most per cash-in (1,000) and the cash-ins a day (3). The dialog also shows what was paid today. After a game, a player may cash in its score. With a global bank only the bot owner sees the button, the settings apply in every server, and cash-ins count across servers.
