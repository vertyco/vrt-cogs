# Events

Host and manage events in your server with a variety of customization options.<br/><br/>Create an event, set a channel for submissions and entry requirements/options.<br/>Users can enter the event and make submissions according to the parameters set.

## [p]enotify

Enable/Disable event notifications for yourself<br/>

You will be notified when events start and end<br/>

 - Usage: `[p]enotify`
 - Checks: `guild_only`

## [p]enter

Enter an event if one exists<br/>

 - Usage: `[p]enter`
 - Checks: `guild_only`

## [p]events

Create, manage and view events<br/>

 - Usage: `[p]events`
 - Checks: `guild_only`

### [p]events blacklistrole

Add/Remove blacklisted roles<br/>

These roles are not allowed to enter events, but can still vote on them<br/>

 - Usage: `[p]events blacklistrole <role>`

### [p]events notifyrole

Add/Remove notify roles<br/>

These roles will be pinged on event start and completion<br/>

 - Usage: `[p]events notifyrole <role>`

### [p]events staffrole

Add/Remove staff roles<br/>

If ping staff is enabled, these roles will be pinged on event completion<br/>

 - Usage: `[p]events staffrole <role>`

### [p]events create

Create a new event<br/>

 - Usage: `[p]events create`

### [p]events resultdelete

(Toggle) Include event results in the messages to delete on cleanup<br/>

If this is on when an event is deleted and the user chooses to clean up the messages,<br/>
the results announcement will also be deleted<br/>

 - Usage: `[p]events resultdelete`

### [p]events delete

Delete an event outright<br/>

 - Usage: `[p]events delete`

### [p]events remove

Remove a user from an active event<br/>

 - Usage: `[p]events remove <user>`

### [p]events pingstaff

(Toggle) Ping staff on event completion<br/>

 - Usage: `[p]events pingstaff`

### [p]events end

End an event early, counting votes/announcing the winner<br/>

This will also delete the event afterwards<br/>

 - Usage: `[p]events end`

### [p]events shorten

Shorten the runtime of an event<br/>

**Examples**<br/>
`10d` - 10 days<br/>
`7d4h` - 7 days 4 hours<br/>

 - Usage: `[p]events shorten <time_string>`

### [p]events autodelete

(Toggle) Auto delete events from config when they complete<br/>

If auto delete is enabled, the messages in the event channel will need to be cleaned up manually<br/>

 - Usage: `[p]events autodelete`

### [p]events emoji

Set the default emoji for votes<br/>

Changing the vote emoji only affects events created after this is changed.<br/>
Existing events will still use the previous emoji for votes<br/>

 - Usage: `[p]events emoji <emoji>`

### [p]events extend

Extend the runtime of an event<br/>

**Examples**<br/>
`10d` - 10 days<br/>
`7d4h` - 7 days 4 hours<br/>

 - Usage: `[p]events extend <time_string>`

### [p]events blacklistuser

Add/Remove blacklisted users<br/>

These users are not allowed to enter events, but can still vote on them<br/>

 - Usage: `[p]events blacklistuser <user>`

### [p]events view

View the current events and settings<br/>

 - Usage: `[p]events view`

