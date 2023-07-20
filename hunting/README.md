# Hunting Help

Hunting, it hunts birds and things that fly.

# hunting
 - Usage: `[p]hunting `
 - Checks: `server_only`

Hunting, it hunts birds and things that fly.

## hunting stop
 - Usage: `[p]hunting stop [channel=None] `
 - Restricted to: `MOD`

Stop the hunt.

## hunting clearleaderboard
 - Usage: `[p]hunting clearleaderboard `
 - Restricted to: `BOT_OWNER`

Clear all the scores from the leaderboard.

## hunting timing
 - Usage: `[p]hunting timing <interval_min> <interval_max> <bang_timeout> `
 - Restricted to: `MOD`

Change the hunting timing.<br/><br/>`interval_min` = Minimum time in seconds for a new bird. (60 min)<br/>`interval_max` = Maximum time in seconds for a new bird. (120 min)<br/>`bang_timeout` = Time in seconds for users to shoot a bird before it flies away. (10s min)

## hunting version
 - Usage: `[p]hunting version `

Show the cog version.

## hunting bangtime
 - Usage: `[p]hunting bangtime `
 - Restricted to: `MOD`

Toggle displaying the bang response time from users.

## hunting eagle
 - Usage: `[p]hunting eagle `
 - Restricted to: `MOD`

Toggle whether shooting an eagle is bad.

## hunting next
 - Usage: `[p]hunting next `
 - Restricted to: `MOD`

When will the next occurrence happen?

## hunting leaderboard
 - Usage: `[p]hunting leaderboard [global_leaderboard=False] `

This will show the top 50 hunters for the server.<br/>Use True for the global_leaderboard variable to show the global leaderboard.

## hunting score
 - Usage: `[p]hunting score [member=None] `

This will show the score of a hunter.

## hunting start
 - Usage: `[p]hunting start [channel=None] `
 - Restricted to: `MOD`

Start the hunt.

## hunting reward
 - Usage: `[p]hunting reward [min_reward=None] [max_reward=None] `
 - Restricted to: `MOD`

Set a credit reward range for successfully shooting a bird<br/><br/>Leave the options blank to disable bang rewards

## hunting mode
 - Usage: `[p]hunting mode `
 - Restricted to: `MOD`

Toggle whether the bot listens for 'bang' or a reaction.

