# Fluent Help

Seamless translation between two languages in one channel.

# fluent
 - Usage: `[p]fluent `
 - Restricted to: `MOD`

Base command

## fluent remove
 - Usage: `[p]fluent remove <channel> `
 - Aliases: `delete, del, and rem`

Remove a channel from Fluent

Extended Arg Info
> ### channel: Optional[discord.channel.TextChannel]
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name
> 
>     
## fluent view
 - Usage: `[p]fluent view `

View all fluent channels

## fluent add
 - Usage: `[p]fluent add <language1> <language2> <channel> `

Add a channel and languages to translate between<br/><br/>Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be<br/>in english, then make english language 2 to use less api calls.

Extended Arg Info
> ### language1: str
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
> ### language2: str
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
> ### channel: Optional[discord.channel.TextChannel]
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name
> 
>     
