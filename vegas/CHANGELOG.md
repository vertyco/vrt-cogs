# Vegas Changelog

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
