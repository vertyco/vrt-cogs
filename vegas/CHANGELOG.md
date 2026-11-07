# Vegas Changelog

## 0.5.4

- The Slots lever's arm sits a pixel or two further right on the machine's side knob.

## 0.5.3

- The Slots lever's arm comes straight out of the middle of the machine's side knob.

## 0.5.2

- The Slots lever rises straight out of the machine's side knob, instead of standing off to its right.

## 0.5.1

- Slots spins with more suspense. The reels spin slower, and each one takes over a second to slow down, so the last few symbols crawl past the line. Then the reel runs a touch past its stop and settles back. A spin now lasts 3 to 5.5 seconds, and a hard pull still spins longer than a gentle one. The odds are the same.
- The Slots lever stands beside the machine, rising from its side hub, instead of covering the column of lights.
- The slot machine sits in the middle of the Slots card on the menu.

## 0.5.0

Needs ActivityHub 0.13.0 or later.

- The casino floor is now a menu of game cards: Texas Hold'em on a big banner at the top, then a card for each of the ten other games, each with its own painting and the faces of who's playing there.
- New table: Texas Hold'em, on the menu's banner. It's 6-seat no-limit poker where players bet against each other, not the casino, and hands are dealt one after another for as long as anyone is seated.
- Sit down alone and you practice for free against 3 CPUs with play chips. When a second person buys in, you're asked to buy in too: the practice hand finishes, the CPUs leave and the real game starts. Saying no, or not answering, stands you up to watch. When only one player is left, practice comes back and their real stack waits.
- You buy in for an amount between the game's Min and Max (400 to 2,000 by default), and the blinds are a hundredth of the Max (10 and 20 by default). Top up between hands, or stand up at any time: mid-hand, you leave when it ends. Your chips go back to your bank when you stand, when the table closes, or when an admin closes Hold'em.
- Card-room rules stop anyone dodging the blinds. Joining a real game means paying one big blind to play the next hand, or waiting for the big blind to reach your seat. Sitting back down within 30 minutes takes at least what you left with.
- You get 35 seconds a turn. Two timeouts in a row stand you up, and a player out of chips is asked to top up.
- The casino keeps a cut of each pot that reaches the flop: 5% by default, at most 3 big blinds. Nobody receives it, so it takes credits out of the economy. Admins set it from 0 to 20% in Hold'em's Payout box on the Settings Games tab, or with `[p]vegasset cut`. Hold'em has no cooldown, multiplier or payout limit, and memberships only decide who may play.
- Your cards are sent only to you until the showdown, so nobody else at the table, watchers included, can see them.
- Credits at a poker table count toward a membership's credit requirement, and they're saved as each hand starts and ends. If the bot stops mid-hand, even in a crash, that hand is called off and everyone's chips go back to their bank as they were when it started. Only real hands count in your stats.
- The action bar slides in on your turn: Fold, Check or Call with the exact amount, and Raise with a slider and quick sizes (Min, ½ pot, ¾ pot, Pot, All in). While others act, you can tick Check/Fold, Check or Call any, and the move is made for you when your turn comes.
- Everything moves. Cards fly from the deck to each seat in dealing order, bets slide onto the felt and sweep into the pot, the flop slides out and turns over card by card, and the dealer button glides to its next seat. When nobody can bet any more, every hand turns face up and the rest of the board comes out one card at a time. At the end, the winning five cards light up, the casino's cut slides away, and the pot slides to its winners, split visibly when it's shared. Pots of 50 big blinds or more get a bigger celebration.
- Whose turn it is is always clear: the acting player's seat glows and their clock drains, as a ring around their picture, or as a bar along your name plate on your own turn. It turns amber at 10 seconds, then red at 5. Your own turn chimes, then ticks in its last 5 seconds, and every move has its own sound.
- Learning help: your hand is named under your cards as each shared card lands, like "Pair of 7s". House rules has the rules in plain words and a "What beats what" chart of the ten hands, with cards for each.
- Your status in the people list says Texas Hold'em with your chips, Practicing Hold'em, or Watching Hold'em.
- New game: Slots. Three reels on the gold slot machine, a fixed pay table from the bet back on one cherry up to 50 times on three diamonds, and the middle row is the only line. Bets 10 to 500 by default, with no cooldown.
- Slots has a progressive jackpot: 2% of every bet grows a pot that 7-7-7 wins. You win the share of it that matches your bet, so a max bet wins it all, and the pot never drops below 60 times the max bet. Resetting the casino's game settings keeps the pot; resetting everything starts it again.
- Slots has no spin button: you pull the machine's lever down, and a hard, quick pull spins the reels faster and longer (it never changes the odds). The machine shows the live jackpot on its marquee, and what 7-7-7 would pay at your bet.
- When someone hits the jackpot, everyone in the casino window sees a short gold note, and the Slots card shows the live jackpot.
- All In is now a lit prize wheel. Its gold slice is your real chance of winning, 1 in (multiplier + 2), so it gets thinner as the multiplier grows, and it redraws as you pick the multiplier, before you bet. The slot machine moved to Slots.
- The music and sound effects buttons in the top bar are now one sound button. It opens a small panel with an on/off switch and a volume slider for the sound effects and for the music, in the lobby and at every table. The button shows crossed out when both are off.
- Each device keeps its own volumes, and the old on/off choices carry over. Letting go of the sound effects slider lays a chip, so the new volume can be heard.

## 0.4.1

Needs ActivityHub 0.13.0 or later.

- Opened outside the bot's servers (a DM, or a server the bot isn't in), the ActivityHub menu marks Vegas "Servers only" and says why instead of opening a casino that can't take bets there.

## 0.4.0

Needs ActivityHub 0.8.0 or later.

- Memberships can raise betting limits. Each membership has a max bet multiplier: at 2x, every game's max bet is doubled for its players, so Blackjack at 50-500 becomes 50-1,000. Min bets stay the same, games with one fixed bet stay fixed, and All In has no limits to raise. Basic and existing memberships start at 1x.
- Admins set it in the Activity's membership form, or with the new Limits button in `[p]vegas memdesigner`. The chip tray's Max button and chips follow the player's own max.
- The membership updater no longer writes a debug log line every 5 minutes.

## 0.3.1

Needs ActivityHub 0.8.0 or later.

- Works with ActivityHub 0.8.0, which changed how games show their menu card's currency line. An older ActivityHub refuses Vegas with a message saying to update it.

## 0.3.0

Needs ActivityHub 0.7.0 or later.

- Vegas's card in the ActivityHub menu says it bets the server's currency, like "Bet credits at the tables".

## 0.2.2

- Changing a game's cooldown now reaches players already waiting on it. Lowering All In's cooldown to 0 frees everyone at once instead of leaving them on the old 12 hour wait, and raising it makes everyone's wait longer.
- Updating clears every player's current cooldowns once, so each game is ready for everyone right after the update.

## 0.2.1

- All In makes it plain that a pull bets your whole balance. The tray says how much in red, along with the chance and what a win pays, the button reads "Bet all 1,000" instead of "Pull", and every pull, from the button or the machine's lever, asks first.
- The yes or no box no longer runs into the edges of a phone screen.

## 0.2.0

Needs ActivityHub 0.5.0 or later.

- The casino floor shows who's where: each table's sign shows the pictures of the people at it instead of a number, and the people standing in the lobby show as a row of faces along the bottom. Hover a face to see who it is and what they're doing.
- Joining someone from the hub's people list walks you straight to their table.
- The hub's people button sits in the top bar, and the menu and people panel show what you're doing: "In the lobby", "Blackjack · bet 200", "Craps · has the dice".
- Join from the hub's people list asks first while you have a bet riding.

## 0.1.1

- Renamed from Casino to Vegas so it can be loaded next to Redjumpman's Casino. Install and load it as `vegas`; the commands are now `[p]vegas`, `[p]vegasset` and `/vegas`. Its data folder changes with the name, so it starts with an empty database.
- A Blackjack player who drops between rounds keeps their seat for the reconnect grace even when they were the last one in the window. Unloading the cog no longer leaves a seat timer running.
- The settings panel reloads after a mode switch, reset or wipe, so saving a tab afterwards no longer writes the old values back.
- On touch screens the lobby shows each table's name, since there is no hover to bring it up.
- On short, wide screens (a sideways phone) the lobby says it scrolls down when the front row of tables is out of sight.
- Sideways, the table scene keeps clear of a phone's notch and home bar.
- The player list shows a push, surrender or refund in gold instead of a loss's red.
- A slow answer from a closed panel no longer fills the panel opened after it.
- A membership's credit requirement uses the server's currency name instead of always saying "credits".

## 0.1.0

- First release: Redjumpman's Casino rebuilt as a Discord Activity for ActivityHub. Nine games on a walk-in Classic Vegas floor, shared tables for everyone in the Activity window (every game also plays alone), Red's bank credits, memberships, and every setting in the Activity's settings panel and in the original's `[p]casino` and `[p]casinoset` commands. Data is kept in SQLite.
