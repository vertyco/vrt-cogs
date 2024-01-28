# IdeaBoard Help

Share Ideas and Suggestions

# idea (Hybrid Command)
 - Usage: `[p]idea <content>`
 - Slash Usage: `/idea <content>`
 - Aliases: `suggest`
 - Checks: `server_only`

Share an idea/make a suggestion.

# ideastats (Hybrid Command)
 - Usage: `[p]ideastats [member]`
 - Slash Usage: `/ideastats [member]`
 - Checks: `server_only`

Display your current profile stats for suggestions and votes.

# ideaset
 - Usage: `[p]ideaset`
 - Restricted to: `ADMIN`
 - Aliases: `ideaboard`

Manage IdeaBoard settings

## ideaset roleblacklist
 - Usage: `[p]ideaset roleblacklist <role>`
 - Aliases: `blacklistrole and rolebl`

Add/remove a role to/from the role blacklist

## ideaset cooldown
 - Usage: `[p]ideaset cooldown <cooldown>`
 - Aliases: `cd`

Set the base cooldown for making suggestions

## ideaset userblacklist
 - Usage: `[p]ideaset userblacklist <member>`
 - Aliases: `blacklistuser and userbl`

Add/remove a user to/from the user blacklist

## ideaset downvoteemoji
 - Usage: `[p]ideaset downvoteemoji <emoji>`
 - Aliases: `downvote and down`

Set the downvote emoji

## ideaset minlevel
 - Usage: `[p]ideaset minlevel <to_vote> <to_suggest>`

Set the LevelUp integration minimum level required to vote and suggest.<br/><br/>Args:<br/>    to_vote: Minimum level required to vote.<br/>    to_suggest: Minimum level required to suggest.

## ideaset toggleanonymous
 - Usage: `[p]ideaset toggleanonymous`
 - Aliases: `toggleanon, anonymous, and anon`

Toggle allowing anonymous suggestions

## ideaset approverole
 - Usage: `[p]ideaset approverole <role>`

Add/remove a role to the approver role list

## ideaset channel
 - Usage: `[p]ideaset channel <channel> <channel_type>`

Set the approved, rejected, or pending channels for IdeaBoard

## ideaset upvoteemoji
 - Usage: `[p]ideaset upvoteemoji <emoji>`
 - Aliases: `upvote and up`

Set the upvote emoji

## ideaset voterole
 - Usage: `[p]ideaset voterole <role>`

Add/remove a role to the voting role whitelist

## ideaset suggestrole
 - Usage: `[p]ideaset suggestrole <role>`

Add/remove a role to the suggest role whitelist

## ideaset minplaytime
 - Usage: `[p]ideaset minplaytime <to_vote> <to_suggest>`

Set the ArkTools integration minimum playtime required to vote and suggest.<br/><br/>Args:<br/>    to_vote: Minimum playtime in hours required to vote.<br/>    to_suggest: Minimum playtime in hours required to suggest.

## ideaset view
 - Usage: `[p]ideaset view`

View IdeaBoard settings

## ideaset rolecooldown
 - Usage: `[p]ideaset rolecooldown <role> <cooldown>`
 - Aliases: `rolecd`

Set the suggestion cooldown for a specific role<br/><br/>To remove a role cooldown, specify 0 as the cooldown.

## ideaset accountage
 - Usage: `[p]ideaset accountage <to_vote> <to_suggest>`

Set the minimum account age required to vote and suggest.<br/><br/>Args:<br/>    to_vote: Minimum age in hours required to vote.<br/>    to_suggest: Minimum age in hours required to suggest.

## ideaset jointime
 - Usage: `[p]ideaset jointime <to_vote> <to_suggest>`

Set the minimum time a user must be in the server to vote and suggest.<br/><br/>Args:<br/>    to_vote: Minimum time in hours required to vote.<br/>    to_suggest: Minimum time in hours required to suggest.

## ideaset togglereveal
 - Usage: `[p]ideaset togglereveal`
 - Aliases: `reveal`

Toggle reveal suggestion author on approval

## ideaset toggledm
 - Usage: `[p]ideaset toggledm`
 - Aliases: `dm`

Toggle DMing users the results of suggestions they made

# approve (Hybrid Command)
 - Usage: `[p]approve <number> [reason]`
 - Slash Usage: `/approve <number> [reason]`
 - Checks: `server_only`

Approve an idea/suggestion.

# reject (Hybrid Command)
 - Usage: `[p]reject <number> [reason]`
 - Slash Usage: `/reject <number> [reason]`
 - Checks: `server_only`

Reject an idea/suggestion.

# viewvotes (Hybrid Command)
 - Usage: `[p]viewvotes <number>`
 - Slash Usage: `/viewvotes <number>`
 - Checks: `server_only`

View the list of who has upvoted and who has downvoted a suggestion.

