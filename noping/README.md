# NoPing

Let users opt out of being pinged using Discord's AutoMod system.<br/><br/>Manages AutoMod keyword filter rules to block pings to opted-out users, with optional per-user availability schedules and timezone support.<br/>All times use Discord's native timestamp formatting so they display correctly in every user's local time.

## [p]noping

Toggle whether you can be pinged.<br/>

Use without a subcommand to quickly toggle on/off.<br/>

 - Usage: `[p]noping`
 - Checks: `guild_only and bot_has_permissions`

### [p]noping schedule

Open the interactive schedule editor.<br/>

Set availability windows for each day of the week. Outside these windows, pings to you will be blocked.<br/>

 - Usage: `[p]noping schedule`

### [p]noping timezone

Set your personal timezone for NoPing schedules.<br/>

Overrides the server default. Use standard names like `America/New_York`, `Europe/London`, etc.<br/>
Use `none` to clear your personal timezone and use the server default.<br/>

 - Usage: `[p]noping timezone <timezone>`
 - Aliases: `tz`

### [p]noping status

Check your current NoPing status and schedule.<br/>

Shows your protection status, effective timezone, current time, schedule overview, and next transition time.<br/>

 - Usage: `[p]noping status`

### [p]noping help

Show an interactive tutorial for the NoPing system.<br/>

A multi-page walkthrough covering toggling, schedules, timezones, and admin settings.<br/>

 - Usage: `[p]noping help`

## [p]nopingset

NoPing admin settings.<br/>

 - Usage: `[p]nopingset`
 - Restricted to: `ADMIN`
 - Checks: `guild_only and bot_has_permissions`

### [p]nopingset timezone

Set the server timezone for NoPing schedules.<br/>

Use standard timezone names like `America/New_York`, `Europe/London`, `Asia/Tokyo`, etc.<br/>

 - Usage: `[p]nopingset timezone <timezone>`
 - Aliases: `tz`

### [p]nopingset toggle

Toggle whether regular users can use the NoPing system.<br/>

 - Usage: `[p]nopingset toggle`

### [p]nopingset add

Force-enable NoPing for a user.<br/>

 - Usage: `[p]nopingset add <user>`

### [p]nopingset remove

Force-disable NoPing for a user and clear their schedule.<br/>

 - Usage: `[p]nopingset remove <user>`

### [p]nopingset view

List all users with NoPing enabled.<br/>

Shows each user's status (active/inactive), schedule type (permanent/scheduled), and personal timezone if set.<br/>

 - Usage: `[p]nopingset view`
 - Aliases: `list`

### [p]nopingset prune

Remove users no longer in the server from NoPing.<br/>

 - Usage: `[p]nopingset prune`

### [p]nopingset settings

View current NoPing settings for this server.<br/>

Shows server timezone, user access toggle, enrollment counts, active rule count, and current time.<br/>

 - Usage: `[p]nopingset settings`
