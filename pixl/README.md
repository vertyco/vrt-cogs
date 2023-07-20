# Pixl Help

Guess pictures for points

# pixlboard
 - Usage: `[p]pixlboard <show_global> `
 - Aliases: `pixlb, pixelb, pixlelb, and pixleaderboard`
 - Checks: `server_only`

View the Pixl leaderboard!<br/><br/>**Arguments**<br/>`show_global`: show the global leaderboard<br/><br/>example: `[p]pixlb true`

# pixl
 - Usage: `[p]pixl `
 - Aliases: `pixle, pixlguess, pixelguess, and pixleguess`
 - Checks: `server_only`

Start a Pixl game!<br/>Guess the image as it is slowly revealed

# pixlset
 - Usage: `[p]pixlset `
 - Aliases: `pixelset and pixleset`
 - Checks: `server_only`

Configure the Pixl game

## pixlset view
 - Usage: `[p]pixlset view `

View the current settings

## pixlset participants
 - Usage: `[p]pixlset participants <amount> `

Set the minimum amount of participants for the game to reward users credits

## pixlset delay
 - Usage: `[p]pixlset delay <seconds> `
 - Restricted to: `BOT_OWNER`

(Owner Only)Set the delay between block reveals<br/><br/>**Warning**<br/>Setting this too low may hit rate limits, default is 5 seconds.

## pixlset blocks
 - Usage: `[p]pixlset blocks <amount> `

Set the amount of blocks to reveal after each delay

## pixlset timelimit
 - Usage: `[p]pixlset timelimit <seconds> `

Set the time limit for Pixl games

## pixlset showdefault
 - Usage: `[p]pixlset showdefault `

(Toggle) Whether to use the default hardcoded images in this server

## pixlset showanswer
 - Usage: `[p]pixlset showanswer `

(Toggle) Showing the answer after a game over

## pixlset useglobal
 - Usage: `[p]pixlset useglobal `

(Toggle) Whether to use global images in this server

## pixlset image
 - Usage: `[p]pixlset image `

Add/Remove images

### pixlset image add
 - Usage: `[p]pixlset image add <url> <answers> `

Add an image for your server to use<br/><br/>**Arguments**<br/>`url:     `the url of the image<br/>`answers: `a list of possible answers separated by a comma<br/><br/>**Alternative**<br/>If args are left blank, a text file can be uploaded with the following format for bulk image adding.<br/>Each line starts with the url followed by all the possible correct answers separated by a comma<br/><br/>Example: `url, answer, answer, answer...`<br/>```<br/>https://some_url.com/example.png, answer1, answer two, another answer<br/>https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer<br/>```

### pixlset image viewdefault
 - Usage: `[p]pixlset image viewdefault `

View the default images

### pixlset image testserver
 - Usage: `[p]pixlset image testserver `

Test the server images to ensure they are valid urls

### pixlset image testglobal
 - Usage: `[p]pixlset image testglobal `
 - Restricted to: `BOT_OWNER`

Test the global images to ensure they are valid urls

### pixlset image view
 - Usage: `[p]pixlset image view `

View the server images

### pixlset image addglobal
 - Usage: `[p]pixlset image addglobal <url> <answers> `
 - Restricted to: `BOT_OWNER`

Add a global image for all servers to use<br/><br/>**Arguments**<br/>`url:     `the url of the image<br/>`answers: `a list of possible answers separated by a comma<br/><br/>**Alternative**<br/>If args are left blank, a text file can be uploaded with the following format for bulk image adding.<br/>Each line starts with the url followed by all the possible correct answers separated by a comma<br/><br/>Example: `url, answer, answer, answer...`<br/>```<br/>https://some_url.com/example.png, answer1, answer two, another answer<br/>https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer<br/>```

### pixlset image viewglobal
 - Usage: `[p]pixlset image viewglobal `

View the global images

## pixlset ratio
 - Usage: `[p]pixlset ratio <ratio> `

Set the point to credit conversion ratio (points x ratio = credit reward)<br/>Points are calculated based on how many hidden blocks are left at the end of the game<br/><br/>Ratio can be a decimal<br/>Set to 0 to disable credit rewards

