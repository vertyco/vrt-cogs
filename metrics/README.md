# Metrics

Track various metrics about your server.

## [p]metricsdb

Database Commands<br/>

 - Usage: `[p]metricsdb`
 - Restricted to: `BOT_OWNER`

### [p]metricsdb postgres

Set the Postgres connection info<br/>

 - Usage: `[p]metricsdb postgres`

### [p]metricsdb nukedb

Delete the database for this cog and reinitialize it<br/>

THIS CANNOT BE UNDONE!<br/>

 - Usage: `[p]metricsdb nukedb <confirm>`
 - Checks: `ensure_db_connection`

### [p]metricsdb diagnose

Check the database connection<br/>

 - Usage: `[p]metricsdb diagnose`

## [p]metrics (Hybrid Command)

View metrics about the bot and server.<br/>

 - Usage: `[p]metrics`
 - Slash Usage: `/metrics`
 - Checks: `ensure_db_connection and guild_only`

### [p]metrics members (Hybrid Command)

View member-related metrics.<br/>

 - Usage: `[p]metrics members [timespan=12h] [metric=total] [show_global=False] [start=None] [end=None]`
 - Slash Usage: `/metrics members [timespan=12h] [metric=total] [show_global=False] [start=None] [end=None]`
 - Aliases: `membercount and population`
 - Cooldown: `1 per 10.0 seconds`

### [p]metrics dashboard (Hybrid Command)

Open the interactive metrics dashboard.<br/>

 - Usage: `[p]metrics dashboard`
 - Slash Usage: `/metrics dashboard`
 - Aliases: `dash`
 - Cooldown: `1 per 10.0 seconds`

### [p]metrics bank (Hybrid Command)

View bank-related metrics.<br/>

 - Usage: `[p]metrics bank [timespan=12h] [average_balance=False] [show_global=False] [start=None] [end=None]`
 - Slash Usage: `/metrics bank [timespan=12h] [average_balance=False] [show_global=False] [start=None] [end=None]`
 - Aliases: `economy`
 - Cooldown: `1 per 10.0 seconds`

### [p]metrics performance (Hybrid Command)

View bot performance metrics.<br/>

 - Usage: `[p]metrics performance [timespan=12h] [metric=latency] [start=None] [end=None]`
 - Slash Usage: `/metrics performance [timespan=12h] [metric=latency] [start=None] [end=None]`
 - Aliases: `perf`
 - Cooldown: `1 per 10.0 seconds`

## [p]setmetrics (Hybrid Command)

Configure the Metrics cog.<br/>

 - Usage: `[p]setmetrics`
 - Slash Usage: `/setmetrics`
 - Restricted to: `ADMIN`
 - Aliases: `metricset and metricsset`

### [p]setmetrics global (Hybrid Command)

View and manage global settings.<br/>

 - Usage: `[p]setmetrics global`
 - Slash Usage: `/setmetrics global`
 - Restricted to: `BOT_OWNER`
 - Checks: `ensure_db_connection`

#### [p]setmetrics global maxage (Hybrid Command)

Set the maximum age in days to keep snapshots.<br/>

 - Usage: `[p]setmetrics global maxage <days>`
 - Slash Usage: `/setmetrics global maxage <days>`

#### [p]setmetrics global track (Hybrid Command)

Toggle tracking for a specific global metric.<br/>

 - Usage: `[p]setmetrics global track <metric>`
 - Slash Usage: `/setmetrics global track <metric>`

#### [p]setmetrics global prunezero (Hybrid Command)

Prune guild member snapshots that have 0 total members.<br/>

These are typically caused by Discord API issues and are not valid data points.<br/>

**Arguments:**<br/>
- `dry_run`: If True (default), only show what would be deleted without deleting<br/>

**Examples:**<br/>
- `[p]setmetrics global prunezero True` - Preview zero-member snapshots<br/>
- `[p]setmetrics global prunezero False` - Delete zero-member snapshots<br/>

 - Usage: `[p]setmetrics global prunezero [dry_run=True]`
 - Slash Usage: `/setmetrics global prunezero [dry_run=True]`

#### [p]setmetrics global view (Hybrid Command)

View the current global settings.<br/>

 - Usage: `[p]setmetrics global view`
 - Slash Usage: `/setmetrics global view`

#### [p]setmetrics global economyinterval (Hybrid Command)

Set the interval in minutes between economy snapshots.<br/>

 - Usage: `[p]setmetrics global economyinterval <minutes>`
 - Slash Usage: `/setmetrics global economyinterval <minutes>`

#### [p]setmetrics global importeconomytrack (Hybrid Command)

Import data from the EconomyTrack cog.<br/>

This imports legacy EconomyTrack data into the new GuildEconomySnapshot<br/>
and GlobalEconomySnapshot tables.<br/>

**Arguments:**<br/>
- `overwrite`: If True, delete all existing economy data before importing<br/>

 - Usage: `[p]setmetrics global importeconomytrack <overwrite>`
 - Slash Usage: `/setmetrics global importeconomytrack <overwrite>`

#### [p]setmetrics global performanceinterval (Hybrid Command)

Set the interval in minutes between performance snapshots.<br/>

 - Usage: `[p]setmetrics global performanceinterval <minutes>`
 - Slash Usage: `/setmetrics global performanceinterval <minutes>`

#### [p]setmetrics global prune (Hybrid Command)

Prune statistical outliers from the database.<br/>

This detects and removes data points that are anomalous based on standard<br/>
deviation analysis. For example, if member count suddenly drops to 0 when<br/>
surrounding data points are ~1000, that's an outlier.<br/>

**Arguments:**<br/>
- `metric`: Which metric to analyze - "members", "economy", or "performance"<br/>
- `scope`: Which snapshots to prune - "global", "guild", or "all"<br/>
- `threshold`: Number of standard deviations from mean to consider outlier (default: 3.0)<br/>
- `dry_run`: If True (default), only show what would be deleted without deleting<br/>

**Examples:**<br/>
- `[p]setmetrics global prune members all 3.0 True` - Preview member outliers<br/>
- `[p]setmetrics global prune economy guild 2.5 False` - Delete guild economy outliers<br/>

 - Usage: `[p]setmetrics global prune <metric> [scope=all] [threshold=3.0] [dry_run=True]`
 - Slash Usage: `/setmetrics global prune <metric> [scope=all] [threshold=3.0] [dry_run=True]`

#### [p]setmetrics global memberinterval (Hybrid Command)

Set the interval in minutes between member snapshots.<br/>

 - Usage: `[p]setmetrics global memberinterval <minutes>`
 - Slash Usage: `/setmetrics global memberinterval <minutes>`

### [p]setmetrics timezone (Hybrid Command)

Set the timezone for this server.<br/>

 - Usage: `[p]setmetrics timezone <tz>`
 - Slash Usage: `/setmetrics timezone <tz>`
 - Checks: `ensure_db_connection`

### [p]setmetrics view (Hybrid Command)

View the current settings for this server.<br/>

 - Usage: `[p]setmetrics view`
 - Slash Usage: `/setmetrics view`
 - Checks: `ensure_db_connection`

### [p]setmetrics track (Hybrid Command)

Toggle tracking for a specific metric in this server.<br/>

 - Usage: `[p]setmetrics track <metric>`
 - Slash Usage: `/setmetrics track <metric>`
 - Checks: `ensure_db_connection`

