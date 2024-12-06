Turn a secondary Discord into a ban appeal server

# [p]appealsfor
Get all appeal submissions for a specific user<br/>
 - Usage: `[p]appealsfor <user>`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
# [p]viewappeal
View an appeal submission by ID<br/>
 - Usage: `[p]viewappeal <submission_id>`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
# [p]appeal
Configure appeal server settings<br/>
 - Usage: `[p]appeal`
 - Restricted to: `ADMIN`
 - Aliases: `appeals and appealset`
 - Checks: `server_only`
## [p]appeal view
View the current appeal server settings<br/>
 - Usage: `[p]appeal view`
 - Checks: `ensure_db_connection`
## [p]appeal nukedb
Nuke the entire appeal database<br/>
 - Usage: `[p]appeal nukedb <confirm>`
 - Restricted to: `BOT_OWNER`
 - Checks: `ensure_db_connection`
## [p]appeal addquestion
Add a question to the appeal form<br/>
 - Usage: `[p]appeal addquestion <question>`
 - Checks: `ensure_db_connection`
## [p]appeal server
Set the server ID where users will be unbanned from<br/>

**NOTES**<br/>
- This is the first step to setting up the appeal system<br/>
- This server will be the appeal server<br/>
- You must be the owner of the target server<br/>
 - Usage: `[p]appeal server <server_id>`
 - Restricted to: `GUILD_OWNER`
 - Checks: `ensure_db_connection`
## [p]appeal editquestion
Edit a question in the appeal form<br/>
 - Usage: `[p]appeal editquestion <question_id> <question>`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal wipeappeals
Wipe all appeal submissions<br/>
 - Usage: `[p]appeal wipeappeals <confirm>`
 - Checks: `ensure_db_connection`
## [p]appeal removequestion
Remove a question from the appeal form<br/>
 - Usage: `[p]appeal removequestion <question_id>`
 - Checks: `ensure_db_connection`
## [p]appeal refresh
Refresh the appeal message with the current appeal form<br/>
 - Usage: `[p]appeal refresh`
 - Checks: `ensure_db_connection`
## [p]appeal channel
Set the channel where submitted appeals will go<br/>

`channel_type` must be one of: pending, approved, denied<br/>

**NOTE**: All 3 channel types must be set for the appeal system to work properly.<br/>
 - Usage: `[p]appeal channel <channel_type> <channel>`
 - Checks: `ensure_db_connection`
## [p]appeal sortorder
Set the sort order for a question in the appeal form<br/>
 - Usage: `[p]appeal sortorder <question_id> <sort_order>`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal approve
Approve an appeal submission by ID<br/>
 - Usage: `[p]appeal approve <submission_id>`
 - Checks: `ensure_db_connection`
## [p]appeal questions
Menu to view questions in the appeal form<br/>
 - Usage: `[p]appeal questions`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal buttonstyle
Set the style of the appeal button<br/>
 - Usage: `[p]appeal buttonstyle <style>`
 - Checks: `ensure_db_connection`
## [p]appeal createappealmessage
Quickly create and set a pre-baked appeal message in the specified channel<br/>
 - Usage: `[p]appeal createappealmessage <channel>`
 - Checks: `ensure_db_connection`
## [p]appeal alertchannel
Set the channel ID where alerts for new appeals will be sent<br/>

This can be in either the appeal server or the target server.<br/>
Alert roles will not be pinged in this message.<br/>
 - Usage: `[p]appeal alertchannel [channel]`
 - Checks: `ensure_db_connection`
## [p]appeal help
How to set up the appeal system<br/>
 - Usage: `[p]appeal help`
 - Aliases: `info and setup`
 - Checks: `ensure_db_connection`
## [p]appeal deny
Deny an appeal submission by ID<br/>
 - Usage: `[p]appeal deny <submission_id>`
 - Checks: `ensure_db_connection`
## [p]appeal questiondetails
Set specific data for a question in the appeal form<br/>

**Arguments**<br/>
- `required`: Whether the question is required or not<br/>
- `modal_style`: The style of the modal for the question<br/>
  - `long`: The modal will be a long text input<br/>
  - `short`: The modal will be a short text input<br/>
- `button_style`: The color of the button for the question<br/>
  - `primary🔵`, `secondary⚫`, `success🟢`, `danger🔴`<br/>
- `placeholder`: The placeholder text for the input<br/>
- `default`: The default value for the input<br/>
- `max_length`: The maximum length for the input<br/>
- `min_length`: The minimum length for the input<br/>
 - Usage: `[p]appeal questiondetails <question_id> <required> [modal_style=None] [button_style=None] [placeholder=None] [default=None] [max_length=None] [min_length=None]`
 - Aliases: `questiondata, setquestiondata, qd, and details`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal listquestions
List all questions in the appeal form<br/>

Questions will be sorted by their sort order and then by creation date.<br/>
 - Usage: `[p]appeal listquestions`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal buttonlabel
Set the label of the appeal button<br/>
 - Usage: `[p]appeal buttonlabel <label>`
 - Checks: `ensure_db_connection`
## [p]appeal appealmessage
Set the message where users will appeal from<br/>
Message format: `channelID-messageID`<br/>
 - Usage: `[p]appeal appealmessage <message>`
 - Checks: `ensure_db_connection`
## [p]appeal alertrole
Add/Remove roles to be pinged when a new appeal is submitted<br/>
These roles will be pinged in the appeal server, NOT the target server.<br/>
 - Usage: `[p]appeal alertrole <role>`
 - Checks: `ensure_db_connection`
## [p]appeal delete
Delete an appeal submission by ID<br/>
 - Usage: `[p]appeal delete <submission_id>`
 - Checks: `ensure_db_connection`
## [p]appeal viewquestion
View a question in the appeal form<br/>
 - Usage: `[p]appeal viewquestion <question_id>`
 - Checks: `ensure_appeal_system_ready and ensure_db_connection`
## [p]appeal buttonemoji
Set the emoji of the appeal button<br/>
 - Usage: `[p]appeal buttonemoji [emoji=None]`
 - Checks: `ensure_db_connection`
