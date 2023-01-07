# VrtUtils Help

Random utility commands

# pull

- Usage: `[p]pull <cogs>`

Auto update & reload cogs

# diskspeed

- Usage: `[p]diskspeed`
- Aliases: `diskbench`

Get disk R/W performance for the server your bot is on<br/><br/>The results of this test may vary, Python isn't fast
enough for this kind of byte-by-byte writing,<br/>and the file buffering and similar adds too much overhead.<br/>Still
this can give a good idea of where the bot is at I/O wise.

# pip

- Usage: `[p]pip <command>`

Run a pip command from within your bots venv

# runshell

- Usage: `[p]runshell <command>`

Run a shell command from within your bots venv

# findguildbyid

- Usage: `[p]findguildbyid <guild_id>`

Find a guild by ID

# botinfo

- Usage: `[p]botinfo`

Get info about the bot

# getuser

- Usage: `[p]getuser <user_id>`

Find a user by ID

# botip

- Usage: `[p]botip`

Get the bots public IP address (in DMs)

# usersjson

- Usage: `[p]usersjson`

Get a json file containing all usernames/ID's in this guild

# guilds

- Usage: `[p]guilds`

View guilds your bot is in

# oldestchannels

- Usage: `[p]oldestchannels [amount=10]`
- Checks: guild_only

See which channel is the oldest

# oldestmembers

- Usage: `[p]oldestmembers [amount=10] [include_bots=False]`
- Aliases: `oldestusers`
- Checks: guild_only

See which users have been in the server the longest<br/><br/>**Arguments**<br/>`amount:` how many members to
display<br/>`include_bots:` (True/False) whether to include bots

# oldestaccounts

- Usage: `[p]oldestaccounts [amount=10] [include_bots=False]`
- Checks: guild_only

See which users have the oldest Discord accounts<br/><br/>**Arguments**<br/>`amount:` how many members to
display<br/>`include_bots:` (True/False) whether to include bots

# wipevcs

- Usage: `[p]wipevcs`
- Checks: guild_only

Clear all voice channels from a guild<br/><br/>This command was made to recover from Nuked servers that were VC
spammed.<br/>Hopefully it will never need to be used again.

# syncslash

- Usage: `[p]syncslash <global_sync>`

Sync slash commands<br/><br/>**Arguments**<br/>`global_sync:` If True, syncs global slash commands, syncs current guild
by default
