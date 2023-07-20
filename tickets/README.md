# Tickets Help

Support ticket system with multi-panel functionality

# add (Hybrid Command)
 - Usage: `[p]add <user> `
 - Slash Usage: `/add <user> `
 - Checks: `server_only`

Add a user to your ticket

# renameticket (Hybrid Command)
 - Usage: `[p]renameticket <new_name> `
 - Slash Usage: `/renameticket <new_name> `
 - Checks: `server_only`

Rename your ticket channel

# close (Hybrid Command)
 - Usage: `[p]close [reason] `
 - Slash Usage: `/close [reason] `
 - Checks: `server_only`

Close your ticket<br/><br/>**Examples**<br/>`[p]close` - closes ticket with no reason attached<br/>`[p]close thanks for helping!` - closes with reason "thanks for helping!"<br/>`[p]close 1h` - closes in 1 hour with no reason attached<br/>`[p]close 1m thanks for helping!` - closes in 1 minute with reason "thanks for helping!"

# tickets
 - Usage: `[p]tickets `
 - Restricted to: `ADMIN`
 - Aliases: `tset`
 - Checks: `server_only`

Base support ticket settings

## tickets view
 - Usage: `[p]tickets view `

View support ticket settings

## tickets usethreads
 - Usage: `[p]tickets usethreads <panel_name> `

Toggle whether a certain panel uses threads or channels

## tickets threadclose
 - Usage: `[p]tickets threadclose `

(Toggle) Thread tickets being closed & archived instead of deleted

## tickets viewmodal
 - Usage: `[p]tickets viewmodal <panel_name> `

View/Delete a ticket message for a support ticket panel

## tickets noresponse
 - Usage: `[p]tickets noresponse <hours> `

Auto-close ticket if opener doesn't say anything after X hours of opening<br/><br/>Set to 0 to disable this

## tickets transcript
 - Usage: `[p]tickets transcript `

(Toggle) Ticket transcripts<br/><br/>Closed tickets will have their transcripts uploaded to the log channel

## tickets buttontext
 - Usage: `[p]tickets buttontext <panel_name> <button_text> `

Set the button text for a support ticket panel

## tickets altchannel
 - Usage: `[p]tickets altchannel <panel_name> <channel> `

Set an alternate channel that tickets will be opened under for a panel<br/><br/>If the panel uses threads, this needs to be a normal text channel.<br/>If the panel uses channels, this needs to be a category.<br/><br/>If the panel is a channel type and a channel is used, the bot will use the category associated with the channel.<br/><br/>To remove the alt channel, specify the existing one

## tickets closemodal
 - Usage: `[p]tickets closemodal <panel_name> `

Throw a modal when the close button is clicked to enter a reason

## tickets maxtickets
 - Usage: `[p]tickets maxtickets <amount> `

Set the max tickets a user can have open at one time of any kind

## tickets selfrename
 - Usage: `[p]tickets selfrename `

(Toggle) If users can rename their own tickets

## tickets addpanel
 - Usage: `[p]tickets addpanel <panel_name> `

Add a support ticket panel

## tickets buttoncolor
 - Usage: `[p]tickets buttoncolor <panel_name> <button_color> `

Set the button color for a support ticket panel

## tickets addmessage
 - Usage: `[p]tickets addmessage <panel_name> `

Add a message embed to be sent when a ticket is opened<br/><br/>You can include any of these in the embed to be replaced by their value when the message is sent<br/>`{username}` - Person's Discord username<br/>`{mention}` - This will mention the user<br/>`{id}` - This is the ID of the user that created the ticket<br/><br/>The bot will walk you through a few steps to set up the embed

## tickets overview
 - Usage: `[p]tickets overview [channel] `

Set a channel for the live overview message<br/><br/>The overview message shows all active tickets across all configured panels for a server.

## tickets priority
 - Usage: `[p]tickets priority <panel_name> <priority> `

Set the priority order of a panel's button

## tickets updatemessage
 - Usage: `[p]tickets updatemessage <source> <target> `

Update a message with another message (Target gets updated using the source)

## tickets setuphelp
 - Usage: `[p]tickets setuphelp `

Ticket Setup Guide

## tickets category
 - Usage: `[p]tickets category <panel_name> <category> `

Set the category ID for a ticket panel

## tickets logchannel
 - Usage: `[p]tickets logchannel <panel_name> <channel> `

Set the logging channel for each panel's tickets

## tickets supportrole
 - Usage: `[p]tickets supportrole <role> [mention=False] `

Add/Remove ticket support roles (one at a time)<br/><br/>**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/><br/>To remove a role, simply run this command with it again to remove it

## tickets selfclose
 - Usage: `[p]tickets selfclose `

(Toggle) If users can close their own tickets

## tickets buttonemoji
 - Usage: `[p]tickets buttonemoji <panel_name> <emoji> `

Set the button emoji for a support ticket panel

## tickets viewmessages
 - Usage: `[p]tickets viewmessages <panel_name> `

View/Delete a ticket message for a support ticket panel

## tickets cleanup
 - Usage: `[p]tickets cleanup `

Cleanup tickets that no longer exist

## tickets embed
 - Usage: `[p]tickets embed <color> <channel> <title> <description> `

Create an embed for ticket panel buttons to be added to

## tickets row
 - Usage: `[p]tickets row <panel_name> <row> `

Set the row of a panel's button (0 - 4)

## tickets panelmessage
 - Usage: `[p]tickets panelmessage <panel_name> <message> `

Set the message ID of a ticket panel<br/>Run this command in the same channel as the ticket panel message

## tickets panelrole
 - Usage: `[p]tickets panelrole <panel_name> <role> [mention=False] `

Add/Remove roles for a specific panel<br/><br/>To remove a role, simply run this command with it again to remove it<br/><br/>**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/><br/>These roles are a specialized subset of the main support roles.<br/>Use this role type if you want to isolate specific groups to a certain panel.

## tickets channel
 - Usage: `[p]tickets channel <panel_name> <channel> `

Set the channel ID where a ticket panel is located

## tickets modaltitle
 - Usage: `[p]tickets modaltitle <panel_name> [title] `

Set a title for a ticket panel's modal

## tickets selfmanage
 - Usage: `[p]tickets selfmanage `

(Toggle) If users can manage their own tickets<br/><br/>Users will be able to add/remove others to their support ticket

## tickets ticketname
 - Usage: `[p]tickets ticketname <panel_name> <ticket_name> `

Set the default ticket channel name for a panel<br/><br/>You can include the following in the name<br/>`{num}` - Ticket number<br/>`{user}` - user's name<br/>`{displayname}` - user's display name<br/>`{id}` - user's ID<br/>`{shortdate}` - mm-dd<br/>`{longdate}` - mm-dd-yyyy<br/>`{time}` - hh-mm AM/PM according to bot host system time<br/><br/>You can set this to {default} to use default "Ticket-Username

## tickets panels
 - Usage: `[p]tickets panels `

View/Delete currently configured support ticket panels

## tickets openrole
 - Usage: `[p]tickets openrole <panel_name> <role> `

Add/Remove roles required to open a ticket for a specific panel<br/><br/>Specify the same role to remove it

## tickets dm
 - Usage: `[p]tickets dm `

(Toggle) The bot sending DM's for ticket alerts

## tickets blacklist
 - Usage: `[p]tickets blacklist <user_or_role> `

Add/Remove users or roles from the blacklist<br/><br/>Users and roles in the blacklist will not be able to create a ticket

## tickets autoadd
 - Usage: `[p]tickets autoadd `

(Toggle) Auto-add support and panel roles to thread tickets<br/><br/>Adding a user to a thread pings them, so this is off by default

## tickets addmodal
 - Usage: `[p]tickets addmodal <panel_name> <field_name> `

Add a modal field a ticket panel<br/><br/>Ticket panels can have up to 5 fields per modal for the user to fill out before opening a ticket.<br/>If modal fields are added and have required fields,<br/>the user will have to fill them out before they can open a ticket.<br/><br/>There is no toggle for modals, if a panel has them it will use them, if they don't then it just opens the ticket<br/>When the ticket is opened, it sends the modal field responses in an embed below the ticket message<br/><br/>**Note**<br/>`field_name` is just the name of the field stored in config,<br/>it won't be shown in the modal and should not have spaces in it<br/><br/><br/>Specify an existing field name to delete a modal field (non-case-sensitive)

