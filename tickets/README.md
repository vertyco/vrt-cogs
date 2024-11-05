Support ticket system with multi-panel functionality

# [p]add (Hybrid Command)
Add a user to your ticket<br/>
 - Usage: `[p]add <user>`
 - Slash Usage: `/add <user>`
 - Checks: `server_only`
# [p]renameticket (Hybrid Command)
Rename your ticket channel<br/>
 - Usage: `[p]renameticket <new_name>`
 - Slash Usage: `/renameticket <new_name>`
 - Checks: `server_only`
# [p]close (Hybrid Command)
Close your ticket<br/>

**Examples**<br/>
`[p]close` - closes ticket with no reason attached<br/>
`[p]close thanks for helping!` - closes with reason "thanks for helping!"<br/>
`[p]close 1h` - closes in 1 hour with no reason attached<br/>
`[p]close 1m thanks for helping!` - closes in 1 minute with reason "thanks for helping!"<br/>
 - Usage: `[p]close [reason]`
 - Slash Usage: `/close [reason]`
 - Checks: `server_only`
# [p]tickets
Base support ticket settings<br/>
 - Usage: `[p]tickets`
 - Restricted to: `ADMIN`
 - Aliases: `tset`
 - Checks: `server_only`
## [p]tickets panelrole
Add/Remove roles for a specific panel<br/>

To remove a role, simply run this command with it again to remove it<br/>

**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/>

These roles are a specialized subset of the main support roles.<br/>
Use this role type if you want to isolate specific groups to a certain panel.<br/>
 - Usage: `[p]tickets panelrole <panel_name> <role> [mention=False]`
## [p]tickets overviewmention
Toggle whether channels are mentioned in the active ticket overview<br/>
 - Usage: `[p]tickets overviewmention`
## [p]tickets transcript
(Toggle) Ticket transcripts<br/>

Closed tickets will have their transcripts uploaded to the log channel<br/>
 - Usage: `[p]tickets transcript`
## [p]tickets ticketname
Set the default ticket channel name for a panel<br/>

You can include the following in the name<br/>
`{num}` - Ticket number<br/>
`{user}` - user's name<br/>
`{displayname}` - user's display name<br/>
`{id}` - user's ID<br/>
`{shortdate}` - mm-dd<br/>
`{longdate}` - mm-dd-yyyy<br/>
`{time}` - hh-mm AM/PM according to bot host system time<br/>

You can set this to {default} to use default "Ticket-Username<br/>
 - Usage: `[p]tickets ticketname <panel_name> <ticket_name>`
## [p]tickets panels
View/Delete currently configured support ticket panels<br/>
 - Usage: `[p]tickets panels`
## [p]tickets suspend
Suspend the ticket system<br/>
If a suspension message is set, any user that tries to open a ticket will receive this message<br/>
 - Usage: `[p]tickets suspend [message]`
## [p]tickets row
Set the row of a panel's button (0 - 4)<br/>
 - Usage: `[p]tickets row <panel_name> <row>`
## [p]tickets buttontext
Set the button text for a support ticket panel<br/>
 - Usage: `[p]tickets buttontext <panel_name> <button_text>`
## [p]tickets addmodal
Add a modal field a ticket panel<br/>

Ticket panels can have up to 5 fields per modal for the user to fill out before opening a ticket.<br/>
If modal fields are added and have required fields,<br/>
the user will have to fill them out before they can open a ticket.<br/>

There is no toggle for modals, if a panel has them it will use them, if they don't then it just opens the ticket<br/>
When the ticket is opened, it sends the modal field responses in an embed below the ticket message<br/>

**Note**<br/>
`field_name` is just the name of the field stored in config,<br/>
it won't be shown in the modal and should not have spaces in it<br/>


Specify an existing field name to delete a modal field (non-case-sensitive)<br/>
 - Usage: `[p]tickets addmodal <panel_name> <field_name>`
## [p]tickets maxclaims
Set how many staff members can claim/join a ticket before the join button is disabled (If using threads)<br/>
 - Usage: `[p]tickets maxclaims <panel_name> <amount>`
## [p]tickets selfrename
(Toggle) If users can rename their own tickets<br/>
 - Usage: `[p]tickets selfrename`
## [p]tickets addpanel
Add a support ticket panel<br/>
 - Usage: `[p]tickets addpanel <panel_name>`
## [p]tickets view
View support ticket settings<br/>
 - Usage: `[p]tickets view`
## [p]tickets cleanup
Cleanup tickets that no longer exist<br/>
 - Usage: `[p]tickets cleanup`
## [p]tickets embed
Create an embed for ticket panel buttons to be added to<br/>
 - Usage: `[p]tickets embed <color> <channel> <title> <description>`
## [p]tickets usethreads
Toggle whether a certain panel uses threads or channels<br/>
 - Usage: `[p]tickets usethreads <panel_name>`
## [p]tickets blacklist
Add/Remove users or roles from the blacklist<br/>

Users and roles in the blacklist will not be able to create a ticket<br/>
 - Usage: `[p]tickets blacklist <user_or_role>`
## [p]tickets buttoncolor
Set the button color for a support ticket panel<br/>
 - Usage: `[p]tickets buttoncolor <panel_name> <button_color>`
## [p]tickets selfclose
(Toggle) If users can close their own tickets<br/>
 - Usage: `[p]tickets selfclose`
## [p]tickets interactivetranscript
(Toggle) Interactive transcripts<br/>

Transcripts will be an interactive html file to visualize the conversation from your browser.<br/>
 - Usage: `[p]tickets interactivetranscript`
 - Aliases: `intertrans, itrans, and itranscript`
## [p]tickets viewmodal
View/Delete a ticket message for a support ticket panel<br/>
 - Usage: `[p]tickets viewmodal <panel_name>`
## [p]tickets openrole
Add/Remove roles required to open a ticket for a specific panel<br/>

Specify the same role to remove it<br/>
 - Usage: `[p]tickets openrole <panel_name> <role>`
## [p]tickets closemodal
Throw a modal when the close button is clicked to enter a reason<br/>
 - Usage: `[p]tickets closemodal <panel_name>`
## [p]tickets getlink
Refetch the transcript link for a ticket<br/>
 - Usage: `[p]tickets getlink <message>`
## [p]tickets category
Set the category ID for a ticket panel<br/>
 - Usage: `[p]tickets category <panel_name> <category>`
## [p]tickets maxtickets
Set the max tickets a user can have open at one time of any kind<br/>
 - Usage: `[p]tickets maxtickets <amount>`
## [p]tickets updatemessage
Update a message with another message (Target gets updated using the source)<br/>
 - Usage: `[p]tickets updatemessage <source> <target>`
## [p]tickets buttonemoji
Set the button emoji for a support ticket panel<br/>
 - Usage: `[p]tickets buttonemoji <panel_name> <emoji>`
## [p]tickets noresponse
Auto-close ticket if opener doesn't say anything after X hours of opening<br/>

Set to 0 to disable this<br/>

If using thread tickets, this translates to the thread's "Hide after inactivity" setting.<br/>
Your options are:<br/>
- 1 hour<br/>
- 24 hours (1 day)<br/>
- 72 hours (3 days)<br/>
- 168 hours (1 week)<br/>
Tickets will default to the closest value you select.<br/>
 - Usage: `[p]tickets noresponse <hours>`
## [p]tickets selfmanage
(Toggle) If users can manage their own tickets<br/>

Users will be able to add/remove others to their support ticket<br/>
 - Usage: `[p]tickets selfmanage`
## [p]tickets addmessage
Add a message embed to be sent when a ticket is opened<br/>

You can include any of these in the embed to be replaced by their value when the message is sent<br/>
`{username}` - Person's Discord username<br/>
`{mention}` - This will mention the user<br/>
`{id}` - This is the ID of the user that created the ticket<br/>

The bot will walk you through a few steps to set up the embed<br/>
 - Usage: `[p]tickets addmessage <panel_name>`
## [p]tickets altchannel
Set an alternate channel that tickets will be opened under for a panel<br/>

If the panel uses threads, this needs to be a normal text channel.<br/>
If the panel uses channels, this needs to be a category.<br/>

If the panel is a channel type and a channel is used, the bot will use the category associated with the channel.<br/>

To remove the alt channel, specify the existing one<br/>
 - Usage: `[p]tickets altchannel <panel_name> <channel>`
## [p]tickets logchannel
Set the logging channel for each panel's tickets<br/>
 - Usage: `[p]tickets logchannel <panel_name> <channel>`
## [p]tickets channel
Set the channel ID where a ticket panel is located<br/>
 - Usage: `[p]tickets channel <panel_name> <channel>`
## [p]tickets supportrole
Add/Remove ticket support roles (one at a time)<br/>

**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/>

To remove a role, simply run this command with it again to remove it<br/>
 - Usage: `[p]tickets supportrole <role> [mention=False]`
## [p]tickets dm
(Toggle) The bot sending DM's for ticket alerts<br/>
 - Usage: `[p]tickets dm`
## [p]tickets toggle
Toggle a panel on/off<br/>

Disabled panels will still show the button but it will be disabled<br/>
 - Usage: `[p]tickets toggle <panel_name>`
## [p]tickets overview
Set a channel for the live overview message<br/>

The overview message shows all active tickets across all configured panels for a server.<br/>
 - Usage: `[p]tickets overview [channel]`
## [p]tickets autoadd
(Toggle) Auto-add support and panel roles to thread tickets<br/>

Adding a user to a thread pings them, so this is off by default<br/>
 - Usage: `[p]tickets autoadd`
## [p]tickets viewmessages
View/Delete a ticket message for a support ticket panel<br/>
 - Usage: `[p]tickets viewmessages <panel_name>`
## [p]tickets setuphelp
Ticket Setup Guide<br/>
 - Usage: `[p]tickets setuphelp`
## [p]tickets priority
Set the priority order of a panel's button<br/>
 - Usage: `[p]tickets priority <panel_name> <priority>`
## [p]tickets panelmessage
Set the message ID of a ticket panel<br/>
Run this command in the same channel as the ticket panel message<br/>
 - Usage: `[p]tickets panelmessage <panel_name> <message>`
## [p]tickets modaltitle
Set a title for a ticket panel's modal<br/>
 - Usage: `[p]tickets modaltitle <panel_name> [title]`
## [p]tickets threadclose
(Toggle) Thread tickets being closed & archived instead of deleted<br/>
 - Usage: `[p]tickets threadclose`
# [p]openfor (Hybrid Command)
Open a ticket for another user<br/>
 - Usage: `[p]openfor <user> <panel_name>`
 - Slash Usage: `/openfor <user> <panel_name>`
 - Restricted to: `MOD`
