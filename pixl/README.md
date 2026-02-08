# Pixl

Guess pictures for points<br/><br/>Pixl is an image guessing game that reveals parts of an image over time while users race to guess the correct answer first.<br/><br/>**Images are split up into 192 blocks and slowly revealed over time.**<br/>The score of the game is based on how many blocks are left when the image is guessed.

## [p]pixlboard

View the Pixl leaderboard!<br/>

**Arguments**<br/>
`show_global`: show the global leaderboard<br/>

example: `[p]pixlb true`<br/>

 - Usage: `[p]pixlboard <show_global>`
 - Aliases: `pixlb, pixelb, pixlelb, and pixleaderboard`
 - Checks: `guild_only`

## [p]pixl

Start a Pixl game!<br/>
Guess the image as it is slowly revealed<br/>

 - Usage: `[p]pixl`
 - Aliases: `pixle, pixlguess, pixelguess, and pixleguess`
 - Checks: `guild_only`

## [p]pixlset

Configure the Pixl game<br/>

 - Usage: `[p]pixlset`
 - Aliases: `pixelset and pixleset`
 - Checks: `guild_only`

### [p]pixlset participants

Set the minimum amount of participants for the game to reward users credits<br/>

 - Usage: `[p]pixlset participants <amount>`

### [p]pixlset ratio

Set the point to credit conversion ratio (points x ratio = credit reward)<br/>
Points are calculated based on how many hidden blocks are left at the end of the game<br/>

Ratio can be a decimal<br/>
Set to 0 to disable credit rewards<br/>

 - Usage: `[p]pixlset ratio <ratio>`

### [p]pixlset blocks

Set the amount of blocks to reveal after each delay<br/>

 - Usage: `[p]pixlset blocks <amount>`

### [p]pixlset timelimit

Set the time limit for Pixl games<br/>

 - Usage: `[p]pixlset timelimit <seconds>`

### [p]pixlset fuzzy

Set the fuzzy matching threshold for answer checking (0.0 to 1.0)<br/>

A lower value means more lenient matching (more answers accepted)<br/>
A higher value requires more accurate spelling<br/>

Examples:<br/>
- 0.92 (default) accepts answers that are 92% similar<br/>
- 0.7 would accept answers that are roughly 70% similar<br/>
- 1.0 would require exact matching<br/>
- 0 would disable fuzzy matching entirely<br/>

 - Usage: `[p]pixlset fuzzy <threshold>`

### [p]pixlset image

Add/Remove images<br/>

 - Usage: `[p]pixlset image`

#### [p]pixlset image testguild

Test the guild images to ensure they are valid urls<br/>

 - Usage: `[p]pixlset image testguild`

#### [p]pixlset image view

View the guild images<br/>

 - Usage: `[p]pixlset image view`

#### [p]pixlset image testglobal

Test the global images to ensure they are valid urls<br/>

 - Usage: `[p]pixlset image testglobal`
 - Restricted to: `BOT_OWNER`

#### [p]pixlset image addglobal

Add a global image for all guilds to use<br/>

**Arguments**<br/>
`url:     `the url of the image<br/>
`answers: `a list of possible answers separated by a comma<br/>

**Alternative**<br/>
If args are left blank, a text file can be uploaded with the following format for bulk image adding.<br/>
Each line starts with the url followed by all the possible correct answers separated by a comma<br/>

Example: `url, answer, answer, answer...`<br/>
```
https://some_url.com/example.png, answer1, answer two, another answer
https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
```

 - Usage: `[p]pixlset image addglobal <url> <answers>`
 - Restricted to: `BOT_OWNER`

#### [p]pixlset image viewdefault

View the default images<br/>

 - Usage: `[p]pixlset image viewdefault`

#### [p]pixlset image viewglobal

View the global images<br/>

 - Usage: `[p]pixlset image viewglobal`

#### [p]pixlset image add

Add an image for your guild to use<br/>

**Arguments**<br/>
`url:     `the url of the image<br/>
`answers: `a list of possible answers separated by a comma<br/>

**Alternative**<br/>
If args are left blank, a text file can be uploaded with the following format for bulk image adding.<br/>
Each line starts with the url followed by all the possible correct answers separated by a comma<br/>

Example: `url, answer, answer, answer...`<br/>
```
https://some_url.com/example.png, answer1, answer two, another answer
https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
```

 - Usage: `[p]pixlset image add <url> <answers>`

#### [p]pixlset image deleteall

Delete all custom images for this guild<br/>

This will remove all custom images that have been added to this guild.<br/>
Default and global images will remain available if enabled.<br/>

 - Usage: `[p]pixlset image deleteall <confirm>`

#### [p]pixlset image cleanup

Clean up invalid or dead image links<br/>

**Arguments**<br/>
`scope`: The scope to clean up - "guild", "global", or "all"<br/>

This command will test all images and remove any that are no longer accessible<br/>

 - Usage: `[p]pixlset image cleanup [scope=guild]`

### [p]pixlset delay

(Owner Only)Set the delay between block reveals<br/>

**Warning**<br/>
Setting this too low may hit rate limits, default is 5 seconds.<br/>

 - Usage: `[p]pixlset delay <seconds>`
 - Restricted to: `BOT_OWNER`

### [p]pixlset reset

Reset the Pixl scoreboard<br/>

**Arguments**<br/>
`user`: (Optional) A specific user to reset scores for. If not provided, resets scores for all users.<br/>

Examples:<br/>
- `[p]pixlset reset` - Resets scores for all users<br/>
- `[p]pixlset reset @user` - Resets scores for the specified user<br/>

 - Usage: `[p]pixlset reset [user=None]`
 - Restricted to: `ADMIN`
 - Checks: `guild_only`

### [p]pixlset usedefault

(Toggle) Whether to use the default hardcoded images in this guild<br/>

 - Usage: `[p]pixlset usedefault`

### [p]pixlset view

View the current settings<br/>

 - Usage: `[p]pixlset view`

### [p]pixlset showanswer

(Toggle) Showing the answer after a game over<br/>

 - Usage: `[p]pixlset showanswer`

### [p]pixlset useglobal

(Toggle) Whether to use global images in this guild<br/>

 - Usage: `[p]pixlset useglobal`

