A collection of stateless utility commands for getting info about various things.

# /latency (Slash Command)
Return the bot's latency.<br/>
 - Usage: `/latency`
# [p]zip
zip a file or files<br/>
 - Usage: `[p]zip [archive_name]`
 - Restricted to: `BOT_OWNER`
# [p]unzip
Unzips a zip file and sends the extracted files in the channel<br/>
 - Usage: `[p]unzip`
 - Restricted to: `BOT_OWNER`
# [p]pull
Auto update & reload cogs<br/>
 - Usage: `[p]pull <cogs>`
 - Restricted to: `BOT_OWNER`
# [p]quickpull
Auto update & reload cogs WITHOUT updating dependencies<br/>
 - Usage: `[p]quickpull <cogs>`
 - Restricted to: `BOT_OWNER`
# [p]todorefresh
Refresh a todo list channel.<br/>

Bring all messages without a ✅ or ❌ to the front of the channel.<br/>

**WARNING**: DO NOT USE THIS COMMAND IN A BUSY CHANNEL.<br/>
 - Usage: `[p]todorefresh <confirm>`
 - Restricted to: `MOD`
 - Aliases: `refreshtodo`
# [p]throwerror (Hybrid Command)
Throw an unhandled exception<br/>

A zero division error will be raised<br/>
 - Usage: `[p]throwerror`
 - Slash Usage: `/throwerror`
 - Restricted to: `BOT_OWNER`
# [p]getsource
Get the source code of a command<br/>
 - Usage: `[p]getsource <command>`
 - Restricted to: `BOT_OWNER`
# [p]text2binary
Convert text to binary<br/>
 - Usage: `[p]text2binary <text>`
# [p]binary2text
Convert a binary string to text<br/>
 - Usage: `[p]binary2text <binary_string>`
# [p]randomnum
Generate a random number between the numbers specified<br/>
 - Usage: `[p]randomnum [minimum=1] [maximum=100]`
 - Aliases: `rnum`
# [p]reactmsg
Add a reaction to a message<br/>
 - Usage: `[p]reactmsg <emoji> [message=None]`
 - Restricted to: `MOD`
 - Checks: `bot_has_server_permissions`
# [p]logs
View the bot's logs.<br/>
 - Usage: `[p]logs [max_pages=50]`
 - Restricted to: `BOT_OWNER`
# [p]diskspeed
Get disk R/W performance for the server your bot is on<br/>

The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,<br/>
and the file buffering and similar adds too much overhead.<br/>
Still this can give a good idea of where the bot is at I/O wise.<br/>
 - Usage: `[p]diskspeed`
 - Restricted to: `BOT_OWNER`
 - Aliases: `diskbench`
# [p]isownerof
Get a list of servers the specified user is the owner of<br/>
 - Usage: `[p]isownerof <user_id>`
 - Restricted to: `BOT_OWNER`
 - Aliases: `ownerof`
# [p]closestuser
Find the closest fuzzy match for a user<br/>
 - Usage: `[p]closestuser <query>`
# [p]getserverid
Find a server by name or ID<br/>
 - Usage: `[p]getserverid <query>`
 - Restricted to: `BOT_OWNER`
 - Aliases: `findserver`
# [p]getchannel
Find a channel by ID<br/>
 - Usage: `[p]getchannel <channel_id>`
 - Restricted to: `BOT_OWNER`
 - Aliases: `findchannel`
 - Checks: `bot_has_server_permissions`
# [p]getmessage
Fetch a channelID-MessageID combo and display the message<br/>
 - Usage: `[p]getmessage <channel_message>`
 - Restricted to: `BOT_OWNER`
 - Aliases: `findmessage`
 - Checks: `bot_has_server_permissions`
# [p]getuser
Find a user by ID<br/>
 - Usage: `[p]getuser <user_id>`
 - Aliases: `finduser`
# [p]getbanner
Get a user's banner<br/>
 - Usage: `[p]getbanner [user=None]`
# [p]getwebhook
Find a webhook by ID<br/>
 - Usage: `[p]getwebhook <webhook_id>`
# [p]usersjson
Get a json file containing all non-bot usernames/ID's in this server<br/>
 - Usage: `[p]usersjson`
 - Restricted to: `BOT_OWNER`
# [p]oldestchannels
See which channel is the oldest<br/>
 - Usage: `[p]oldestchannels [amount=10]`
 - Checks: `server_only`
# [p]oldestmembers
See which users have been in the server the longest<br/>

**Arguments**<br/>
`amount:` how many members to display<br/>
`include_bots:` (True/False) whether to include bots<br/>
 - Usage: `[p]oldestmembers [amount=10] [include_bots=False]`
 - Aliases: `oldestusers`
 - Checks: `server_only`
# [p]oldestaccounts
See which users have the oldest Discord accounts<br/>

**Arguments**<br/>
`amount:` how many members to display<br/>
`include_bots:` (True/False) whether to include bots<br/>
 - Usage: `[p]oldestaccounts [amount=10] [include_bots=False]`
 - Checks: `server_only`
# [p]rolemembers
View all members that have a specific role<br/>
 - Usage: `[p]rolemembers <role>`
 - Checks: `server_only`
# [p]wipevcs
Clear all voice channels from a server<br/>
 - Usage: `[p]wipevcs`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# [p]wipethreads
Clear all threads from a server<br/>
 - Usage: `[p]wipethreads`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# [p]emojidata
Get info about an emoji<br/>
 - Usage: `[p]emojidata <emoji>`
# [p]exportchat
Export chat history to an html file<br/>
 - Usage: `[p]exportchat [channel=operator.attrgetter('channel')] [limit=50] [tz_info=UTC] [military_time=False]`
 - Restricted to: `GUILD_OWNER`
# [p]botemojis
Add/Edit/List/Delete bot emojis<br/>
 - Usage: `[p]botemojis`
 - Restricted to: `BOT_OWNER`
 - Aliases: `botemoji and bmoji`
## [p]botemojis delete
Delete an bot emoji<br/>
 - Usage: `[p]botemojis delete <emoji_id>`
## [p]botemojis add
Create a new emoji from an image attachment<br/>

If a name is not specified, the image's filename will be used<br/>
 - Usage: `[p]botemojis add [name=None]`
## [p]botemojis edit
Edit a bot emoji's name<br/>
 - Usage: `[p]botemojis edit <emoji_id> <name>`
## [p]botemojis fromemoji
Create a new bot emoji from an existing one<br/>
 - Usage: `[p]botemojis fromemoji <emoji>`
 - Aliases: `addfrom and addemoji`
## [p]botemojis list
List all existing bot emojis<br/>
 - Usage: `[p]botemojis list`
## [p]botemojis get
Get details about a bot emoji<br/>
 - Usage: `[p]botemojis get <emoji_id>`
# [p]pip
Run a pip command from within your bots venv<br/>
 - Usage: `[p]pip <command>`
 - Restricted to: `BOT_OWNER`
# [p]runshell
Run a shell command from within your bots venv<br/>
 - Usage: `[p]runshell <command>`
 - Restricted to: `BOT_OWNER`
# [p]servers
View servers your bot is in<br/>
 - Usage: `[p]servers`
 - Restricted to: `BOT_OWNER`
 - Checks: `server_only`
# [p]botinfo
Get info about the bot<br/>
 - Usage: `[p]botinfo`
 - Cooldown: `1 per 15.0 seconds`
# [p]botip
Get the bots public IP address (in DMs)<br/>
 - Usage: `[p]botip`
 - Restricted to: `BOT_OWNER`
# [p]ispeed
Run an internet speed test.<br/>

Keep in mind that this speedtest is single threaded and may not be accurate!<br/>

Based on PhasecoreX's [netspeed](https://github.com/PhasecoreX/PCXCogs/tree/master/netspeed) cog<br/>
 - Usage: `[p]ispeed`
 - Restricted to: `BOT_OWNER`
# [p]shared
View members in a specified server that are also in this server<br/>
 - Usage: `[p]shared <server>`
 - Restricted to: `BOT_OWNER`
# [p]botshared
View servers that the bot and a user are both in together<br/>

Does not include the server this command is run in<br/>
 - Usage: `[p]botshared <user>`
 - Restricted to: `BOT_OWNER`
# [p]viewapikeys
DM yourself the bot's API keys<br/>
 - Usage: `[p]viewapikeys`
 - Restricted to: `BOT_OWNER`
# [p]cleantmp
Cleanup all the `.tmp` files left behind by Red's config<br/>
 - Usage: `[p]cleantmp`
 - Restricted to: `BOT_OWNER`
# [p]cogsizes
View the storage space each cog's saved data is taking up<br/>
 - Usage: `[p]cogsizes`
 - Restricted to: `BOT_OWNER`
# [p]codesizes
View the storage space each cog's code is taking up<br/>
 - Usage: `[p]codesizes`
 - Restricted to: `BOT_OWNER`
