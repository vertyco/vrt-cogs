Log when the bot joins or leaves a guild

# [p]serverlogset

Configure GuildLog Settings<br/>

- Usage: `[p]serverlogset`
- Restricted to: `BOT_OWNER`
- Aliases: `glset`
- Checks: `server_only`

## [p]serverlogset view

View GuildLog Settings<br/>

- Usage: `[p]serverlogset view`

## [p]serverlogset join

Configure join settings<br/>

- Usage: `[p]serverlogset join`

### [p]serverlogset join msg

Set the server join message<br/>

Valid placeholders are:<br/>
`{server}` - the name of the server the bot just joined<br/>
`{serverid}` - the id of the server the bot just joined<br/>
`{servers}` - the amount of servers the bot is now in<br/>
`{botname}` - the name of the bot<br/>
`{bots}` - the amount of bots in the server<br/>
`{members}` - the member count of the server<br/>

To set back to default just to `default` as the message value<br/>

- Usage: `[p]serverlogset join msg <message>`

### [p]serverlogset join color

Set the color of the server join embed<br/>

If embeds are on, this will be the join color.<br/>
Color value must be an integer<br/>

- Usage: `[p]serverlogset join color <color>`

## [p]serverlogset leave

Configure leave settings<br/>

- Usage: `[p]serverlogset leave`

### [p]serverlogset leave color

Set the color of the server leave embed<br/>

If embeds are on, this will be the leave color.<br/>
Color value must be an integer<br/>

- Usage: `[p]serverlogset leave color <color>`

### [p]serverlogset leave msg

Set the server leave message<br/>

Valid placeholders are:<br/>
`{server}` - the name of the server the bot just joined<br/>
`{serverid}` - the id of the server the bot just joined<br/>
`{servers}` - the amount of servers the bot is now in<br/>
`{botname}` - the name of the bot<br/>
`{bots}` - the amount of bots that were in the server<br/>
`{members}` - the member count of the server<br/>

To set back to default just to `default` as the message value<br/>

- Usage: `[p]serverlogset leave msg <message>`

## [p]serverlogset channel

Set a channel for the bot to log servers it leaves/joins<br/>

- Usage: `[p]serverlogset channel [channel]`

## [p]serverlogset embeds

(Toggle) Embeds for join/leave log<br/>

- Usage: `[p]serverlogset embeds`
