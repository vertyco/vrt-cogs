# XTools Help

Cool Tools for Xbox

# apiset
 - Usage: `[p]apiset `
 - Restricted to: `BOT_OWNER`

Set up the XTools cog

## apiset tokens
 - Usage: `[p]apiset tokens <client_id> <client_secret> `

Set Client ID and Secret

Extended Arg Info
> ### client_id
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
> ### client_secret
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
## apiset auth
 - Usage: `[p]apiset auth `



## apiset help
 - Usage: `[p]apiset help `

Tutorial for getting your ClientID and Secret

## apiset reset
 - Usage: `[p]apiset reset `

Reset the all token data

# xstatuschannel
 - Usage: `[p]xstatuschannel <channel> `
 - Restricted to: `ADMIN`

Set the channel for Microsoft status alerts<br/><br/>Any time microsoft services go down an alert will go out in the channel and be updated

Extended Arg Info
> ### channel: Optional[discord.channel.TextChannel]
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name
> 
>     
# setgt
 - Usage: `[p]setgt <gamertag> `

Set your Gamertag to use commands without entering it

Extended Arg Info
> ### gamertag
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xuid
 - Usage: `[p]xuid [gamertag] `

Get a player's XUID

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# gamertag
 - Usage: `[p]gamertag <xuid> `

Get the Gamertag associated with an XUID

Extended Arg Info
> ### xuid
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xprofile
 - Usage: `[p]xprofile [gamertag] `

View your Xbox profile

Extended Arg Info
> ### gamertag: str = None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xscreenshots
 - Usage: `[p]xscreenshots [gamertag] `

View your Screenshots

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xgames
 - Usage: `[p]xgames [gamertag] `

View your games and achievements

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xfriends
 - Usage: `[p]xfriends [gamertag] `

View your friends list

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xclips
 - Usage: `[p]xclips [gamertag] `

View your game clips

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
# xstatus
 - Usage: `[p]xstatus `

Check Microsoft Services Status

# gameswithgold
 - Usage: `[p]gameswithgold `

View this month's free games with Gold

# xmostplayed
 - Usage: `[p]xmostplayed [gamertag] `

View your most played games

Extended Arg Info
> ### gamertag=None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
