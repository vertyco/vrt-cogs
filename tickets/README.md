# Tickets

Support ticket system with multi-panel functionality

## [p]add (Hybrid Command)

Add a user to your ticket<br/>

 - Usage: `[p]add <user>`
 - Slash Usage: `/add <user>`
 - Checks: `guild_only`

## [p]renameticket (Hybrid Command)

Rename your ticket channel<br/>

 - Usage: `[p]renameticket <new_name>`
 - Slash Usage: `/renameticket <new_name>`
 - Checks: `guild_only`

## [p]close (Hybrid Command)

Close your ticket<br/>

**Examples**<br/>
`[p]close` - closes ticket with no reason attached<br/>
`[p]close thanks for helping!` - closes with reason "thanks for helping!"<br/>
`[p]close 1h` - closes in 1 hour with no reason attached<br/>
`[p]close 1m thanks for helping!` - closes in 1 minute with reason "thanks for helping!"<br/>

 - Usage: `[p]close [reason]`
 - Slash Usage: `/close [reason]`
 - Checks: `guild_only`

## [p]ticketstats

View ticket analytics and statistics.<br/>

 - Usage: `[p]ticketstats`
 - Restricted to: `ADMIN`
 - Aliases: `tstats`
 - Checks: `guild_only`

### [p]ticketstats reset

Reset statistics data.<br/>

**Targets:**<br/>
- `staff <user>` - Reset a specific staff member's stats<br/>
- `user <user>` - Reset a specific user's ticket stats<br/>
- `server` - Reset all server-wide stats<br/>
- `responsetime` - Reset the response time data shown on ticket panels<br/>
- `all` - Reset ALL statistics (staff, user, server, and response times)<br/>

**Examples:**<br/>
- `[p]ticketstats reset staff @User`<br/>
- `[p]ticketstats reset server`<br/>
- `[p]ticketstats reset responsetime`<br/>
- `[p]ticketstats reset all`<br/>

 - Usage: `[p]ticketstats reset <target> [user=None]`

### [p]ticketstats user

View statistics for a user who has opened tickets.<br/>

**Arguments:**<br/>
- `<user>` - The user to view stats for<br/>
- `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30m)<br/>

**Examples:**<br/>
- `[p]ticketstats user @User`<br/>
- `[p]ticketstats user @User 30d`<br/>

 - Usage: `[p]ticketstats user <user> [timespan=None]`

### [p]ticketstats busytimes

View when tickets are opened most frequently.<br/>

Shows hourly and daily distribution of ticket opens.<br/>

**Arguments:**<br/>
- `[timespan]` - Time period to analyze (e.g., 7d, 30d)<br/>

 - Usage: `[p]ticketstats busytimes [timespan=None]`
 - Aliases: `peak and busy`

### [p]ticketstats retention

Set how many days of detailed event data to retain.<br/>

Older events are pruned but cumulative counters (lifetime stats) are preserved.<br/>

**Arguments:**<br/>
- `[days]` - Days to retain (0 = unlimited). Shows current if not specified.<br/>

**Examples:**<br/>
- `[p]ticketstats retention` - View current setting<br/>
- `[p]ticketstats retention 90` - Keep 90 days of events<br/>
- `[p]ticketstats retention 0` - Keep all events forever<br/>

 - Usage: `[p]ticketstats retention [days=None]`
 - Aliases: `dataretention`

### [p]ticketstats staff

View detailed statistics for a support staff member.<br/>

**Arguments:**<br/>
- `[member]` - The staff member to view stats for (defaults to you)<br/>
- `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30m, 2w, 1mo)<br/>

**Examples:**<br/>
- `[p]ticketstats staff` - Your all-time stats<br/>
- `[p]ticketstats staff @User` - User's all-time stats<br/>
- `[p]ticketstats staff @User 7d` - User's stats for last 7 days<br/>

 - Usage: `[p]ticketstats staff [member=None] [timespan=None]`

### [p]ticketstats staffboard

View staff leaderboard for a specific metric.<br/>

**Metrics:**<br/>
- `response` - Fastest average response time<br/>
- `closed` - Most tickets closed<br/>
- `claimed` - Most tickets claimed<br/>
- `messages` - Most messages sent<br/>
- `resolution` - Fastest average resolution time<br/>

**Arguments:**<br/>
- `<metric>` - The metric to rank by<br/>
- `[timespan]` - Time period to filter (e.g., 7d, 24h, 2w)<br/>

**Examples:**<br/>
- `[p]ticketstats staffboard response`<br/>
- `[p]ticketstats staffboard closed 7d`<br/>

 - Usage: `[p]ticketstats staffboard [metric=response] [timespan=None]`
 - Aliases: `leaderboard and lb`

### [p]ticketstats responsetime

View the average staff response time for tickets.<br/>

This shows the average time it takes for staff to send their first<br/>
response in a ticket, based on the last 100 tickets.<br/>

 - Usage: `[p]ticketstats responsetime`
 - Aliases: `avgresponse`

### [p]ticketstats server

View server-wide ticket statistics.<br/>

**Arguments:**<br/>
- `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30d)<br/>

**Examples:**<br/>
- `[p]ticketstats server`<br/>
- `[p]ticketstats server 7d`<br/>

 - Usage: `[p]ticketstats server [timespan=None]`
 - Aliases: `global and overview`

### [p]ticketstats panel

View statistics for ticket panels.<br/>

**Arguments:**<br/>
- `[panel_name]` - Specific panel to view (shows all if not specified)<br/>
- `[timespan]` - Time period to filter (e.g., 7d, 30d)<br/>

**Examples:**<br/>
- `[p]ticketstats panel` - All panels overview<br/>
- `[p]ticketstats panel support 7d` - Support panel last 7 days<br/>

 - Usage: `[p]ticketstats panel [panel_name=None] [timespan=None]`
 - Aliases: `panels`

### [p]ticketstats frequent

View users who open the most tickets.<br/>

**Arguments:**<br/>
- `[limit]` - Number of users to show (default: 10, max: 25)<br/>
- `[timespan]` - Time period to filter (e.g., 7d, 30d)<br/>

**Examples:**<br/>
- `[p]ticketstats frequent`<br/>
- `[p]ticketstats frequent 20 30d`<br/>

 - Usage: `[p]ticketstats frequent [limit=10] [timespan=None]`
 - Aliases: `frequentusers and topusers`

## [p]tickets

Base support ticket settings<br/>

 - Usage: `[p]tickets`
 - Restricted to: `ADMIN`
 - Aliases: `tset`
 - Checks: `guild_only`

### [p]tickets blockoutside

Toggle blocking ticket creation outside working hours<br/>

When enabled, users cannot create tickets outside of the configured working hours.<br/>
When disabled (default), users can still create tickets but will see a notice about delayed responses.<br/>

 - Usage: `[p]tickets blockoutside <panel_name>`

### [p]tickets showresponsetime

(Toggle) Show average response time to users when they open a ticket<br/>

 - Usage: `[p]tickets showresponsetime`

### [p]tickets suspend

Suspend the ticket system<br/>
If a suspension message is set, any user that tries to open a ticket will receive this message<br/>

 - Usage: `[p]tickets suspend [message]`

### [p]tickets category

Set the category ID for a ticket panel<br/>

 - Usage: `[p]tickets category <panel_name> <category>`

### [p]tickets row

Set the row of a panel's button (0 - 4)<br/>

 - Usage: `[p]tickets row <panel_name> <row>`

### [p]tickets selfrename

(Toggle) If users can rename their own tickets<br/>

 - Usage: `[p]tickets selfrename`

### [p]tickets analyticsblacklist

Toggle a panel's exclusion from analytics/telemetry tracking.<br/>

Panels on the analytics blacklist will not have any ticket events<br/>
(opens, closes, claims, messages, response times) recorded.<br/>

**Arguments:**<br/>
- `<panel_name>` - The panel name to toggle<br/>

**Examples:**<br/>
- `[p]tickets analyticsblacklist apply` - Exclude "apply" panel from analytics<br/>
- `[p]tickets analyticsblacklist apply` - Run again to re-include it<br/>

 - Usage: `[p]tickets analyticsblacklist <panel_name>`

### [p]tickets addpanel

Add a support ticket panel<br/>

 - Usage: `[p]tickets addpanel <panel_name>`

### [p]tickets viewmessages

View/Delete a ticket message for a support ticket panel<br/>

 - Usage: `[p]tickets viewmessages <panel_name>`

### [p]tickets priority

Set the priority order of a panel's button<br/>

 - Usage: `[p]tickets priority <panel_name> <priority>`

### [p]tickets toggle

Toggle a panel on/off<br/>

Disabled panels will still show the button but it will be disabled<br/>

 - Usage: `[p]tickets toggle <panel_name>`

### [p]tickets selfclose

(Toggle) If users can close their own tickets<br/>

 - Usage: `[p]tickets selfclose`

### [p]tickets cleanup

Cleanup tickets that no longer exist<br/>

 - Usage: `[p]tickets cleanup`

### [p]tickets transcript

(Toggle) Ticket transcripts<br/>

Closed tickets will have their transcripts uploaded to the log channel<br/>

 - Usage: `[p]tickets transcript`

### [p]tickets buttoncolor

Set the button color for a support ticket panel<br/>

 - Usage: `[p]tickets buttoncolor <panel_name> <button_color>`

### [p]tickets outsidehoursmsg

Set a custom message to display when a ticket is created outside working hours<br/>

Leave message empty to reset to default.<br/>
The default message will inform users that response times may be delayed.<br/>

**Example**<br/>
`[p]tickets outsidehoursmsg support Our team is currently offline. We'll respond during business hours!`<br/>

 - Usage: `[p]tickets outsidehoursmsg <panel_name> [message]`

### [p]tickets buttonemoji

Set the button emoji for a support ticket panel<br/>

 - Usage: `[p]tickets buttonemoji <panel_name> <emoji>`

### [p]tickets addmessage

Add a message embed to be sent when a ticket is opened<br/>

You can include any of these in the embed to be replaced by their value when the message is sent<br/>
`{username}` - Person's Discord username<br/>
`{mention}` - This will mention the user<br/>
`{id}` - This is the ID of the user that created the ticket<br/>

The bot will walk you through a few steps to set up the embed including:<br/>
- Title (optional)<br/>
- Description (required)<br/>
- Footer (optional)<br/>
- Custom color (optional) - hex color code like #FF0000<br/>
- Image (optional) - URL to an image<br/>

 - Usage: `[p]tickets addmessage <panel_name>`

### [p]tickets viewhours

View the configured working hours for a panel<br/>

 - Usage: `[p]tickets viewhours <panel_name>`

### [p]tickets embed

Create an embed for ticket panel buttons to be added to<br/>

 - Usage: `[p]tickets embed <color> <channel> <title> <description>`

### [p]tickets addmodal

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

### [p]tickets workinghours

Set working hours for a specific day on a panel<br/>

Times should be in 24-hour format (HH:MM), e.g., 09:00 or 17:30<br/>
Days: monday, tuesday, wednesday, thursday, friday, saturday, sunday<br/>

**Examples**<br/>
`[p]tickets workinghours support monday 09:00 17:00`<br/>
`[p]tickets workinghours support friday 10:00 18:00`<br/>

To remove working hours for a day, use `[p]tickets workinghours <panel> <day> off`<br/>

 - Usage: `[p]tickets workinghours <panel_name> <day> <start_time> <end_time>`

### [p]tickets maxtickets

Set the max tickets a user can have open at one time of any kind<br/>

 - Usage: `[p]tickets maxtickets <amount>`

### [p]tickets overviewmention

Toggle whether channels are mentioned in the active ticket overview<br/>

 - Usage: `[p]tickets overviewmention`

### [p]tickets setuphelp

Ticket Setup Guide<br/>

 - Usage: `[p]tickets setuphelp`

### [p]tickets openrole

Add/Remove roles required to open a ticket for a specific panel<br/>

Specify the same role to remove it<br/>

 - Usage: `[p]tickets openrole <panel_name> <role>`

### [p]tickets buttontext

Set the button text for a support ticket panel<br/>

 - Usage: `[p]tickets buttontext <panel_name> <button_text>`

### [p]tickets timezone

Set the timezone for a panel's working hours<br/>

Use IANA timezone names (e.g., America/New_York, Europe/London, Asia/Tokyo)<br/>
Default is UTC if not set.<br/>

**Examples**<br/>
`[p]tickets timezone support America/New_York`<br/>
`[p]tickets timezone support Europe/London`<br/>
`[p]tickets timezone support UTC`<br/>

 - Usage: `[p]tickets timezone <panel_name> <timezone_str>`

### [p]tickets noresponse

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

### [p]tickets channel

Set the channel ID where a ticket panel is located<br/>

 - Usage: `[p]tickets channel <panel_name> <channel>`

### [p]tickets ticketname

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

### [p]tickets viewmodal

View/Delete a ticket message for a support ticket panel<br/>

 - Usage: `[p]tickets viewmodal <panel_name>`

### [p]tickets dm

(Toggle) The bot sending DM's for ticket alerts<br/>

 - Usage: `[p]tickets dm`

### [p]tickets logchannel

Set the logging channel for each panel's tickets<br/>

 - Usage: `[p]tickets logchannel <panel_name> <channel>`

### [p]tickets panels

View/Delete currently configured support ticket panels<br/>

 - Usage: `[p]tickets panels`

### [p]tickets supportrole

Add/Remove ticket support roles (one at a time)<br/>

**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/>

To remove a role, simply run this command with it again to remove it<br/>

 - Usage: `[p]tickets supportrole <role> [mention=False]`

### [p]tickets autoadd

(Toggle) Auto-add support and panel roles to thread tickets<br/>

Adding a user to a thread pings them, so this is off by default<br/>

 - Usage: `[p]tickets autoadd`

### [p]tickets view

View support ticket settings<br/>

 - Usage: `[p]tickets view`

### [p]tickets panelrole

Add/Remove roles for a specific panel<br/>

To remove a role, simply run this command with it again to remove it<br/>

**Optional**: include `true` for mention to have that role mentioned when a ticket is opened<br/>

These roles are a specialized subset of the main support roles.<br/>
Use this role type if you want to isolate specific groups to a certain panel.<br/>

 - Usage: `[p]tickets panelrole <panel_name> <role> [mention=False]`

### [p]tickets overview

Set a channel for the live overview message<br/>

The overview message shows all active tickets across all configured panels for a server.<br/>

 - Usage: `[p]tickets overview [channel]`

### [p]tickets usethreads

Toggle whether a certain panel uses threads or channels<br/>

 - Usage: `[p]tickets usethreads <panel_name>`

### [p]tickets maxclaims

Set how many staff members can claim/join a ticket before the join button is disabled (If using threads)<br/>

 - Usage: `[p]tickets maxclaims <panel_name> <amount>`

### [p]tickets selfmanage

(Toggle) If users can manage their own tickets<br/>

Users will be able to add/remove others to their support ticket<br/>

 - Usage: `[p]tickets selfmanage`

### [p]tickets blacklist

Add/Remove users or roles from the blacklist<br/>

Users and roles in the blacklist will not be able to create a ticket<br/>

 - Usage: `[p]tickets blacklist <user_or_role>`

### [p]tickets threadclose

(Toggle) Thread tickets being closed & archived instead of deleted<br/>

 - Usage: `[p]tickets threadclose`

### [p]tickets altchannel

Set an alternate channel that tickets will be opened under for a panel<br/>

If the panel uses threads, this needs to be a normal text channel.<br/>
If the panel uses channels, this needs to be a category.<br/>

If the panel is a channel type and a channel is used, the bot will use the category associated with the channel.<br/>

To remove the alt channel, specify the existing one<br/>

 - Usage: `[p]tickets altchannel <panel_name> <channel>`

### [p]tickets getlink

Get a direct download link for a ticket transcript<br/>

The HTML transcript can be downloaded and opened in any web browser.<br/>

 - Usage: `[p]tickets getlink <message>`

### [p]tickets updatemessage

Update a message with another message (Target gets updated using the source)<br/>

 - Usage: `[p]tickets updatemessage <source> <target>`

### [p]tickets panelmessage

Set the message ID of a ticket panel<br/>
Run this command in the same channel as the ticket panel message<br/>

 - Usage: `[p]tickets panelmessage <panel_name> <message>`

### [p]tickets closemodal

Throw a modal when the close button is clicked to enter a reason<br/>

 - Usage: `[p]tickets closemodal <panel_name>`

### [p]tickets interactivetranscript

(Toggle) Interactive transcripts<br/>

Transcripts will be an interactive html file to visualize the conversation from your browser.<br/>

 - Usage: `[p]tickets interactivetranscript`
 - Aliases: `intertrans, itrans, and itranscript`

### [p]tickets modaltitle

Set a title for a ticket panel's modal<br/>

 - Usage: `[p]tickets modaltitle <panel_name> [title]`

## [p]openfor (Hybrid Command)

Open a ticket for another user<br/>

 - Usage: `[p]openfor <user> <panel_name>`
 - Slash Usage: `/openfor <user> <panel_name>`
 - Restricted to: `MOD`

