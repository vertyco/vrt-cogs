# PalTools Changelog

## 0.1.0

Initial release.

- PalWorld dedicated server management over the official REST API (no RCON).
- 30 second poll loop with join/leave and server online/offline logging. One line per event, batched into a single message per tick, and never showing a player's IP.
- Live status panel: `[p]paltools statuschannel` keeps one Components V2 message with per-server player counts, offline timestamps and a 12 hour player count graph, edited in place each tick. The graph is derived from the stored sessions, so it needs no snapshot table.
- Player database: identity, name history, IP history, sessions and playtime.
- Player lookups: `[p]palstats`, `[p]paltop`, `[p]palstatus`, `[p]palplayers`, `[p]paltools findplayer`.
- Staff controls: announce, kick, ban, unban, save, and a confirmed shutdown.
- Interactive server manager panel for adding, editing, testing, toggling and removing servers.
- `[p]paltools timezone [name]`: the status panel graph is labelled in UTC unless you set an IANA timezone for the Discord server. The axis label tracks daylight saving, and the setting travels with a backup.
- `[p]paltools settings [server]`: live server settings from the `/settings` endpoint, headline values in an embed with the full payload attached as JSON. A highlighted value the server does not report reads as "not reported" instead of quietly disappearing.
- `[p]paltools findplayer` shows IP history and shared-IP overlaps only when `logips` is on, the person asking is a mod or higher, and the channel is not readable by `@everyone`. `logips` gates that lookup alone: addresses are recorded either way and the join log never carries them.
- `[p]paltools backup` and `[p]paltools restore`: move a Discord server's whole setup and history between bots or databases. The dump is DMed rather than posted since it holds the AdminPasswords, and the restore remaps every row id so it can land anywhere.
