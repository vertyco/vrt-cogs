# Vegas Changelog

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
