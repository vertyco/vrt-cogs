Pickaxe in hand, fortune awaits

# [p]miner (Hybrid Command)
Miner commands for users.<br/>
 - Usage: `[p]miner`
 - Slash Usage: `/miner`
## [p]miner trade (Hybrid Command)
Trade resources with another miner.<br/>
 - Usage: `[p]miner trade <user>`
 - Slash Usage: `/miner trade <user>`
 - Checks: `ensure_db_connection`
## [p]miner repair (Hybrid Command)
Repair your pickaxe.<br/>
 - Usage: `[p]miner repair [confirm=False]`
 - Slash Usage: `/miner repair [confirm=False]`
 - Checks: `ensure_db_connection`
## [p]miner lb (Hybrid Command)
View the top players for a specific resource.<br/>
 - Usage: `[p]miner lb`
 - Slash Usage: `/miner lb`
 - Checks: `ensure_db_connection`
## [p]miner upgrade (Hybrid Command)
Upgrade your mining tool if you have enough resources (with confirmation).<br/>
 - Usage: `[p]miner upgrade`
 - Slash Usage: `/miner upgrade`
 - Checks: `ensure_db_connection`
## [p]miner inventory (Hybrid Command)
View your mining inventory and tool.<br/>
 - Usage: `[p]miner inventory [user=None]`
 - Slash Usage: `/miner inventory [user=None]`
 - Aliases: `inv`
 - Checks: `ensure_db_connection`
# [p]minerlb (Hybrid Command)
View the top players for a specific resource.<br/>
 - Usage: `[p]minerlb`
 - Slash Usage: `/minerlb`
 - Checks: `ensure_db_connection`
# [p]minerdb
Database Commands<br/>
 - Usage: `[p]minerdb`
 - Restricted to: `BOT_OWNER`
## [p]minerdb nukedb
Delete the database for this cog and reinitialize it<br/>

THIS CANNOT BE UNDONE!<br/>
 - Usage: `[p]minerdb nukedb <confirm>`
 - Checks: `ensure_db_connection`
## [p]minerdb postgres
Set the Postgres connection info<br/>
 - Usage: `[p]minerdb postgres`
## [p]minerdb diagnose
Check the database connection<br/>
 - Usage: `[p]minerdb diagnose`
# [p]minerset
Admin commands<br/>
 - Usage: `[p]minerset`
 - Restricted to: `ADMIN`
## [p]minerset spawn
Spawn a new mining rock in the specified channel.<br/>
 - Usage: `[p]minerset spawn <rock_type> <channel>`
 - Checks: `ensure_db_connection`
## [p]minerset toggle
Toggle active mining channels<br/>
 - Usage: `[p]minerset toggle <channel>`
 - Checks: `ensure_db_connection`
## [p]minerset view
View active mining channels<br/>
 - Usage: `[p]minerset view`
 - Checks: `ensure_db_connection`
