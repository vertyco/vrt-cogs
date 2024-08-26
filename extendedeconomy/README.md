# ExtendedEconomy Help

Set prices for commands, customize how prices are applied, log bank events and more!

# .bankpie
View a pie chart of the top X bank balances.<br/>
 - Usage: `.bankpie [amount=10]`
# .extendedeconomy
Extended Economy settings<br/>

**NOTE**<br/>
Although setting prices for pure slash commands works, there is no refund mechanism in place for them.<br/>

Should a hybrid or text command fail due to an unhandled exception, the user will be refunded.<br/>
 - Usage: `.extendedeconomy`
 - Restricted to: `ADMIN`
 - Aliases: `ecoset and exteco`
 - Checks: `server_only`
## .extendedeconomy rolebonus
Add/Remove Payday role bonuses<br/>

Example: `.ecoset rolebonus @role 0.1` - Adds a 10% bonus to the user's payday if they have the role.<br/>

To remove a bonus, set the bonus to 0.<br/>
 - Usage: `.extendedeconomy rolebonus <role> <bonus>`
## .extendedeconomy autoclaimchannel
Set the auto claim channel<br/>
 - Usage: `.extendedeconomy autoclaimchannel [channel]`
## .extendedeconomy transfertax
Set the transfer tax percentage as a decimal<br/>

*Example: `0.05` is for 5% tax*<br/>

- Set to 0 to disable<br/>
- Default is 0<br/>
 - Usage: `.extendedeconomy transfertax <tax>`
## .extendedeconomy eventlog
Set an event log channel<br/>

**Events:**<br/>
- set_balance<br/>
- transfer_credits<br/>
- bank_wipe<br/>
- prune<br/>
- set_global<br/>
- payday_claim<br/>
 - Usage: `.extendedeconomy eventlog <event> [channel=None]`
## .extendedeconomy autopayday
Toggle whether paydays are claimed automatically (Global bank)<br/>
 - Usage: `.extendedeconomy autopayday`
 - Restricted to: `BOT_OWNER`
## .extendedeconomy deleteafter
Set the delete after time for cost check messages<br/>

- Set to 0 to disable (Recommended for public bots)<br/>
- Default is 0 (disabled)<br/>
 - Usage: `.extendedeconomy deleteafter <seconds>`
 - Restricted to: `BOT_OWNER`
## .extendedeconomy mainlog
Set the main log channel<br/>
 - Usage: `.extendedeconomy mainlog [channel=None]`
## .extendedeconomy resetcooldown
Reset the payday cooldown for a user<br/>
 - Usage: `.extendedeconomy resetcooldown <member>`
## .extendedeconomy view
View the current settings<br/>
 - Usage: `.extendedeconomy view`
## .extendedeconomy stackpaydays
Toggle whether payday roles stack or not<br/>
 - Usage: `.extendedeconomy stackpaydays`
 - Aliases: `stackpayday`
## .extendedeconomy autopaydayrole
Add/Remove auto payday roles<br/>
 - Usage: `.extendedeconomy autopaydayrole <role>`
# .addcost
Add a cost to a command<br/>
 - Usage: `.addcost [command=] [cost=0] [duration=3600] [level=all] [prompt=notify] [modifier=static] [value=0.0]`
 - Restricted to: `ADMIN`
 - Checks: `server_only`
# .banksetrole
Set the balance of all user accounts that have a specific role<br/>

Putting + or - signs before the amount will add/remove currency on the user's bank account instead.<br/>

Examples:<br/>
- `.banksetrole @everyone 420` - Sets everyones balance to 420<br/>
- `.banksetrole @role +69` - Increases balance by 69 for everyone with the role<br/>
- `.banksetrole @role -42` - Decreases balance by 42 for everyone with the role<br/>

**Arguments**<br/>

- `<role>` The role to set the currency of for each user that has it.<br/>
- `<creds>` The amount of currency to set their balance to.<br/>
 - Usage: `.banksetrole <role> <creds>`
 - Restricted to: `ADMIN`
 - Checks: `is_owner_if_bank_global`
