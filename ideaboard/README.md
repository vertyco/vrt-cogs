Share Ideas and Suggestions

# [p]idea (Hybrid Command)
Share an idea/make a suggestion.<br/>
 - Usage: `[p]idea <content>`
 - Slash Usage: `/idea <content>`
 - Aliases: `suggest`
 - Cooldown: `10000 per 1.0 second`
 - Checks: `bot_has_server_permissions and server_only`
# [p]ideastats (Hybrid Command)
Display your current profile stats for suggestions and votes.<br/>
 - Usage: `[p]ideastats [member]`
 - Slash Usage: `/ideastats [member]`
 - Checks: `server_only`
# [p]approve (Hybrid Command)
Approve an idea/suggestion.<br/>
 - Usage: `[p]approve <number> [reason]`
 - Slash Usage: `/approve <number> [reason]`
 - Restricted to: `MOD`
 - Checks: `server_only`
# [p]reject (Hybrid Command)
Reject an idea/suggestion.<br/>
 - Usage: `[p]reject <number> [reason]`
 - Slash Usage: `/reject <number> [reason]`
 - Restricted to: `MOD`
 - Checks: `server_only`
# [p]viewvotes (Hybrid Command)
View the list of who has upvoted and who has downvoted a suggestion.<br/>
 - Usage: `[p]viewvotes <number>`
 - Slash Usage: `/viewvotes <number>`
 - Restricted to: `MOD`
 - Checks: `server_only`
# [p]refresh (Hybrid Command)
Refresh the buttons on a suggestion if it gets stuck.<br/>
 - Usage: `[p]refresh <number>`
 - Slash Usage: `/refresh <number>`
 - Checks: `server_only`
# [p]ideaset
Manage IdeaBoard settings<br/>
 - Usage: `[p]ideaset`
 - Restricted to: `ADMIN`
 - Aliases: `ideaboard`
## [p]ideaset showstale
View the numbers of suggestions who's message no longer exists.<br/>
 - Usage: `[p]ideaset showstale`
## [p]ideaset approverole
Add/remove a role to the approver role list<br/>
 - Usage: `[p]ideaset approverole <role>`
## [p]ideaset minlevel
Set the LevelUp integration minimum level required to vote and suggest.<br/>

Args:<br/>
    to_vote: Minimum level required to vote.<br/>
    to_suggest: Minimum level required to suggest.<br/>
 - Usage: `[p]ideaset minlevel <to_vote> <to_suggest>`
## [p]ideaset downvoteemoji
Set the downvote emoji<br/>
 - Usage: `[p]ideaset downvoteemoji <emoji>`
 - Aliases: `downvote and down`
## [p]ideaset togglevotecount
Toggle showing vote counts on suggestions<br/>
 - Usage: `[p]ideaset togglevotecount`
 - Aliases: `votecount`
## [p]ideaset cleanup
Cleanup the config.<br/>
- Remove suggestions who's message no longer exists.<br/>
- Remove profiles of users who have left the server.<br/>
- Remove votes from users who have left the server.<br/>
 - Usage: `[p]ideaset cleanup`
## [p]ideaset roleblacklist
Add/remove a role to/from the role blacklist<br/>
 - Usage: `[p]ideaset roleblacklist <role>`
 - Aliases: `blacklistrole and rolebl`
## [p]ideaset toggledm
Toggle DMing users the results of suggestions they made<br/>
 - Usage: `[p]ideaset toggledm`
 - Aliases: `dm`
## [p]ideaset minplaytime
Set the ArkTools integration minimum playtime required to vote and suggest.<br/>

Args:<br/>
    to_vote: Minimum playtime in hours required to vote.<br/>
    to_suggest: Minimum playtime in hours required to suggest.<br/>
 - Usage: `[p]ideaset minplaytime <to_vote> <to_suggest>`
## [p]ideaset channel
Set the approved, rejected, or pending channels for IdeaBoard<br/>
 - Usage: `[p]ideaset channel <channel> <channel_type>`
## [p]ideaset cooldown
Set the base cooldown for making suggestions<br/>
 - Usage: `[p]ideaset cooldown <cooldown>`
 - Aliases: `cd`
## [p]ideaset insights
View insights about the server's suggestions.<br/>

**Arguments**<br/>
- `amount` The number of top users to display for each section.<br/>
 - Usage: `[p]ideaset insights [amount=3]`
## [p]ideaset suggestrole
Add/remove a role to the suggest role whitelist<br/>
 - Usage: `[p]ideaset suggestrole <role>`
## [p]ideaset view
View IdeaBoard settings<br/>
 - Usage: `[p]ideaset view`
## [p]ideaset rolecooldown
Set the suggestion cooldown for a specific role<br/>

To remove a role cooldown, specify 0 as the cooldown.<br/>
 - Usage: `[p]ideaset rolecooldown <role> <cooldown>`
 - Aliases: `rolecd`
## [p]ideaset jointime
Set the minimum time a user must be in the server to vote and suggest.<br/>

Args:<br/>
    to_vote: Minimum time in hours required to vote.<br/>
    to_suggest: Minimum time in hours required to suggest.<br/>
 - Usage: `[p]ideaset jointime <to_vote> <to_suggest>`
## [p]ideaset discussions
Toggle opening a discussion thread for each suggestion<br/>
 - Usage: `[p]ideaset discussions`
 - Aliases: `threads and discussion`
## [p]ideaset resetuser
Reset a user's stats<br/>
 - Usage: `[p]ideaset resetuser <member>`
## [p]ideaset voterole
Add/remove a role to the voting role whitelist<br/>
 - Usage: `[p]ideaset voterole <role>`
## [p]ideaset userblacklist
Add/remove a user to/from the user blacklist<br/>
 - Usage: `[p]ideaset userblacklist <member>`
 - Aliases: `blacklistuser and userbl`
## [p]ideaset deletethreads
Toggle deleting discussion threads when a suggestion is approved/denied<br/>
 - Usage: `[p]ideaset deletethreads`
 - Aliases: `delete and delthreads`
## [p]ideaset toggleanonymous
Toggle allowing anonymous suggestions<br/>
 - Usage: `[p]ideaset toggleanonymous`
 - Aliases: `toggleanon, anonymous, and anon`
## [p]ideaset accountage
Set the minimum account age required to vote and suggest.<br/>

Args:<br/>
    to_vote: Minimum age in hours required to vote.<br/>
    to_suggest: Minimum age in hours required to suggest.<br/>
 - Usage: `[p]ideaset accountage <to_vote> <to_suggest>`
## [p]ideaset resetall
Reset all user stats<br/>
 - Usage: `[p]ideaset resetall`
## [p]ideaset upvoteemoji
Set the upvote emoji<br/>
 - Usage: `[p]ideaset upvoteemoji <emoji>`
 - Aliases: `upvote and up`
## [p]ideaset togglereveal
Toggle reveal suggestion author on approval<br/>

Approved suggestions are ALWAYS revealed regardless of this setting.<br/>
 - Usage: `[p]ideaset togglereveal`
 - Aliases: `reveal`
