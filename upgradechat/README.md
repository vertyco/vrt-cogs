# UpgradeChat Help

Upgrade.Chat API integration for buying economy credits directly instead of roles<br/><br/>https://upgrade.chat/

# upgradechat
 - Usage: `[p]upgradechat `
 - Restricted to: `GUILD_OWNER`
 - Aliases: `upchat`
 - Checks: `server_only`

Base command for cog settings

## upgradechat message
 - Usage: `[p]upgradechat message <claim_message> `

Set the message the bot sends when a user claims a purchase<br/><br/>Valid placeholders:<br/>{mention} - mention the user<br/>{username} - the users discord name<br/>{displayname} - the users nickname(if they have one)<br/>{uid} - the users Discord ID<br/>{server} - server name<br/>{creditsname} - name of the currency in your server<br/>{amount} - the amount of credits the user has claimed<br/><br/>set to `default` to use the default message

## upgradechat tokens
 - Usage: `[p]upgradechat tokens <client_id> <client_secret> `

Set your Upgrade.Chat api tokens<br/>By using this feature it is assumed that you are already familiar with Upgrade.Chat<br/><br/>1. Create your api keys here: https://upgrade.chat/developers<br/><br/>2. Copy your client ID and Client Secret<br/><br/>3. Run this command with your credentials<br/><br/>**Enjoy!**

## upgradechat ratio
 - Usage: `[p]upgradechat ratio <credit_worth> `

Set the worth of 1 unit of real currency to economy credits<br/><br/>for example, if `credit_worth` is 100, then $1 = 100 Credits

## upgradechat view
 - Usage: `[p]upgradechat view `

View your current products

## upgradechat purchases
 - Usage: `[p]upgradechat purchases `

View user purchase history

## upgradechat logchannel
 - Usage: `[p]upgradechat logchannel <channel> `

Set log channel for claims

## upgradechat delproduct
 - Usage: `[p]upgradechat delproduct <uuid> `

Delete an Upgrade.Chat product by UUID

## upgradechat addproduct
 - Usage: `[p]upgradechat addproduct <uuid> `

Add an Upgrade.Chat product by UUID<br/><br/>This can be any type of product, either subscription or one-time purchase.<br/>Users will be accredited based on `amount spend * conversion ratio`.<br/>Transactions can only be claimed once.

# claim
 - Usage: `[p]claim `
 - Cooldown: `1 per 60.0 seconds`
 - Checks: `server_only`

Claim your Upgrade.Chat purchases!

