# EconomyTrack Help

Track your economy's total balance over time

# economytrack
 - Usage: `[p]economytrack `
 - Restricted to: `ADMIN`
 - Aliases: `ecotrack`
 - Checks: `server_only`

Configure EconomyTrack

## economytrack toggle
 - Usage: `[p]economytrack toggle `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Enable/Disable economy tracking for this server

## economytrack maxpoints
 - Usage: `[p]economytrack maxpoints <max_points> `
 - Restricted to: `BOT_OWNER`

Set the max amount of data points the bot will store<br/><br/>**Arguments**<br/>`<max_points>` Maximum amount of data points to store<br/><br/>The loop runs every minute, so 1440 points equals 1 day<br/>The default is 43200 (30 days)<br/>Set to 0 to store data indefinitely (Not Recommended)

Extended Arg Info
> ### max_points: int
> ```
> A number without decimal places.
> ```
## economytrack view
 - Usage: `[p]economytrack view `

View EconomyTrack Settings

## economytrack timezone
 - Usage: `[p]economytrack timezone [timezone=None] `

Set your desired timezone for the graph<br/><br/>**Arguments**<br/>`<timezone>` A string representing a valid timezone<br/><br/>Use this command without the argument to get a huge list of valid timezones.

Extended Arg Info
> ### timezone: str = None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# remoutliers
 - Usage: `[p]remoutliers <max_value> `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Cleanup data above a certain total economy balance

Extended Arg Info
> ### max_value: int
> ```
> A number without decimal places.
> ```
# bankgraph
 - Usage: `[p]bankgraph [timespan=1d] `
 - Aliases: `bgraph`
 - Cooldown: `5 per 60.0 seconds`
 - Checks: `server_only`

View bank status over a period of time.<br/>**Arguments**<br/>`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.<br/>Must be at least 1 hour.<br/>**Examples:**<br/>    - `[p]bankgraph 3w2d`<br/>    - `[p]bankgraph 5d`<br/>    - `[p]bankgraph all`

Extended Arg Info
> ### timespan: str = '1d'
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
