# LevelUp Help

Your friendly neighborhood leveling system

# stars
 - Usage: `[p]stars <user>`
 - Aliases: `givestar, addstar, and thanks`
 - Checks: guild_only

Reward a good noodle<br/>Give a star to a user for being a good noodle

# myprofile
 - Usage: `[p]myprofile`
 - Aliases: `mypf and pfset`
 - Checks: guild_only

Customize your profile colors<br/><br/>Here is a link to google's color picker:<br/>**[Hex Color Picker](https://htmlcolorcodes.com/)**

## myprofile addfont
 - Usage: `[p]myprofile addfont [preferred_filename=None]`

Add a custom font to the cog from discord<br/><br/>**Arguments**<br/>`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/>**Note:** do not include the file extension in the preferred name, it will be added automatically

## myprofile namecolor
 - Usage: `[p]myprofile namecolor <hex_color>`
 - Aliases: `name`

Set a hex color for your username<br/><br/>Here is a link to google's color picker:<br/>**[Hex Color Picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize your name color each time you run the command

## myprofile background
 - Usage: `[p]myprofile background [image_url=None]`
 - Aliases: `bg`
 - Cooldown: 1 per 30.0 seconds

Set a background for your profile<br/><br/>This will override your profile banner as the background<br/><br/>**WARNING**<br/>Profile backgrounds are wide landscapes (1050 by 450 pixels) with an aspect ratio of 21:9<br/>Using portrait images will be cropped.<br/><br/>Tip: Googling "dual monitor backgrounds" gives good results for the right images<br/><br/>Here are some good places to look.<br/>[dualmonitorbackgrounds](https://www.dualmonitorbackgrounds.com/)<br/>[setaswall](https://www.setaswall.com/dual-monitor-wallpapers/)<br/>[pexels](https://www.pexels.com/photo/panoramic-photography-of-trees-and-lake-358482/)<br/>[teahub](https://www.teahub.io/searchw/dual-monitor/)<br/><br/>**Additional Options**<br/> - Leave image_url blank to reset back to using your profile banner (or random if you don't have one)<br/> - `random` will randomly select from a pool of default backgrounds each time<br/> - `filename` run `[p]mypf backgrounds` to view default options you can use by including their filename

## myprofile rembackground
 - Usage: `[p]myprofile rembackground <filename>`

Remove a default background from the cog's backgrounds folder

## myprofile addbackground
 - Usage: `[p]myprofile addbackground [preferred_filename=None]`

Add a custom background to the cog from discord<br/><br/>**Arguments**<br/>`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/>**Note:** do not include the file extension in the preferred name, it will be added automatically

## myprofile fonts
 - Usage: `[p]myprofile fonts`
 - Cooldown: 1 per 30.0 seconds

View available fonts to use

## myprofile fontpath
 - Usage: `[p]myprofile fontpath`

Get folder path for this cog's default backgrounds

## myprofile remfont
 - Usage: `[p]myprofile remfont <filename>`

Remove a font from the cog's font folder

## myprofile statcolor
 - Usage: `[p]myprofile statcolor <hex_color>`
 - Aliases: `stat`

Set a hex color for your server stats<br/><br/>Here is a link to google's color picker:<br/>**[Hex Color Picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize your name color each time you run the command

## myprofile levelbar
 - Usage: `[p]myprofile levelbar <hex_color>`
 - Aliases: `lvlbar and bar`

Set a hex color for your level bar<br/><br/>Here is a link to google's color picker:<br/>**[Hex Color Picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize your name color each time you run the command

## myprofile bgpath
 - Usage: `[p]myprofile bgpath`

Get folder path for this cog's default backgrounds

## myprofile type
 - Usage: `[p]myprofile type`

Toggle your profile image type (full/slim)<br/><br/>Full size includes your balance, role icon and prestige icon<br/>Slim is a smaller slimmed down version

## myprofile font
 - Usage: `[p]myprofile font <font_name>`

Set a font for your profile<br/><br/>To view available fonts, type `[p]myprofile fonts`<br/>To revert to the default font, use `default` for the `font_name` argument

## myprofile backgrounds
 - Usage: `[p]myprofile backgrounds`
 - Cooldown: 1 per 30.0 seconds

View the default backgrounds

# pf
 - Usage: `[p]pf [user]`
 - Cooldown: 1 per 5.0 seconds
 - Checks: guild_only

View your profile

# prestige
 - Usage: `[p]prestige`
 - Checks: guild_only

Prestige your rank!<br/>Once you have reached this servers prestige level requirement, you can<br/>reset your level and experience to gain a prestige level and any perks associated with it<br/><br/>If you are over level and xp when you prestige, your xp and levels will carry over

# lvltop
 - Usage: `[p]lvltop <stat>`
 - Aliases: `topstats, membertop, and topranks`
 - Checks: guild_only

View the Leaderboard<br/><br/>**Arguments**<br/>`stat`: What kind of stat to display the weekly leaderboard for<br/>Valid options are `exp`, `messages`, and `voice`<br/>Abbreviations of those arguments may also be used

# startop
 - Usage: `[p]startop`
 - Aliases: `starlb`
 - Checks: guild_only

View the star leaderboard

# weekly
 - Usage: `[p]weekly <stat>`

View the weekly leaderboard<br/><br/>**Arguments**<br/>`stat`: What kind of stat to display the weekly leaderboard for<br/>Valid options are `exp`, `messages`, `stars`, and `voice`<br/>Abbreviations of those arguments may also be used

# lvlset
 - Usage: `[p]lvlset`
 - Aliases: `lset and levelup`
 - Checks: guild_only

Access LevelUp setting commands

## lvlset voice
 - Usage: `[p]lvlset voice`

Voice settings

### lvlset voice solo
 - Usage: `[p]lvlset voice solo`

Ignore solo voice users<br/>Toggle whether solo users in a voice channel can gain voice XP

### lvlset voice xp
 - Usage: `[p]lvlset voice xp <voice_xp>`

Set voice XP gain<br/>Sets the amount of XP gained per minute in a voice channel (default is 2)

### lvlset voice muted
 - Usage: `[p]lvlset voice muted`

Ignore muted voice users<br/>Toggle whether self-muted users in a voice channel can gain voice XP

### lvlset voice channelbonus
 - Usage: `[p]lvlset voice channelbonus <channel> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain channels<br/><br/>This bonus applies to voice time xp<br/><br/>Set both min and max to 0 to remove the role bonus

### lvlset voice rolebonus
 - Usage: `[p]lvlset voice rolebonus <role> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain roles<br/><br/>This bonus applies to voice time xp<br/><br/>Set both min and max to 0 to remove the role bonus

### lvlset voice deafened
 - Usage: `[p]lvlset voice deafened`

Ignore deafened voice users<br/>Toggle whether deafened users in a voice channel can gain voice XP

### lvlset voice invisible
 - Usage: `[p]lvlset voice invisible`

Ignore invisible voice users<br/>Toggle whether invisible users in a voice channel can gain voice XP

## lvlset setlevel
 - Usage: `[p]lvlset setlevel <user> <level>`

Set a user to a specific level

## lvlset roles
 - Usage: `[p]lvlset roles`

Level role assignment

### lvlset roles del
 - Usage: `[p]lvlset roles del <level>`

Assign a role to a level

### lvlset roles initialize
 - Usage: `[p]lvlset roles initialize`

Initialize level roles<br/><br/>This command is for if you added level roles after users have achieved that level,<br/>it will apply all necessary roles to a user according to their level and prestige

### lvlset roles add
 - Usage: `[p]lvlset roles add <level> <role>`

Assign a role to a level

### lvlset roles autoremove
 - Usage: `[p]lvlset roles autoremove`

Automatic removal of previous level roles

## lvlset prestige
 - Usage: `[p]lvlset prestige`

Level Prestige Settings

### lvlset prestige autoremove
 - Usage: `[p]lvlset prestige autoremove`

Automatic removal of previous prestige level roles

### lvlset prestige add
 - Usage: `[p]lvlset prestige add <prestige_level> <role> <emoji>`

Add a prestige level role<br/>Add a role and emoji associated with a specific prestige level<br/><br/>When a user prestiges, they will get that role and the emoji will show on their profile

### lvlset prestige level
 - Usage: `[p]lvlset prestige level <level>`

Set the level required to prestige<br/>Set to 0 to disable prestige

### lvlset prestige del
 - Usage: `[p]lvlset prestige del <prestige_level>`

Delete a prestige level role

## lvlset levelchannel
 - Usage: `[p]lvlset levelchannel [levelup_channel=None]`

Set LevelUP message channel<br/>Set a channel for all level up messages to send to

## lvlset admin
 - Usage: `[p]lvlset admin`

Cog admin commands<br/><br/>Reset levels, backup and restore cog data

### lvlset admin guildreset
 - Usage: `[p]lvlset admin guildreset`

Reset cog data for this guild

### lvlset admin view
 - Usage: `[p]lvlset admin view`

View current loop times and cached data

### lvlset admin guildbackup
 - Usage: `[p]lvlset admin guildbackup`

Create a backup of the LevelUp config

### lvlset admin importleveler
 - Usage: `[p]lvlset admin importleveler <yes_or_no>`

Import data from Fixator's Leveler cog<br/><br/>This will overwrite existing LevelUp level data and stars<br/>It will also import XP range level roles, and ignored channels<br/>*Obviously you will need Leveler loaded while you run this command*

### lvlset admin cleanup
 - Usage: `[p]lvlset admin cleanup`

Delete users no longer in the server<br/><br/>Also cleans up any missing keys or discrepancies in the config

### lvlset admin globalbackup
 - Usage: `[p]lvlset admin globalbackup`

Create a backup of the LevelUp config

### lvlset admin guildrestore
 - Usage: `[p]lvlset admin guildrestore`

Restore a guild backup<br/><br/>Attach the .json file to the command message to import

### lvlset admin globalreset
 - Usage: `[p]lvlset admin globalreset`

Reset cog data for all guilds

### lvlset admin rendergifs
 - Usage: `[p]lvlset admin rendergifs`

Toggle whether to render profiles as gifs if the user's discord profile is animated

### lvlset admin statreset
 - Usage: `[p]lvlset admin statreset`

Reset everyone's exp and level

### lvlset admin importmee6
 - Usage: `[p]lvlset admin importmee6 <import_by> <replace> <i_agree>`

Import levels and exp from MEE6<br/><br/>**Make sure your guild's leaderboard is public!**<br/><br/>**Arguments**<br/>`export_by` - which stat to prioritize (`level` or `exp`)<br/>If exp is entered, it will import their experience and base their new level off of that.<br/>If level is entered, it will import their level and calculate their exp based off of that.<br/>`replace` - (True/False) if True, it will replace the user's exp or level, otherwise it will add it<br/>`i_agree` - (Yes/No) Just an extra option to make sure you want to execute this command

### lvlset admin globalrestore
 - Usage: `[p]lvlset admin globalrestore`

Restore a global backup<br/><br/>Attach the .json file to the command message to import

### lvlset admin profilecache
 - Usage: `[p]lvlset admin profilecache <seconds>`

Set how long to keep profile images in cache<br/>When a user runs the profile command their generated image will be stored in cache to be reused for X seconds<br/><br/>If profile embeds are enabled this setting will have no effect<br/>Anything less than 5 seconds will effectively disable the cache

## lvlset dm
 - Usage: `[p]lvlset dm`

Toggle DM notifications<br/>Toggle whether LevelUp messages are DM'd to the user

## lvlset ignored
 - Usage: `[p]lvlset ignored`

Base command for all ignore lists

### lvlset ignored role
 - Usage: `[p]lvlset ignored role <role>`

Add/Remove a role from the ignore list<br/>Roles in the ignore list don't gain XP<br/><br/>Use the command with a role already in the ignore list to remove it

### lvlset ignored channel
 - Usage: `[p]lvlset ignored channel <channel>`

Add/Remove a channel in the ignore list<br/>Channels in the ignore list don't gain XP<br/><br/>Use the command with a channel already in the ignore list to remove it

### lvlset ignored guild
 - Usage: `[p]lvlset ignored guild <guild_id>`

Add/Remove a guild in the ignore list<br/><br/>**THIS IS A GLOBAL SETTING ONLY BOT OWNERS CAN USE**<br/><br/>Use the command with a guild already in the ignore list to remove it

### lvlset ignored member
 - Usage: `[p]lvlset ignored member <member>`

Add/Remove a member from the ignore list<br/>Members in the ignore list don't gain XP<br/><br/>Use the command with a member already in the ignore list to remove them

## lvlset showbalance
 - Usage: `[p]lvlset showbalance`

Toggle whether to show user's economy credit balance in their profile

## lvlset mention
 - Usage: `[p]lvlset mention`

Toggle levelup mentions<br/>Toggle whether the user in mentioned in LevelUp messages

## lvlset messages
 - Usage: `[p]lvlset messages`
 - Aliases: `message and msg`

Message settings

### lvlset messages xp
 - Usage: `[p]lvlset messages xp [min_xp=3] [max_xp=6]`

Set message XP range<br/>Set the Min and Max amount of XP that a message can gain

### lvlset messages cooldown
 - Usage: `[p]lvlset messages cooldown <cooldown>`

Cooldown threshold for message XP<br/><br/>When a user sends a message they will have to wait X seconds before their message<br/>counts as XP gained

### lvlset messages length
 - Usage: `[p]lvlset messages length <minimum_length>`

Set minimum message length for XP<br/>Minimum length a message must be to count towards XP gained<br/><br/>Set to 0 to disable

### lvlset messages channelbonus
 - Usage: `[p]lvlset messages channelbonus <channel> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain channels<br/><br/>This bonus applies to message xp<br/><br/>Set both min and max to 0 to remove the role bonus

### lvlset messages rolebonus
 - Usage: `[p]lvlset messages rolebonus <role> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain roles<br/><br/>This bonus applies to message xp<br/><br/>Set both min and max to 0 to remove the role bonus

## lvlset algorithm
 - Usage: `[p]lvlset algorithm`

Customize the leveling algorithm for your guild

### lvlset algorithm base
 - Usage: `[p]lvlset algorithm base <base_multiplier>`

Base multiplier for the leveling algorithm<br/><br/>Affects leveling on a more linear scale(higher values makes leveling take longer)

### lvlset algorithm exp
 - Usage: `[p]lvlset algorithm exp <exponent_multiplier>`

Exponent multiplier for the leveling algorithm<br/><br/>Affects leveling on an exponential scale(higher values makes leveling take exponentially longer)

## lvlset embeds
 - Usage: `[p]lvlset embeds`

Toggle using embeds or generated pics

## lvlset levelnotify
 - Usage: `[p]lvlset levelnotify`

Toggle the level up message when a user levels up

## lvlset view
 - Usage: `[p]lvlset view`

View all LevelUP settings

## lvlset starmention
 - Usage: `[p]lvlset starmention`

Toggle star reaction mentions<br/>Toggle whether the bot mentions that a user reacted to a message with a star

## lvlset starcooldown
 - Usage: `[p]lvlset starcooldown <time_in_seconds>`

Set the star cooldown<br/><br/>Users can give another user a star every X seconds

## lvlset barlength
 - Usage: `[p]lvlset barlength <bar_length>`

Set the progress bar length for embed profiles

## lvlset starmentiondelete
 - Usage: `[p]lvlset starmentiondelete <deleted_after>`

Toggle whether the bot auto-deletes the star mentions<br/>Set to 0 to disable auto-delete

## lvlset addxp
 - Usage: `[p]lvlset addxp <user_or_role> <xp>`

Add XP to a user or role

## lvlset seelevels
 - Usage: `[p]lvlset seelevels`

Test the level algorithm<br/>View the first 20 levels using the current algorithm to test experience curve

# weeklyset
 - Usage: `[p]weeklyset`
 - Aliases: `wset`
 - Checks: guild_only

Access the weekly settings for levelUp

## weeklyset top
 - Usage: `[p]weeklyset top <top_count>`

Top weekly member count<br/>Set amount of members to include in the weekly top leaderboard

## weeklyset bonus
 - Usage: `[p]weeklyset bonus <exp_bonus>`

Weekly winners bonus experience points<br/>Set to 0 to disable exp bonus

## weeklyset role
 - Usage: `[p]weeklyset role <role>`

Weekly winner role reward<br/>Set the role awarded to the top member of the weekly leaderboard

## weeklyset view
 - Usage: `[p]weeklyset view`

View the current weekly settings

## weeklyset reset
 - Usage: `[p]weeklyset reset <yes_or_no>`

Reset the weekly leaderboard manually and announce winners

## weeklyset toggle
 - Usage: `[p]weeklyset toggle`

Toggle weekly stat tracking

## weeklyset roleall
 - Usage: `[p]weeklyset roleall`

Toggle whether to give the weekly winner role to all winners or only 1st place

## weeklyset autoreset
 - Usage: `[p]weeklyset autoreset`

Toggle weekly auto-reset

## weeklyset autoremove
 - Usage: `[p]weeklyset autoremove`

One role holder at a time<br/>Toggle whether the winner role is removed from the previous holder when a new winner is selected

## weeklyset hour
 - Usage: `[p]weeklyset hour <hour>`

What hour the weekly stats reset<br/>Set the hour (0 - 23 in UTC) for the weekly reset to take place

## weeklyset day
 - Usage: `[p]weeklyset day <day_of_the_week>`

What day of the week the weekly stats reset<br/>Set the day of the week (0 - 6 = Monday - Sunday) for weekly reset to take place

## weeklyset channel
 - Usage: `[p]weeklyset channel <channel>`

Weekly winner announcement channel<br/>set the channel for weekly winners to be announced in when auto-reset is enabled

