Bot Arena - Build and Battle Robots!<br/><br/>Create custom battle bots from chassis, plating, and weapons,<br/>then fight against other players in arena combat.

## Requirements

Battle videos are rendered using PyAV. If you experience rendering issues on Linux, you may need to install ffmpeg:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# RHEL/CentOS
sudo yum install ffmpeg
```

# [p]botarenaset
Configure Bot Arena settings for this server<br/>
 - Usage: `[p]botarenaset`
 - Restricted to: `ADMIN`
 - Aliases: `baset`
 - Checks: `server_only`
## [p]botarenaset wipeall
[Owner] Wipe ALL player data from Bot Arena<br/>

This is irreversible! Type the confirmation code to proceed.<br/>
 - Usage: `[p]botarenaset wipeall [confirm=False]`
 - Restricted to: `BOT_OWNER`
## [p]botarenaset resetplayer
[Owner] Reset a player's data completely<br/>
 - Usage: `[p]botarenaset resetplayer <user> [confirm=False]`
 - Restricted to: `BOT_OWNER`
## [p]botarenaset viewparts
[Owner] View all parts and their render offsets<br/>

Debug tool for previewing part combinations and weapon offsets.<br/>
 - Usage: `[p]botarenaset viewparts`
 - Restricted to: `BOT_OWNER`
# [p]botarena
Bot Arena - Build and battle robots!<br/>

Opens the main game hub where you can:<br/>
- Play through the Campaign<br/>
- Build and customize bots<br/>
- Challenge other players<br/>
- Browse the shop<br/>
 - Usage: `[p]botarena`
 - Aliases: `ba`
 - Checks: `server_only`
# [p]botprofile
View a player's Bot Arena profile and stats.<br/>

Shows campaign progress, battle record, combat stats, and owned bots.<br/>

**Arguments:**<br/>
- `member`: The player to view (defaults to yourself)<br/>

**Examples:**<br/>
- `[p]botprofile` - View your own profile<br/>
- `[p]botprofile @User` - View another player's profile<br/>
 - Usage: `[p]botprofile [member=None]`
 - Aliases: `bp`
 - Checks: `server_only`# [p]botarenareset
Reset your Bot Arena account.<br/>

**⚠️ WARNING:** This permanently deletes ALL your progress!<br/>
- All credits will be lost<br/>
- All bots and parts will be deleted<br/>
- All campaign progress will be reset<br/>
- All battle statistics will be cleared<br/>

You will start fresh with 8,200 credits.<br/>

Use this if you're stuck and can't afford to continue.<br/>
 - Usage: `[p]botarenareset`
 - Aliases: `bareset`
 - Checks: `server_only`