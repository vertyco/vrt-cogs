Your friendly neighborhood leveling system<br/><br/>Earn experience by chatting in text and voice channels, compare levels with your friends, customize your profile and view various leaderboards!

# weekly

- Usage: `[p]weekly [stat=exp] [displayname=True]`
- Aliases: `week`
- Checks: `server_only`

View Weekly Leaderboard

# lastweekly

- Usage: `[p]lastweekly`
- Checks: `server_only`

View Last Week's Leaderboard

# weeklyset

- Usage: `[p]weeklyset`
- Restricted to: `ADMIN`
- Aliases: `wset`
- Checks: `server_only`

Configure Weekly LevelUp Settings

## weeklyset autoremove

- Usage: `[p]weeklyset autoremove`

Remove role from previous winner when new one is announced

## weeklyset ping

- Usage: `[p]weeklyset ping`

Toggle whether to ping winners in announcement

## weeklyset day

- Usage: `[p]weeklyset day <day>`

Set day for weekly stats reset

## weeklyset hour

- Usage: `[p]weeklyset hour <hour>`

Set hour for weekly stats reset

## weeklyset reset

- Usage: `[p]weeklyset reset <yes_or_no>`

Reset the weekly leaderboard manually and announce winners

## weeklyset role

- Usage: `[p]weeklyset role <role>`

Set role to award top weekly winners

## weeklyset roleall

- Usage: `[p]weeklyset roleall`

Toggle whether all winners get the role

## weeklyset winners

- Usage: `[p]weeklyset winners <count>`

Set number of winners to display<br/><br/>Due to Discord limitations with max embed field count, the maximum number of winners is 25

## weeklyset view

- Usage: `[p]weeklyset view`

View the current weekly settings

## weeklyset bonus

- Usage: `[p]weeklyset bonus <bonus>`

Set bonus exp for top weekly winners

## weeklyset autoreset

- Usage: `[p]weeklyset autoreset`

Toggle auto reset of weekly stats

## weeklyset channel

- Usage: `[p]weeklyset channel <channel>`

Set channel to announce weekly winners

## weeklyset toggle

- Usage: `[p]weeklyset toggle`

Toggle weekly stat tracking

# leveltop (Hybrid Command)

- Usage: `[p]leveltop [stat=exp] [globalstats=False] [displayname=True]`
- Slash Usage: `/leveltop [stat=exp] [globalstats=False] [displayname=True]`
- Aliases: `lvltop, topstats, membertop, and topranks`
- Checks: `server_only`

View the LevelUp leaderboard

# roletop

- Usage: `[p]roletop`
- Checks: `server_only`

View the leaderboard for roles

# profile (Hybrid Command)

- Usage: `[p]profile [user]`
- Slash Usage: `/profile [user]`
- Aliases: `pf`
- Cooldown: `3 per 10.0 seconds`
- Checks: `server_only`

View User Profile

# prestige (Hybrid Command)

- Usage: `[p]prestige`
- Slash Usage: `/prestige`
- Checks: `server_only`

Prestige your rank!<br/>Once you have reached this servers prestige level requirement, you can<br/>reset your level and experience to gain a prestige level and any perks associated with it<br/><br/>If you are over level and xp when you prestige, your xp and levels will carry over

# setprofile (Hybrid Command)

- Usage: `[p]setprofile`
- Slash Usage: `/setprofile`
- Aliases: `myprofile, mypf, and pfset`
- Checks: `server_only`

Customize your profile

## setprofile view (Hybrid Command)

- Usage: `[p]setprofile view`
- Slash Usage: `/setprofile view`

View your profile settings

## setprofile backgrounds (Hybrid Command)

- Usage: `[p]setprofile backgrounds`
- Slash Usage: `/setprofile backgrounds`
- Cooldown: `1 per 5.0 seconds`

View the all available backgrounds

## setprofile style (Hybrid Command)

- Usage: `[p]setprofile style <style>`
- Slash Usage: `/setprofile style <style>`

Set your profile image style<br/><br/>- `default` is the default profile style, very customizable<br/>- `runescape` is a runescape style profile, less customizable but more nostalgic<br/>- (WIP) - more to come

## setprofile barcolor (Hybrid Command)

- Usage: `[p]setprofile barcolor <color>`
- Slash Usage: `/setprofile barcolor <color>`
- Aliases: `levelbar, lvlbar, and bar`

Set a color for your level bar<br/><br/>For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize the color each time your profile is generated

## setprofile addbackground (Hybrid Command)

- Usage: `[p]setprofile addbackground [preferred_filename=None]`
- Slash Usage: `/setprofile addbackground [preferred_filename=None]`
- Restricted to: `BOT_OWNER`

Add a custom background to the cog from discord<br/><br/>**Arguments**<br/>`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/><br/>**DISCLAIMER**<br/>- Do not replace any existing file names with custom images<br/>- If you add broken or corrupt images it can break the cog<br/>- Do not include the file extension in the preferred name, it will be added automatically

## setprofile shownick (Hybrid Command)

- Usage: `[p]setprofile shownick`
- Slash Usage: `/setprofile shownick`

Toggle whether your nickname or username is shown in your profile

## setprofile font (Hybrid Command)

- Usage: `[p]setprofile font <font_name>`
- Slash Usage: `/setprofile font <font_name>`

Set a font for your profile<br/><br/>To view available fonts, type `[p]myprofile fonts`<br/>To revert to the default font, use `default` for the `font_name` argument

## setprofile remfont (Hybrid Command)

- Usage: `[p]setprofile remfont <filename>`
- Slash Usage: `/setprofile remfont <filename>`
- Restricted to: `BOT_OWNER`

Remove a default font from the cog's fonts folder

## setprofile namecolor (Hybrid Command)

- Usage: `[p]setprofile namecolor <color>`
- Slash Usage: `/setprofile namecolor <color>`
- Aliases: `name`

Set a color for your username<br/><br/>For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize the color each time your profile is generated

## setprofile statcolor (Hybrid Command)

- Usage: `[p]setprofile statcolor <color>`
- Slash Usage: `/setprofile statcolor <color>`
- Aliases: `stat`

Set a color for your server stats<br/><br/>For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/><br/>Set to `default` to randomize the color each time your profile is generated

## setprofile blur (Hybrid Command)

- Usage: `[p]setprofile blur`
- Slash Usage: `/setprofile blur`

Toggle a slight blur effect on the background image where the text is displayed.

## setprofile background (Hybrid Command)

- Usage: `[p]setprofile background [url=None]`
- Slash Usage: `/setprofile background [url=None]`
- Aliases: `bg`

Set a background for your profile<br/><br/>This will override your profile banner as the background<br/><br/>**WARNING**<br/>The default profile style is wide (1050 by 450 pixels) with an aspect ratio of 21:9.<br/>Portrait images will be cropped.<br/><br/>Tip: Googling "dual monitor backgrounds" gives good results for the right images<br/><br/>Here are some good places to look.<br/>[dualmonitorbackgrounds](https://www.dualmonitorbackgrounds.com/)<br/>[setaswall](https://www.setaswall.com/dual-monitor-wallpapers/)<br/>[pexels](https://www.pexels.com/photo/panoramic-photography-of-trees-and-lake-358482/)<br/>[teahub](https://www.teahub.io/searchw/dual-monitor/)<br/><br/>**Additional Options**<br/> - Leave `url` blank or specify `default` to reset back to using your profile banner (or random if you don't have one)<br/> - `random` will randomly select from a pool of default backgrounds each time<br/> - `filename` run `[p]mypf backgrounds` to view default options you can use by including their filename

## setprofile bgpath (Hybrid Command)

- Usage: `[p]setprofile bgpath`
- Slash Usage: `/setprofile bgpath`
- Restricted to: `BOT_OWNER`

Get the folder paths for this cog's backgrounds

## setprofile addfont (Hybrid Command)

- Usage: `[p]setprofile addfont [preferred_filename=None]`
- Slash Usage: `/setprofile addfont [preferred_filename=None]`
- Restricted to: `BOT_OWNER`

Add a custom font to the cog from discord<br/><br/>**Arguments**<br/>`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/>**Note:** do not include the file extension in the preferred name, it will be added automatically

## setprofile fonts (Hybrid Command)

- Usage: `[p]setprofile fonts`
- Slash Usage: `/setprofile fonts`
- Cooldown: `1 per 5.0 seconds`

View the available fonts you can use

## setprofile fontpath (Hybrid Command)

- Usage: `[p]setprofile fontpath`
- Slash Usage: `/setprofile fontpath`
- Restricted to: `BOT_OWNER`

Get folder paths for this cog's fonts

## setprofile rembackground (Hybrid Command)

- Usage: `[p]setprofile rembackground <filename>`
- Slash Usage: `/setprofile rembackground <filename>`
- Restricted to: `BOT_OWNER`

Remove a default background from the cog's backgrounds folder

# stars (Hybrid Command)

- Usage: `[p]stars <user>`
- Slash Usage: `/stars <user>`
- Aliases: `givestar, addstar, and thanks`
- Checks: `server_only`

Reward a good noodle

# startop

- Usage: `[p]startop [globalstats=False] [displayname=True]`
- Aliases: `topstars, starleaderboard, and starlb`
- Checks: `server_only`

View the Star Leaderboard

# starset

- Usage: `[p]starset`
- Restricted to: `ADMIN`
- Checks: `server_only`

Configure LevelUp Star Settings

## starset view

- Usage: `[p]starset view`

View Star Settings

## starset mention

- Usage: `[p]starset mention`

Toggle star reaction mentions

## starset cooldown

- Usage: `[p]starset cooldown <cooldown>`

Set the star cooldown

## starset mentiondelete

- Usage: `[p]starset mentiondelete <delete_after>`

Toggle whether the bot auto-deletes the star mentions<br/><br/>Set to 0 to disable auto-delete

# levelowner

- Usage: `[p]levelowner`
- Restricted to: `BOT_OWNER`
- Aliases: `lvlowner`
- Checks: `server_only`

Owner Only LevelUp Settings

## levelowner externalapi

- Usage: `[p]levelowner externalapi <url>`

Set the external API URL for image generation<br/><br/>Set to an `none` to disable the external API<br/><br/>**Notes**<br/>- If the API fails, the cog will fall back to the default image generation method.

## levelowner rendergifs

- Usage: `[p]levelowner rendergifs`
- Aliases: `rendergif and gif`

Toggle rendering of GIFs for animated profiles

## levelowner ignore

- Usage: `[p]levelowner ignore <server_id>`

Add/Remove a server from the ignore list

## levelowner view

- Usage: `[p]levelowner view`

View Global LevelUp Settings

## levelowner forceembeds

- Usage: `[p]levelowner forceembeds`
- Aliases: `forceembed`

Toggle enforcing profile embeds<br/><br/>If enabled, profiles will only use embeds on all servers.<br/>This disables image generation globally.

## levelowner cache

- Usage: `[p]levelowner cache <seconds>`

Set the cache time for user profiles

## levelowner internalapi

- Usage: `[p]levelowner internalapi <port>`

Enable internal API for parallel image generation<br/><br/>Setting a port will spin up a detatched but cog-managed FastAPI server to handle image generation.<br/><br/>**USE AT YOUR OWN RISK!!!**<br/>Using the internal API will spin up multiple subprocesses to handle bulk image generation.<br/>If your bot crashes, the API subprocess will not be killed and will need to be manually terminated!<br/>It is HIGHLY reccommended to host the api separately!<br/><br/>Set to 0 to disable the internal API<br/><br/>**Notes**<br/>- This will spin up a 1 worker per core on the bot's cpu.<br/>- If the API fails, the cog will fall back to the default image generation method.

## levelowner autoclean

- Usage: `[p]levelowner autoclean`

Toggle auto-cleanup of server configs

# leveldata

- Usage: `[p]leveldata`
- Restricted to: `ADMIN`
- Aliases: `lvldata and ldata`
- Checks: `server_only`

Admin Only Data Commands

## leveldata backupcog

- Usage: `[p]leveldata backupcog`
- Restricted to: `BOT_OWNER`

Backup the cog's data

## leveldata backup

- Usage: `[p]leveldata backup`

Backup this server's data

## leveldata importmee6

- Usage: `[p]leveldata importmee6 <import_by> <replace> <include_settings> <all_users>`
- Restricted to: `GUILD_OWNER`

Import levels and exp from MEE6<br/><br/>**Arguments**<br/>➣ `import_by` - Import by level or exp<br/>• If `level`, it will import their level and calculate exp from that.<br/>• If `exp`, it will import their exp directly and calculate level from that.<br/>➣ `replace` - Replace existing data (True/False)<br/>➣ `include_settings` - Include MEE6 settings (True/False)<br/>➣ `all_users` - Import all users regardless of if they're in the server (True/False)

## leveldata cleanup

- Usage: `[p]leveldata cleanup`

Cleanup the database<br/><br/>Performs the following actions:<br/>- Delete data for users no longer in the server<br/>- Removes channels and roles that no longer exist

## leveldata importamari

- Usage: `[p]leveldata importamari <import_by> <replace> <api_key> <all_users>`
- Restricted to: `GUILD_OWNER`

Import levels and exp from AmariBot<br/>**Arguments**<br/>➣ `import_by` - Import by level or exp<br/>• If `level`, it will import their level and calculate exp from that.<br/>• If `exp`, it will import their exp directly and calculate level from that.<br/>➣ `replace` - Replace existing data (True/False)<br/>• If True, it will replace existing data.<br/>➣ `api_key` - Your [AmariBot API key](https://docs.google.com/forms/d/e/1FAIpQLScQDCsIqaTb1QR9BfzbeohlUJYA3Etwr-iSb0CRKbgjA-fq7Q/viewform?usp=send_form)<br/>➣ `all_users` - Import all users regardless of if they're in the server (True/False)

## leveldata restorecog

- Usage: `[p]leveldata restorecog`
- Restricted to: `BOT_OWNER`

Restore the cog's data

## leveldata importfixator

- Usage: `[p]leveldata importfixator`
- Restricted to: `BOT_OWNER`

Import data from Fixator's Leveler cog<br/><br/>This will overwrite existing LevelUp level data and stars<br/>It will also import XP range level roles, and ignored channels<br/><br/>_Obviously you will need MongoDB running while you run this command_

## leveldata resetcog

- Usage: `[p]leveldata resetcog`
- Restricted to: `BOT_OWNER`

Reset the ENTIRE cog's data

## leveldata reset

- Usage: `[p]leveldata reset`

Reset all user data in this server

## leveldata importmalarne

- Usage: `[p]leveldata importmalarne <import_by> <replace> <all_users>`
- Restricted to: `BOT_OWNER`

Import levels and exp from Malarne's Leveler cog<br/><br/>**Arguments**<br/>➣ `import_by` - Import by level or exp<br/>• If `level`, it will import their level and calculate exp from that.<br/>• If `exp`, it will import their exp directly and calculate level from that.<br/>➣ `replace` - Replace existing data (True/False)<br/>• If True, it will replace existing data.<br/>➣ `all_users` - Import all users regardless of if they're in the server (True/False)

## leveldata restore

- Usage: `[p]leveldata restore`

Restore this server's data

## leveldata resetglobal

- Usage: `[p]leveldata resetglobal`
- Restricted to: `BOT_OWNER`

Reset user data for all servers

## leveldata importpolaris

- Usage: `[p]leveldata importpolaris <replace> <include_settings> <all_users>`
- Restricted to: `GUILD_OWNER`

Import levels and exp from Polaris<br/><br/>**Make sure your server's leaderboard is public!**<br/><br/>**Arguments**<br/>➣ `replace` - Replace existing data (True/False)<br/>➣ `include_settings` - Include Polaris settings (True/False)<br/>➣ `all_users` - Import all users regardless of if they're in the server (True/False)<br/><br/>[Polaris](https://gdcolon.com/polaris/)

# levelset

- Usage: `[p]levelset`
- Restricted to: `ADMIN`
- Aliases: `lvlset and lset`
- Checks: `server_only`

Configure LevelUp Settings

## levelset toggle

- Usage: `[p]levelset toggle`

Toggle the LevelUp system

## levelset prestige

- Usage: `[p]levelset prestige`

Prestige settings

### levelset prestige level

- Usage: `[p]levelset prestige level <level>`

Set the level required to prestige

### levelset prestige add

- Usage: `[p]levelset prestige add <prestige> <role> <emoji>`
- Checks: `bot_has_server_permissions`

Add a role to a prestige level

### levelset prestige stack

- Usage: `[p]levelset prestige stack`

Toggle stacking roles on prestige<br/><br/>For example each time you prestige, you keep the previous prestige roles

### levelset prestige remove

- Usage: `[p]levelset prestige remove <prestige>`
- Aliases: `rem and del`

Remove a prestige level

## levelset setlevel

- Usage: `[p]levelset setlevel <user> <level>`

Set a user's level<br/><br/>**Arguments**<br/>• `user` - The user to set the level for<br/>• `level` - The level to set the user to

## levelset showbalance

- Usage: `[p]levelset showbalance`
- Aliases: `showbal`

Toggle whether to show user's economy credit balance in their profile

## levelset ignore

- Usage: `[p]levelset ignore`

Base command for all ignore lists

### levelset ignore role

- Usage: `[p]levelset ignore role <role>`

Add/Remove a role in the ignore list<br/>Members with roles in the ignore list don't gain XP<br/><br/>Use the command with a role already in the ignore list to remove it

### levelset ignore user

- Usage: `[p]levelset ignore user <user>`

Add/Remove a user in the ignore list<br/>Members in the ignore list don't gain XP<br/><br/>Use the command with a user already in the ignore list to remove them

### levelset ignore channel

- Usage: `[p]levelset ignore channel <channel>`

Add/Remove a channel in the ignore list<br/>Channels in the ignore list don't gain XP<br/><br/>Use the command with a channel already in the ignore list to remove it

## levelset starmentiondelete

- Usage: `[p]levelset starmentiondelete <deleted_after>`

Toggle whether the bot auto-deletes the star mentions<br/>Set to 0 to disable auto-delete

## levelset view

- Usage: `[p]levelset view`

View all LevelUP settings

## levelset roles

- Usage: `[p]levelset roles`

Level role assignment

### levelset roles remove

- Usage: `[p]levelset roles remove <level>`
- Aliases: `rem and del`

Unassign a role from a level

### levelset roles autoremove

- Usage: `[p]levelset roles autoremove`

Automatic removal of previous level roles

### levelset roles add

- Usage: `[p]levelset roles add <level> <role>`

Assign a role to a level

### levelset roles initialize

- Usage: `[p]levelset roles initialize`
- Aliases: `init`
- Cooldown: `1 per 240.0 seconds`

Initialize level roles<br/><br/>This command is for if you added level roles after users have achieved that level,<br/>it will apply all necessary roles to a user according to their level and prestige

## levelset algorithm

- Usage: `[p]levelset algorithm <part> <value>`
- Aliases: `algo`

Customize the leveling algorithm for your server<br/>• Default base is 100<br/>• Default exp is 2<br/><br/>**Equation**<br/>➣ Getting required XP for a level<br/>• `base * (level ^ exp) = XP`<br/>➣ Getting required level for an XP value<br/>• `level = (XP / base) ^ (1 / exp)`<br/><br/>**Arguments**<br/>➣ `part` - The part of the algorithm to change<br/>➣ `value` - The value to set it to

## levelset mention

- Usage: `[p]levelset mention`

Toggle whether to mention the user in the level up message

## levelset setprestige

- Usage: `[p]levelset setprestige <user> <prestige>`

Set a user to a specific prestige level<br/><br/>Prestige roles will need to be manually added/removed when using this command

## levelset dm

- Usage: `[p]levelset dm`

Toggle DM notifications<br/><br/>Determines whether LevelUp messages are DM'd to the user

## levelset embeds

- Usage: `[p]levelset embeds`

Toggle using embeds or generated pics

## levelset resetemojis

- Usage: `[p]levelset resetemojis`

Reset the emojis to default

## levelset rolegroup

- Usage: `[p]levelset rolegroup <role>`

Add or remove a role to the role group<br/><br/>These roles gain their own experience points as a group<br/>When a member gains xp while having this role, the xp they earn is also added to the role group

## levelset starmention

- Usage: `[p]levelset starmention`

Toggle star reaction mentions<br/>Toggle whether the bot mentions that a user reacted to a message with a star

## levelset voice

- Usage: `[p]levelset voice`

Voice settings

### levelset voice streambonus

- Usage: `[p]levelset voice streambonus <min_xp> <max_xp>`

Add a range of bonus XP to users who are Discord streaming<br/><br/>This bonus applies to voice time xp<br/><br/>Set both min and max to 0 to remove the bonus

### levelset voice muted

- Usage: `[p]levelset voice muted`

Ignore muted voice users<br/>Toggle whether self-muted users in a voice channel can gain voice XP

### levelset voice invisible

- Usage: `[p]levelset voice invisible`

Ignore invisible voice users<br/>Toggle whether invisible users in a voice channel can gain voice XP

### levelset voice deafened

- Usage: `[p]levelset voice deafened`

Ignore deafened voice users<br/>Toggle whether deafened users in a voice channel can gain voice XP

### levelset voice xp

- Usage: `[p]levelset voice xp <voice_xp>`

Set voice XP gain<br/>Sets the amount of XP gained per minute in a voice channel (default is 2)

### levelset voice solo

- Usage: `[p]levelset voice solo`

Ignore solo voice users<br/>Toggle whether solo users in a voice channel can gain voice XP

### levelset voice channelbonus

- Usage: `[p]levelset voice channelbonus <channel> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain channels<br/><br/>This bonus applies to voice time xp<br/><br/>Set both min and max to 0 to remove the role bonus

### levelset voice rolebonus

- Usage: `[p]levelset voice rolebonus <role> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain roles<br/><br/>This bonus applies to voice time xp<br/><br/>Set both min and max to 0 to remove the role bonus

## levelset levelchannel

- Usage: `[p]levelset levelchannel [channel=None]`

Set LevelUP message channel<br/><br/>Set a channel for all level up messages to send to

## levelset commandxp

- Usage: `[p]levelset commandxp`

Toggle whether users can gain Exp from running commands

## levelset levelnotify

- Usage: `[p]levelset levelnotify`

Toggle the level up message when a user levels up

## levelset seelevels

- Usage: `[p]levelset seelevels`

Test the level algorithm<br/>View the first 20 levels using the current algorithm to test experience curve

## levelset removexp

- Usage: `[p]levelset removexp <user_or_role> <xp>`

Remove XP from a user or role

## levelset emojis

- Usage: `[p]levelset emojis <level> <prestige> <star> <chat> <voicetime> <experience> <balance>`

Set the emojis used to represent each stat type

## levelset alerts

- Usage: `[p]levelset alerts`
- Aliases: `lvlalerts and levelalerts`

Level up alert messages<br/><br/>**Arguments**<br/>The following placeholders can be used:<br/>• `{username}`: The user's name<br/>• `{mention}`: Mentions the user<br/>• `{displayname}`: The user's display name<br/>• `{level}`: The level the user just reached<br/>• `{server}`: The server the user is in<br/><br/>**If using dmrole or msgrole**<br/>• `{role}`: The role the user just recieved

### levelset alerts view

- Usage: `[p]levelset alerts view`

View the current level up alert messages

### levelset alerts dm

- Usage: `[p]levelset alerts dm [message]`

Set the DM a user gets when they level up (Without recieving a role).<br/><br/>**Arguments**<br/>The following placeholders can be used:<br/>• `{username}`: The user's name<br/>• `{mention}`: Mentions the user<br/>• `{displayname}`: The user's display name<br/>• `{level}`: The level the user just reached<br/>• `{server}`: The server the user is in

### levelset alerts dmrole

- Usage: `[p]levelset alerts dmrole [message]`

Set the DM a user gets when they level up and recieve a role.<br/><br/>**Arguments**<br/>The following placeholders can be used:<br/>• `{username}`: The user's name<br/>• `{mention}`: Mentions the user<br/>• `{displayname}`: The user's display name<br/>• `{level}`: The level the user just reached<br/>• `{server}`: The server the user is in<br/>• `{role}`: The role the user just recieved

### levelset alerts msgrole

- Usage: `[p]levelset alerts msgrole [message]`

Set the message sent when a user levels up and recieves a role.<br/><br/>**Arguments**<br/>The following placeholders can be used:<br/>• `{username}`: The user's name<br/>• `{mention}`: Mentions the user<br/>• `{displayname}`: The user's display name<br/>• `{level}`: The level the user just reached<br/>• `{server}`: The server the user is in<br/>• `{role}`: The role the user just recieved

### levelset alerts msg

- Usage: `[p]levelset alerts msg [message]`

Set the message sent when a user levels up.<br/><br/>**Arguments**<br/>The following placeholders can be used:<br/>• `{username}`: The user's name<br/>• `{mention}`: Mentions the user<br/>• `{displayname}`: The user's display name<br/>• `{level}`: The level the user just reached<br/>• `{server}`: The server the user is in

## levelset messages

- Usage: `[p]levelset messages`
- Aliases: `message and msg`

Message settings

### levelset messages rolebonus

- Usage: `[p]levelset messages rolebonus <role> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain roles<br/><br/>This bonus applies to message xp<br/><br/>Set both min and max to 0 to remove the role bonus

### levelset messages xp

- Usage: `[p]levelset messages xp <min_xp> <max_xp>`

Set message XP range<br/><br/>Set the Min and Max amount of XP that a message can gain<br/>Default is 3 min and 6 max

### levelset messages channelbonus

- Usage: `[p]levelset messages channelbonus <channel> <min_xp> <max_xp>`

Add a range of bonus XP to apply to certain channels<br/><br/>This bonus applies to message xp<br/><br/>Set both min and max to 0 to remove the role bonus

### levelset messages cooldown

- Usage: `[p]levelset messages cooldown <cooldown>`

Cooldown threshold for message XP<br/><br/>When a user sends a message they will have to wait X seconds before their message<br/>counts as XP gained

### levelset messages length

- Usage: `[p]levelset messages length <length>`

Set minimum message length for XP<br/>Minimum length a message must be to count towards XP gained<br/><br/>Set to 0 to disable

## levelset addxp

- Usage: `[p]levelset addxp <user_or_role> <xp>`

Add XP to a user or role

## levelset starcooldown

- Usage: `[p]levelset starcooldown <seconds>`

Set the star cooldown<br/><br/>Users can give another user a star every X seconds
