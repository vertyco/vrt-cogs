# VrtUtils Help

Random utility commands

# pull
 - Usage: `[p]pull <cogs> `

Auto update & reload cogs

# diskspeed
 - Usage: `[p]diskspeed `
 - Restricted to: `BOT_OWNER`
 - Aliases: `diskbench`

Get disk R/W performance for the server your bot is on<br/><br/>The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,<br/>and the file buffering and similar adds too much overhead.<br/>Still this can give a good idea of where the bot is at I/O wise.

# pip
 - Usage: `[p]pip <command> `
 - Restricted to: `BOT_OWNER`

Run a pip command from within your bots venv

Extended Arg Info
> ### command: str
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# runshell
 - Usage: `[p]runshell <command> `
 - Restricted to: `BOT_OWNER`

Run a shell command from within your bots venv

Extended Arg Info
> ### command: str
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# findserverbyid
 - Usage: `[p]findserverbyid <server_id> `
 - Restricted to: `BOT_OWNER`

Find a server by ID

Extended Arg Info
> ### server_id: int
> ```
> A number without decimal places.
> ```
# botinfo
 - Usage: `[p]botinfo `

Get info about the bot

# getuser
 - Usage: `[p]getuser <user_id> `

Find a user by ID

Extended Arg Info
> ### user_id: Union[int, discord.user.User]
> ```
> A number without decimal places.
> ```
# botip
 - Usage: `[p]botip `
 - Restricted to: `BOT_OWNER`

Get the bots public IP address (in DMs)

# usersjson
 - Usage: `[p]usersjson `
 - Restricted to: `BOT_OWNER`

Get a json file containing all usernames/ID's in this server

# servers
 - Usage: `[p]servers `
 - Restricted to: `BOT_OWNER`

View servers your bot is in

# oldestchannels
 - Usage: `[p]oldestchannels [amount=10] `
 - Checks: `server_only`

See which channel is the oldest

Extended Arg Info
> ### amount: int = 10
> ```
> A number without decimal places.
> ```
# oldestmembers
 - Usage: `[p]oldestmembers [amount=10] [include_bots=False] `
 - Aliases: `oldestusers`
 - Checks: `server_only`

See which users have been in the server the longest<br/><br/>**Arguments**<br/>`amount:` how many members to display<br/>`include_bots:` (True/False) whether to include bots

Extended Arg Info
> ### amount: Optional[int] = 10
> ```
> A number without decimal places.
> ```
> ### include_bots: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
# oldestaccounts
 - Usage: `[p]oldestaccounts [amount=10] [include_bots=False] `
 - Checks: `server_only`

See which users have the oldest Discord accounts<br/><br/>**Arguments**<br/>`amount:` how many members to display<br/>`include_bots:` (True/False) whether to include bots

Extended Arg Info
> ### amount: Optional[int] = 10
> ```
> A number without decimal places.
> ```
> ### include_bots: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
# wipevcs
 - Usage: `[p]wipevcs `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Clear all voice channels from a server<br/><br/>This command was made to recover from Nuked servers that were VC spammed.<br/>Hopefully it will never need to be used again.

# syncslash
 - Usage: `[p]syncslash <global_sync> `
 - Restricted to: `BOT_OWNER`

Sync slash commands<br/><br/>**Arguments**<br/>`global_sync:` If True, syncs global slash commands, syncs current server by default

Extended Arg Info
> ### global_sync: bool
> ```
> Can be 1, 0, true, false, t, f
> ```
