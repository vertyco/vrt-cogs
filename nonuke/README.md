# NoNuke Help

Anti-Nuke System for lazy guild owners!

Monitors the following events:
Kicks & Bans
Channel Creation/Edit/Deletion
Role Creation/Edit/Deletion

Set a cooldown(in seconds)
Set an overload count(X events in X seconds)
Set an action(kick, ban, strip, notify)

If a user or bot exceeds X mod events within X seconds, the set action will be performed

# nonuke
 - Usage: `[p]nonuke`

Anti-Nuke System for lazy guild owners!

Monitors the following events:
Kicks & Bans
Channel Creation/Edit/Deletion
Role Creation/Edit/Deletion

Set a cooldown(in seconds)
Set an overload count(X events in X seconds)
Set an action(kick, ban, strip, notify)

If a user or bot exceeds X mod events within X seconds, the set action will be performed

## nonuke logchannel
 - Usage: `[p]nonuke logchannel <channel>`

Set the log channel for Anti-Nuke kicks

## nonuke dm
 - Usage: `[p]nonuke dm`

Toggle whether the bot sends the user a DM when a kick or ban action is performed

## nonuke enable
 - Usage: `[p]nonuke enable`

Enable/Disable the NoNuke system

## nonuke view
 - Usage: `[p]nonuke view`

View the NoNuke settings

## nonuke ignorebots
 - Usage: `[p]nonuke ignorebots`

Toggle whether other bots are ignored

**NOTE:** Bot specific roles (the role created when the bot joins) cannot be removed.
If NoNuke is set to strip roles, and a bot triggers it while having an integrated role, NoNuke will fail
to remove the role from it.

## nonuke whitelist
 - Usage: `[p]nonuke whitelist <user>`

Add/Remove users from the whitelist

## nonuke overload
 - Usage: `[p]nonuke overload <overload>`

How many mod actions can be done within the set cooldown

**Mod actions include:**
Kicks & Bans
Channel Creation/Edit/Deletion
Role Creation/Edit/Deletion

## nonuke action
 - Usage: `[p]nonuke action <action>`

Set the action for the bot to take when NoNuke is triggered

**Actions**
`kick` - kick the user
`ban` - ban the user
`strip` - strip all roles with permissions from user
`notify` - just sends a report to the log channel

## nonuke cooldown
 - Usage: `[p]nonuke cooldown <cooldown>`

Cooldown (in seconds) for NoNuke to trigger
