# Pupper Help

Pet the doggo!

# .pets
Manage your pet.<br/>
 - Usage: `.pets`
 - Restricted to: `MOD`
 - Aliases: `pupper`
 - Checks: `server_only`
## .pets credits
Set the pet credits range on successful petting.<br/>
 - Usage: `.pets credits <min_amt> <max_amt>`
## .pets cooldown
Set the pet appearance cooldown in seconds.<br/>

300s/5 minute minimum. Default is 3600s/1 hour.<br/>
 - Usage: `.pets cooldown [seconds=None]`
## .pets channel
Channel management for pet appearance.<br/>
 - Usage: `.pets channel`
 - Restricted to: `MOD`
 - Checks: `server_only`
### .pets channel addall
Add all valid channels for the server that the bot can speak in.<br/>
 - Usage: `.pets channel addall`
### .pets channel removeall
Remove all petting channels from the list.<br/>
 - Usage: `.pets channel removeall`
### .pets channel add
Add a text channel for pets.<br/>
 - Usage: `.pets channel add <channel>`
### .pets channel remove
Remove a text channel from petting.<br/>
 - Usage: `.pets channel remove <channel>`
## .pets toggle
Toggle pets on the server.<br/>
 - Usage: `.pets toggle`
## .pets delete
Set how long to wait before deleting the thanks message.<br/>
To leave the thanks message with no deletion, use 0 as the amount.<br/>
10 is the default.<br/>
Max is 5 minutes (300).<br/>
 - Usage: `.pets delete [amount=0]`
## .pets thanks
Set the pet thanks message.<br/>
 - Usage: `.pets thanks [message]`
## .pets hello
Set the pet greeting message.<br/>
 - Usage: `.pets hello [message]`
