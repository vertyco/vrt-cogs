Simple referral system for Discord servers.

# /referredby (Slash Command)
Claim a referral<br/>
 - Usage: `/referredby <referred_by>`
 - `referred_by:` (Required) The user who referred you

 - Checks: `Server Only`
# [p]referredby
Claim a referral<br/>

Claim a referral from a user who referred you<br/>

If referral rewards are enabled, you will receive the reward for being referred.<br/>
If referrer rewards are enabled, the person who referred you will also receive a reward.<br/>
 - Usage: `[p]referredby <referred_by>`
 - Checks: `ensure_db_connection and server_only`
# [p]myreferrals (Hybrid Command)
Check your referrals<br/>
 - Usage: `[p]myreferrals`
 - Slash Usage: `/myreferrals`
 - Checks: `ensure_db_connection and server_only`
# [p]whoreferred (Hybrid Command)
Check if a specific user has been referred<br/>
 - Usage: `[p]whoreferred <user>`
 - Slash Usage: `/whoreferred <user>`
 - Checks: `ensure_db_connection and server_only`
# [p]referset
Settings for the referral system<br/>
 - Usage: `[p]referset`
 - Restricted to: `ADMIN`
 - Aliases: `refset and referralset`
 - Checks: `server_only`
## [p]referset channel
Set the channel where referral events will be sent<br/>
 - Usage: `[p]referset channel [channel=None]`
 - Checks: `ensure_db_connection`
## [p]referset reward
Set the reward for referring or being referred<br/>

**Arguments:**<br/>
- `reward_type` - Either `referral` or `referred`<br/>
  - `referral` - The reward for referring someone<br/>
  - `referred` - The reward for being referred<br/>
- `amount` - The amount of currency to reward<br/>

*Set to 0 to disable the reward*<br/>
 - Usage: `[p]referset reward <reward_type> <amount>`
 - Checks: `ensure_db_connection`
## [p]referset timeout
Set the time frame for users to claim their reward after joining<br/>

- `timeout` - The time frame in the format of `30m`, `1h`, `2d12h`, etc.<br/>
 - Usage: `[p]referset timeout <timeout>`
 - Checks: `ensure_db_connection`
## [p]referset resetreferrals
Reset all referral records for the server<br/>

This keeps your settings but removes all referral history.<br/>
 - Usage: `[p]referset resetreferrals <confirm>`
 - Checks: `ensure_db_connection`
## [p]referset age
Set the minimum account age for referred users to be eligible for rewards<br/>

- `age` - The minimum account age in the format of `30m`, `1h`, `2d12h`, etc.<br/>
 - Usage: `[p]referset age <age>`
 - Checks: `ensure_db_connection`
## [p]referset view
View the current settings for the server<br/>
 - Usage: `[p]referset view`
 - Checks: `ensure_db_connection`
## [p]referset resetinitialized
Reset the list of initialized users for the server<br/>

This clears the record of which users have been initialized, allowing them<br/>
to potentially claim referrals.<br/>
 - Usage: `[p]referset resetinitialized <confirm>`
 - Checks: `ensure_db_connection`
## [p]referset toggle
Toggle the referral system on or off<br/>
 - Usage: `[p]referset toggle`
 - Checks: `ensure_db_connection`
## [p]referset resetall
Reset all referral data and settings for the server<br/>

This deletes all referrals and settings, completely starting fresh.<br/>
 - Usage: `[p]referset resetall <confirm>`
 - Checks: `ensure_db_connection`
## [p]referset resetsettings
Reset all referral settings for the server<br/>

This keeps your referral history but resets all configuration settings.<br/>
 - Usage: `[p]referset resetsettings <confirm>`
 - Checks: `ensure_db_connection`
## [p]referset listreferrals
List all referrals made in the server<br/>
 - Usage: `[p]referset listreferrals`
 - Checks: `ensure_db_connection`
## [p]referset init
Initialize all unreferred users in the server so they cannot retroactively claim rewards<br/>
 - Usage: `[p]referset init`
 - Aliases: `initialize`
 - Checks: `ensure_db_connection`
