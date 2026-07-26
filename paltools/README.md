# PalTools

Manage PalWorld dedicated servers from Discord via the official REST API. Join/leave logging, a live status panel with per-server player counts, player database with playtime and name history, and staff moderation tools (kick, ban, unban, announce, save, shutdown).

RCON is deliberately unsupported: Pocketpair has deprecated it, and the REST API covers everything this cog needs.

## Requirements

- A PostgreSQL server. The cog stores all player and server data in its own Postgres database (configured once per bot via `[p]paltools postgres`, shared with other Vrt-Cogs Piccolo cogs through the `postgres` shared API token).
- One or more PalWorld dedicated servers with the REST API enabled in `PalWorldSettings.ini`:
  - `RESTAPIEnabled=True`
  - `RESTAPIPort=8212` (or any port you choose)
  - An `AdminPassword` set (the REST API authenticates as user `admin` with this password).

## Security notes (read these)

- The PalWorld REST API is not designed for raw internet exposure. Keep it LAN-only or firewalled so that only your bot host can reach the port.
- The `AdminPassword` for each server is stored in plaintext in the cog's database. Treat database access accordingly.
- Player IP addresses are collected for moderation purposes. Public commands never show IPs. The join log embeds show them only when the bot owner has enabled `[p]paltools logips`.
- `[p]paltools findplayer` shows IP history and shared-IP overlaps only when **all three** of these hold, since any one alone leaks addresses:
  1. `[p]paltools logips` is enabled.
  2. The person running it is a mod or admin (by Red's mod/admin roles), the Discord server owner, or the bot owner. Manage Server alone is not enough, even though it is enough to run the command.
  3. The channel is not readable by the `@everyone` role. A public channel would publish the addresses to everyone who can read the reply, regardless of who asked.

  When `logips` is on but the other conditions are not met, the dossier says so in its footer rather than silently omitting the section.

## Setup walkthrough

1. `[p]paltools postgres` (bot owner): set the Postgres connection info. The cog creates and migrates its own `paltools` database.
2. `[p]paltools servers` (bot owner): opens the interactive server manager panel. Click Add Server and enter a name, host, REST port, and admin password. Use Test Connection to verify the cog can reach the API.
3. `[p]paltools logchannel #channel` (bot owner): set the channel for join/leave and server online/offline embeds.
4. Optional: `[p]paltools statuschannel #channel` (bot owner): set the channel for the live status panel.
5. Optional: `[p]paltools logips` (bot owner) to include player IPs in join embeds and in `[p]paltools findplayer`. Only enable this if the log channel and your admins are staff-only.

The poll loop starts automatically once the database is configured. It checks all enabled servers every 30 seconds.

## Live status panel

`[p]paltools statuschannel #channel` posts a single message and edits it in place on every poll tick, so the channel keeps one always-current panel instead of a stream of them:

```
## PalWorld Server Status
Total Players: 22

`Feybreak:  ` 0/16
`Modded PVP:` Offline 2 hours ago
`Palpiton:  ` 9/32
`Sakurajima:` 2/32

[ 12 hour player count graph ]

-# Last Updated 8 seconds ago
```

The graph's x axis is drawn in UTC by default. Set your own with `[p]paltools timezone America/New_York` (any IANA name works), and the axis label follows daylight saving on its own, showing EDT in summer and EST in winter. Changing it re-renders the graph on the next poll rather than waiting out the ten minute render interval.

One line per server, not one line per player. That is deliberate: a roster of names is bounded by how many people are playing, so it would start dropping names exactly when the panel matters most. Use `[p]palplayers` for who is actually online.

The graph is rebuilt from the session rows the cog already stores, so there is no snapshot table and no extra polling behind it. It is re-rendered every 10 minutes and reused between ticks rather than re-uploaded every 30 seconds.

The panel is a Components V2 layout, not an embed, which caps it at 4000 display characters: roughly 100 servers before Discord's own limit is reached, and if that ever happens the overflow is counted on a trailing line instead of servers silently vanishing.

Give the bot Send Messages and Attach Files in that channel, and keep the channel read-only for everyone else so the panel stays the last message. Moving the panel with `statuschannel` deletes the old one, and `[p]paltools statuschannel` with no channel turns it off.

The panel asks each server for metrics (for the `9/32` max), so it costs one extra REST request per server per tick; Discord servers without a panel never make that per-tick request. `[p]palstatus` makes the same metrics request on demand when someone runs it.

## Backup and restore

`[p]paltools backup` dumps everything this Discord server has stored (settings, server rows, players, IP history, sessions) into a JSON file and sends it by DM. It is a DM and not a channel post because the file contains every server's `AdminPassword` in plain text. Large dumps are gzipped automatically; restore accepts either form.

`[p]paltools restore` takes that file back, either attached to the command or on a message you reply to. It asks for confirmation first, then **deletes everything currently stored for this Discord server** and inserts the backup's contents in one transaction, so a failure part way leaves the existing data untouched.

This is the intended way to build a setup on a test bot and move it to the live one. Row ids are per database, so the restore reissues them and rewrites every reference as it goes: the file can land on a different bot, a different database, or a different Discord server. Restoring a backup taken on a different Discord server keeps the `logips` toggle but drops the log and status channels, since those ids mean nothing there.

The status panel message id is never part of a backup. The panel belongs to whichever bot posted it, so the restoring bot posts a fresh one on its next poll tick.

## Commands

### User commands (public)

| Command | Description |
|---|---|
| `[p]palstats <player>` | Player stats by in-game name or account name: level, playtime (total and per server), first/last seen, name history |
| `[p]paltop` | Playtime leaderboard for this Discord server |
| `[p]palstatus [server]` | Live server status: version, FPS, uptime, players/max |
| `[p]palplayers [server]` | Live player list: name, level, ping |

### Staff group `[p]paltools`

Owner-only:

| Subcommand | Description |
|---|---|
| `postgres` | Configure the Postgres connection |
| `servers` | Interactive server manager (add/edit/test/toggle/remove servers) |
| `logchannel [channel]` | Set or clear the join/leave log channel |
| `statuschannel [channel]` | Set or clear the live status panel channel |
| `logips` | Toggle IP display in join embeds and `findplayer` |
| `timezone [name]` | Set the timezone the status panel graph is labelled in, or show the current one |
| `backup` | DM a backup file of this Discord server's PalTools data |
| `restore` | Restore an attached backup file, replacing this Discord server's data |

Admin, or the Manage Server permission:

| Subcommand | Description |
|---|---|
| `findplayer <name or id>` | Full player dossier: identity, playtime, name history, plus IP history and shared-IP overlaps when the three IP conditions under Security notes are all met |
| `settings [server]` | Live PalWorld settings from the `/settings` endpoint: headline values in an embed, the full set attached as JSON |
| `kick <name or userId> [reason]` | Kick from all enabled servers |
| `ban <name or userId> [reason]` | Ban on all enabled servers |
| `unban <name or userId>` | Unban on all enabled servers |
| `announce <message>` | Broadcast to all enabled servers |
| `save [server]` | Save world(s) |
| `shutdown <server> [seconds] [message]` | Graceful shutdown with confirmation prompt |

Kick, ban, and unban accept an in-game name (resolved through the player database) or a raw userId such as `steam_76561198...`. Quote names that contain spaces, for example `[p]paltools kick "Bob The Builder" griefing`. Multi-server actions report per-server success or failure.
