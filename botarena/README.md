# BotArena

Bot Arena - Build and Battle Robots!<br/><br/>Create custom battle bots from chassis, plating, and weapons,<br/>then fight against other players in arena combat.

## [p]botarenaset

Configure Bot Arena settings for this server<br/>

 - Usage: `[p]botarenaset`
 - Restricted to: `ADMIN`
 - Aliases: `baset`
 - Checks: `guild_only`

### [p]botarenaset telemetry

[Owner] View and manage campaign battle telemetry<br/>

 - Usage: `[p]botarenaset telemetry`
 - Restricted to: `BOT_OWNER`

#### [p]botarenaset telemetry prune

Remove telemetry entries older than a duration<br/>

**Arguments:**<br/>
- `older_than` - Remove entries older than this (e.g., `30d`, `1w`, `7d`)<br/>
- `confirm` - Set to True to confirm deletion<br/>

 - Usage: `[p]botarenaset telemetry prune <older_than> [confirm=False]`

#### [p]botarenaset telemetry report

View campaign mission statistics<br/>

Shows win rates, attempt counts, and difficulty indicators.<br/>

**Arguments:**<br/>
- `since` - Only include data from this time period (e.g., `7d`, `24h`, `1w`)<br/>

 - Usage: `[p]botarenaset telemetry report [since=None]`

#### [p]botarenaset telemetry wipe

Delete all telemetry data<br/>

**Arguments:**<br/>
- `confirm` - Set to True to confirm deletion<br/>

 - Usage: `[p]botarenaset telemetry wipe [confirm=False]`

### [p]botarenaset resetplayer

[Owner] Reset a player's data completely<br/>

 - Usage: `[p]botarenaset resetplayer <user> [confirm=False]`
 - Restricted to: `BOT_OWNER`

### [p]botarenaset wipeall

[Owner] Wipe ALL player data from Bot Arena<br/>

This is irreversible! Type the confirmation code to proceed.<br/>

 - Usage: `[p]botarenaset wipeall [confirm=False]`
 - Restricted to: `BOT_OWNER`

### [p]botarenaset viewparts

[Owner] View all parts and their render offsets<br/>

Debug tool for previewing part combinations and weapon offsets.<br/>

 - Usage: `[p]botarenaset viewparts`
 - Restricted to: `BOT_OWNER`

## [p]botarena

Bot Arena - Build and battle robots!<br/>

Opens the main game hub where you can:<br/>
- Play through the Campaign<br/>
- Build and customize bots<br/>
- Challenge other players<br/>
- Browse the shop<br/>

 - Usage: `[p]botarena`
 - Aliases: `ba`
 - Checks: `guild_only`

## [p]botprofile

View a player's Bot Arena profile and stats.<br/>

Shows campaign progress, battle record, combat stats, and owned bots.<br/>

**Arguments:**<br/>
- `member`: The player to view (defaults to yourself)<br/>

**Examples:**<br/>
- `[p]botprofile` - View your own profile<br/>
- `[p]botprofile @User` - View another player's profile<br/>

 - Usage: `[p]botprofile [member=None]`
 - Aliases: `bp`
 - Checks: `guild_only`

## [p]botarenareset

Reset your Bot Arena account.<br/>

**⚠️ WARNING:** This permanently deletes ALL your progress!<br/>
- All credits will be lost<br/>
- All bots and parts will be deleted<br/>
- All campaign progress will be reset<br/>
- All battle statistics will be cleared<br/>

You will start fresh with 8,200 credits.<br/>

Use this if you're stuck and can't afford to continue.<br/>

 - Usage: `[p]botarenareset`
 - Aliases: `bareset`
 - Checks: `guild_only`

## [p]botleaderboard

View the Bot Arena leaderboard.<br/>

**Modes:**<br/>
- `wins` - Total wins (campaign + PvP) [default]<br/>
- `pvp` - PvP wins<br/>
- `campaign` - Campaign wins<br/>
- `damage` - Total damage dealt<br/>
- `credits` - Current credit balance<br/>
- `bots` - Enemy bots destroyed<br/>

**Examples:**<br/>
- `[p]botleaderboard` - Show total wins leaderboard<br/>
- `[p]botlb pvp` - Show PvP wins leaderboard<br/>
- `[p]botlb damage` - Show damage dealt leaderboard<br/>

 - Usage: `[p]botleaderboard [mode=wins]`
 - Aliases: `botlb`
 - Checks: `guild_only`

