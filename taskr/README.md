# Taskr

Schedule bot commands with ease

## [p]taskrset (Hybrid Command)

Configure Taskr settings<br/>

 - Usage: `[p]taskrset`
 - Slash Usage: `/taskrset`
 - Restricted to: `BOT_OWNER`

### [p]taskrset openai (Hybrid Command)

Set an openai key for the AI helper<br/>

 - Usage: `[p]taskrset openai`
 - Slash Usage: `/taskrset openai`

### [p]taskrset mininterval (Hybrid Command)

Set the minimum interval between tasks in seconds, default is 60 seconds.<br/>

Be careful with this setting, setting it too low can cause performance issues.<br/>

 - Usage: `[p]taskrset mininterval <interval>`
 - Slash Usage: `/taskrset mininterval <interval>`

### [p]taskrset premium (Hybrid Command)

Premium settings<br/>

 - Usage: `[p]taskrset premium`
 - Slash Usage: `/taskrset premium`

#### [p]taskrset premium view (Hybrid Command)

View premium settings<br/>

 - Usage: `[p]taskrset premium view`
 - Slash Usage: `/taskrset premium view`

#### [p]taskrset premium role (Hybrid Command)

Set the premium role for premium features<br/>

 - Usage: `[p]taskrset premium role <role>`
 - Slash Usage: `/taskrset premium role <role>`

#### [p]taskrset premium maxfree (Hybrid Command)

Set the maximum number of free tasks<br/>

 - Usage: `[p]taskrset premium maxfree <max_tasks>`
 - Slash Usage: `/taskrset premium maxfree <max_tasks>`

#### [p]taskrset premium mininterval (Hybrid Command)

Set the minimum interval between tasks for premium users<br/>

 - Usage: `[p]taskrset premium mininterval <interval>`
 - Slash Usage: `/taskrset premium mininterval <interval>`

#### [p]taskrset premium toggle (Hybrid Command)

Toggle premium system<br/>

 - Usage: `[p]taskrset premium toggle`
 - Slash Usage: `/taskrset premium toggle`

#### [p]taskrset premium mainserver (Hybrid Command)

Set the main server for premium features<br/>

 - Usage: `[p]taskrset premium mainserver <server_id>`
 - Slash Usage: `/taskrset premium mainserver <server_id>`

### [p]taskrset maxtasks (Hybrid Command)

Set the maximum number of tasks allowed per guild<br/>

 - Usage: `[p]taskrset maxtasks <max_tasks>`
 - Slash Usage: `/taskrset maxtasks <max_tasks>`

## [p]taskr (Hybrid Command)

Open the task menu<br/>

 - Usage: `[p]taskr [query]`
 - Slash Usage: `/taskr [query]`
 - Restricted to: `ADMIN`
 - Aliases: `tasker`
 - Checks: `guild_only`

## [p]tasktimezone (Hybrid Command)

Set the timezone used for scheduled tasks in this server<br/>

 - Usage: `[p]tasktimezone <timezone>`
 - Slash Usage: `/tasktimezone <timezone>`

## [p]aitask (Hybrid Command)

Create a scheduled task using AI<br/>

Example requests:<br/>
- Please run the ping command every second friday at 3pm starting in January<br/>
- Please run the ping command every odd hour at the 30 minute mark from 5am to 8pm<br/>
- Please run the ping command on the 15th of each month at 3pm<br/>

 - Usage: `[p]aitask <request>`
 - Slash Usage: `/aitask <request>`
 - Restricted to: `ADMIN`
 - Checks: `guild_only`

