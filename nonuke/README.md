Anti-Nuke System for lazy server owners!<br/><br/>Monitors the following events:<br/>Kicks/Bans/Unbans/Prunes<br/>Channel Creation/Edit/Deletion<br/>Role Creation/Edit/Deletion<br/>Emoji Creation/Edit/Deletion<br/>Sticker Creation/Edit/Deletion<br/>Webhook Creation/Edit/Deletion<br/>Member role/nickname updates<br/><br/>Set a cooldown(in seconds)<br/>Set an overload count(X events in X seconds)<br/>Set an action(kick, ban, strip, notify)<br/><br/>If a user or bot exceeds X mod events within X seconds, the set action will be performed.<br/><br/>- Any dangerous permissions added to a role will be logged.<br/>- If the vanity URL is changed, it will be logged.

# [p]nonuke
Anti-Nuke System for lazy server owners!<br/>

Monitors the following events:<br/>
Kicks & Bans<br/>
Channel Creation/Edit/Deletion<br/>
Role Creation/Edit/Deletion<br/>

Set a cooldown(in seconds)<br/>
Set an overload count(X events in X seconds)<br/>
Set an action(kick, ban, strip, notify)<br/>

If a user or bot exceeds X mod events within X seconds, the set action will be performed<br/>
 - Usage: `[p]nonuke`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
## [p]nonuke overload
How many mod actions can be done within the set cooldown<br/>

**Mod actions include:**<br/>
Kicks & Bans<br/>
Channel Creation/Edit/Deletion<br/>
Role Creation/Edit/Deletion<br/>
 - Usage: `[p]nonuke overload <overload>`
## [p]nonuke action
Set the action for the bot to take when NoNuke is triggered<br/>

**Actions**<br/>
`kick` - kick the user<br/>
`ban` - ban the user<br/>
`strip` - strip all roles with permissions from user<br/>
`notify` - just sends a report to the log channel<br/>
 - Usage: `[p]nonuke action <action>`
## [p]nonuke view
View the NoNuke settings<br/>
 - Usage: `[p]nonuke view`
## [p]nonuke whitelist
Add/Remove users from the whitelist<br/>
 - Usage: `[p]nonuke whitelist <user>`
## [p]nonuke cooldown
Cooldown (in seconds) for NoNuke to trigger<br/>
 - Usage: `[p]nonuke cooldown <cooldown>`
## [p]nonuke logchannel
Set the log channel for Anti-Nuke kicks<br/>
 - Usage: `[p]nonuke logchannel <channel>`
## [p]nonuke dm
Toggle whether the bot sends the user a DM when a kick or ban action is performed<br/>
 - Usage: `[p]nonuke dm`
## [p]nonuke enable
Enable/Disable the NoNuke system<br/>
 - Usage: `[p]nonuke enable`
## [p]nonuke ignorebots
Toggle whether other bots are ignored<br/>

**NOTE:** Bot specific roles (the role created when the bot joins) cannot be removed.<br/>
If NoNuke is set to strip roles, and a bot triggers it while having an integrated role, NoNuke will fail<br/>
to remove the role from it.<br/>
 - Usage: `[p]nonuke ignorebots`
