# Events Help

Host and manage events in your server with a variety of customization options.<br/><br/>Create an event, set a channel for submissions and entry requirements/options.<br/>Users can enter the event and make submissions according to the parameters set.

# .enotify
Enable/Disable event notifications for yourself<br/>

You will be notified when events start and end<br/>
 - Usage: `.enotify`
 - Checks: `server_only`
# .enter
Enter an event if one exists<br/>
 - Usage: `.enter`
 - Checks: `server_only`
# .events
Create, manage and view events<br/>
 - Usage: `.events`
 - Checks: `server_only`
## .events blacklistrole
Add/Remove blacklisted roles<br/>

These roles are not allowed to enter events, but can still vote on them<br/>
 - Usage: `.events blacklistrole <role>`
## .events emoji
Set the default emoji for votes<br/>

Changing the vote emoji only affects events created after this is changed.<br/>
Existing events will still use the previous emoji for votes<br/>
 - Usage: `.events emoji <emoji>`
## .events notifyrole
Add/Remove notify roles<br/>

These roles will be pinged on event start and completion<br/>
 - Usage: `.events notifyrole <role>`
## .events extend
Extend the runtime of an event<br/>

**Examples**<br/>
`10d` - 10 days<br/>
`7d4h` - 7 days 4 hours<br/>
 - Usage: `.events extend <time_string>`
## .events staffrole
Add/Remove staff roles<br/>

If ping staff is enabled, these roles will be pinged on event completion<br/>
 - Usage: `.events staffrole <role>`
## .events create
Create a new event<br/>
 - Usage: `.events create`
## .events resultdelete
(Toggle) Include event results in the messages to delete on cleanup<br/>

If this is on when an event is deleted and the user chooses to clean up the messages,<br/>
the results announcement will also be deleted<br/>
 - Usage: `.events resultdelete`
## .events delete
Delete an event outright<br/>
 - Usage: `.events delete`
## .events remove
Remove a user from an active event<br/>
 - Usage: `.events remove <user>`
## .events view
View the current events and settings<br/>
 - Usage: `.events view`
## .events end
End an event early, counting votes/announcing the winner<br/>

This will also delete the event afterwards<br/>
 - Usage: `.events end`
## .events shorten
Shorten the runtime of an event<br/>

**Examples**<br/>
`10d` - 10 days<br/>
`7d4h` - 7 days 4 hours<br/>
 - Usage: `.events shorten <time_string>`
## .events pingstaff
(Toggle) Ping staff on event completion<br/>
 - Usage: `.events pingstaff`
## .events blacklistuser
Add/Remove blacklisted users<br/>

These users are not allowed to enter events, but can still vote on them<br/>
 - Usage: `.events blacklistuser <user>`
## .events autodelete
(Toggle) Auto delete events from config when they complete<br/>

If auto delete is enabled, the messages in the event channel will need to be cleaned up manually<br/>
 - Usage: `.events autodelete`
