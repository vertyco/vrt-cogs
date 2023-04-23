# GuildLog Help

Log when the bot joins or leaves a guild

# serverlogset
 - Usage: `[p]serverlogset `
 - Restricted to: `BOT_OWNER`
 - Aliases: `glset`
 - Checks: `server_only`

Configure GuildLog Settings

## serverlogset view
 - Usage: `[p]serverlogset view `

View GuildLog Settings

## serverlogset embeds
 - Usage: `[p]serverlogset embeds `

(Toggle) Embeds for join/leave log

## serverlogset channel
 - Usage: `[p]serverlogset channel [channel] `

Set a channel for the bot to log servers it leaves/joins

## serverlogset join
 - Usage: `[p]serverlogset join `

Configure join settings

### serverlogset join color
 - Usage: `[p]serverlogset join color <color> `

Set the color of the server join embed<br/><br/>If embeds are on, this will be the join color.<br/>Color value must be an integer

### serverlogset join msg
 - Usage: `[p]serverlogset join msg <message> `

Set the server join message<br/><br/>Valid placeholders are:<br/>{server} - the name of the server the bot just joined<br/>{servers} - the amount of servers the bot is now in<br/>{botname} - the name of the bot<br/>{bots} - the amount of bots in the server<br/>{members} - the member count of the server<br/><br/>To set back to default just to default as the message value

## serverlogset leave
 - Usage: `[p]serverlogset leave `

Configure leave settings

### serverlogset leave msg
 - Usage: `[p]serverlogset leave msg <message> `

Set the server leave message<br/><br/>Valid placeholders are:<br/>{server} - the name of the server the bot just joined<br/>{servers} - the amount of servers the bot is now in<br/>{botname} - the name of the bot<br/>{bots} - the amount of bots that were in the server<br/>{members} - the member count of the server<br/><br/>To set back to default just to default as the message value

### serverlogset leave color
 - Usage: `[p]serverlogset leave color <color> `

Set the color of the server leave embed<br/><br/>If embeds are on, this will be the leave color.<br/>Color value must be an integer

