# Pupper Help

Pet the doggo!

# pets
 - Usage: `[p]pets `
 - Restricted to: `MOD`
 - Aliases: `pupper`
 - Checks: `server_only`

Manage your pet.

## pets channel
 - Usage: `[p]pets channel `
 - Restricted to: `MOD`
 - Checks: `server_only`

Channel management for pet appearance.

### pets channel addall
 - Usage: `[p]pets channel addall `

Add all valid channels for the server that the bot can speak in.

### pets channel removeall
 - Usage: `[p]pets channel removeall `

Remove all petting channels from the list.

### pets channel remove
 - Usage: `[p]pets channel remove <channel> `

Remove a text channel from petting.

Extended Arg Info
> ### channel: discord.channel.TextChannel
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name
> 
>     
### pets channel add
 - Usage: `[p]pets channel add <channel> `

Add a text channel for pets.

Extended Arg Info
> ### channel: discord.channel.TextChannel
> 
> 
>     1. Lookup by ID.
>     2. Lookup by mention.
>     3. Lookup by name
> 
>     
## pets toggle
 - Usage: `[p]pets toggle `

Toggle pets on the server.

## pets thanks
 - Usage: `[p]pets thanks [message] `

Set the pet thanks message.

Extended Arg Info
> ### message: str = None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
## pets delete
 - Usage: `[p]pets delete [amount=0] `

Set how long to wait before deleting the thanks message.<br/>To leave the thanks message with no deletion, use 0 as the amount.<br/>10 is the default.<br/>Max is 5 minutes (300).

Extended Arg Info
> ### amount: int = 0
> ```
> A number without decimal places.
> ```
## pets hello
 - Usage: `[p]pets hello [message] `

Set the pet greeting message.

Extended Arg Info
> ### message: str = None
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
## pets credits
 - Usage: `[p]pets credits <min_amt> <max_amt> `

Set the pet credits range on successful petting.

Extended Arg Info
> ### min_amt: int
> ```
> A number without decimal places.
> ```
> ### max_amt: int
> ```
> A number without decimal places.
> ```
## pets cooldown
 - Usage: `[p]pets cooldown [seconds=None] `

Set the pet appearance cooldown in seconds.<br/><br/>300s/5 minute minimum. Default is 3600s/1 hour.

Extended Arg Info
> ### seconds: int = None
> ```
> A number without decimal places.
> ```
