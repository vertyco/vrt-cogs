# Miner

Pickaxe in hand, fortune awaits

## [p]miner (Hybrid Command)

User commands<br/>

 - Usage: `[p]miner`
 - Slash Usage: `/miner`

### [p]miner notify (Hybrid Command)

Toggle rock spawn notifications.<br/>

 - Usage: `[p]miner notify [enable=None]`
 - Slash Usage: `/miner notify [enable=None]`
 - Checks: `ensure_db_connection`

### [p]miner transfer (Hybrid Command)

Transfer resources to another miner.<br/>

 - Usage: `[p]miner transfer <user> <resource> <amount>`
 - Slash Usage: `/miner transfer <user> <resource> <amount>`
 - Checks: `ensure_db_connection`

### [p]miner inventory (Hybrid Command)

View your stats.<br/>

 - Usage: `[p]miner inventory [user=None]`
 - Slash Usage: `/miner inventory [user=None]`
 - Aliases: `inv`
 - Checks: `ensure_db_connection`

### [p]miner guide (Hybrid Command)

Send an in-game guide covering the core loop, spawns, overswing, and repairs.<br/>

 - Usage: `[p]miner guide`
 - Slash Usage: `/miner guide`
 - Checks: `ensure_db_connection`

### [p]miner trade (Hybrid Command)

Trade resources with another miner.<br/>

 - Usage: `[p]miner trade <user>`
 - Slash Usage: `/miner trade <user>`
 - Checks: `ensure_db_connection`

### [p]miner leaderboard (Hybrid Command)

View the leaderboard.<br/>

 - Usage: `[p]miner leaderboard [local=True]`
 - Slash Usage: `/miner leaderboard [local=True]`
 - Aliases: `lb`
 - Checks: `ensure_db_connection`

### [p]miner status (Hybrid Command)

Show an approximate rock spawn chance for this server.<br/>

This reports a bucketed spawn chance (Low / Medium / High) based on<br/>
recent activity and time since the last rock, without exposing exact<br/>
internal percentages.<br/>

 - Usage: `[p]miner status`
 - Slash Usage: `/miner status`
 - Checks: `ensure_db_connection`

### [p]miner upgrade (Hybrid Command)

Upgrade your mining tool if you have enough resources (with confirmation).<br/>

 - Usage: `[p]miner upgrade`
 - Slash Usage: `/miner upgrade`
 - Checks: `ensure_db_connection`

### [p]miner convert (Hybrid Command)

Convert resources to economy credits (if enabled).<br/>

**Arguments:**<br/>
`resource`: The type of resource to convert (stone, iron, gems).<br/>
`amount`: The amount of the resource to convert.<br/>

 - Usage: `[p]miner convert <resource> <amount>`
 - Slash Usage: `/miner convert <resource> <amount>`
 - Checks: `ensure_db_connection`

### [p]miner repair (Hybrid Command)

Repair your pickaxe.<br/>

 - Usage: `[p]miner repair [confirm=False]`
 - Slash Usage: `/miner repair [confirm=False]`
 - Checks: `ensure_db_connection`

## [p]minerlb (Hybrid Command)

View the leaderboard.<br/>

 - Usage: `[p]minerlb [local=True]`
 - Slash Usage: `/minerlb [local=True]`
 - Checks: `ensure_db_connection`

## [p]minerdb

Database Commands<br/>

 - Usage: `[p]minerdb`
 - Restricted to: `BOT_OWNER`

### [p]minerdb postgres

Set the Postgres connection info<br/>

 - Usage: `[p]minerdb postgres`

### [p]minerdb nukedb

Delete the database for this cog and reinitialize it<br/>

THIS CANNOT BE UNDONE!<br/>

 - Usage: `[p]minerdb nukedb <confirm>`
 - Checks: `ensure_db_connection`

### [p]minerdb diagnose

Check the database connection<br/>

 - Usage: `[p]minerdb diagnose`

## [p]minerset

Admin commands<br/>

 - Usage: `[p]minerset`
 - Restricted to: `ADMIN`

### [p]minerset toggle

Toggle active mining channels<br/>

 - Usage: `[p]minerset toggle <channel>`
 - Checks: `ensure_db_connection`

### [p]minerset spawn

Spawn a new mining rock in the specified channel.<br/>

 - Usage: `[p]minerset spawn <channel> <rock_type>`
 - Restricted to: `BOT_OWNER`
 - Checks: `ensure_db_connection`

### [p]minerset activitytracking

Toggle per-channel or per-guild activity tracking.<br/>

`Per Channel` mode tracks activity in each channel separately, and rocks can spawn in any active channel.<br/>
`Per Guild` mode tracks activity across the entire guild, and rocks will spawn in random active channels.<br/>

 - Usage: `[p]minerset activitytracking`
 - Checks: `ensure_db_connection`

### [p]minerset spawntiming

Set the global minimum and maximum time between rock spawns in seconds.<br/>

Example: `[p]minerset spawntiming 30 600`<br/>

 - Usage: `[p]minerset spawntiming <min_seconds> <max_seconds>`
 - Restricted to: `BOT_OWNER`
 - Checks: `ensure_db_connection`

### [p]minerset spawnprobability

View the current rock spawn probability for a channel.<br/>

 - Usage: `[p]minerset spawnprobability <channel>`
 - Aliases: `prob`
 - Checks: `ensure_db_connection`

### [p]minerset convertratio

Set the conversion ratio for a resource.<br/>

**Examples:**<br/>
- `[p]minerset convertratio stone 20` (20 stone = 1 credit)<br/>
- `[p]minerset convertratio iron 5` (5 iron = 1 credit)<br/>
- `[p]minerset convertratio gems 0.1` (1 gem = 10 credits)<br/>

 - Usage: `[p]minerset convertratio <resource> <ratio>`
 - Checks: `ensure_db_connection`

### [p]minerset view

View active mining channels<br/>

 - Usage: `[p]minerset view`
 - Checks: `ensure_db_connection`

### [p]minerset toggleconvert

Toggle resource conversion on/off.<br/>

 - Usage: `[p]minerset toggleconvert`
 - Checks: `ensure_db_connection`

