import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from .server import DEFAULT_HOST, DEFAULT_PORT

_ = Translator("ActivityHub", __file__)

README_URL = "https://github.com/vertyco/vrt-cogs/blob/main/activityhub/README.md#setup-bot-owner"
PORTAL_URL = "https://discord.com/developers/applications"
CLOUDFLARE_URL = "https://dash.cloudflare.com"
CLOUDFLARED_URL = "https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/"
CADDY_URL = "https://caddyserver.com/docs/install"
EXAMPLE_HOST = "games.example.com"
# Listening on every network still means a tunnel or proxy on the same machine reaches it at its own address
EVERY_NETWORK = ("0.0.0.0", "::", "")


def local_address(host: str, port: int) -> str:
    """The address a tunnel or proxy on the bot's machine uses to reach the web server"""
    if host in EVERY_NETWORK:
        host = "127.0.0.1"
    elif ":" in host:
        host = f"[{host}]"
    return f"{host}:{port}"


def overview_page(prefix: str, listening: str, running: bool) -> discord.Embed:
    if running:
        now = _("**Right now** the web server listens on `{}` and is running.").format(listening)
    else:
        now = _(
            "**Right now** the web server should listen on `{}`, but it **isn't running**. Check the bot's logs, "
            "or pick another address with `{}activityhub webserver <host> <port>`."
        ).format(listening, prefix)
    text = _(
        "Discord shows the activities menu as a web page. This bot serves that page from its own small web server. "
        "Discord only opens pages from a public `https://` address, so most of the setup is giving that web "
        "server one.\n\n"
        "{now}\n\n"
        "**The steps**\n"
        "1. Turn on Activities for this bot\n"
        "2. Give the bot its client secret\n"
        "3. Give the web server a public HTTPS address (Cloudflare Tunnel, Caddy or nginx)\n"
        "4. Point Discord at that address\n"
        "5. Add the `/activities` command and check everything\n\n"
        "Use the arrow buttons to go through the steps. The same guide is in the [README]({readme})."
    ).format(now=now, readme=README_URL)
    return discord.Embed(title=_("ActivityHub setup"), description=text)


def portal_page(app_id: int) -> discord.Embed:
    text = _(
        "1. Open [this bot's page in the Developer Portal]({url}).\n"
        "2. Go to **Activities > Settings** and turn Activities on.\n"
        "3. Go to **OAuth2** and add any redirect URL, like `https://127.0.0.1`. Discord needs one to exist, even "
        "though the hub never uses it.\n\n"
        "Discord only lets an app open its own Activity, so this has to be this bot's own app."
    ).format(url=f"{PORTAL_URL}/{app_id}")
    return discord.Embed(title=_("Step 1: Turn on Activities"), description=text)


def secret_page(prefix: str, has_secret: bool) -> discord.Embed:
    if has_secret:
        now = _("**Right now** a client secret is saved.")
    else:
        now = _("**Right now** no client secret is saved.")
    text = _(
        "The client secret is what lets the bot log players in.\n"
        "1. In the Developer Portal, open **OAuth2** and copy the **Client Secret**. If it's hidden, press "
        "**Reset Secret** to get a new one.\n"
        "2. Run `{prefix}activityhub secret`, press **Set secret** and paste it in. The bot checks it with Discord "
        "before it saves it.\n\n"
        "{now}"
    ).format(prefix=prefix, now=now)
    return discord.Embed(title=_("Step 2: Give the bot its client secret"), description=text)


def address_page(prefix: str, local: str, port: int) -> discord.Embed:
    text = _(
        "Discord needs an `https://` address that leads to this bot's web server at `{local}`. Pick one of these "
        "ways. Each one has its own page next.\n\n"
        "**A. Cloudflare Tunnel** (easiest to keep running): no ports to open, and Cloudflare handles HTTPS. Needs a "
        "free Cloudflare account and a domain you own.\n"
        "**B. Quick test tunnel**: no account and no domain. The address changes every time it starts, so it's only "
        "for trying things out.\n"
        "**C. Caddy**: a web server that gets its own HTTPS certificate. Needs a domain pointing at this machine, and "
        "ports 80 and 443 open.\n"
        "**D. nginx**: if you already run nginx.\n\n"
        "Whatever you pick must let WebSockets through, since games use them for live play. All four ways here do.\n\n"
        "**Bot in Docker?** Inside a container, `127.0.0.1` can't be reached from outside it. If the tunnel or proxy "
        "runs outside the container, run `{prefix}activityhub webserver 0.0.0.0 {port}` and publish port {port}."
    ).format(local=local, prefix=prefix, port=port)
    return discord.Embed(title=_("Step 3: Give the web server a public address"), description=text)


def cloudflare_page(local: str) -> discord.Embed:
    text = _(
        "A tunnel is a small program on this machine that connects out to Cloudflare. Players reach Cloudflare, and "
        "Cloudflare passes them down the tunnel to the bot. Nothing on your network has to be opened.\n"
        "1. Make a free account at [Cloudflare]({cloudflare}) and add your domain to it, so Cloudflare runs the "
        "domain's DNS.\n"
        "2. In the Cloudflare dashboard, go to **Networking > Tunnels** and press **Create a tunnel**. Name it, like "
        "`activityhub`.\n"
        "3. Pick your operating system. Cloudflare shows an install command: run it on the machine the bot runs on. "
        "It installs the tunnel and starts it with the machine.\n"
        "4. Once the tunnel shows as connected, open its **Routes** tab, press **Add route** and pick **Published "
        "application**.\n"
        "5. Subdomain: `games`. Domain: yours. Service URL: `http://{local}`. Press **Add route**.\n\n"
        "Your public host is now your subdomain plus domain, like `{example}`. Use it in step 4."
    ).format(cloudflare=CLOUDFLARE_URL, local=local, example=EXAMPLE_HOST)
    return discord.Embed(title=_("Option A: Cloudflare Tunnel"), description=text)


def quick_tunnel_page(local: str) -> discord.Embed:
    text = _(
        "Good for a first test. No account or domain needed.\n"
        "1. Install `cloudflared` from [Cloudflare's download page]({downloads}).\n"
        "2. Run this on the machine the bot runs on:\n{command}\n"
        "3. It prints an address like `https://some-random-words.trycloudflare.com`. The part after `https://` is "
        "your public host for step 4.\n\n"
        "The address only works while that command runs. You get a new one every time it starts, and then the URL "
        "mapping in step 4 has to change too. For something that stays up, use option A, C or D."
    ).format(downloads=CLOUDFLARED_URL, command=box(f"cloudflared tunnel --url http://{local}"))
    return discord.Embed(title=_("Option B: Quick test tunnel"), description=text)


def caddy_page(local: str) -> discord.Embed:
    caddyfile = f"{EXAMPLE_HOST} {{\n    reverse_proxy {local}\n}}"
    text = _(
        "Caddy is a web server that gets and renews its HTTPS certificate by itself.\n"
        "1. Where your domain's DNS is managed, add an `A` record for your subdomain (like `{example}`) pointing at "
        "this machine's public IP address.\n"
        "2. Open ports 80 and 443 to this machine (port forwarding on the router, and the firewall).\n"
        "3. [Install Caddy]({install}).\n"
        "4. Put this in your Caddyfile, with your own host name:\n{caddyfile}\n"
        "5. Start or reload Caddy. It passes WebSockets through on its own.\n\n"
        "Your public host is the name in the Caddyfile, like `{example}`. Use it in step 4."
    ).format(example=EXAMPLE_HOST, install=CADDY_URL, caddyfile=box(caddyfile))
    return discord.Embed(title=_("Option C: Caddy"), description=text)


def nginx_page(local: str) -> discord.Embed:
    site = (
        "server {\n"
        "    listen 80;\n"
        f"    server_name {EXAMPLE_HOST};\n\n"
        "    location / {\n"
        f"        proxy_pass http://{local};\n"
        "        proxy_http_version 1.1;\n"
        "        proxy_set_header Upgrade $http_upgrade;\n"
        '        proxy_set_header Connection "upgrade";\n'
        "        proxy_set_header Host $host;\n"
        "    }\n"
        "}"
    )
    text = _(
        "1. Point your domain's DNS at this machine and open ports 80 and 443, like for Caddy.\n"
        "2. Add a site like this, with your own host name:\n{site}\n"
        "The `Upgrade` and `Connection` lines are what let WebSockets through. Without them, live games can't "
        "connect.\n"
        "3. Get a certificate with `sudo certbot --nginx -d {example}`. Certbot adds the HTTPS part to the site.\n\n"
        "Your public host is the `server_name`, like `{example}`. Use it in step 4."
    ).format(site=box(site, lang="nginx"), example=EXAMPLE_HOST)
    return discord.Embed(title=_("Option D: nginx"), description=text)


def mapping_page(app_id: int) -> discord.Embed:
    text = _(
        "1. In [the Developer Portal]({url}), go to **Activities > URL Mappings**.\n"
        "2. Set the root mapping, the one with the prefix `/`, to your public host **without** `https://`. For "
        "example `{example}`.\n"
        "3. Save.\n\n"
        "Discord now loads the menu from that address whenever someone opens this bot's Activity."
    ).format(url=f"{PORTAL_URL}/{app_id}", example=EXAMPLE_HOST)
    return discord.Embed(title=_("Step 4: Point Discord at it"), description=text)


def finish_page(prefix: str) -> discord.Embed:
    text = _(
        "1. Run `{prefix}slash enable activities`, then `{prefix}slash sync`. Players open the menu with "
        "`/activities`, and `{prefix}activities` posts a button that does the same.\n"
        "2. Run `{prefix}activityhub check`. It tests every step, including the URL mapping through Discord's own "
        "proxy, and says which one is missing. Add your public host, like `{prefix}activityhub check {example}`, to "
        "also test that address directly.\n\n"
        "**Handy later**\n"
        "`{prefix}activityhub view` shows the current settings.\n"
        "`{prefix}activityhub webserver <host> <port>` moves the web server (the default is `{host} {port}`). If you "
        "move it, point your tunnel or proxy at the new address too.\n"
        "`{prefix}activityhub games` lists the installed activities."
    ).format(prefix=prefix, example=EXAMPLE_HOST, host=DEFAULT_HOST, port=DEFAULT_PORT)
    return discord.Embed(title=_("Step 5: Add the command and check"), description=text)


def setup_pages(
    prefix: str, host: str, port: int, running: bool, has_secret: bool, app_id: int, color: discord.Color
) -> list[discord.Embed]:
    """The whole setup as pages, filled in with this bot's own address and state"""
    local = local_address(host, port)
    pages = [
        overview_page(prefix, f"{host}:{port}", running),
        portal_page(app_id),
        secret_page(prefix, has_secret),
        address_page(prefix, local, port),
        cloudflare_page(local),
        quick_tunnel_page(local),
        caddy_page(local),
        nginx_page(local),
        mapping_page(app_id),
        finish_page(prefix),
    ]
    for page in pages:
        page.color = color
        # Every title links to the same guide on GitHub
        page.url = README_URL
    return pages
