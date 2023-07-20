# NoNuke Help

Anti-Nuke System for lazy guild owners!<br/><br/>Monitors the following events:<br/>Kicks & Bans<br/>Channel Creation/Edit/Deletion<br/>Role Creation/Edit/Deletion<br/><br/>Set a cooldown(in seconds)<br/>Set an overload count(X events in X seconds)<br/>Set an action(kick, ban, strip, notify)<br/><br/>If a user or bot exceeds X mod events within X seconds, the set action will be performed

# nonuke
 - Usage: `[p]nonuke `
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`

Anti-Nuke System for lazy server owners!<br/><br/>Monitors the following events:<br/>Kicks & Bans<br/>Channel Creation/Edit/Deletion<br/>Role Creation/Edit/Deletion<br/><br/>Set a cooldown(in seconds)<br/>Set an overload count(X events in X seconds)<br/>Set an action(kick, ban, strip, notify)<br/><br/>If a user or bot exceeds X mod events within X seconds, the set action will be performed

## nonuke logchannel
 - Usage: `[p]nonuke logchannel <channel> `

Set the log channel for Anti-Nuke kicks

## nonuke action
 - Usage: `[p]nonuke action <action> `

Set the action for the bot to take when NoNuke is triggered<br/><br/>**Actions**<br/>`kick` - kick the user<br/>`ban` - ban the user<br/>`strip` - strip all roles with permissions from user<br/>`notify` - just sends a report to the log channel

## nonuke view
 - Usage: `[p]nonuke view `

View the NoNuke settings

## nonuke cooldown
 - Usage: `[p]nonuke cooldown <cooldown> `

Cooldown (in seconds) for NoNuke to trigger

## nonuke dm
 - Usage: `[p]nonuke dm `

Toggle whether the bot sends the user a DM when a kick or ban action is performed

## nonuke whitelist
 - Usage: `[p]nonuke whitelist <user> `

Add/Remove users from the whitelist

## nonuke enable
 - Usage: `[p]nonuke enable `

Enable/Disable the NoNuke system

## nonuke overload
 - Usage: `[p]nonuke overload <overload> `

How many mod actions can be done within the set cooldown<br/><br/>**Mod actions include:**<br/>Kicks & Bans<br/>Channel Creation/Edit/Deletion<br/>Role Creation/Edit/Deletion

## nonuke ignorebots
 - Usage: `[p]nonuke ignorebots `

Toggle whether other bots are ignored<br/><br/>**NOTE:** Bot specific roles (the role created when the bot joins) cannot be removed.<br/>If NoNuke is set to strip roles, and a bot triggers it while having an integrated role, NoNuke will fail<br/>to remove the role from it.

