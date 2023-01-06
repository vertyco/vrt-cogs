# Tickets Help

Support ticket system with multi-panel functionality

# tickets

- Usage: `[p]tickets`
- Aliases: `tset`

Base support ticket settings

## tickets addmessage

- Usage: `[p]tickets addmessage <panel_name>`

Add a message embed to be sent when a ticket is opened

You can include any of these in the embed to be replaced by their value when the message is sent
`{username}` - Person's Discord username
`{mention}` - This will mention the user
`{id}` - This is the ID of the user that created the ticket

The bot will walk you through a few steps to set up the embed

## tickets blacklist

- Usage: `[p]tickets blacklist <user_or_role>`

Add/Remove users or roles from the blacklist

Users and roles in the blacklist will not be able to create a ticket

## tickets channel

- Usage: `[p]tickets channel <panel_name> <channel>`

Set the channel ID where a ticket panel is located

## tickets viewmessages

- Usage: `[p]tickets viewmessages <panel_name>`

View/Delete a ticket message for a support ticket panel

## tickets transcript

- Usage: `[p]tickets transcript`

(Toggle) Ticket transcripts

Closed tickets will have their transcripts uploaded to the log channel

## tickets selfmanage

- Usage: `[p]tickets selfmanage`

(Toggle) If users can manage their own tickets

Users will be able to add/remove others to their support ticket

## tickets selfclose

- Usage: `[p]tickets selfclose`

(Toggle) If users can close their own tickets

## tickets view

- Usage: `[p]tickets view`

View support ticket settings

## tickets buttonemoji

- Usage: `[p]tickets buttonemoji <panel_name> <emoji>`

Set the button emoji for a support ticket panel

## tickets logchannel

- Usage: `[p]tickets logchannel <panel_name> <channel>`

Set the logging channel for each panel's tickets

## tickets noresponse

- Usage: `[p]tickets noresponse <hours>`

Auto-close ticket if opener doesn't say anything after X hours of opening

Set to 0 to disable this

## tickets selfrename

- Usage: `[p]tickets selfrename`

(Toggle) If users can rename their own tickets

## tickets buttontext

- Usage: `[p]tickets buttontext <panel_name> <button_text>`

Set the button text for a support ticket panel

## tickets setuphelp

- Usage: `[p]tickets setuphelp`

Ticket Setup Guide

## tickets addpanel

- Usage: `[p]tickets addpanel <panel_name>`

Add a support ticket panel

## tickets panelmessage

- Usage: `[p]tickets panelmessage <panel_name> <message>`

Set the message ID of a ticket panel
Run this command in the same channel as the ticket panel message

## tickets maxtickets

- Usage: `[p]tickets maxtickets <amount>`

Set the max tickets a user can have open at one time of any kind

## tickets panels

- Usage: `[p]tickets panels`

View/Delete currently configured support ticket panels

## tickets supportrole

- Usage: `[p]tickets supportrole <role>`

Add/Remove ticket support roles (one at a time)

To remove a role, simply run this command with it again to remove it

## tickets cleanup

- Usage: `[p]tickets cleanup`

Cleanup tickets that no longer exist

## tickets category

- Usage: `[p]tickets category <panel_name> <category>`

Set the category ID for a ticket panel

## tickets buttoncolor

- Usage: `[p]tickets buttoncolor <panel_name> <button_color>`

Set the button color for a support ticket panel

## tickets ticketname

- Usage: `[p]tickets ticketname <panel_name> <ticket_name>`

Set the default ticket channel name for a panel

You can include the following in the name
`{num}` - Ticket number
`{user}` - user's name
`{id}` - user's ID
`{shortdate}` - mm-dd
`{longdate}` - mm-dd-yyyy
`{time}` - hh-mm AM/PM according to bot host system time

You can set this to {default} to use default "Ticket-Username

## tickets dm

- Usage: `[p]tickets dm`

(Toggle) The bot sending DM's for ticket alerts

# add

- Usage: `[p]add <user>`

Add a user to your ticket

# renameticket

- Usage: `[p]renameticket <new_name>`
- Aliases: `renamet`

Rename your ticket channel

# close

- Usage: `[p]close [reason]`

Close your ticket
