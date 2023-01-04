# UpgradeChat Help

Upgrade.Chat API integration for buying economy credits directly instead of roles

https://upgrade.chat/

# upgradechat
 - Usage: `[p]upgradechat`
 - Aliases: `upchat`


Base command for cog settings

## upgradechat logchannel
 - Usage: `[p]upgradechat logchannel <channel>`

Set log channel for claims

## upgradechat delproduct
 - Usage: `[p]upgradechat delproduct <uuid>`

Delete an Upgrade.Chat product by UUID

## upgradechat addproduct
 - Usage: `[p]upgradechat addproduct <uuid>`

Add an Upgrade.Chat product by UUID

This can be any type of product, either subscription or one-time purchase.
Users will be accredited based on `amount spend * conversion ratio`.
Transactions can only be claimed once.

## upgradechat message
 - Usage: `[p]upgradechat message <claim_message>`

Set the message the bot sends when a user claims a purchase

Valid placeholders:
{mention} - mention the user
{username} - the users discord name
{displayname} - the users nickname(if they have one)
{uid} - the users Discord ID
{guild} - guild name
{creditsname} - name of the currency in your guild
{amount} - the amount of credits the user has claimed

set to `default` to use the default message

## upgradechat view
 - Usage: `[p]upgradechat view`

View your current products

## upgradechat ratio
 - Usage: `[p]upgradechat ratio <credit_worth>`

Set the worth of 1 unit of real currency to economy credits

for example, if `credit_worth` is 100, then $1 = 100 Credits

## upgradechat tokens
 - Usage: `[p]upgradechat tokens <client_id> <client_secret>`

Set your Upgrade.Chat api tokens
By using this feature it is assumed that you are already familiar with Upgrade.Chat

1. Create your api keys here: https://upgrade.chat/developers

2. Copy your client ID and Client Secret

3. Run this command with your credentials

**Enjoy!**

# claim
 - Usage: `[p]claim`

Claim your Upgrade.Chat purchases!
