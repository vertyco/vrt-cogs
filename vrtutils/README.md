# VrtUtils Help

Random utility commands

# makemedocs
 - Usage: `[p]makemedocs <cog_name> [replace_prefix=False] [include_hidden=False]`

Create a Markdown docs page for a cog and send to discord

The full version of this is now a separate cog called AutoDocs

**Arguments**
`cog_name:`(str) The name of the cog you want to make docs for (Case Sensitive)
`replace_prefix:`(bool) If True, replaces the prefix placeholder [] with the prefix for the server its run in
`include_hidden:`(bool) If True, includes hidden commands

# diskspeed
 - Usage: `[p]diskspeed`
 - Aliases: `diskbench`


Get disk R/W performance for the server your bot is on

The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,
and the file buffering and similar adds too much overhead.
Still this can give a good idea of where the bot is at I/O wise.

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

See which channel is the oldest

# oldestmembers
 - Usage: `[p]oldestmembers [amount=10]`
 - Aliases: `oldestusers`


See which users have been in the server the longest

# oldestaccounts
 - Usage: `[p]oldestaccounts [amount=10]`

See which users have the oldest Discord accounts

# wipevcs
 - Usage: `[p]wipevcs`

Clear all voice channels from a guild

This command was made to recover from Nuked servers that were VC spammed.
Hopefully it will never need to be used again.

# syncslash
 - Usage: `[p]syncslash <global_sync>`

Sync slash commands

**Arguments**
`global_sync:` If True, syncs global slash commands, syncs current guild by default

