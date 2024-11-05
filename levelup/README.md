Your friendly neighborhood leveling system<br/><br/>Earn experience by chatting in text and voice channels, compare levels with your friends, customize your profile and view various leaderboards!

# [p]weekly
View Weekly Leaderboard<br/>
 - Usage: `[p]weekly [stat=exp] [displayname=True]`
 - Aliases: `week`
 - Checks: `server_only`
# [p]lastweekly
View Last Week's Leaderboard<br/>
 - Usage: `[p]lastweekly`
 - Checks: `server_only`
# [p]weeklyset
Configure Weekly LevelUp Settings<br/>
 - Usage: `[p]weeklyset`
 - Restricted to: `ADMIN`
 - Aliases: `wset`
 - Checks: `server_only`
## [p]weeklyset autoreset
Toggle auto reset of weekly stats<br/>
 - Usage: `[p]weeklyset autoreset`
## [p]weeklyset winners
Set number of winners to display<br/>

Due to Discord limitations with max embed field count, the maximum number of winners is 25<br/>
 - Usage: `[p]weeklyset winners <count>`
## [p]weeklyset toggle
Toggle weekly stat tracking<br/>
 - Usage: `[p]weeklyset toggle`
## [p]weeklyset channel
Set channel to announce weekly winners<br/>
 - Usage: `[p]weeklyset channel <channel>`
## [p]weeklyset bonus
Set bonus exp for top weekly winners<br/>
 - Usage: `[p]weeklyset bonus <bonus>`
## [p]weeklyset role
Set role to award top weekly winners<br/>
 - Usage: `[p]weeklyset role <role>`
## [p]weeklyset roleall
Toggle whether all winners get the role<br/>
 - Usage: `[p]weeklyset roleall`
## [p]weeklyset view
View the current weekly settings<br/>
 - Usage: `[p]weeklyset view`
## [p]weeklyset hour
Set hour for weekly stats reset<br/>
 - Usage: `[p]weeklyset hour <hour>`
## [p]weeklyset reset
Reset the weekly leaderboard manually and announce winners<br/>
 - Usage: `[p]weeklyset reset <yes_or_no>`
## [p]weeklyset day
Set day for weekly stats reset<br/>
0 = Monday<br/>
1 = Tuesday<br/>
2 = Wednesday<br/>
3 = Thursday<br/>
4 = Friday<br/>
5 = Saturday<br/>
6 = Sunday<br/>
 - Usage: `[p]weeklyset day <day>`
## [p]weeklyset ping
Toggle whether to ping winners in announcement<br/>
 - Usage: `[p]weeklyset ping`
## [p]weeklyset autoremove
Remove role from previous winner when new one is announced<br/>
 - Usage: `[p]weeklyset autoremove`
# [p]leveltop (Hybrid Command)
View the LevelUp leaderboard<br/>
 - Usage: `[p]leveltop [stat=exp] [globalstats=False] [displayname=True]`
 - Slash Usage: `/leveltop [stat=exp] [globalstats=False] [displayname=True]`
 - Aliases: `lvltop, topstats, membertop, and topranks`
 - Checks: `server_only`
# [p]roletop
View the leaderboard for roles<br/>
 - Usage: `[p]roletop`
 - Checks: `server_only`
# [p]profile (Hybrid Command)
View User Profile<br/>
 - Usage: `[p]profile [user]`
 - Slash Usage: `/profile [user]`
 - Aliases: `pf`
 - Cooldown: `3 per 10.0 seconds`
 - Checks: `server_only`
# [p]prestige (Hybrid Command)
Prestige your rank!<br/>
Once you have reached this servers prestige level requirement, you can<br/>
reset your level and experience to gain a prestige level and any perks associated with it<br/>

If you are over level and xp when you prestige, your xp and levels will carry over<br/>
 - Usage: `[p]prestige`
 - Slash Usage: `/prestige`
 - Checks: `server_only`
# [p]setprofile (Hybrid Command)
Customize your profile<br/>
 - Usage: `[p]setprofile`
 - Slash Usage: `/setprofile`
 - Aliases: `myprofile, mypf, and pfset`
 - Checks: `server_only`
## [p]setprofile shownick (Hybrid Command)
Toggle whether your nickname or username is shown in your profile<br/>
 - Usage: `[p]setprofile shownick`
 - Slash Usage: `/setprofile shownick`
## [p]setprofile backgrounds (Hybrid Command)
View the all available backgrounds<br/>
 - Usage: `[p]setprofile backgrounds`
 - Slash Usage: `/setprofile backgrounds`
 - Cooldown: `1 per 5.0 seconds`
## [p]setprofile namecolor (Hybrid Command)
Set a color for your username<br/>

For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/>

Set to `default` to randomize the color each time your profile is generated<br/>
 - Usage: `[p]setprofile namecolor <color>`
 - Slash Usage: `/setprofile namecolor <color>`
 - Aliases: `name`
## [p]setprofile font (Hybrid Command)
Set a font for your profile<br/>

To view available fonts, type `[p]myprofile fonts`<br/>
To revert to the default font, use `default` for the `font_name` argument<br/>
 - Usage: `[p]setprofile font <font_name>`
 - Slash Usage: `/setprofile font <font_name>`
## [p]setprofile blur (Hybrid Command)
Toggle a slight blur effect on the background image where the text is displayed.<br/>
 - Usage: `[p]setprofile blur`
 - Slash Usage: `/setprofile blur`
## [p]setprofile remfont (Hybrid Command)
Remove a default font from the cog's fonts folder<br/>
 - Usage: `[p]setprofile remfont <filename>`
 - Slash Usage: `/setprofile remfont <filename>`
 - Restricted to: `BOT_OWNER`
## [p]setprofile style (Hybrid Command)
Set your profile image style<br/>

- `default` is the default profile style, very customizable<br/>
- `runescape` is a runescape style profile, less customizable but more nostalgic<br/>
- (WIP) - more to come<br/>
 - Usage: `[p]setprofile style <style>`
 - Slash Usage: `/setprofile style <style>`
## [p]setprofile background (Hybrid Command)
Set a background for your profile<br/>

This will override your profile banner as the background<br/>

**WARNING**<br/>
The default profile style is wide (1050 by 450 pixels) with an aspect ratio of 21:9.<br/>
Portrait images will be cropped.<br/>

Tip: Googling "dual monitor backgrounds" gives good results for the right images<br/>

Here are some good places to look.<br/>
[dualmonitorbackgrounds](https://www.dualmonitorbackgrounds.com/)<br/>
[setaswall](https://www.setaswall.com/dual-monitor-wallpapers/)<br/>
[pexels](https://www.pexels.com/photo/panoramic-photography-of-trees-and-lake-358482/)<br/>
[teahub](https://www.teahub.io/searchw/dual-monitor/)<br/>

**Additional Options**<br/>
 - Leave `url` blank or specify `default` to reset back to using your profile banner (or random if you don't have one)<br/>
 - `random` will randomly select from a pool of default backgrounds each time<br/>
 - `filename` run `[p]mypf backgrounds` to view default options you can use by including their filename<br/>
 - Usage: `[p]setprofile background [url=None]`
 - Slash Usage: `/setprofile background [url=None]`
 - Aliases: `bg`
## [p]setprofile rembackground (Hybrid Command)
Remove a default background from the cog's backgrounds folder<br/>
 - Usage: `[p]setprofile rembackground <filename>`
 - Slash Usage: `/setprofile rembackground <filename>`
 - Restricted to: `BOT_OWNER`
## [p]setprofile addfont (Hybrid Command)
Add a custom font to the cog from discord<br/>

**Arguments**<br/>
`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/>
**Note:** do not include the file extension in the preferred name, it will be added automatically<br/>
 - Usage: `[p]setprofile addfont [preferred_filename=None]`
 - Slash Usage: `/setprofile addfont [preferred_filename=None]`
 - Restricted to: `BOT_OWNER`
## [p]setprofile bgpath (Hybrid Command)
Get the folder paths for this cog's backgrounds<br/>
 - Usage: `[p]setprofile bgpath`
 - Slash Usage: `/setprofile bgpath`
 - Restricted to: `BOT_OWNER`
## [p]setprofile view (Hybrid Command)
View your profile settings<br/>
 - Usage: `[p]setprofile view`
 - Slash Usage: `/setprofile view`
## [p]setprofile addbackground (Hybrid Command)
Add a custom background to the cog from discord<br/>

**Arguments**<br/>
`preferred_filename` - If a name is given, it will be saved as this name instead of the filename<br/>

**DISCLAIMER**<br/>
- Do not replace any existing file names with custom images<br/>
- If you add broken or corrupt images it can break the cog<br/>
- Do not include the file extension in the preferred name, it will be added automatically<br/>
 - Usage: `[p]setprofile addbackground [preferred_filename=None]`
 - Slash Usage: `/setprofile addbackground [preferred_filename=None]`
 - Restricted to: `BOT_OWNER`
## [p]setprofile fonts (Hybrid Command)
View the available fonts you can use<br/>
 - Usage: `[p]setprofile fonts`
 - Slash Usage: `/setprofile fonts`
 - Cooldown: `1 per 5.0 seconds`
## [p]setprofile fontpath (Hybrid Command)
Get folder paths for this cog's fonts<br/>
 - Usage: `[p]setprofile fontpath`
 - Slash Usage: `/setprofile fontpath`
 - Restricted to: `BOT_OWNER`
## [p]setprofile statcolor (Hybrid Command)
Set a color for your server stats<br/>

For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/>

Set to `default` to randomize the color each time your profile is generated<br/>
 - Usage: `[p]setprofile statcolor <color>`
 - Slash Usage: `/setprofile statcolor <color>`
 - Aliases: `stat`
## [p]setprofile barcolor (Hybrid Command)
Set a color for your level bar<br/>

For a specific color, try **[Google's hex color picker](https://htmlcolorcodes.com/)**<br/>

Set to `default` to randomize the color each time your profile is generated<br/>
 - Usage: `[p]setprofile barcolor <color>`
 - Slash Usage: `/setprofile barcolor <color>`
 - Aliases: `levelbar, lvlbar, and bar`
# [p]stars (Hybrid Command)
Reward a good noodle<br/>
 - Usage: `[p]stars [user]`
 - Slash Usage: `/stars [user]`
 - Aliases: `givestar, addstar, and thanks`
 - Checks: `server_only`
# [p]startop
View the Star Leaderboard<br/>
 - Usage: `[p]startop [globalstats=False] [displayname=True]`
 - Aliases: `topstars, starleaderboard, and starlb`
 - Checks: `server_only`
# [p]starset
Configure LevelUp Star Settings<br/>
 - Usage: `[p]starset`
 - Restricted to: `ADMIN`
 - Checks: `server_only`
## [p]starset view
View Star Settings<br/>
 - Usage: `[p]starset view`
## [p]starset mentiondelete
Toggle whether the bot auto-deletes the star mentions<br/>

Set to 0 to disable auto-delete<br/>
 - Usage: `[p]starset mentiondelete <delete_after>`
## [p]starset cooldown
Set the star cooldown<br/>
 - Usage: `[p]starset cooldown <cooldown>`
## [p]starset mention
Toggle star reaction mentions<br/>
 - Usage: `[p]starset mention`
# [p]levelowner
Owner Only LevelUp Settings<br/>
 - Usage: `[p]levelowner`
 - Restricted to: `BOT_OWNER`
 - Aliases: `lvlowner`
 - Checks: `server_only`
## [p]levelowner ignorebots
Toggle ignoring bots for XP and profiles<br/>

**USE AT YOUR OWN RISK**<br/>
Allowing your bot to listen to other bots is a BAD IDEA and should NEVER be enabled on public bots.<br/>
 - Usage: `[p]levelowner ignorebots`
## [p]levelowner internalapi
Enable internal API for parallel image generation<br/>

Setting a port will spin up a detatched but cog-managed FastAPI server to handle image generation.<br/>
The process ID will be attached to the bot object and persist through reloads.<br/>

**USE AT YOUR OWN RISK!!!**<br/>
Using the internal API will spin up multiple subprocesses to handle bulk image generation.<br/>
If your bot crashes, the API subprocess will not be killed and will need to be manually terminated!<br/>
It is HIGHLY reccommended to host the api separately!<br/>

Set to 0 to disable the internal API<br/>

**Notes**<br/>
- This will spin up a 1 worker per core on the bot's cpu.<br/>
- If the API fails, the cog will fall back to the default image generation method.<br/>
 - Usage: `[p]levelowner internalapi <port>`
## [p]levelowner externalapi
Set the external API URL for image generation<br/>

Set to an `none` to disable the external API<br/>

**Notes**<br/>
- If the API fails, the cog will fall back to the default image generation method.<br/>
 - Usage: `[p]levelowner externalapi <url>`
## [p]levelowner rendergifs
Toggle rendering of GIFs for animated profiles<br/>
 - Usage: `[p]levelowner rendergifs`
 - Aliases: `rendergif and gif`
## [p]levelowner cache
Set the cache time for user profiles<br/>
 - Usage: `[p]levelowner cache <seconds>`
## [p]levelowner maxbackups
Set the maximum number of backups to keep<br/>
 - Usage: `[p]levelowner maxbackups <backups>`
## [p]levelowner ignore
Add/Remove a server from the ignore list<br/>
 - Usage: `[p]levelowner ignore <server_id>`
## [p]levelowner backupinterval
Set the interval for backups<br/>
 - Usage: `[p]levelowner backupinterval <interval>`
## [p]levelowner view
View Global LevelUp Settings<br/>
 - Usage: `[p]levelowner view`
## [p]levelowner forceembeds
Toggle enforcing profile embeds<br/>

If enabled, profiles will only use embeds on all servers.<br/>
This disables image generation globally.<br/>
 - Usage: `[p]levelowner forceembeds`
 - Aliases: `forceembed`
## [p]levelowner autoclean
Toggle purging of config data for servers the bot is no longer in<br/>
 - Usage: `[p]levelowner autoclean`
# [p]leveldata
Admin Only Data Commands<br/>
 - Usage: `[p]leveldata`
 - Restricted to: `ADMIN`
 - Aliases: `lvldata and ldata`
 - Checks: `server_only`
## [p]leveldata reset
Reset all user data in this server<br/>
 - Usage: `[p]leveldata reset`
## [p]leveldata resetglobal
Reset user data for all servers<br/>
 - Usage: `[p]leveldata resetglobal`
 - Restricted to: `BOT_OWNER`
## [p]leveldata restorecog
Restore the cog's data<br/>
 - Usage: `[p]leveldata restorecog`
 - Restricted to: `BOT_OWNER`
## [p]leveldata importamari
Import levels and exp from AmariBot<br/>
**Arguments**<br/>
➣ `import_by` - Import by level or exp<br/>
• If `level`, it will import their level and calculate exp from that.<br/>
• If `exp`, it will import their exp directly and calculate level from that.<br/>
➣ `replace` - Replace existing data (True/False)<br/>
• If True, it will replace existing data.<br/>
➣ `api_key` - Your [AmariBot API key](https://docs.google.com/forms/d/e/1FAIpQLScQDCsIqaTb1QR9BfzbeohlUJYA3Etwr-iSb0CRKbgjA-fq7Q/viewform?usp=send_form)<br/>
➣ `all_users` - Import all users regardless of if they're in the server (True/False)<br/>
 - Usage: `[p]leveldata importamari <import_by> <replace> <api_key> <all_users>`
 - Restricted to: `GUILD_OWNER`
## [p]leveldata importmalarne
Import levels and exp from Malarne's Leveler cog<br/>

**Arguments**<br/>
➣ `import_by` - Import by level or exp<br/>
• If `level`, it will import their level and calculate exp from that.<br/>
• If `exp`, it will import their exp directly and calculate level from that.<br/>
➣ `replace` - Replace existing data (True/False)<br/>
• If True, it will replace existing data.<br/>
➣ `all_users` - Import all users regardless of if they're in the server (True/False)<br/>
 - Usage: `[p]leveldata importmalarne <import_by> <replace> <all_users>`
 - Restricted to: `BOT_OWNER`
## [p]leveldata importmee6
Import levels and exp from MEE6<br/>

**Arguments**<br/>
➣ `import_by` - Import by level or exp<br/>
• If `level`, it will import their level and calculate exp from that.<br/>
• If `exp`, it will import their exp directly and calculate level from that.<br/>
➣ `replace` - Replace existing data (True/False)<br/>
➣ `include_settings` - Include MEE6 settings (True/False)<br/>
➣ `all_users` - Import all users regardless of if they're in the server (True/False)<br/>
 - Usage: `[p]leveldata importmee6 <import_by> <replace> <include_settings> <all_users>`
 - Restricted to: `GUILD_OWNER`
## [p]leveldata backup
Backup this server's data<br/>
 - Usage: `[p]leveldata backup`
## [p]leveldata importpolaris
Import levels and exp from Polaris<br/>

**Make sure your server's leaderboard is public!**<br/>

**Arguments**<br/>
➣ `replace` - Replace existing data (True/False)<br/>
➣ `include_settings` - Include Polaris settings (True/False)<br/>
➣ `all_users` - Import all users regardless of if they're in the server (True/False)<br/>

[Polaris](https://gdcolon.com/polaris/)<br/>
 - Usage: `[p]leveldata importpolaris <replace> <include_settings> <all_users>`
 - Restricted to: `GUILD_OWNER`
## [p]leveldata resetcog
Reset the ENTIRE cog's data<br/>
 - Usage: `[p]leveldata resetcog`
 - Restricted to: `BOT_OWNER`
## [p]leveldata restore
Restore this server's data<br/>
 - Usage: `[p]leveldata restore`
## [p]leveldata backupcog
Backup the cog's data<br/>
 - Usage: `[p]leveldata backupcog`
 - Restricted to: `BOT_OWNER`
## [p]leveldata cleanup
Cleanup the database<br/>

Performs the following actions:<br/>
- Delete data for users no longer in the server<br/>
- Removes channels and roles that no longer exist<br/>
 - Usage: `[p]leveldata cleanup`
## [p]leveldata importfixator
Import data from Fixator's Leveler cog<br/>

This will overwrite existing LevelUp level data and stars<br/>
It will also import XP range level roles, and ignored channels<br/>

*Obviously you will need MongoDB running while you run this command*<br/>
 - Usage: `[p]leveldata importfixator`
 - Restricted to: `BOT_OWNER`
# [p]levelset
Configure LevelUp Settings<br/>
 - Usage: `[p]levelset`
 - Restricted to: `ADMIN`
 - Aliases: `lvlset and lset`
 - Checks: `server_only`
## [p]levelset showbalance
Toggle whether to show user's economy credit balance in their profile<br/>
 - Usage: `[p]levelset showbalance`
 - Aliases: `showbal`
## [p]levelset voice
Voice settings<br/>
 - Usage: `[p]levelset voice`
### [p]levelset voice invisible
Ignore invisible voice users<br/>
Toggle whether invisible users in a voice channel can gain voice XP<br/>
 - Usage: `[p]levelset voice invisible`
### [p]levelset voice deafened
Ignore deafened voice users<br/>
Toggle whether deafened users in a voice channel can gain voice XP<br/>
 - Usage: `[p]levelset voice deafened`
### [p]levelset voice xp
Set voice XP gain<br/>
Sets the amount of XP gained per minute in a voice channel (default is 2)<br/>
 - Usage: `[p]levelset voice xp <voice_xp>`
### [p]levelset voice rolebonus
Add a range of bonus XP to apply to certain roles<br/>

This bonus applies to voice time xp<br/>

Set both min and max to 0 to remove the role bonus<br/>
 - Usage: `[p]levelset voice rolebonus <role> <min_xp> <max_xp>`
### [p]levelset voice solo
Ignore solo voice users<br/>
Toggle whether solo users in a voice channel can gain voice XP<br/>
 - Usage: `[p]levelset voice solo`
### [p]levelset voice streambonus
Add a range of bonus XP to users who are Discord streaming<br/>

This bonus applies to voice time xp<br/>

Set both min and max to 0 to remove the bonus<br/>
 - Usage: `[p]levelset voice streambonus <min_xp> <max_xp>`
### [p]levelset voice muted
Ignore muted voice users<br/>
Toggle whether self-muted users in a voice channel can gain voice XP<br/>
 - Usage: `[p]levelset voice muted`
### [p]levelset voice channelbonus
Add a range of bonus XP to apply to certain channels<br/>

This bonus applies to voice time xp<br/>

Set both min and max to 0 to remove the role bonus<br/>
 - Usage: `[p]levelset voice channelbonus <channel> <min_xp> <max_xp>`
## [p]levelset starcooldown
Set the star cooldown<br/>

Users can give another user a star every X seconds<br/>
 - Usage: `[p]levelset starcooldown <seconds>`
## [p]levelset prestige
Prestige settings<br/>
 - Usage: `[p]levelset prestige`
### [p]levelset prestige level
Set the level required to prestige<br/>
 - Usage: `[p]levelset prestige level <level>`
### [p]levelset prestige stack
Toggle stacking roles on prestige<br/>

For example each time you prestige, you keep the previous prestige roles<br/>
 - Usage: `[p]levelset prestige stack`
### [p]levelset prestige keeproles
Keep level roles after prestiging<br/>
 - Usage: `[p]levelset prestige keeproles`
### [p]levelset prestige add
Add a role to a prestige level<br/>
 - Usage: `[p]levelset prestige add <prestige> <role> <emoji>`
 - Checks: `bot_has_server_permissions`
### [p]levelset prestige remove
Remove a prestige level<br/>
 - Usage: `[p]levelset prestige remove <prestige>`
 - Aliases: `rem and del`
## [p]levelset roles
Level role assignment<br/>
 - Usage: `[p]levelset roles`
### [p]levelset roles add
Assign a role to a level<br/>
 - Usage: `[p]levelset roles add <level> <role>`
### [p]levelset roles autoremove
Automatic removal of previous level roles<br/>
 - Usage: `[p]levelset roles autoremove`
### [p]levelset roles initialize
Initialize level roles<br/>

This command is for if you added level roles after users have achieved that level,<br/>
it will apply all necessary roles to a user according to their level and prestige<br/>
 - Usage: `[p]levelset roles initialize`
 - Aliases: `init`
 - Cooldown: `1 per 240.0 seconds`
### [p]levelset roles remove
Unassign a role from a level<br/>
 - Usage: `[p]levelset roles remove <level>`
 - Aliases: `rem and del`
## [p]levelset levelupmessages
Level up alert messages<br/>

**Arguments**<br/>
The following placeholders can be used:<br/>
• `{username}`: The user's name<br/>
• `{mention}`: Mentions the user<br/>
• `{displayname}`: The user's display name<br/>
• `{level}`: The level the user just reached<br/>
• `{server}`: The server the user is in<br/>

**If using dmrole or msgrole**<br/>
• `{role}`: The role the user just recieved<br/>
 - Usage: `[p]levelset levelupmessages`
 - Aliases: `lvlalerts, levelalerts, lvlmessages, and lvlmsg`
### [p]levelset levelupmessages msgrole
Set the message sent when a user levels up and recieves a role.<br/>

**Arguments**<br/>
The following placeholders can be used:<br/>
• `{username}`: The user's name<br/>
• `{mention}`: Mentions the user<br/>
• `{displayname}`: The user's display name<br/>
• `{level}`: The level the user just reached<br/>
• `{server}`: The server the user is in<br/>
• `{role}`: The role the user just recieved<br/>
 - Usage: `[p]levelset levelupmessages msgrole [message]`
### [p]levelset levelupmessages msg
Set the message sent when a user levels up.<br/>

**Arguments**<br/>
The following placeholders can be used:<br/>
• `{username}`: The user's name<br/>
• `{mention}`: Mentions the user<br/>
• `{displayname}`: The user's display name<br/>
• `{level}`: The level the user just reached<br/>
• `{server}`: The server the user is in<br/>
 - Usage: `[p]levelset levelupmessages msg [message]`
### [p]levelset levelupmessages dmrole
Set the DM a user gets when they level up and recieve a role.<br/>

**Arguments**<br/>
The following placeholders can be used:<br/>
• `{username}`: The user's name<br/>
• `{mention}`: Mentions the user<br/>
• `{displayname}`: The user's display name<br/>
• `{level}`: The level the user just reached<br/>
• `{server}`: The server the user is in<br/>
• `{role}`: The role the user just recieved<br/>
 - Usage: `[p]levelset levelupmessages dmrole [message]`
### [p]levelset levelupmessages dm
Set the DM a user gets when they level up (Without recieving a role).<br/>

**Arguments**<br/>
The following placeholders can be used:<br/>
• `{username}`: The user's name<br/>
• `{mention}`: Mentions the user<br/>
• `{displayname}`: The user's display name<br/>
• `{level}`: The level the user just reached<br/>
• `{server}`: The server the user is in<br/>
 - Usage: `[p]levelset levelupmessages dm [message]`
### [p]levelset levelupmessages view
View the current level up alert messages<br/>
 - Usage: `[p]levelset levelupmessages view`
## [p]levelset view
View all LevelUP settings<br/>
 - Usage: `[p]levelset view`
## [p]levelset addxp
Add XP to a user or role<br/>
 - Usage: `[p]levelset addxp <user_or_role> <xp>`
## [p]levelset setlevel
Set a user's level<br/>

**Arguments**<br/>
• `user` - The user to set the level for<br/>
• `level` - The level to set the user to<br/>
 - Usage: `[p]levelset setlevel <user> <level>`
## [p]levelset forcestyle
Force a profile style for all users<br/>

Specify `none` to disable the forced style<br/>
 - Usage: `[p]levelset forcestyle <style>`
## [p]levelset starmentiondelete
Toggle whether the bot auto-deletes the star mentions<br/>
Set to 0 to disable auto-delete<br/>
 - Usage: `[p]levelset starmentiondelete <deleted_after>`
## [p]levelset removexp
Remove XP from a user or role<br/>
 - Usage: `[p]levelset removexp <user_or_role> <xp>`
## [p]levelset levelchannel
Set LevelUp log channel<br/>

Set a channel for all level up messages to send to.<br/>

If level notify is off and mention is on, the bot will mention the user in the channel<br/>
 - Usage: `[p]levelset levelchannel [channel=None]`
## [p]levelset resetemojis
Reset the emojis to default<br/>
 - Usage: `[p]levelset resetemojis`
## [p]levelset setprestige
Set a user to a specific prestige level<br/>

Prestige roles will need to be manually added/removed when using this command<br/>
 - Usage: `[p]levelset setprestige <user> <prestige>`
## [p]levelset messages
Message settings<br/>
 - Usage: `[p]levelset messages`
 - Aliases: `message and msg`
### [p]levelset messages channelbonus
Add a range of bonus XP to apply to certain channels<br/>

This bonus applies to message xp<br/>

Set both min and max to 0 to remove the role bonus<br/>
 - Usage: `[p]levelset messages channelbonus <channel> <min_xp> <max_xp>`
### [p]levelset messages xp
Set message XP range<br/>

Set the Min and Max amount of XP that a message can gain<br/>
Default is 3 min and 6 max<br/>
 - Usage: `[p]levelset messages xp <min_xp> <max_xp>`
### [p]levelset messages rolebonus
Add a range of bonus XP to apply to certain roles<br/>

This bonus applies to message xp<br/>

Set both min and max to 0 to remove the role bonus<br/>
 - Usage: `[p]levelset messages rolebonus <role> <min_xp> <max_xp>`
### [p]levelset messages length
Set minimum message length for XP<br/>
Minimum length a message must be to count towards XP gained<br/>

Set to 0 to disable<br/>
 - Usage: `[p]levelset messages length <length>`
### [p]levelset messages cooldown
Cooldown threshold for message XP<br/>

When a user sends a message they will have to wait X seconds before their message<br/>
counts as XP gained<br/>
 - Usage: `[p]levelset messages cooldown <cooldown>`
## [p]levelset rolegroup
Add or remove a role to the role group<br/>

These roles gain their own experience points as a group<br/>
When a member gains xp while having this role, the xp they earn is also added to the role group<br/>
 - Usage: `[p]levelset rolegroup <role>`
## [p]levelset levelnotify
Send levelup message in the channel the user is typing in<br/>

Send a message in the channel a user is typing in when they level up<br/>
 - Usage: `[p]levelset levelnotify`
## [p]levelset commandxp
Toggle whether users can gain Exp from running commands<br/>
 - Usage: `[p]levelset commandxp`
## [p]levelset allowed
Base command for all allowed lists<br/>
 - Usage: `[p]levelset allowed`
### [p]levelset allowed role
Add/Remove a role in the allowed list<br/>
If the allow list is not empty, only roles in the list will gain XP<br/>

Use the command with a role already in the allowed list to remove it<br/>
 - Usage: `[p]levelset allowed role <role>`
### [p]levelset allowed channel
Add/Remove a channel in the allowed list<br/>
If the allow list is not empty, only channels in the list will gain XP<br/>

Use the command with a channel already in the allowed list to remove it<br/>
 - Usage: `[p]levelset allowed channel <channel>`
## [p]levelset dm
Toggle DM notifications<br/>

Determines whether LevelUp messages are DM'd to the user<br/>
 - Usage: `[p]levelset dm`
## [p]levelset starmention
Toggle star reaction mentions<br/>
Toggle whether the bot mentions that a user reacted to a message with a star<br/>
 - Usage: `[p]levelset starmention`
## [p]levelset seelevels
Test the level algorithm<br/>
View the first 20 levels using the current algorithm to test experience curve<br/>
 - Usage: `[p]levelset seelevels`
## [p]levelset ignore
Base command for all ignore lists<br/>
 - Usage: `[p]levelset ignore`
### [p]levelset ignore channel
Add/Remove a channel in the ignore list<br/>
Channels in the ignore list don't gain XP<br/>

Use the command with a channel already in the ignore list to remove it<br/>
 - Usage: `[p]levelset ignore channel <channel>`
### [p]levelset ignore role
Add/Remove a role in the ignore list<br/>
Members with roles in the ignore list don't gain XP<br/>

Use the command with a role already in the ignore list to remove it<br/>
 - Usage: `[p]levelset ignore role <role>`
### [p]levelset ignore user
Add/Remove a user in the ignore list<br/>
Members in the ignore list don't gain XP<br/>

Use the command with a user already in the ignore list to remove them<br/>
 - Usage: `[p]levelset ignore user <user>`
## [p]levelset algorithm
Customize the leveling algorithm for your server<br/>
• Default base is 100<br/>
• Default exp is 2<br/>

**Equation**<br/>
➣ Getting required XP for a level<br/>
• `base * (level ^ exp) = XP`<br/>
➣ Getting required level for an XP value<br/>
• `level = (XP / base) ^ (1 / exp)`<br/>

**Arguments**<br/>
➣ `part` - The part of the algorithm to change<br/>
➣ `value` - The value to set it to<br/>
 - Usage: `[p]levelset algorithm <part> <value>`
 - Aliases: `algo`
## [p]levelset mention
Toggle whether to mention the user in the level up message<br/>

If level notify is on AND a log channel is set, the user will only be mentioned in the channel they are in.<br/>
 - Usage: `[p]levelset mention`
## [p]levelset toggle
Toggle the LevelUp system<br/>
 - Usage: `[p]levelset toggle`
## [p]levelset emojis
Set the emojis used to represent each stat type<br/>
 - Usage: `[p]levelset emojis <level> <prestige> <star> <chat> <voicetime> <experience> <balance>`
## [p]levelset embeds
Toggle using embeds or generated pics<br/>
 - Usage: `[p]levelset embeds`
