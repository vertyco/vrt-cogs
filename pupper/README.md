# Pupper

Pet the doggo!

## [p]pets

Manage your pet.<br/>

 - Usage: `[p]pets`
 - Restricted to: `MOD`
 - Aliases: `pupper`
 - Checks: `guild_only`

### [p]pets delete

Set how long to wait before deleting the thanks message.<br/>
To leave the thanks message with no deletion, use 0 as the amount.<br/>
10 is the default.<br/>
Max is 5 minutes (300).<br/>

 - Usage: `[p]pets delete [amount=0]`

### [p]pets toggle

Toggle pets on the server.<br/>

 - Usage: `[p]pets toggle`

### [p]pets channel

Channel management for pet appearance.<br/>

 - Usage: `[p]pets channel`
 - Restricted to: `MOD`
 - Checks: `guild_only`

#### [p]pets channel removeall

Remove all petting channels from the list.<br/>

 - Usage: `[p]pets channel removeall`

#### [p]pets channel add

Add a text channel for pets.<br/>

 - Usage: `[p]pets channel add <channel>`

#### [p]pets channel addall

Add all valid channels for the guild that the bot can speak in.<br/>

 - Usage: `[p]pets channel addall`

#### [p]pets channel remove

Remove a text channel from petting.<br/>

 - Usage: `[p]pets channel remove <channel>`

### [p]pets credits

Set the pet credits range on successful petting.<br/>

 - Usage: `[p]pets credits <min_amt> <max_amt>`

### [p]pets cooldown

Set the pet appearance cooldown in seconds.<br/>

300s/5 minute minimum. Default is 3600s/1 hour.<br/>

 - Usage: `[p]pets cooldown [seconds=None]`

### [p]pets thanks

Set the pet thanks message.<br/>

 - Usage: `[p]pets thanks [message]`

### [p]pets hello

Set the pet greeting message.<br/>

 - Usage: `[p]pets hello [message]`

## [p]pettop

View the petting leaderboard.<br/>

Use `[p]pettop true` to see the global leaderboard across all servers.<br/>

 - Usage: `[p]pettop [globally=False]`
 - Aliases: `petlb and petleaderboard`
 - Checks: `guild_only`

