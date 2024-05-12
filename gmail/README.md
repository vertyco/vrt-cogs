# Gmail Help

Simple cog to send emails using your Gmail account.<br/><br/>Use `[p]gmailhelp` for help getting started.

# email (Slash Command)

- Usage: `/email <sender> <recipient> <subject> <message> [attachment1] [attachment2] [attachment3]`
- `sender:` (Required) …
- `recipient:` (Required) …
- `subject:` (Required) …
- `message:` (Required) …
- `attachment1:` (Optional) …
- `attachment2:` (Optional) …
- `attachment3:` (Optional) …

- Checks: `Server Only

Send an email

# email

- Usage: `[p]email <sender> <recipient> <subject> <message>`
- Checks: `server_only`

Send an email<br/><br/>Attach files to the command to send them as attachments

# addemail

- Usage: `[p]addemail`
- Restricted to: `GUILD_OWNER`
- Aliases: `addgmail`
- Checks: `server_only`

Add an email account

# editemail

- Usage: `[p]editemail <email>`
- Restricted to: `GUILD_OWNER`
- Aliases: `editgmail`
- Checks: `server_only`

Edit an email account

# deleteemail

- Usage: `[p]deleteemail <email>`
- Restricted to: `GUILD_OWNER`
- Checks: `server_only`

Delete an email account

# signature

- Usage: `[p]signature <email> <signature>`
- Restricted to: `GUILD_OWNER`
- Checks: `server_only`

Set a signature for your email account<br/><br/>Enter `none` to remove the signature

# gmailroles

- Usage: `[p]gmailroles <roles>`
- Restricted to: `GUILD_OWNER`
- Checks: `server_only`

Set the roles allowed to send emails

# gmailsettings

- Usage: `[p]gmailsettings`
- Checks: `server_only`

View the email settings for the server

# gmailhelp

- Usage: `[p]gmailhelp`
- Aliases: `gmailsetup`
- Checks: `server_only`

Get instructions for setting up Gmail
