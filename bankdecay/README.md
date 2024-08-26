# BankDecay Help

Economy decay!<br/><br/>Periodically reduces users' red currency based on inactivity, encouraging engagement.<br/>Server admins can configure decay parameters, view settings, and manually trigger decay cycles.<br/>User activity is tracked via messages and reactions.

# .bankdecay
Setup economy credit decay for your server<br/>
 - Usage: `.bankdecay`
 - Restricted to: `ADMIN`
 - Aliases: `bdecay`
 - Checks: `server_only`
## .bankdecay setdays
Set the number of inactive days before decay starts.<br/>
 - Usage: `.bankdecay setdays <days>`
## .bankdecay resettotal
Reset the total amount decayed to zero.<br/>
 - Usage: `.bankdecay resettotal`
## .bankdecay getexpired
Get a list of users who are currently expired and how much they will lose if decayed<br/>
 - Usage: `.bankdecay getexpired`
## .bankdecay bulkaddpercent
Add a percentage to all member balances.<br/>

Accidentally decayed too many credits? Bulk add to every user's balance in the server based on a percentage of their current balance.<br/>
 - Usage: `.bankdecay bulkaddpercent <percent> <confirm>`
## .bankdecay view
View Bank Decay Settings<br/>
 - Usage: `.bankdecay view`
## .bankdecay seen
Check when a user was last active (if at all)<br/>
 - Usage: `.bankdecay seen <user>`
## .bankdecay bulkrempercent
Remove a percentage from all member balances.<br/>

Accidentally refunded too many credits with bulkaddpercent? Bulk remove from every user's balance in the server based on a percentage of their current balance.<br/>
 - Usage: `.bankdecay bulkrempercent <percent> <confirm>`
## .bankdecay toggle
Toggle the bank decay feature on or off.<br/>
 - Usage: `.bankdecay toggle`
## .bankdecay initialize
Initialize the server and add every member to the config.<br/>

**Arguments**<br/>
- as_expired: (t/f) if True, initialize users as already expired<br/>
 - Usage: `.bankdecay initialize <as_expired>`
## .bankdecay logchannel
Set the log channel, each time the decay cycle runs this will be updated<br/>
 - Usage: `.bankdecay logchannel <channel>`
## .bankdecay decaynow
Run a decay cycle on this server right now<br/>
 - Usage: `.bankdecay decaynow [force=False]`
## .bankdecay cleanup
Remove users from the config that are no longer in the server or have no balance<br/>
 - Usage: `.bankdecay cleanup <confirm>`
## .bankdecay setpercent
Set the percentage of decay that occurs after the inactive period.<br/>

**Example**<br/>
If decay is 5%, then after the set days of inactivity they will lose 5% of their balance every day.<br/>
 - Usage: `.bankdecay setpercent <percent>`
## .bankdecay ignorerole
Add/Remove a role from the ignore list<br/>

Users with an ignored role will not have their balance decay<br/>
 - Usage: `.bankdecay ignorerole <role>`
