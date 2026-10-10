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
- **Settings** is the last item in the Orb theme's list, or the gear button in the Standard theme. **My look** picks the theme, the Orb theme's glow color, whether descriptions show, and whether the frame rate counter shows in the corner (on by default). **My order** sets the order of the games. Both follow you to every server.
- There are two themes. **Orb**, the default, is a glowing console-style menu: each game's icon sits in a glass pod on a ring around a big orb, and a see-through robot arm holds a panel with the selected game's picture and description beside the ring (below it on a phone held upright). Every move turns the panel on the arm and the frame around the orb. It has menu sounds (on by default, with a switch to turn them off) and a glow color that colors the whole theme, green by default. In the Orb theme the arrow keys, the mouse wheel, or sliding a finger up and down the ring or across the screen move between games. A long list scrolls along the ring, and Settings is the last item instead of the gear button. **Standard** looks like Discord, and you pick its layout, color and background.

## For server admins

The server owner, and members with the Manage Server permission (or Red's admin role), see a **This server** tab in the settings. It sets the server's default look, theme included, which every member sees until they pick their own in **My look**, and turns games on or off. A game that is off can't be played in this server at all, and anyone playing it is stopped. Games the bot owner turned off for every server don't show up here.

They can also put the **Open Activities** button on any message the bot sent in their server, like a welcome or rules message: `[p]activities pin <message link>` adds it, and `[p]activities unpin <message link>` takes it off. The message keeps its text, embeds and other buttons, and the button keeps working after the bot restarts. If the cog that posted the message redraws its own buttons later, the pinned button goes away and needs pinning again.

The bot owner also sees a **Defaults** tab. It sets the look every server starts from, and turns games on or off in every server at once. A game the owner turns off leaves every menu, can't be played anywhere, and server admins can't turn it back on.

## Setup (bot owner)

The cog hosts the menu and every game on a small web server. Discord loads it over HTTPS, so it needs a public address.

`[p]activityhub setup` walks through these same steps inside Discord, filled in with your bot's own address. `[p]activityhub view` shows the current settings at any time.

1. **Turn on Activities.** In the [Discord Developer Portal](https://discord.com/developers/applications), open your bot's application, go to **Activities > Settings** and enable Activities. Under **OAuth2**, add any redirect URL (for example `https://127.0.0.1`), since Discord requires one to exist.
2. **Give the bot its client secret.** Copy the client secret from the **OAuth2** page, run `[p]activityhub secret`, press **Set secret** and paste it in. The bot checks it with Discord before saving it. (`[p]set api activityhub client_secret,YOUR_SECRET` does the same without the check.)
3. **Expose the web server.** The cog listens on `127.0.0.1:8742` by default. Change it with `[p]activityhub webserver <host> <port>`. Put a tunnel (Cloudflare Tunnel) or an HTTPS reverse proxy (Caddy, nginx) in front of it, for example `https://games.example.com` pointing at `127.0.0.1:8742`. WebSockets must be allowed through it. [Getting a public HTTPS address](#getting-a-public-https-address) below walks through each way.
4. **Point Discord at it.** In **Activities > URL Mappings**, set the root mapping `/` to your public host without `https://` (for example `games.example.com`).
5. **Add the menu command.** `[p]slash enable activities`, then `[p]slash sync`.
6. **Check it.** `[p]activityhub check` goes through every step above and says which one is missing. It tests the URL mapping through Discord's own proxy, the same way players load the menu. Add your public host (`[p]activityhub check games.example.com`) to also test that address directly: it then says whether the name doesn't resolve, the connection is refused, or something else answers.
7. **Add more games (optional).** The included games are ready to play. To add more, install and load any cog made for ActivityHub (`[p]cog install <repo> <cog>`, then `[p]load <cog>`). `[p]activityhub games` lists what is installed with the Discord permissions (scopes) each game asks for, and why a game cog was refused if one was. Every game's scopes go into one Discord login, so a game asking for a scope Discord doesn't accept stops logins for every game: this list shows which game it is.

The bot running this cog must be the same Discord application that has Activities turned on, because Discord only lets an app open its own Activity.

### Getting a public HTTPS address

Discord only opens the menu from a public `https://` address. Something has to take visits to that address and pass them to the bot's web server. Pick one of these four ways. The examples use `games.example.com` as the public host and the default `127.0.0.1:8742` as the bot's address: swap in your own.

Whatever you pick must let WebSockets through, since games use them for live play. All four ways below do.

**Bot in Docker?** Inside a container, `127.0.0.1` can't be reached from outside it. If the tunnel or proxy runs outside the container, run `[p]activityhub webserver 0.0.0.0 8742` and publish port 8742.

#### A. Cloudflare Tunnel (easiest to keep running)

A tunnel is a small program on the bot's machine that connects out to Cloudflare. Players reach Cloudflare, and Cloudflare passes them down the tunnel to the bot. Nothing on your network has to be opened, and Cloudflare handles HTTPS. You need a free Cloudflare account and a domain you own.

1. Make a free account at [Cloudflare](https://dash.cloudflare.com) and add your domain to it, so Cloudflare runs the domain's DNS.
2. In the Cloudflare dashboard, go to **Networking > Tunnels** and press **Create a tunnel**. Name it, like `activityhub`.
3. Pick your operating system. Cloudflare shows an install command: run it on the machine the bot runs on. It installs the tunnel and starts it with the machine.
4. Once the tunnel shows as connected, open its **Routes** tab, press **Add route** and pick **Published application**.
5. Subdomain: `games`. Domain: yours. Service URL: `http://127.0.0.1:8742`. Press **Add route**.

Your public host is now your subdomain plus domain, like `games.example.com`.

#### B. Quick test tunnel (no account, no domain)

Good for a first test only.

1. Install `cloudflared` from [Cloudflare's download page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/).
2. Run this on the machine the bot runs on:

   ```
   cloudflared tunnel --url http://127.0.0.1:8742
   ```

3. It prints an address like `https://some-random-words.trycloudflare.com`. The part after `https://` is your public host.

The address only works while that command runs. You get a new one every time it starts, and then the URL mapping (setup step 4) has to change too. For something that stays up, use A, C or D.

#### C. Caddy

Caddy is a web server that gets and renews its HTTPS certificate by itself.

1. Where your domain's DNS is managed, add an `A` record for `games.example.com` pointing at the bot machine's public IP address.
2. Open ports 80 and 443 to that machine (port forwarding on the router, and the firewall).
3. [Install Caddy](https://caddyserver.com/docs/install).
4. Put this in your Caddyfile:

   ```
   games.example.com {
       reverse_proxy 127.0.0.1:8742
   }
   ```

5. Start or reload Caddy. It passes WebSockets through on its own.

#### D. nginx

1. Point your domain's DNS at the bot's machine and open ports 80 and 443, like for Caddy.
2. Add a site like this:

   ```nginx
   server {
       listen 80;
       server_name games.example.com;

       location / {
           proxy_pass http://127.0.0.1:8742;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
       }
   }
   ```

   The `Upgrade` and `Connection` lines are what let WebSockets through. Without them, live games can't connect.
3. Get a certificate with `sudo certbot --nginx -d games.example.com`. Certbot adds the HTTPS part to the site.

## Owner commands

| Command | Does |
|---|---|
| `[p]activityhub view` | Shows where the web server listens (and the default), whether it is running, whether a client secret is saved, and how many games are installed. |
| `[p]activityhub setup` | Walks through the whole setup page by page, including Cloudflare Tunnel, Caddy and nginx, filled in with your bot's own address. |
| `[p]activityhub webserver <host> <port>` | Saves where the web server listens and restarts it. The default is `127.0.0.1 8742`. |
| `[p]activityhub secret` | Opens a form for the client secret, checks it with Discord, saves it. |
| `[p]activityhub check [public host]` | Checks every setup step, including the URL mapping through Discord, and says what to fix. |
| `[p]activityhub games` | Lists installed games (marking any you turned off) with the Discord scopes each asks for, and refused game cogs with the reason. |

## Making games

Any cog can add a game to the menu. [DEVELOPERS.md](DEVELOPERS.md) walks through it with a complete example, and covers testing a game's Python without Discord, multiplayer, uploads and sharing your game.
