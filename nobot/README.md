# NoBot Help

Filter messages from other bots<br/><br/>Some "Free" bots spam ads and links when using their commands, this cog fixes that.<br/>Add a bot to the watchlist and add phrases to look for and if that phrase is found in the other bot's<br/>message, this cog will delete them.

# nobot
 - Usage: `[p]nobot `
 - Restricted to: `ADMIN`

Main setup command for NoBot

## nobot addfilter
 - Usage: `[p]nobot addfilter <message> `

Add text context to match against the bot filter list, use phrases that match what the bot sends exactly

Extended Arg Info
> ### message
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
## nobot addbot
 - Usage: `[p]nobot addbot <bot> `

Add a bot to the filter list

Extended Arg Info
> ### bot: discord.member.Member
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name#discrim
>     4. Lookup by name
>     5. Lookup by nickname
> 
>     
## nobot view
 - Usage: `[p]nobot view `

View NoBot settings

## nobot delfilter
 - Usage: `[p]nobot delfilter `

Delete a filter

## nobot delbot
 - Usage: `[p]nobot delbot <bot> `

Remove a bot from the filter list<br/><br/>If bot is no longer in the server, use its ID

Extended Arg Info
> ### bot: Union[discord.member.Member, int]
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name#discrim
>     4. Lookup by name
>     5. Lookup by nickname
> 
>     
