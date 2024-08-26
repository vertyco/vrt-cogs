# EconomyTrack Help

Track your economy's total balance over time<br/><br/>Also track you server's member count!

# .economytrack
Configure EconomyTrack<br/>
 - Usage: `.economytrack`
 - Aliases: `ecotrack`
 - Checks: `server_only`
## .economytrack timezone
Set your desired timezone for the graph<br/>

**Arguments**<br/>
`<timezone>` A string representing a valid timezone<br/>

**Example:** `.ecotrack timezone US/Eastern`<br/>

Use this command without the argument to get a huge list of valid timezones.<br/>
 - Usage: `.economytrack timezone <timezone>`
## .economytrack togglebanktrack
Enable/Disable economy tracking for this server<br/>
 - Usage: `.economytrack togglebanktrack`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
## .economytrack maxpoints
Set the max amount of data points the bot will store<br/>

**Arguments**<br/>
`<max_points>` Maximum amount of data points to store<br/>

The loop runs every 2 minutes, so 720 points equals 1 day<br/>
The default is 21600 (30 days)<br/>
Set to 0 to store data indefinitely (Not Recommended)<br/>
 - Usage: `.economytrack maxpoints <max_points>`
 - Restricted to: `BOT_OWNER`
## .economytrack view
View EconomyTrack Settings<br/>
 - Usage: `.economytrack view`
## .economytrack togglemembertrack
Enable/Disable member tracking for this server<br/>
 - Usage: `.economytrack togglemembertrack`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# .remoutliers
Cleanup data above a certain total economy balance<br/>

**Arguments**<br/>
datatype: either `bank` or `member`<br/>
 - Usage: `.remoutliers <max_value> [datatype=bank]`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# .bankgraph
View bank status over a period of time.<br/>
**Arguments**<br/>
`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.<br/>
Must be at least 1 hour.<br/>
**Examples:**<br/>
    - `.bankgraph 3w2d`<br/>
    - `.bankgraph 5d`<br/>
    - `.bankgraph all`<br/>
 - Usage: `.bankgraph [timespan=1d]`
 - Aliases: `bgraph`
 - Cooldown: `5 per 60.0 seconds`
 - Checks: `server_only`
# .membergraph
View member count over a period of time.<br/>
**Arguments**<br/>
`<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.<br/>
Must be at least 1 hour.<br/>
**Examples:**<br/>
    - `.membergraph 3w2d`<br/>
    - `.membergraph 5d`<br/>
    - `.membergraph all`<br/>
 - Usage: `.membergraph [timespan=1d]`
 - Aliases: `memgraph`
 - Cooldown: `5 per 60.0 seconds`
 - Checks: `server_only`
