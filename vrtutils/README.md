# VrtUtils Help

Random utility commands

# pull
 - Usage: `[p]pull <cogs> `
 - Restricted to: `BOT_OWNER`

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

# runshell
 - Usage: `[p]runshell <command> `
 - Restricted to: `BOT_OWNER`

Run a shell command from within your bots venv

# findserverbyid
 - Usage: `[p]findserverbyid <server_id> `
 - Restricted to: `BOT_OWNER`

Find a server by ID

# botinfo
 - Usage: `[p]botinfo `

Get info about the bot

# getuser
 - Usage: `[p]getuser <user_id> `

Find a user by ID

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

# oldestmembers
 - Usage: `[p]oldestmembers [amount=10] [include_bots=False] `
 - Aliases: `oldestusers`
 - Checks: `server_only`

See which users have been in the server the longest<br/><br/>**Arguments**<br/>`amount:` how many members to display<br/>`include_bots:` (True/False) whether to include bots

# oldestaccounts
 - Usage: `[p]oldestaccounts [amount=10] [include_bots=False] `
 - Checks: `server_only`

See which users have the oldest Discord accounts<br/><br/>**Arguments**<br/>`amount:` how many members to display<br/>`include_bots:` (True/False) whether to include bots

# rolemembers
 - Usage: `[p]rolemembers <role> `
 - Checks: `server_only`

View all members that have a specific role

# wipevcs
 - Usage: `[p]wipevcs `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Clear all voice channels from a server

# wipethreads
 - Usage: `[p]wipethreads `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Clear all threads from a server

# text2binary
 - Usage: `[p]text2binary <text> `

Convert text to binary

# binary2text
 - Usage: `[p]binary2text <binary_string> `

Convert a binary string to text

# randomnum
 - Usage: `[p]randomnum [minimum=1] [maximum=100] `
 - Aliases: `rnum`

Generate a random number between the numbers specified

