# EconomyTrack Help

Track your economy's total balance over time<br/><br/>Also track you server's member count!

# economytrack
 - Usage: `[p]economytrack `
 - Aliases: `ecotrack`
 - Checks: `server_only`

Configure EconomyTrack

## economytrack maxpoints
 - Usage: `[p]economytrack maxpoints <max_points> `
 - Restricted to: `BOT_OWNER`

Set the max amount of data points the bot will store<br/><br/>**Arguments**<br/>`<max_points>` Maximum amount of data points to store<br/><br/>The loop runs every minute, so 1440 points equals 1 day<br/>The default is 43200 (30 days)<br/>Set to 0 to store data indefinitely (Not Recommended)

## economytrack togglebanktrack
 - Usage: `[p]economytrack togglebanktrack `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Enable/Disable economy tracking for this server

## economytrack timezone
 - Usage: `[p]economytrack timezone <timezone> `

Set your desired timezone for the graph<br/><br/>**Arguments**<br/>`<timezone>` A string representing a valid timezone<br/><br/>**Example:** `[p]ecotrack timezone US/Eastern`<br/><br/>Use this command without the argument to get a huge list of valid timezones.

## economytrack view
 - Usage: `[p]economytrack view `

View EconomyTrack Settings

## economytrack togglemembertrack
 - Usage: `[p]economytrack togglemembertrack `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Enable/Disable member tracking for this server

# remoutliers
 - Usage: `[p]remoutliers <max_value> `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Cleanup data above a certain total economy balance

# bankgraph
 - Usage: `[p]bankgraph [timespan=1d] `
 - Aliases: `bgraph`
 - Cooldown: `5 per 60.0 seconds`
 - Checks: `server_only`

View bank status over a period of time.<br/>**Arguments**<br/>`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.<br/>Must be at least 1 hour.<br/>**Examples:**<br/>    - `[p]bankgraph 3w2d`<br/>    - `[p]bankgraph 5d`<br/>    - `[p]bankgraph all`

# membergraph
 - Usage: `[p]membergraph [timespan=1d] `
 - Aliases: `memgraph`
 - Cooldown: `5 per 60.0 seconds`
 - Checks: `server_only`

View member count over a period of time.<br/>**Arguments**<br/>`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.<br/>Must be at least 1 hour.<br/>**Examples:**<br/>    - `[p]membergraph 3w2d`<br/>    - `[p]membergraph 5d`<br/>    - `[p]membergraph all`

