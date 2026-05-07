# ModLogTools

Extended tooling for Red-DiscordBot's core modlog and warnings systems.

## Features

- Automatically expire warning points after a configured duration.
- Preserve a warning history ledger with active, expired, and manually removed states.
- Add a dedicated modlog case when a warning expires automatically.
- Show guild warning insights:
  - overall warning overview for a time window
  - top warned members
  - top moderators issuing warnings
  - member-specific warning summaries

## Commands

- `[p]modlogtool`
  - Show help for subcommands.
- `[p]modlogtool status`
  - Show current expiry setting and tracked warning counts.
- `[p]modlogtool expiry <duration|off>`
  - Dry run defaults to `true`; append `false` to apply.
  - Example: `30d false`, `12h false`, `2w false`, `off false`
- `[p]modlogtool deletemodlogmessages [true|false]`
  - Toggle deleting original warning modlog messages when warnings expire. Defaults to `false`.
- `[p]modlogtool sync`
  - Full rescan of Red warnings data + modlog warning cases.
- `[p]modlogtool exportconfig`
  - Export current guild warnings/modlog/modlogtools config as JSON.
- `[p]modlogtool importconfig [dry_run=true]`
  - Attach or reply to an export JSON file. Dry run defaults to `true`.
- `[p]modlogtool expire`
  - Dry run defaults to `true`; append `false` to remove warnings for real.
- `[p]modlogtool overview [timespan]`
  - High-level warning summary for a guild.
- `[p]modlogtool leaderboard [timespan] [limit]`
  - Top warned members in a period.
- `[p]modlogtool moderators [timespan] [limit]`
  - Top moderators by warnings issued.
- `[p]modlogtool member <member> [timespan]`
  - Warning summary for a single member.

## Notes

- This cog depends on Red's core `Warnings` cog being loaded.
- Existing warnings are backfilled from core modlog warning cases the first time the cog syncs a guild.
- Automatic expiry removes warning entries and warning points from Red's core warnings config.