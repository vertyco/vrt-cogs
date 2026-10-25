# GlassRelay

Sell your server's economy credits through GlassRelay.

## [p]claim

Claim the credits for your GlassRelay purchases<br/>

 - Usage: `[p]claim`
 - Cooldown: `1 per 60.0 seconds`
 - Checks: `guild_only`

## [p]glassrelay

GlassRelay settings<br/>

 - Usage: `[p]glassrelay`
 - Restricted to: `GUILD_OWNER`
 - Checks: `guild_only`

### [p]glassrelay ratio

Set how many credits 1 unit of your store's currency buys<br/>

For example, if `credit_worth` is 1000, then $1 = 1000 credits.<br/>

 - Usage: `[p]glassrelay ratio <credit_worth>`

### [p]glassrelay addproduct

Add a product from your GlassRelay store<br/>

Opens a menu of your store's products.<br/>
Buyers get `amount paid * ratio` credits for each payment on the product you pick.<br/>
Each payment is credited once.<br/>
Run `[p]glassrelay init` right after, so payments made before now aren't credited.<br/>

 - Usage: `[p]glassrelay addproduct`

### [p]glassrelay delproduct

Remove a product<br/>

Opens a menu of the products you added.<br/>
Removing one also deletes its payment records, so if you add it again, run `[p]glassrelay init` again too.<br/>

 - Usage: `[p]glassrelay delproduct`

### [p]glassrelay view

View the settings<br/>

 - Usage: `[p]glassrelay view`

### [p]glassrelay logchannel

Set the channel where credited payments are logged<br/>

Leave the channel out to turn logging off.<br/>

 - Usage: `[p]glassrelay logchannel [channel=None]`

### [p]glassrelay init

Mark a product's past payments as done, so they are never credited<br/>

Opens a menu of the products you added.<br/>
Run this right after adding a product. Payments made after this are credited as normal.<br/>
Each past payment still shows in purchase history under its buyer, worth `amount paid * ratio` at<br/>
today's ratio.<br/>

 - Usage: `[p]glassrelay init`
 - Aliases: `initialize`

### [p]glassrelay purchases

View purchase history, one buyer per page<br/>

Give a member or user id to open their page first.<br/>

 - Usage: `[p]glassrelay purchases [member]`

### [p]glassrelay message

Set the message the bot sends when a buyer gets their credits<br/>

Valid placeholders:<br/>
{mention} - mention the user<br/>
{username} - the user's Discord name<br/>
{displayname} - the user's nickname (if they have one)<br/>
{uid} - the user's Discord ID<br/>
{guild} - server name<br/>
{creditsname} - name of the currency in your server<br/>
{amount} - the amount of credits the user got<br/>

Set to `default` to use the default message.<br/>

 - Usage: `[p]glassrelay message <claim_message>`

### [p]glassrelay key

Connect your GlassRelay store with an API key<br/>

Opens a form to paste the key into, so the key never shows in the channel.<br/>

 - Usage: `[p]glassrelay key`

