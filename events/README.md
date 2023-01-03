# Events Help

Host and manage events in your server with a variety of customization options.

Create an event, set a channel for submissions and entry requirements/options.
Users can enter the event and make submissions according to the parameters set.

# enotify
 - Usage: `[p]enotify`

Enable/Disable event notifications for yourself

You will be notified when events start and end

# enter
 - Usage: `[p]enter`

Enter an event if one exists

# events
 - Usage: `[p]events`

Create, manage and view events

## events blacklistuser
 - Usage: `[p]events blacklistuser <user>`

Add/Remove blacklisted users

These users are not allowed to enter events, but can still vote on them

## events blacklistrole
 - Usage: `[p]events blacklistrole <role>`

Add/Remove blacklisted roles

These roles are not allowed to enter events, but can still vote on them

## events notifyrole
 - Usage: `[p]events notifyrole <role>`

Add/Remove notify roles

These roles will be pinged on event start and completion

## events staffrole
 - Usage: `[p]events staffrole <role>`

Add/Remove staff roles

If ping staff is enabled, these roles will be pinged on event completion

## events emoji
 - Usage: `[p]events emoji <emoji>`

Set the default emoji for votes

Changing the vote emoji only affects events created after this is changed.
Existing events will still use the previous emoji for votes

## events extend
 - Usage: `[p]events extend <time_string>`

Extend the runtime of an event

**Examples**
`10d` - 10 days
`7d4h` - 7 days 4 hours

## events resultdelete
 - Usage: `[p]events resultdelete`

(Toggle) Include event results in the messages to delete on cleanup

If this is on when an event is deleted and the user chooses to clean up the messages,
the results announcement will also be deleted

## events create
 - Usage: `[p]events create`

Create a new event

## events autodelete
 - Usage: `[p]events autodelete`

(Toggle) Auto delete events from config when they complete

If auto delete is enabled, the messages in the event channel will need to be cleaned up manually

## events remove
 - Usage: `[p]events remove <user>`

Remove a user from an active event

## events delete
 - Usage: `[p]events delete`

Delete an event outright

## events view
 - Usage: `[p]events view`

View the current events and settings

## events end
 - Usage: `[p]events end`

End an event early, counting votes/announcing the winner

This will also delete the event afterwards

## events shorten
 - Usage: `[p]events shorten <time_string>`

Shorten the runtime of an event

**Examples**
`10d` - 10 days
`7d4h` - 7 days 4 hours

## events pingstaff
 - Usage: `[p]events pingstaff`

(Toggle) Ping staff on event completion
