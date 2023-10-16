# GuildLock Help

Tools for managing guild joins and leaves.

# serverlock
 - Usage: `[p]serverlock `
 - Restricted to: `BOT_OWNER`
 - Aliases: `glock`

View GuildLock settings

## serverlock limit
 - Usage: `[p]serverlock limit <limit> `

Set the maximum amount of servers the bot can be in.<br/><br/>Set to **0** to disable the server limit.

## serverlock minmembers
 - Usage: `[p]serverlock minmembers <minimum_members> `

Set the minimum number of members a server should have for the bot to stay in it.<br/><br/>Set to **0** to disable.

## serverlock botratio
 - Usage: `[p]serverlock botratio <bot_ratio> `

Set the the threshold percentage of bots-to-members for the bot to auto-leave.<br/><br/>**Example**<br/>If bot ratio is 60% and it joins a server with 10 members (7 bots and 3 members) it will auto-leave since that ratio is 70%.<br/><br/>Set to **0** to disable.

## serverlock channel
 - Usage: `[p]serverlock channel [channel] `

Set the log channel for the bot

## serverlock leave
 - Usage: `[p]serverlock leave <check> `

Make the bot leave certain servers.<br/><br/><br/>**Leave Arguments**<br/>- `botfarms`: leave servers with a bot ratio above the set percentage.<br/>- `minmembers`: leave servers with a member count below the set amount.<br/>- `blacklist`: leave any servers in the blacklist.<br/>- `whitelist`: leave any server not in the whitelist.

