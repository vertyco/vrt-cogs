Guess pictures for points<br/><br/>Pixl is an image guessing game that reveals parts of an image over time while users race to guess the correct answer first.<br/><br/>**Images are split up into 192 blocks and slowly revealed over time.**<br/>The score of the game is based on how many blocks are left when the image is guessed.

# [p]pixlboard
View the Pixl leaderboard!<br/>

**Arguments**<br/>
`show_global`: show the global leaderboard<br/>

example: `[p]pixlb true`<br/>
 - Usage: `[p]pixlboard <show_global>`
 - Aliases: `pixlb, pixelb, pixlelb, and pixleaderboard`
 - Checks: `server_only`
# [p]pixl
Start a Pixl game!<br/>
Guess the image as it is slowly revealed<br/>
 - Usage: `[p]pixl`
 - Aliases: `pixle, pixlguess, pixelguess, and pixleguess`
 - Checks: `server_only`
# [p]pixlset
Configure the Pixl game<br/>
 - Usage: `[p]pixlset`
 - Aliases: `pixelset and pixleset`
 - Checks: `server_only`
## [p]pixlset delay
(Owner Only)Set the delay between block reveals<br/>

**Warning**<br/>
Setting this too low may hit rate limits, default is 5 seconds.<br/>
 - Usage: `[p]pixlset delay <seconds>`
 - Restricted to: `BOT_OWNER`
## [p]pixlset timelimit
Set the time limit for Pixl games<br/>
 - Usage: `[p]pixlset timelimit <seconds>`
## [p]pixlset usedefault
(Toggle) Whether to use the default hardcoded images in this server<br/>
 - Usage: `[p]pixlset usedefault`
## [p]pixlset showanswer
(Toggle) Showing the answer after a game over<br/>
 - Usage: `[p]pixlset showanswer`
## [p]pixlset useglobal
(Toggle) Whether to use global images in this server<br/>
 - Usage: `[p]pixlset useglobal`
## [p]pixlset view
View the current settings<br/>
 - Usage: `[p]pixlset view`
## [p]pixlset image
Add/Remove images<br/>
 - Usage: `[p]pixlset image`
### [p]pixlset image viewdefault
View the default images<br/>
 - Usage: `[p]pixlset image viewdefault`
### [p]pixlset image testserver
Test the server images to ensure they are valid urls<br/>
 - Usage: `[p]pixlset image testserver`
### [p]pixlset image view
View the server images<br/>
 - Usage: `[p]pixlset image view`
### [p]pixlset image testglobal
Test the global images to ensure they are valid urls<br/>
 - Usage: `[p]pixlset image testglobal`
 - Restricted to: `BOT_OWNER`
### [p]pixlset image addglobal
Add a global image for all servers to use<br/>

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
### [p]pixlset image viewglobal
View the global images<br/>
 - Usage: `[p]pixlset image viewglobal`
### [p]pixlset image add
Add an image for your server to use<br/>

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
## [p]pixlset participants
Set the minimum amount of participants for the game to reward users credits<br/>
 - Usage: `[p]pixlset participants <amount>`
## [p]pixlset ratio
Set the point to credit conversion ratio (points x ratio = credit reward)<br/>
Points are calculated based on how many hidden blocks are left at the end of the game<br/>

Ratio can be a decimal<br/>
Set to 0 to disable credit rewards<br/>
 - Usage: `[p]pixlset ratio <ratio>`
## [p]pixlset blocks
Set the amount of blocks to reveal after each delay<br/>
 - Usage: `[p]pixlset blocks <amount>`
