# BankDecay Help

Economy decay!<br/><br/>Periodically reduces users' red currency based on inactivity, encouraging engagement.<br/>Server admins can configure decay parameters, view settings, and manually trigger decay cycles.<br/>User activity is tracked via messages and reactions.

# bankdecay

- Usage: `[p]bankdecay `
- Restricted to: `ADMIN`
- Aliases: `bdecay`
- Checks: `server_only`

Setup economy credit decay for your server

## bankdecay view

- Usage: `[p]bankdecay view `

View Bank Decay Settings

## bankdecay initialize

- Usage: `[p]bankdecay initialize `

Initialize the server and add every member to the config.

## bankdecay resettotal

- Usage: `[p]bankdecay resettotal `

Reset the total amount decayed to zero.

## bankdecay decaynow

- Usage: `[p]bankdecay decaynow <confirm> `

Run a decay cycle on this server right now

## bankdecay setpercent

- Usage: `[p]bankdecay setpercent <percent> `

Set the percentage of decay that occurs after the inactive period.

## bankdecay setdays

- Usage: `[p]bankdecay setdays <days> `

Set the number of inactive days before decay starts.

## bankdecay toggle

- Usage: `[p]bankdecay toggle `

Toggle the bank decay feature on or off.

## bankdecay seen

- Usage: `[p]bankdecay seen <user> `

Check when a user was last active (if at all)
