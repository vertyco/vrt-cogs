# UpgradeChat

Upgrade.Chat API integration for buying economy credits directly instead of roles<br/><br/>https://upgrade.chat/

## [p]upgradechat

Base command for cog settings<br/>

 - Usage: `[p]upgradechat`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `upchat`
 - Checks: `guild_only`

### [p]upgradechat ratio

Set the worth of 1 unit of real currency to economy credits<br/>

for example, if `credit_worth` is 100, then $1 = 100 Credits<br/>

 - Usage: `[p]upgradechat ratio <credit_worth>`

### [p]upgradechat view

View your current products<br/>

 - Usage: `[p]upgradechat view`

### [p]upgradechat purchases

View user purchase history<br/>

 - Usage: `[p]upgradechat purchases [member]`

### [p]upgradechat tokens

Set your Upgrade.Chat api tokens<br/>
By using this feature it is assumed that you are already familiar with Upgrade.Chat<br/>

1. Create your api keys here: https://upgrade.chat/developers<br/>

2. Copy your client ID and Client Secret<br/>

3. Run this command with your credentials<br/>

**Enjoy!**<br/>

 - Usage: `[p]upgradechat tokens <client_id> <client_secret>`

### [p]upgradechat logchannel

Set log channel for claims<br/>

 - Usage: `[p]upgradechat logchannel <channel>`

### [p]upgradechat delproduct

Delete an Upgrade.Chat product by UUID<br/>

 - Usage: `[p]upgradechat delproduct <uuid>`

### [p]upgradechat addproduct

Add an Upgrade.Chat product by UUID<br/>

This can be any type of product, either subscription or one-time purchase.<br/>
Users will be accredited based on `amount spend * conversion ratio`.<br/>
Transactions can only be claimed once.<br/>

 - Usage: `[p]upgradechat addproduct <uuid>`

### [p]upgradechat message

Set the message the bot sends when a user claims a purchase<br/>

Valid placeholders:<br/>
{mention} - mention the user<br/>
{username} - the users discord name<br/>
{displayname} - the users nickname(if they have one)<br/>
{uid} - the users Discord ID<br/>
{guild} - guild name<br/>
{creditsname} - name of the currency in your guild<br/>
{amount} - the amount of credits the user has claimed<br/>

set to `default` to use the default message<br/>

 - Usage: `[p]upgradechat message <claim_message>`

## [p]claim

Claim your Upgrade.Chat purchases!<br/>

 - Usage: `[p]claim`
 - Cooldown: `1 per 60.0 seconds`
 - Checks: `guild_only`

