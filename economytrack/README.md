# EconomyTrack Help

Track your economy's total balance over time

# economytrack
 - Usage: `[p]economytrack`
 - Aliases: `ecotrack`


Configure EconomyTrack

## economytrack maxpoints
 - Usage: `[p]economytrack maxpoints <max_points>`

Set the max amount of data points the bot will store

**Arguments**
`<max_points>` Maximum amount of data points to store

The loop runs every minute, so 1440 points equals 1 day
The default is 43200 (30 days)
Set to 0 to store data indefinitely (Not Recommended)

## economytrack timezone
 - Usage: `[p]economytrack timezone [timezone=None]`

Set your desired timezone for the graph

**Arguments**
`<timezone>` A string representing a valid timezone

Use this command without the argument to get a huge list of valid timezones.

## economytrack toggle
 - Usage: `[p]economytrack toggle`

Enable/Disable economy tracking for this server

## economytrack view
 - Usage: `[p]economytrack view`

View EconomyTrack Settings

# remoutliers
 - Usage: `[p]remoutliers <max_value>`

Cleanup data above a certain total economy balance

# bankgraph
 - Usage: `[p]bankgraph [timespan=1d]`
 - Aliases: `bgraph`


View bank status over a period of time.
**Arguments**
`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.
Must be at least 1 hour.
**Examples:**
    - `[p]bankgraph 3w2d`
    - `[p]bankgraph 5d`
    - `[p]bankgraph all`
