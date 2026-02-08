# Gmail

Send emails using your Gmail account.<br/><br/>Use `[p]gmailhelp` for help getting started.

## /email (Slash Command)

Send an email<br/>

 - Usage: `/email <sender> <recipient> <subject> <message> [attachment1] [attachment2] [attachment3]`
 - `sender:` (Required) …
 - `recipient:` (Required) …
 - `subject:` (Required) …
 - `message:` (Required) …
 - `attachment1:` (Optional) …
 - `attachment2:` (Optional) …
 - `attachment3:` (Optional) …

 - Checks: `Server Only`

## [p]email

Send an email<br/>

Attach files to the command to send them as attachments<br/>

 - Usage: `[p]email <sender> <recipient> <subject> <message>`
 - Checks: `guild_only`

## [p]addemail

Add an email account<br/>

 - Usage: `[p]addemail`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `addgmail`
 - Checks: `guild_only`

## [p]editemail

Edit an email account<br/>

 - Usage: `[p]editemail <email>`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `editgmail`
 - Checks: `guild_only`

## [p]deleteemail

Delete an email account<br/>

 - Usage: `[p]deleteemail <email>`
 - Restricted to: `GUILD_OWNER`
 - Checks: `guild_only`

## [p]gmailroles

Set the roles allowed to send emails<br/>

 - Usage: `[p]gmailroles <roles>`
 - Restricted to: `GUILD_OWNER`
 - Checks: `guild_only`

## [p]gmailsettings

View the email settings for the server<br/>

 - Usage: `[p]gmailsettings`
 - Checks: `guild_only`

## [p]gmailhelp

Get instructions for setting up Gmail<br/>

 - Usage: `[p]gmailhelp`
 - Aliases: `gmailsetup`
 - Checks: `guild_only`

