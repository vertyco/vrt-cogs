# ActivityHub

ActivityHub gives your bot one Discord Activity (a game window that opens inside Discord) with a menu of games in it. Each game is its own cog. Install a game cog, load it, and it shows up in the menu. Nothing else to set up per game.

Discord only lets a bot have one Activity. ActivityHub is how one bot offers many games.

## Games included

Three small games come with the hub, so the menu works the moment it is set up:

- **Snake**: eat apples to grow longer and faster, and don't run into a wall or yourself.
- **Brick Breaker**: bounce the ball off your paddle, catch power-ups, and break every brick to clear the level.
- **2048**: slide matching tiles together to build bigger numbers.

Each one shows its controls before you start, pauses with Esc or P, and works with a keyboard, a mouse or a touch screen. Snake and Brick Breaker also pause by themselves when you click away from them.

Each one keeps every player's best score in each server. When a round ends, it shows that server's top 10 and where you stand. Scores are only saved when the game is played in a server, not in a DM.

Players can't fake a score by changing the game page. For Snake and 2048 the bot plays the whole round again from the player's moves and works out the score itself. For Brick Breaker it checks the bricks and levels against the level layouts and how long the round took.

Server admins and the bot owner can turn these games off like any other game.

## For players

- `/activities` opens the menu. `[p]activities` posts an **Open Activities** button that does the same thing, and works even if slash commands aren't synced.
- Pick a game to play it. The game opens inside the menu, and its menu button brings you back.
- The gear button opens settings. **My look** picks the theme and whether descriptions show. **My order** sets the order of the games. Both follow you to every server.
- There are two themes. **Standard** looks like Discord, and you pick its layout, color and background. **Orb** is a green glowing console-style menu: the games sit on glowing pods along a ring around a big orb, with a preview of the selected game beside them and menu sounds (on by default, with a switch to turn them off). In the Orb theme the arrow keys or the mouse wheel move between games, a long list scrolls along the ring, and Settings is the last item instead of the gear button.

## For server admins

Members with the Manage Server permission (or Red's admin role) see a **This server** tab in the settings. It sets the server's default look and turns games on or off. A game that is off can't be played in this server at all, and anyone playing it is stopped. Games the bot owner turned off for every server don't show up here.

The bot owner also sees a **Defaults** tab. It sets the look every server starts from, and turns games on or off in every server at once. A game the owner turns off leaves every menu, can't be played anywhere, and server admins can't turn it back on.

## Setup (bot owner)

The cog hosts the menu and every game on a small web server. Discord loads it over HTTPS, so it needs a public address.

1. **Turn on Activities.** In the [Discord Developer Portal](https://discord.com/developers/applications), open your bot's application, go to **Activities > Settings** and enable Activities. Under **OAuth2**, add any redirect URL (for example `https://127.0.0.1`), since Discord requires one to exist.
2. **Give the bot its client secret.** Copy the client secret from the **OAuth2** page, run `[p]activityhub secret`, press **Set secret** and paste it in. The bot checks it with Discord before saving it. (`[p]set api activityhub client_secret,YOUR_SECRET` does the same without the check.)
3. **Expose the web server.** The cog listens on `127.0.0.1:8742` by default. Change it with `[p]activityhub webserver <host> <port>`. Put an HTTPS reverse proxy (nginx, Caddy) or a tunnel (cloudflared) in front of it, for example `https://games.example.com` pointing at `127.0.0.1:8742`. WebSockets must be allowed through it.
4. **Point Discord at it.** In **Activities > URL Mappings**, set the root mapping `/` to your public host without `https://` (for example `games.example.com`).
5. **Add the menu command.** `[p]slash enable activities`, then `[p]slash sync`.
6. **Check it.** `[p]activityhub check games.example.com` goes through every step above and says which one is missing.
7. **Add more games (optional).** The included games are ready to play. To add more, install and load any cog made for ActivityHub (`[p]cog install <repo> <cog>`, then `[p]load <cog>`). `[p]activityhub games` lists what is installed with the Discord permissions (scopes) each game asks for, and why a game cog was refused if one was. Every game's scopes go into one Discord login, so a game asking for a scope Discord doesn't accept stops logins for every game: this list shows which game it is.

The bot running this cog must be the same Discord application that has Activities turned on, because Discord only lets an app open its own Activity.

## Owner commands

| Command | Does |
|---|---|
| `[p]activityhub webserver <host> <port>` | Saves where the web server listens and restarts it. |
| `[p]activityhub secret` | Opens a form for the client secret, checks it with Discord, saves it. |
| `[p]activityhub check <public host>` | Checks every setup step and says what to fix. |
| `[p]activityhub games` | Lists installed games (marking any you turned off) with the Discord scopes each asks for, and refused game cogs with the reason. |

## Making games

Any cog can add a game to the menu. [DEVELOPERS.md](DEVELOPERS.md) walks through it with a complete example, and covers testing a game's Python without Discord, multiplayer, uploads and sharing your game.
