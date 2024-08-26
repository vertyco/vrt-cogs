# Pixl Help

Guess pictures for points<br/><br/>Pixl is an image guessing game that reveals parts of an image over time while users race to guess the correct answer first.<br/><br/>**Images are split up into 192 blocks and slowly revealed over time.**<br/>The score of the game is based on how many blocks are left when the image is guessed.

# .pixlboard
View the Pixl leaderboard!<br/>

**Arguments**<br/>
`show_global`: show the global leaderboard<br/>

example: `.pixlb true`<br/>
 - Usage: `.pixlboard <show_global>`
 - Aliases: `pixlb, pixelb, pixlelb, and pixleaderboard`
 - Checks: `server_only`
# .pixl
Start a Pixl game!<br/>
Guess the image as it is slowly revealed<br/>
 - Usage: `.pixl`
 - Aliases: `pixle, pixlguess, pixelguess, and pixleguess`
 - Checks: `server_only`
# .pixlset
Configure the Pixl game<br/>
 - Usage: `.pixlset`
 - Aliases: `pixelset and pixleset`
 - Checks: `server_only`
## .pixlset blocks
Set the amount of blocks to reveal after each delay<br/>
 - Usage: `.pixlset blocks <amount>`
## .pixlset delay
(Owner Only)Set the delay between block reveals<br/>

**Warning**<br/>
Setting this too low may hit rate limits, default is 5 seconds.<br/>
 - Usage: `.pixlset delay <seconds>`
 - Restricted to: `BOT_OWNER`
## .pixlset timelimit
Set the time limit for Pixl games<br/>
 - Usage: `.pixlset timelimit <seconds>`
## .pixlset usedefault
(Toggle) Whether to use the default hardcoded images in this server<br/>
 - Usage: `.pixlset usedefault`
## .pixlset showanswer
(Toggle) Showing the answer after a game over<br/>
 - Usage: `.pixlset showanswer`
## .pixlset useglobal
(Toggle) Whether to use global images in this server<br/>
 - Usage: `.pixlset useglobal`
## .pixlset image
Add/Remove images<br/>
 - Usage: `.pixlset image`
### .pixlset image viewdefault
View the default images<br/>
 - Usage: `.pixlset image viewdefault`
### .pixlset image testserver
Test the server images to ensure they are valid urls<br/>
 - Usage: `.pixlset image testserver`
### .pixlset image testglobal
Test the global images to ensure they are valid urls<br/>
 - Usage: `.pixlset image testglobal`
 - Restricted to: `BOT_OWNER`
### .pixlset image view
View the server images<br/>
 - Usage: `.pixlset image view`
### .pixlset image addglobal
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
 - Usage: `.pixlset image addglobal <url> <answers>`
 - Restricted to: `BOT_OWNER`
### .pixlset image viewglobal
View the global images<br/>
 - Usage: `.pixlset image viewglobal`
### .pixlset image add
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
 - Usage: `.pixlset image add <url> <answers>`
## .pixlset ratio
Set the point to credit conversion ratio (points x ratio = credit reward)<br/>
Points are calculated based on how many hidden blocks are left at the end of the game<br/>

Ratio can be a decimal<br/>
Set to 0 to disable credit rewards<br/>
 - Usage: `.pixlset ratio <ratio>`
## .pixlset participants
Set the minimum amount of participants for the game to reward users credits<br/>
 - Usage: `.pixlset participants <amount>`
## .pixlset view
View the current settings<br/>
 - Usage: `.pixlset view`
