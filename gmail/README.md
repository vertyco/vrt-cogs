# Gmail Help

Send emails using your Gmail account.<br/><br/>Use `[p]gmailhelp` for help getting started.

# /email (Slash Command)
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
# .email
Send an email<br/>

Attach files to the command to send them as attachments<br/>
 - Usage: `.email <sender> <recipient> <subject> <message>`
 - Checks: `server_only`
# .addemail
Add an email account<br/>
 - Usage: `.addemail`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `addgmail`
 - Checks: `server_only`
# .editemail
Edit an email account<br/>
 - Usage: `.editemail <email>`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `editgmail`
 - Checks: `server_only`
# .deleteemail
Delete an email account<br/>
 - Usage: `.deleteemail <email>`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# .gmailroles
Set the roles allowed to send emails<br/>
 - Usage: `.gmailroles <roles>`
 - Restricted to: `GUILD_OWNER`
 - Checks: `server_only`
# .gmailsettings
View the email settings for the server<br/>
 - Usage: `.gmailsettings`
 - Checks: `server_only`
# .gmailhelp
Get instructions for setting up Gmail<br/>
 - Usage: `.gmailhelp`
 - Aliases: `gmailsetup`
 - Checks: `server_only`
