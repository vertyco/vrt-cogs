# CommandLock

Lock command or cog usage to specific channels and redirect users to the correct ones.

## [p]commandlock

Manage command and cog locks to specific channels.<br/>

 - Usage: `[p]commandlock`
 - Restricted to: `ADMIN`
 - Aliases: `cmdlock`
 - Checks: `guild_only`

### [p]commandlock whitelistrole

Add/Remove whitelisted roles to bypass all command and cog locks.<br/>

 - Usage: `[p]commandlock whitelistrole <role>`

### [p]commandlock lock

Add a lock to a cog or command to restrict its usage to the specified channels.<br/>

**Notes:**<br/>
- Bot owners, server owners, and admins are immune to command locks.<br/>
- Whitelisted roles bypass all command and cog locks.<br/>
- Command locks take precedence over cog locks.<br/>
- Channels can be categories, in which case all channels within that category are included.<br/>

**Examples:**<br/>
`[p]commandlock lock #allowed-channel MyCog`<br/>
`[p]commandlock lock channel_id channel_id_2 MyCommand`<br/>
`[p]commandlock lock #channel1 #channel2 MyCog`<br/>

 - Usage: `[p]commandlock lock <allowed_channels> <cog_or_command>`
 - Aliases: `set and add`

### [p]commandlock toggelchannel

Toggle a channel for an existing cog or command lock.<br/>

This quickly adds or removes a channel from the lock configuration.<br/>

Example:<br/>
`[p]commandlock toggle #channel MyCog`<br/>
`[p]cmdlock toggle #channel mycommand`<br/>

 - Usage: `[p]commandlock toggelchannel <channel> <cog_or_command>`
 - Aliases: `toggle`

### [p]commandlock view

View the current lock settings for a cog or command.<br/>

If no cog or command is specified, shows all locks for the server.<br/>

If a cog is specified, shows the useable channels for that cog including individual command locks.<br/>
If a command is specified, shows the useable channels for that command.<br/>

 - Usage: `[p]commandlock view [cog_or_command=None]`

### [p]commandlock deleteafter

Set a duration in seconds after the redirect message is deleted.<br/>

Set to 0 to never delete the messages.<br/>

 - Usage: `[p]commandlock deleteafter <seconds>`

### [p]commandlock unlock

Remove a lock from a cog or command, allowing it to be used in any channel.<br/>

 - Usage: `[p]commandlock unlock <cog_or_command>`
 - Aliases: `remove, rem, and del`

