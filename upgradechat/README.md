# UpgradeChat Help

Upgrade.Chat API integration for buying economy credits directly instead of roles<br/><br/>https://upgrade.chat/

# .upgradechat
Base command for cog settings<br/>
 - Usage: `.upgradechat`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `upchat`
 - Checks: `server_only`
## .upgradechat tokens
Set your Upgrade.Chat api tokens<br/>
By using this feature it is assumed that you are already familiar with Upgrade.Chat<br/>

1. Create your api keys here: https://upgrade.chat/developers<br/>

2. Copy your client ID and Client Secret<br/>

3. Run this command with your credentials<br/>

**Enjoy!**<br/>
 - Usage: `.upgradechat tokens <client_id> <client_secret>`
## .upgradechat ratio
Set the worth of 1 unit of real currency to economy credits<br/>

for example, if `credit_worth` is 100, then $1 = 100 Credits<br/>
 - Usage: `.upgradechat ratio <credit_worth>`
## .upgradechat purchases
View user purchase history<br/>
 - Usage: `.upgradechat purchases [member]`
## .upgradechat view
View your current products<br/>
 - Usage: `.upgradechat view`
## .upgradechat logchannel
Set log channel for claims<br/>
 - Usage: `.upgradechat logchannel <channel>`
## .upgradechat delproduct
Delete an Upgrade.Chat product by UUID<br/>
 - Usage: `.upgradechat delproduct <uuid>`
## .upgradechat addproduct
Add an Upgrade.Chat product by UUID<br/>

This can be any type of product, either subscription or one-time purchase.<br/>
Users will be accredited based on `amount spend * conversion ratio`.<br/>
Transactions can only be claimed once.<br/>
 - Usage: `.upgradechat addproduct <uuid>`
## .upgradechat message
Set the message the bot sends when a user claims a purchase<br/>

Valid placeholders:<br/>
{mention} - mention the user<br/>
{username} - the users discord name<br/>
{displayname} - the users nickname(if they have one)<br/>
{uid} - the users Discord ID<br/>
{server} - server name<br/>
{creditsname} - name of the currency in your server<br/>
{amount} - the amount of credits the user has claimed<br/>

set to `default` to use the default message<br/>
 - Usage: `.upgradechat message <claim_message>`
# .claim
Claim your Upgrade.Chat purchases!<br/>
 - Usage: `.claim`
 - Cooldown: `1 per 60.0 seconds`
 - Checks: `server_only`
