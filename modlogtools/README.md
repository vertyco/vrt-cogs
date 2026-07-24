# ModLogTools

Extended tooling for Red-DiscordBot's core modlog and warnings systems.

## Features

- Automatically expire warning points after a configured duration.
- Gradual warning point decay as an alternative (or complement) to hard expiry.
- Per-warning expiry overrides for holds and appeals.
- Optional DM notification when a member's warnings expire or fully decay.
- Preserve a warning history ledger with active, expired, decayed, and manually removed states.
- Add a dedicated modlog case when a warning expires or fully decays automatically.
- Show guild warning insights:
  - overall warning overview for a time window
  - top warned members
  - top moderators issuing warnings
  - member-specific warning summaries and full history
- Members can view their own active warnings with `[p]mywarnings`.

## Commands

- `[p]modlogtool`
  - Show help for subcommands.
- `[p]modlogtool view`
  - Show current expiry setting and tracked warning counts.
- `[p]modlogtool expiry <duration|off>`
  - Dry run defaults to `true`; append `false` to apply.
  - Example: `30d false`, `12h false`, `2w false`, `off false`
- `[p]modlogtool deletemodlogmessages [true|false]`
  - Toggle deleting original warning modlog messages when warnings expire. Defaults to `false`.
- `[p]modlogtool dmexpiry [true|false]`
  - Toggle DMing members when their warnings expire or fully decay. Defaults to `false`.
- `[p]modlogtool decay <points_per_day|off>`
  - Set gradual warning point decay. Each active warning loses points per day since it was
    issued and is removed once it reaches 0 points.
- `[p]modlogtool extend <member> <warn_id> <duration|never|reset>`
  - Override one warning's expiry (duration from now, minimum `10m`). `never` pins it active,
    `reset` follows the guild-wide expiry again. Overridden warnings ignore guild expiry changes.
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
- `[p]modlogtool leaderboard [active|warns|points] [timespan] [limit]`
  - Top warned members in a period, sorted by active warnings (default), total warnings, or points.
- `[p]modlogtool moderators [case_type] [timespan] [limit]`
  - Top moderators by modlog cases issued. `case_type` defaults to `warn` and accepts any modlog action (`ban`, `kick`, `tempban`, `expired`, ...).
- `[p]modlogtool member <member> [timespan]`
  - Warning summary for a single member.
- `[p]modlogtool history <member> [timespan]`
  - Full pagified warning history for a single member.
- `[p]mywarnings`
  - Members view their own active warnings, points, and expiry times.

## Notes

- This cog depends on Red's core `Warnings` cog being loaded.
- Existing warnings are backfilled from core modlog warning cases the first time the cog syncs a guild.
- Automatic expiry removes warning entries and warning points from Red's core warnings config.
- Automatic expiry does NOT run Red's `warnaction` drop commands. If a member crossed a point
  threshold action (e.g. an auto-mute), expiring their warnings will not reverse it; staff must
  undo threshold actions manually.
- Deleting original modlog messages on expiry only works while the case message is still in the
  guild's current modlog channel; messages posted to a previous modlog channel are left behind.
- The `[p]modlogtool expire` dry run previews hard expiry only; point decay amounts are applied
  and reported on the real run.