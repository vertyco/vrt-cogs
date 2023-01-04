# Pixl Help

Guess pictures for points

# pixlboard
 - Usage: `[p]pixlboard <show_global>`
 - Aliases: `pixlb, pixelb, pixlelb, and pixleaderboard`


View the Pixl leaderboard!

**Arguments**
`show_global`: show the global leaderboard

example: `[p]pixlb true`

# pixl
 - Usage: `[p]pixl`
 - Aliases: `pixle, pixlguess, pixelguess, and pixleguess`


Start a Pixl game!
Guess the image as it is slowly revealed

# pixlset
 - Usage: `[p]pixlset`
 - Aliases: `pixelset and pixleset`


Configure the Pixl game

## pixlset participants
 - Usage: `[p]pixlset participants <amount>`

Set the minimum amount of participants for the game to reward users credits

## pixlset timelimit
 - Usage: `[p]pixlset timelimit <seconds>`

Set the time limit for Pixl games

## pixlset showdefault
 - Usage: `[p]pixlset showdefault`

(Toggle) Whether to use the default hardcoded images in this guild

## pixlset ratio
 - Usage: `[p]pixlset ratio <ratio>`

Set the point to credit conversion ratio (points x ratio = credit reward)
Points are calculated based on how many hidden blocks are left at the end of the game

Ratio can be a decimal
Set to 0 to disable credit rewards

## pixlset showanswer
 - Usage: `[p]pixlset showanswer`

(Toggle) Showing the answer after a game over

## pixlset delay
 - Usage: `[p]pixlset delay <seconds>`

(Owner Only)Set the delay between block reveals

**Warning**
Setting this too low may hit rate limits, default is 5 seconds.

## pixlset image
 - Usage: `[p]pixlset image`

Add/Remove images

### pixlset image view
 - Usage: `[p]pixlset image view`

View the guild images

### pixlset image add
 - Usage: `[p]pixlset image add <url> <answers>`

Add an image for your guild to use

**Arguments**
`url:     `the url of the image
`answers: `a list of possible answers separated by a comma

**Alternative**
If args are left blank, a text file can be uploaded with the following format for bulk image adding.
Each line starts with the url followed by all the possible correct answers separated by a comma

Example: `url, answer, answer, answer...`
```
https://some_url.com/example.png, answer1, answer two, another answer
https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
```

### pixlset image viewdefault
 - Usage: `[p]pixlset image viewdefault`

View the default images

### pixlset image addglobal
 - Usage: `[p]pixlset image addglobal <url> <answers>`

Add a global image for all guilds to use

**Arguments**
`url:     `the url of the image
`answers: `a list of possible answers separated by a comma

**Alternative**
If args are left blank, a text file can be uploaded with the following format for bulk image adding.
Each line starts with the url followed by all the possible correct answers separated by a comma

Example: `url, answer, answer, answer...`
```
https://some_url.com/example.png, answer1, answer two, another answer
https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
```

### pixlset image testguild
 - Usage: `[p]pixlset image testguild`

Test the guild images to ensure they are valid urls

### pixlset image viewglobal
 - Usage: `[p]pixlset image viewglobal`

View the global images

### pixlset image testglobal
 - Usage: `[p]pixlset image testglobal`

Test the global images to ensure they are valid urls

## pixlset blocks
 - Usage: `[p]pixlset blocks <amount>`

Set the amount of blocks to reveal after each delay

## pixlset view
 - Usage: `[p]pixlset view`

View the current settings

## pixlset useglobal
 - Usage: `[p]pixlset useglobal`

(Toggle) Whether to use global images in this guild
