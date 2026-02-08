# CowClicker

Click the cow!<br/><br/><br/>A DEMO cog for integrating the Piccolo ORM library with Red.<br/>Based on the [Cow Clicker](https://en.wikipedia.org/wiki/Cow_Clicker) game by Ian Bogost.

## [p]click (Hybrid Command)

Click the button!<br/>

 - Usage: `[p]click`
 - Slash Usage: `/click`
 - Cooldown: `1 per 15.0 seconds`
 - Checks: `ensure_db_connection`

## [p]clicks

Show the number of clicks you have<br/>

 - Usage: `[p]clicks [member=None] [delta=None]`
 - Checks: `ensure_db_connection`

## [p]topclickers

Show the top clickers<br/>

**Arguments:**<br/>
- `show_global`: Show global top clickers instead of server top clickers.<br/>
- `delta`: Show top clickers within a time delta. (e.g. 1d, 1h, 1m)<br/>

 - Usage: `[p]topclickers [show_global=True] [delta=None]`
 - Aliases: `clicklb`
 - Checks: `ensure_db_connection`

## [p]clickerset

Cow Clicker settings<br/>

**Base Commands**<br/>
- `[p]click` - Start a Cow Clicker session<br/>
- `[p]clicks [@user=Yourself]` - Show the number of clicks you have, or another user if specified<br/>
- `[p]topclickers [show_global=False]` - Show the top clickers, optionally show global top clickers<br/>

Use `[p]help CowClicker` to view the cog help and version (Case sensitive)<br/>

 - Usage: `[p]clickerset`
 - Restricted to: `BOT_OWNER`
 - Aliases: `cowclicker`

### [p]clickerset postgres

Set the Postgres connection info<br/>

 - Usage: `[p]clickerset postgres`

### [p]clickerset diagnose

Check the database connection<br/>

 - Usage: `[p]clickerset diagnose`

### [p]clickerset nukedb

Delete the database for this cog and reinitialize it<br/>

THIS CANNOT BE UNDONE!<br/>

 - Usage: `[p]clickerset nukedb <confirm>`

